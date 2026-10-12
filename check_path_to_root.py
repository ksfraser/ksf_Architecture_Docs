#!/usr/bin/env python3
"""
check_path_to_root.py — CI gate for FrontAccounting module $path_to_root bugs.

A module entry point at <FA root>/modules/<mod>[/subdirs...]/page.php must set
$path_to_root to a traversal that resolves, from the file's OWN directory, back
to the FA root. Too shallow resolves to /var/www/html/modules, so
include_once($path_to_root . "/includes/session.inc") silently fails and the
page dies on an undefined page() with a bare HTTP 500.

Usage:
    check_path_to_root.py <fa_root> [--repo <module repo> ...]

Exits non-zero if any entry point is wrong.
"""
import argparse
import os
import re
import sys

# Directories that are NOT web entry points (never requested directly).
NON_ENTRY_DIRS = {
    "vendor", "node_modules", "tests", "test", "Tests", "src", "lib", "sql",
    "lang", "languages", "doc", "docs", "Assets", "assets", "js", "css",
    "templates", "Templates", "bin", "build", ".git", ".github", "_cache",
    "tmp", "cache", "models", "fixtures", "migrations",
}

# Directory names that ARE entry-point namespaces (a page in here is reachable).
ENTRY_DIRS = {
    "pages", "menu", "popup", "views", "view", "forms", "ui", "reports",
    "includes", "inc", "ajax", "api", "dialog", "scripts", "controllers",
    "admin", "public", "www", "web", "html", "report",
}

ASSIGN = re.compile(
    r"""\$path_to_root\s*=\s*        # assignment
        (?P<q>['"])                   # opening quote
        (?P<val>[^'"]*)               # the literal
        (?P=q)\s*;                    # closing quote + semicolon""",
    re.X,
)

# Matches the whole right-hand side up to the terminating semicolon, so that
# both plain literals and equivalent expression forms are captured.
RHS = re.compile(r"""\$path_to_root\s*=\s*(?P<rhs>[^;]+);""")

# Equivalent, correct-but-not-plain-literal forms. These compute the right
# depth, so they are NOT findings; they are recognised and accepted.
#   dirname(__DIR__, N)            -> N levels up
#   dirname(dirname(...(__DIR__))) -> one level per dirname()
#   __DIR__ . "/../../.."          -> count the ../ segments
SAFE_PATTERNS = [
    re.compile(r"^\s*dirname\s*\(\s*__DIR__\s*,\s*(\d+)\s*\)\s*$"),
    re.compile(r"^\s*(?:dirname\s*\(\s*)*__DIR__(?:\s*\))*\s*$"),
    re.compile(r"^\s*__DIR__\s*\.\s*['\"]([^'\"]*)['\"]\s*$"),
]


def safe_form_depth(expr):
    """
    If `expr` is a recognised non-literal-but-correct form, return the number
    of levels it ascends; else None.
    """
    m = SAFE_PATTERNS[0].match(expr)
    if m:
        return int(m.group(1))
    if SAFE_PATTERNS[1].match(expr):
        # count nested dirname() calls
        return expr.count("dirname(")
    m = SAFE_PATTERNS[2].match(expr)
    if m:
        return literal_depth(m.group(1))
    return None


def literal_depth(value):
    """Number of '../' segments; None if not a pure upward traversal."""
    if value in (".", "", "./"):
        return 0
    depth = 0
    for part in value.split("/"):
        if part == "..":
            depth += 1
        elif part in ("", "."):
            continue
        else:
            return None  # not a pure traversal (e.g. '/var/www/html', __DIR__)
    return depth


def depth_below_modules(abspath, modules_dir):
    """
    Depth of the file's own directory below the FA root.

    A module is deployed at <FA root>/modules/<mod>/, so the traversal count is
    1 ('modules') + the directory depth WITHIN the modules tree. Computing it
    from the modules tree (not from the FA root) keeps this correct when the FA
    root and modules/ are bind-mounted from different host trees, and identical
    when they are the same tree.
    """
    rel = os.path.relpath(os.path.dirname(abspath), modules_dir)
    parts = [] if rel == "." else [p for p in rel.split(os.sep) if p not in (".", "")]
    return 1 + len(parts)


def virtual_resolve(modules_dir, abspath, value):
    """
    Where the include would land, expressed against a virtual FA root.

    Returns the absolute virtual path the traversal produces, so we can assert
    it equals the FA root regardless of where things physically live.
    """
    rel = os.path.relpath(abspath, modules_dir)          # <mod>/pages/x.php
    parts = [p for p in rel.split(os.sep) if p not in (".", "")]
    virtual = ["/FA"] + ["modules"] + parts[:-1]        # dir of the file
    if value in (".", "", "./"):
        return "/".join(virtual) or "/"
    for seg in value.split("/"):
        if seg == "..":
            if len(virtual) > 1:
                virtual.pop()
        elif seg not in ("", "."):
            virtual.append(seg)
    return "/".join(virtual)


