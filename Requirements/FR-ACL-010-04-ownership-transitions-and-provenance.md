# FR-ACL-010-04 — Ownership transitions and provenance

@BABOK Related: BR-ACL-010 R4, R5, BABOK 8.2 Solution Analysis
Status: **Proposed**
Module: `ksf_FA_RBAC` (registry), `ksf_FA_Sales` / `ksf_FA_CRM` / `ksf_FA_HRM` (responders)
Date: 2026-10-14

> **Documentation only.** No responder was registered and no table was altered.

---

## 1. Transitions are registered responders, not a ruleset

> **[D] BR-ACL-010 R4. The framework knows nothing about invoices versus customers.
> Neither does RBAC. Each module registers its own semantics.**

This is the requirement that keeps the framework from becoming a second monolith. A
central ruleset would need a code change in RBAC every time a module gains a table; a
responder registry needs a change in the *owning* module only, which is where the
knowledge already lives.

### 1.1 The decline protocol

**[D] Returning `null` means "not my concern."**

| Rule | Consequence |
|---|---|
| A responder is asked about `(module, record_type)`; if it does not own them it returns `null` | No central registry edit is needed for an unrelated module |
| The framework applies no default | A missing responder means *nobody claims this record*, which is a visible state (R6), **not** a silent allow |

**[UNVERIFIED]** — the protocol depends on `hook_invoke_first` treating `null` as "not
handled" in the installed FA version. See Q-ACL-010-6 and
[FR-ACL-010-03](./FR-ACL-010-03-lifecycle-events.md) §4.

## 2. The agreed examples

**[D]** These are the registrations agreed for the first cohort. They are
**examples of the mechanism**, not an exhaustive table.

| Module | Trigger | Transition |
|---|---|---|
| `ksf_FA_Sales` | `record_changed` on `quote`, `sales_order`, `cust_invoice` | `Transition::none()` — historical documents; ownership **never transfers** |
| `ksf_FA_CRM` | `record_changed` on `contact` | `Transition::transferTo($newAccountManager)` |
| `ksf_FA_HRM` | `user_changed` **and** is a team change | Revoke group-derived ownership where the group no longer includes the user |

### 2.1 Why `ksf_FA_Sales` returns `Transition::none()`

**[D]** A posted invoice is a financial record. If it silently moved to a new owner's
book, the audit trail of *who sold what* would break retroactively — and any payroll or
commission report computed from "invoices I own" would change value for a past period.
`none()` says: **this record's ownership is a historical fact, not a live
assignment.** Sales documents keep the owner they were created with.

### 2.2 Why the `ksf_FA_HRM` responder is narrower than it looks

**[D]** It revokes **group-derived** ownership only. It must **not** touch `explicit`
ownership — a contact explicitly assigned to someone is not affected by their team
changing. Enforcing that is **impossible without provenance** (§3), which is why §3
is a core requirement and not a nicety.

## 3. Ownership provenance — core requirement

> **[D] BR-ACL-010 R5. Every ownership row records how it came to exist:
> `explicit | group | inherited`.**

| Value | Meaning |
|---|---|
| `explicit` | A person was deliberately assigned it |
| `group` | It is reachable through a group membership |
| `inherited` | It derives from an owner — e.g. all of a customer's contacts follow the account owner |

### 3.1 Why this is load-bearing, not bookkeeping

Without provenance, two responders write to the same record with no way to coordinate:

| Scenario | Without provenance | With provenance |
|---|---|---|
| Account manager leaves the CRM | The team responder **cannot tell** which contacts were theirs explicitly and which they merely reached through a team | Revoke only `group`-derived rows |
| CRM transfers a contact | The transfer responder overwrites a row that the team responder also manages, and the loser silently strips a grant | `explicit` rows are not `group` rows; the responder checks the value |

**The failure mode is silent.** Nothing errors. One grant quietly disappears and the
only evidence is a user who can no longer see a record they should. That is why R5 is
stated as a core requirement.

## 4. Requirements on the ownership tables

**[V] These tables do not exist yet.** `0_rbac_record_owner` and `0_rbac_record_group`
are *proposed* by [FR-ACL-001-01](./FR-ACL-001-01-ownership-schema.md) §3.1/§3.2; no
`.php` or `.sql` file in either `ksf_FA_RBAC/` tree references them. This FR is
**blocked on FR-ACL-001-01**.

Requirements this FR places on that schema:

| # | Requirement |
|---|---|
| 1 | An ownership row **must** carry a provenance column, constrained to the three values. `NULL` is not permitted — an unlabelled row cannot be reasoned about. |
| 2 | Provenance must be queryable per row without a join to another table. |
| 3 | The FR-ACL-001-01 indexes must support lookup **by owner** (the sweeper's main access pattern), not only by record. **[V]** `owner_lookup (owner_id, module, record_type)` is proposed there; confirm it survives. |
| 4 | Transfer (`transferTo`) must be a single atomic operation. A transfer that clears the old row before writing the new one is a **transient orphan** — visible to the sweeper as corruption (R7 cause b) when it is actually cause (a)-adjacent ordinary work. **[UNVERIFIED]** — whether the ordering is achievable depends on transaction availability; see Q-ACL-010-3. |

**[V] Data-type note.** Ownership rows key on a **string** `user_id`, not the `smallint`
`0_users.id`. See [BR-ACL-010](./BR-ACL-010-event-driven-ownership.md) §3.2 — the existing
`0_rbac_teams.owner_id` / `0_rbac_team_members.user_id` are already `VARCHAR(64)`, but
their `COMMENT` wrongly names `0_users.id`, which is a trap for the next reader.

## 5. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | An unowned `(module, record_type)` with no responder produces **no** ownership row and **no** transition — the record lands in the orphan bucket. |
| AC2 | A responder for `contact` returning `null` leaves the transition entirely to the next responder. |
| AC3 | `Transition::none()` on a sales invoice leaves any existing ownership row **byte-identical**. |
| AC4 | `Transition::transferTo($new)` leaves **exactly one** row with provenance `explicit` and no transient orphan visible to the sweeper. |
| AC5 | An HRM team-change revocation removes **only** `group`-derived rows; `explicit` rows for the same record survive untouched. |
| AC6 | No ownership row exists with a NULL or unknown provenance value. |
| AC7 | A `record_changed` with no matching responder does **not** throw and does **not** default to an owner. |

## 6. Explicitly unverified

| Item | Status |
|---|---|
| The exact `Transition` type shape (`none()`, `transferTo()`) | **Not designed.** Names are illustrative; no signature is proposed here. |
| Whether provenance belongs on the ownership table or on a separate claim table | Not decided; interacts with FR-ACL-001-01 §3. |
| Whether "account manager" on a contact is a real column on `ksf_FA_CRM`'s contact model | **[UNVERIFIED]** — the CRM responder's input field was not traced to a schema column. |
| Whether a transfer is atomic given uncertain transaction coverage | **[UNVERIFIED]** — requirement 4 above. |

## 7. Related

- [BR-ACL-010](./BR-ACL-010-event-driven-ownership.md) R4, R5
- [FR-ACL-010-03](./FR-ACL-010-03-lifecycle-events.md) — where `record_changed` / `user_changed` are emitted
- [FR-ACL-001-01](./FR-ACL-001-01-ownership-schema.md) — the blocking schema
- [FR-ACL-010-05](./FR-ACL-010-05-orphaned-records.md) — what happens when no responder claims a record