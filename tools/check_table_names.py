#!/usr/bin/env python3
"""
Estate-wide guard: no table may be named in the `fa_` namespace.

WHY
---
`0_` is the COMPANY prefix, not a vendor segment.  A table whose second
segment is `fa` therefore lands in FrontAccounting core's own namespace, and
it becomes impossible to tell from the name whether the table is ours or the
platform's.  FrontAccounting 2.4.3 core uses no `0_fa_*` name at all -- its
tables are `0_debtors_master`, `0_cust_branch`, `0_crm_contacts`,
`0_sales_orders` and so on -- so every `0_fa_*` table in this estate is ours
and must be named `0_ksf_<owning-module>_<noun>` (AGENTS_ARCH.md section 12).

WHAT IT CHECKS
--------------
A table can be named `0_fa_*` in three different ways, and a plain grep for
the literal only catches the first:

  R1  the literal string            `0_fa_calendar_entries`
  R2  the runtime form              `TB_PREF . 'fa_calendar_entries'`
  R3  a table constant              `const TABLE_ENTRIES = 'fa_calendar_entries';`
  R4  a prefixless CREATE TABLE     `CREATE TABLE IF NOT EXISTS `fa_assets``
      (not applied inside test fixtures, which mock a fake table prefix)
  R5  a bare name in SQL position   `... FROM fa_calendar_entries ...`
      (reported as a WARNING, not a failure: it also fires on column names
      such as `ON DUPLICATE KEY UPDATE fa_debtor_no = ...` and on test
      fixtures that mock a fake table prefix)

R2 and R3 are the ones that matter at runtime: `TB_PREF` is the company
prefix, so `TB_PREF . 'fa_x'` addresses `0_fa_x` -- a table in FA core's
namespace that no schema creates.  FrontAccounting's `db_query()` returns
false WITHOUT raising an error when a statement fails, so a module that
addresses a table it never created fails *silently*: reads come back empty,
writes go nowhere, and nothing lands in the log.

WHAT IS ALLOWED
---------------
* A migration line -- `ALTER TABLE IF EXISTS `0_fa_x` RENAME TO `0_ksf_x``.
  That is the one place the legacy name must still be written: it is the
  statement that moves the table OFF the legacy name.
* A constant whose name says it is a legacy name (`const LEGACY_...`).
* Comments and prose.  PHP and SQL comments are stripped before scanning.

EXIT CODES
----------
  0  no violation
  1  at least one violation (one line per violation on stdout)

USAGE
-----
    python3 tools/check_table_names.py                 # scan ~/Documents
    python3 tools/check_table_names.py --root /path    # scan another tree
    python3 tools/check_table_names.py --quiet         # summary only

IN CI
-----
Run it from the repository root of the estate, e.g. as a pre-merge job:

    python3 ksf_Architecture_Docs/tools/check_table_names.py

A non-zero exit must fail the build.  It is a whole-estate check, so it
belongs in a pipeline that has the estate checked out, not in a single
module's PHPUnit suite.  Individual modules can additionally assert the rule
for their own schema -- `ksf_FA_Mail/tests/Unit/TableNamingTest.php` and
`ksf_FA_Calendar/tests/Unit/SqlSchemaFilesTest.php` are the reference
implementations.
"""

import argparse
import os
import re
import sys

SKIP_DIRS = {
    'vendor', 'node_modules', '.git', 'phpdoc', '.phpunit.cache', '.idea',
    'build', 'dist', '__pycache__', '.venv',
}
SCAN_EXTS = ('.php', '.sql', '.inc', '.phtml', '.mjs', '.js')

# A table name in the fa_ namespace.
FA_NAME = r"fa_[A-Za-z0-9_]+"

R1_LITERAL = re.compile(r"\b0_" + FA_NAME)
R2_TBPREF = re.compile(r"TB_PREF\s*\.\s*['\"]" + FA_NAME + r"['\"]")
R3_CONST = re.compile(
    r"\bconst\s+[A-Za-z0-9_]*TABLE[A-Za-z0-9_]*\s*=\s*['\"]" + FA_NAME + r"['\"]")
R3_LEGACY_CONST = re.compile(
    r"\bconst\s+[A-Za-z0-9_]*LEGACY[A-Za-z0-9_]*\s*=\s*['\"]" + FA_NAME + r"['\"]")