def is_entry_point(rel_to_modules):
    parts = rel_to_modules.split(os.sep)
    if len(parts) == 1:
        return True  # module-root php: modules/<mod>/x.php
    if parts[0].lower().endswith(".php"):
        return True
    return parts[1].lower() in ENTRY_DIRS


def iter_module_files(modules_dir):
    """Yield (abs_path, rel_to_modules) for candidate entry points."""
    if not os.path.isdir(modules_dir):
        return
    for dirpath, dirnames, filenames in os.walk(modules_dir):
        dirnames[:] = [d for d in dirnames
                       if d not in NON_ENTRY_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.lower().endswith(".php"):
                continue
            ap = os.path.join(dirpath, fn)
            rel = os.path.relpath(ap, modules_dir)
            if is_entry_point(rel):
                yield ap, rel


def audit(fa_root, modules_dir, verify=True):
    """
    Returns findings as (rel, value, expected_depth, kind, correct).

    kind is one of: TOO_SHALLOW, TOO_DEEP, NON_LITERAL, UNRESOLVED.
    """
    findings = []
    session_rel = os.path.join("includes", "session.inc")
    for abspath, rel in iter_module_files(modules_dir):
        try:
            src = open(abspath, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if "$path_to_root" not in src:
            continue
        exp = depth_below_modules(abspath, modules_dir)
        # Ignore pure `global $path_to_root;` / `echo $path_to_root;` lines by
        # requiring an actual assignment.
        m = RHS.search(src)
        if not m:
            continue
        rhs = m.group("rhs").strip()
        qm = ASSIGN.search(src)
        if qm:
            val = qm.group("val")
        else:
            val = None
        depth = literal_depth(val) if val is not None else safe_form_depth(rhs)
        if depth is None:
            findings.append((rel, rhs, exp, "NON_LITERAL", None))
            continue

        # Does the traversal actually land on the FA root?
        # (safe forms already encode an absolute-ish path, so only literals
        #  can be resolved relatively here)
        if val is not None:
            landed = virtual_resolve(modules_dir, abspath, val)
            if landed != "/FA":
                correct = "/".join([".."] * exp) or "."
                findings.append((rel, val, exp, "UNRESOLVED", correct))
                continue

        if depth != exp:
            kind = "TOO_SHALLOW" if depth < exp else "TOO_DEEP"
            correct = "/".join([".."] * exp) or "."
            findings.append((rel, rhs, exp, kind, correct))
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fa_root", help="path to the FA root (contains includes/session.inc)")
    ap.add_argument("--modules", action="append", default=[], dest="modules_dirs",
                    help="directory holding the deployed modules (repeatable). "
                         "In a container deployment the FA root and modules/ are "
                         "often bind-mounted from DIFFERENT host trees, so pass "
                         "the modules dir here while fa_root stays the app root. "
                         "Defaults to <fa_root>/modules.")
    ap.add_argument("--no-verify", action="store_true",
                    help="accepted for compatibility; resolution is always checked")
    args = ap.parse_args()

    fa_root = os.path.abspath(args.fa_root)
    if not os.path.isfile(os.path.join(fa_root, "includes", "session.inc")):
        sys.exit(f"error: {fa_root}/includes/session.inc not found; "
                 f"is this the FA root?")

    modules_dirs = args.modules_dirs or [os.path.join(fa_root, "modules")]

    total = 0
    for modules_dir in modules_dirs:
        modules_dir = os.path.abspath(modules_dir)
        if not os.path.isdir(modules_dir):
            print(f"skip: no such modules dir: {modules_dir}")
            continue
        findings = audit(fa_root, modules_dir, not args.no_verify)
        if findings:
            print(f"--- {modules_dir} ---")
        for rel, val, exp, kind, correct in findings:
            total += 1
            if kind == "NON_LITERAL":
                print(f"  NON-LITERAL  {rel}: $path_to_root={val!r} "
                      f"(expected {exp} '../' segments)")
            elif kind == "UNRESOLVED":
                print(f"  UNRESOLVED   {rel}: $path_to_root={val!r} "
                      f"does not resolve to the FA root; should be {correct!r}")
            else:
                print(f"  {kind:12} {rel}: $path_to_root={val!r} -> should be {correct!r}")

    if total:
        print(f"\nFAIL: {total} path_to_root problem(s).")
        return 1
    print("OK: all module entry points have a correct $path_to_root.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
