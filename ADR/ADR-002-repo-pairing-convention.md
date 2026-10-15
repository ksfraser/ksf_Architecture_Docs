# ADR-002 — `ksf_<module>` is business logic; `ksf_FA_<module>` is the FA wrapper

**Status:** Accepted
**Date:** 2026-10-11
**Relates to:** ADR-001

## Context

There are **two GitHub repositories per feature**, and they are NOT duplicates:

| Repo | Contains | Branch observed |
|---|---|---|
| `ksfraser/ksf_<module>` | Target-agnostic business logic — reusable across FA, WordPress, Joomla, anything | `v7.4` |
| `ksfraser/ksf_FA_<module>` | The FrontAccounting wrapper — `hooks.php`, security areas, pages, controller. **Consumes** `ksf_<module>` | `main` |

Examples verified: `ksf_ProjectManagement` vs `ksf_FA_ProjectManagement`;
`ksf_Calendar` vs `ksf_FA_Calendar`; `ksf_insurance`, `ksf-fa-insurance`
and `ksf-wp-insurance` (three targets of one feature).

## Problem

On 2026-10-11 these were mistaken for the same repository diverging. I
compared `ksf_ProjectManagement` against **its own** `origin/main` when its
work is on `v7.4`, concluded it was 25 commits behind, and rebased onto the
wrong base. This produced a false alarm and an unnecessary rebase.

The duplication of `ksf_FA_<module>` at two filesystem paths (ADR-001) adds a
second, genuinely harmful axis of confusion on top of a legitimate split.

## Decision

1. `ksf_<module>` and `ksf_FA_<module>` are **distinct repositories by design**.
   Never reconcile, merge, or treat one as a clone of the other.
2. Feature work lives in `ksf_<module>`. FA-specific wiring (hooks, security
   areas, pages, controller) lives in `ksf_FA_<module>`.
3. **Before any git operation, identify which of the two you are in** — by
   remote URL, not by directory name. The FA wrapper is the one named
   `ksf_FA_*`.
4. Branches differ by repo and are not interchangeable. Check the branch
   before comparing against a remote.

## Consequences

- Never run a `git fetch && rebase` that crosses repos.
- A commit intended for FA wiring must go to `ksf_FA_<module>`, even when the
  business logic change was made in `ksf_<module>`.
- The FA wrapper depends on the business-logic package, so it needs a
  Composer requirement + release of the logic package before the wrapper can
  consume it.
