# ADR-003 — Deploy hygiene: exclude `.git`, and check the working directory first

**Status:** Accepted
**Date:** 2026-10-11
**Relates to:** ADR-001, ADR-002

## Decision

### 1. Deploys must exclude `.git`

Source `~/Documents/<repo>` → target
`ksf_Infrastructure/fa_modules/<module>/`.

```bash
# CORRECT
rsync -a --delete \
      --exclude '.git' \
      --exclude 'vendor'          # install vendor separately with composer
      ./ ~/Documents/<repo>/ ksf_Infrastructure/fa_modules/<repo>/

# WRONG - ships .git into the deploy tree and can clobber commits made there
rsync -a --delete ./ ~/Documents/<repo>/ ksf_Infrastructure/fa_modules/<repo>/
```

`vendor/` is excluded because Composer must run separately with
`composer install --no-dev`. Dev dependencies (notably PHPUnit 10, which
requires PHP >= 8.1) in a deployed vendor tree have caused **site-wide HTTP
500s** on the PHP 7.4 runtime. Verify after every deploy:

```bash
ls <deployed>/vendor/                     # no phpunit, sebastian, doctrine, myclabs
grep -c 'installed.*dev.*true' <deployed>/vendor/composer/installed.json   # expect 0
```

### 2. Check the working directory before every file change

**Before editing any file, run:**

```bash
pwd                                              # am I in ~/Documents or in fa_modules?
basename "$(git rev-parse --show-toplevel)"     # which repo, and is it a git tree?
git remote get-url origin                        # ksf_X or ksf_FA_X?
git branch --show-current
```

If the path contains `fa_modules`, **stop** — you are in deployed output.
Find the dev checkout under `~/Documents` and work there.

Rationale: on 2026-10-11 six modules' worth of changes were committed and
pushed from inside `fa_modules/` because no check was performed. The commits
survived only because they were pushed; they were one `rsync` away from being
silently overwritten.

### 3. Never edit a module's `hooks.php` without a shape check

Module hooks load during FA bootstrap. An error in `hooks.php` **breaks every
page in the application**, not just that module's.

```bash
php -l hooks.php                            # NECESSARY BUT NOT SUFFICIENT
grep -cE '^[[:space:]]+public function ' hooks.php   # compare against git HEAD
git diff --stat hooks.php
```

A previous splice silently deleted a method while `php -l` passed, which
500'd the entire site. Always compare the shape, not just the syntax.

### 4. Write files in place; never replace the inode

Shared docs (`AGENTS.md`, `AGENTS_ARCH.md`, `APP_TAB_ARCHITECTURE.md`,
`MODULE_DIRECTORY.md`, `PACKAGIST.md`) are **hardlinked** across ~186 holders.
Editing must preserve the inode:

```bash
# CORRECT - truncate in place
cat new-content > target.md
python3 -c "open('$f','w').write(s)"       # open+write, no rename

# WRONG - replaces the inode, silently detaching every other holder
sed -i 's/x/y/' target.md
mv newfile target.md
git checkout -- target.md                   # replaces the inode too
```

Verify with `stat -c %h target.md` — the link count must be unchanged after
the edit.

## Consequences

- 32 `.git` directories in `fa_modules/` must be removed (ADR-001) and the
  deploy script updated to match.
- Every future deploy and every file edit carries three explicit checks. That
  is the cost of the failures these prevent.
