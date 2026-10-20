# PARTY-ACCOUNT-MODEL — pointer to the shared requirement set

**Date:** 2026-10-20
**Status:** **Pointer. No requirement id. The shared requirement set named below
is NOT YET WRITTEN.**
**Design:** [`../Party_Account_Model_2026-10.md`](../Party_Account_Model_2026-10.md)
**Decision:** [`../ADR/ADR-004-party-account-lifecycle-model.md`](../ADR/ADR-004-party-account-lifecycle-model.md)

---

## Why this file exists

`../Party_Account_Model_2026-10.md` §7.1 decides that the party/account model's
requirement documents live in **this** directory, alongside `BR-EM-001`,
`BR-ACL-001` and `BR-CAL-010` — the estate's established home for cross-module
requirements. §7.2 then names the ids.

This file is the pointer the design document asks for: it says where the
authoritative files live, what they are called, and — because a pointer that
points at nothing is worse than no pointer — **that they have not been written
yet**.

---

## The ids

| Id | Scope |
|---|---|
| **BR-COM-010** | the business need: one human being wears several hats; the estate must not confuse the human, the entity, the account and the role |
| **FR-COM-010-001** | vocabulary and invariants |
| **FR-COM-010-002** | person and card schema |
| **FR-COM-010-003** | party and membership schema |
| **FR-COM-010-004** | account, role and link schema |
| **FR-COM-010-005** | MERGE operation |
| **FR-COM-010-006** | SPLIT operation |
| **FR-COM-010-007** | SPIN-OFF and sale |
| **FR-COM-010-008** | PROMOTE operation |
| **FR-COM-010-009** | ASSOCIATE / DISSOCIATE operation |
| **FR-COM-010-010** | CLONE-WITH-LINK operation |
| **FR-COM-010-011** | SOFT LINK operation |
| **FR-COM-010-012** | resolver composition and hooks |
| **FR-COM-010-013** | seeding and reconciliation |
| **FR-COM-010-014** | incomplete handling and degradation |
| **UC-COM-010-001 … UC-COM-010-007** | one use case per lifecycle operation |

---

## State as of 2026-10-20

**Verified:** this directory contains `BR-ACL-001`, `BR-ACL-010`, `BR-CAL-010`,
`BR-EM-001`, the `FR-ACL-*` / `FR-CAL-*` / `FR-EM-*` sets, `UC-EM-001`,
`OPEN-QUESTIONS.md` and this pointer — and **no `COM-010` file of any kind**.
The shared design document's own header states that the requirement set it is
traceable to "are **not yet written**" (line 11).

**The first written expression of this model is therefore the CRM's:**
`~/Documents/ksf_FA_CRM/ProjectDcs/BR-CRM-011-party-account-lifecycle.md`,
`FR-CRM-011-001…008` and `UC-CRM-011-001…007`, together with
`PARTY-ACCOUNT-MODEL-NOTES.md` (the narrative) and
`PARTY-ACCOUNT-MODEL-INCOMPLETE-HANDLING.md` (the CRM-facing degradation rules).

**When the COM-010 files are written they must be consistent with BR-CRM-011**,
and the reverse: a change to the CRM's set must land in the same commit as the
corresponding change to the shared design document and to ADR-004.

---

## The two views

| | Shared view | CRM view |
|---|---|---|
| Design | `../Party_Account_Model_2026-10.md` | `~/Documents/ksf_FA_CRM/ProjectDcs/PARTY-ACCOUNT-MODEL-NOTES.md` |
| Requirements | this directory — `BR-COM-010`, `FR-COM-010-001…014`, `UC-COM-010-001…007` (**to be written**) | `~/Documents/ksf_FA_CRM/ProjectDcs/BR-CRM-011…`, `FR-CRM-011-001…008`, `UC-CRM-011-001…007` |
| Decision | `../ADR/ADR-004-party-account-lifecycle-model.md` | referenced by BR-CRM-011 and every FR in the set |
| Incomplete handling | design §6.4 (items I1–I9) | `~/Documents/ksf_FA_CRM/ProjectDcs/PARTY-ACCOUNT-MODEL-INCOMPLETE-HANDLING.md` |
| Open questions | design §9 (`OQ-1…OQ-9`) | notes §8 (`OQ-A…OQ-I`) |

**The rule that keeps them from drifting:** the shared set specifies the
**contracts** and the **operations**; the CRM set specifies the **CRM's screens,
its acceptance criteria and its supersessions**. Neither duplicates the other,
and the CRM set names **no** `0_fa_*` table and **no** unratified shared table
name — it names contracts, because a parallel sweep is renaming table names
across the estate right now.

---

## Open questions to add to `OPEN-QUESTIONS.md`

The shared design document §6.5 (place 2) asks for the model's open decisions to
be registered in `OPEN-QUESTIONS.md` in the format that file already uses. They
have **not** been added yet. When they are, they should carry **Q14–Q20** and
map onto the shared design's `OQ-1…OQ-9` and the CRM notes' `OQ-A…OQ-I`:

| Shared | CRM | Subject |
|---|---|---|
| OQ-1 | OQ-H | Add the PERSON/CARD sentence to `AGENTS_ARCH.md` §12.2 |
| OQ-2 | OQ-A | May a merge delete the absorbed account? |
| OQ-3 | OQ-B | What happens to the absorbed account's transactions? |
| OQ-4 | OQ-C | Who keeps the balance on a divorce split? |
| OQ-5 | OQ-D | Which GL accounts does a spun-off company post to? |
| OQ-6 | OQ-F | Global or company-scoped registry? |
| OQ-7 | OQ-E | Move or clone on a promotion? |
| OQ-8 | OQ-G | Do life events stay in the CRM? |
| OQ-9 | OQ-I | May a merge change contact details? |

---

*Pointer produced 2026-10-20. **No requirement id — this file carries none.** No
production code was modified and no test suite was run.*
