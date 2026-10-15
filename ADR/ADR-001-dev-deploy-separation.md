# ADR-001 — Development happens only in `~/Documents`, never in `fa_modules`

**Status:** Accepted, remediation pending
**Date:** 2026-10-11
**Relates to:** ADR-002

## Context

FrontAccounting modules are served from
`ksf_Infrastructure/fa_modules/<module>/`, bind-mounted into the FA container
at `/var/www/html/modules`. That directory is **deployed output**.

As of 2026-10-11 it contained **32 git repositories** (`.git` directories),
each a duplicate clone of a dev checkout that already exists directly under
`~/Documents/`. Verified: `ksf_FA_ProjectManagement`, `ksf_FA_CRM`,
`ksf_FA_HRM`, `ksf_FA_Workflow`, `ksf_FA_EmailManager` and
`ksf_FA_SuggestedPurchaseOrder` all have BOTH a dev checkout under
`~/Documents/` AND a clone inside `fa_modules/`.

## Problem

Two clones of the same repository diverge. Work committed in the deploy tree
lives only in that clone. A subsequent deploy (`rsync` without `--exclude
.git`, or a fresh checkout) **silently overwrites it**.

This is not theoretical — on 2026-10-11 an agent committed and pushed
EmailManager, SuggestedPurchaseOrder, CRM, Calendar and Workflow changes
**from inside `fa_modules/`** when the dev checkout was sitting a directory
away. The commits survived only because they were pushed. Had they not been,
they would have been lost without warning.

The divergence also caused real confusion: comparing a business-logic repo
against its own `origin/main` when its work lives on another branch produced a
false "25 commits behind", which triggered an unnecessary rebase (recovered
via reflog, no harm done).

## Decision

1. **All development, commits and pushes happen in `~/Documents/<repo>`.**
2. `fa_modules/` is **build output only**. It must never be a git working tree.
3. **Every deploy MUST exclude `.git`.** See ADR-003.
4. Before changing any file, **confirm which working directory you are in and
   that it is a dev checkout** (see the check in ADR-003).

## Consequences

- 32 `.git` directories must be removed from `fa_modules/`.
- **Before** removal, confirm each deploy-tree clone has no commits absent from
  its `~/Documents` counterpart. Deleting git history on a hunch is not
  acceptable; verify first.
- Deploys become reproducible: the tree is derived from `~/Documents`, so the
  same input always produces the same output.

## Remediation order

1. For each of the 32: `git -C fa_modules/<m> log --oneline origin/<branch>..HEAD`
   — anything listed must be ported to the dev checkout first.
2. Push the dev checkout.
3. `rm -rf fa_modules/<m>/.git`.
4. Update the deploy script to exclude `.git` (ADR-003).
5. Redeploy and verify the site still loads.