R4_PREFIXLESS_CREATE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?" + FA_NAME + r"`?", re.I)
R5_SQL_POSITION = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+`?" + FA_NAME + r"`?", re.I)

# A migration line: the legacy name is the SOURCE of a rename.
MIGRATION = re.compile(r"RENAME\s+TO\s+`?0_ksf_[A-Za-z0-9_]+`?", re.I)


PHP_STRINGS_AND_COMMENTS = re.compile(
    r"(?P<string>'[^'\\]*(?:\\.[^'\\]*)*'"
    r'|"[^"\\]*(?:\\.[^"\\]*)*")'
    r"|(?P<comment>//[^\n]*|/\*.*?\*/|#[^\n]*)",
    re.S,
)


def strip_php_comments(source):
    """Remove PHP comments, keeping string literals intact."""
    def repl(match):
        if match.group('comment') is not None:
            return ' '
        return match.group('string')
    return PHP_STRINGS_AND_COMMENTS.sub(repl, source)


def strip_sql_comments(source):
    """Remove `--` and `/* */` comment lines from SQL."""
    out = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith('--') or stripped.startswith('#'):
            out.append('')
        else:
            out.append(line)
    return '\n'.join(out)


def is_test_fixture(path):
    """True for files under a tests/ directory.

    Test fixtures mock a fake table prefix ("fa_"), so a bare name in SQL
    position there is not necessarily a table name.  The hard rules (R1-R4)
    still apply inside tests.
    """
    parts = path.replace('\\', '/').split('/')
    return 'tests' in parts or 'plugin-tests' in parts


def scan_file(path, root):
    """Return a list of (line_number, rule, text) violations in one file."""
    try:
        raw = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return []

    if path.endswith('.sql'):
        text = strip_sql_comments(raw)
    elif path.endswith(('.php', '.inc', '.phtml')):
        text = strip_php_comments(raw)
    else:
        text = raw

    violations = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if 'fa_' not in line:
            continue
        if MIGRATION.search(line):
            # The legacy name is the source of a rename: allowed.
            continue
        if R3_LEGACY_CONST.search(line):
            # A constant that declares itself a legacy name: allowed.
            continue
        fixture = is_test_fixture(path)
        for rule, pattern in (
            ('R1 literal 0_fa_*', R1_LITERAL),
            ('R2 TB_PREF . fa_*', R2_TBPREF),
            ('R3 table constant fa_*', R3_CONST),
        ):
            if pattern.search(line):
                violations.append((lineno, rule, line.strip()))

        # R4 also fires on test fixtures that mock a fake table prefix.
        if not fixture and R4_PREFIXLESS_CREATE.search(line):
            violations.append((lineno, 'R4 prefixless CREATE TABLE fa_*', line.strip()))

        # R5 is advisory only.
        if not fixture:
            for match in R5_SQL_POSITION.finditer(line):
                before = line[:match.start()]
                if 'DUPLICATE KEY' in before:
                    continue
                violations.append((lineno, 'R5 SQL table position fa_* (warning)', line.strip()))
                break
    return violations


# Deployment and build staging trees.  They are copies of the dev trees (which
# the scan does cover) and are git-ignored, so scanning them would only
# report the same violation twice.
STAGING = (
    os.path.join('ksf_Infrastructure', 'fa_modules'),
    os.path.join('ksf_Infrastructure', 'docker', 'fa-alpine', 'fa_files', 'modules'),
)


def walk(root, skip_self):
    """Yield every scannable source file under root."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel = os.path.relpath(dirpath, root)
        if any(rel == stage or rel.startswith(stage + os.sep) for stage in STAGING):
            dirnames[:] = []
            continue
        for name in filenames:
            if not name.endswith(SCAN_EXTS):
                continue
            path = os.path.join(dirpath, name)
            if skip_self and os.path.abspath(path) == os.path.abspath(__file__):
                continue
            yield path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    default_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    ap.add_argument('--root', default=default_root,
                    help='estate root to scan (default: the directory that holds '
                         'this repository)')
    ap.add_argument('--quiet', action='store_true',
                    help='print only the summary line')
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.root))
    if not os.path.isdir(root):
        print('not a directory: %s' % root, file=sys.stderr)
        return 2

    total = 0
    warnings = 0
    files = 0
    for path in walk(root, skip_self=True):
        files += 1
        violations = scan_file(path, root)
        if not violations:
            continue
        rel = os.path.relpath(path, root)
        for lineno, rule, text in violations:
            if rule.endswith('(warning)'):
                warnings += 1
            else:
                total += 1
            if not args.quiet:
                print('%s:%d: %s\n    %s' % (rel, lineno, rule, text))

    print('')
    print('')
    print('scanned %d files under %s' % (files, root))
    if warnings:
        print('%d advisory hit(s) (R5: a bare fa_* name in SQL position)' % warnings)
    if total:
        print('FAIL: %d table name(s) in the fa_ namespace' % total)
        return 1
    print('OK: no table is named in the fa_ namespace')
    return 0


if __name__ == '__main__':
    sys.exit(main())
