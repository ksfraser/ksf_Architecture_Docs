# FR-ACL-010-01 — The per-module ACL toggle

@BABOK Related: BR-ACL-010 R1, BR-ACL-001, BABOK 8.2 Solution Analysis
Status: **Proposed**
Module: `ksfraser/ksf-common-db` (`src/Query/QueryBuilder.php`), `ksf_FA_RBAC`
Date: 2026-10-14

> **Documentation only.** No code was written and no builder was extended.

---

## 1. Requirement

> A module declares whether a table is ACL-governed. The framework builder emits the
> row predicate and the column mask when it is declared, and emits **nothing** when it
> is not. **Modules never write ACL SQL.**

## 2. The declaration contract

**[D]** Illustrative shape only — **this is not an API** and no method name here is
binding.

| Element | Value |
|---|---|
| module | `'sales'` |
| record_type | `'cust_invoice'` |
| table | logical, **unprefixed** — `'sales_invoices'` |
| action axis | which actions this declaration governs |

A declaration names a **logical, unprefixed** table. Never name a `0_rbac_*` table with
a hardcoded `0_` in builder code: `FaDbAdapter::prefixTables()` line 70 skips a table
only when it already begins with the configured prefix, so under a company prefix of
`1_` a literal `0_` name becomes `1_0_rbac_…`
**[V — `FaDbAdapter.php:70`; see FR-ACL-001-02 §2.1]**.

## 3. Why the toggle must be *declarative* rather than a flag in the builder

**[D]** Three properties fall out of the declaration being the switch, and each is
load-bearing:

| Property | Why it matters |
|---|---|
| **Absent ⇒ no clause** | ACL is opt-in per table. Bringing a table under ACL is a deliberate, reviewable act (R7(a) depends on this). |
| **The builder owns the SQL** | One place knows the predicate shape. Fixing the shape — e.g. swapping `IN` for `EXISTS` — is one change, not 1,510. |
| **The declaration is data** | It can live in the data dictionary ([`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) §2.4) rather than in code, so a table can be governed without touching module source. **[UNVERIFIED]** — whether `TableDefinition` is the right home is OD-3 there; not decided here. |

## 4. `SELECT *` rejection

When ACL is active for a table, `SELECT *` is **rejected**, not warned about.

**[V]** `QueryBuilder::$select` defaults to `['*']` at `src/Query/QueryBuilder.php:26`
and `toSql()` implodes the raw fragments at `:174-207`, so a builder that is not told
to select explicitly emits a wildcard.

The reasoning is mechanical, not stylistic: a wildcard cannot be masked, because the
mask must name each column it touches
(`CASE WHEN :canReadX = 1 THEN col ELSE NULL END`). A wildcard under active ACL would
silently bypass the column axis.

Rejection is the correct behaviour rather than substitution, because a framework that
*guesses* which columns were meant is guessing at a **security** decision.

## 5. Prerequisite the toggle depends on

**[V]** `from()` stores an **opaque string** (`QueryBuilder.php:83`) and there are **no
public getters** for the select list or the table. The builder therefore cannot key a
policy lookup on what it is selecting from.

> **A builder that cannot see its own `FROM` cannot key an ACL policy on it.**

This is why [FR-ACL-010-02](./FR-ACL-010-02-row-and-column-predicates.md) requires the
builder to be **extended to carry the declared table**. Row ACL must be a **builder
capability, not a decorator** — a decorator that rewrites the SQL string cannot reliably
tell an ACL table from an ordinary one, and cannot reject `SELECT *` before emission.

## 6. Module-facing rules

| Rule | Rationale |
|---|---|
| Modules supply **rule fragments**, never SQL | Keeps module semantics (R4) separate from predicate shape (R2). |
| A module's fragment may **decline** by returning nothing | Keeps the "not my concern" path uniform with R4. |
| A module may **not** add its own join to an ACL table | An extra join to an ACL table can fan out rows, which is exactly what R2 forbids. |
| Modules **may** add ordinary business joins | The fan-out rule is about ACL tables, not about joins in general. **[UNVERIFIED]** — a business join that fans out still breaks the caller's row count; whether the builder detects this is not decided. **Q-ACL-010-7.** |

## 7. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | A table with no declaration emits SQL byte-identical to today. (Guards against the toggle silently altering the other ~1,500 call sites.) |
| AC2 | A declared table queried with `SELECT *` is **rejected** with a message naming the table and the module. |
| AC3 | Declaring `(module, record_type)` for an unknown module is rejected, not silently ignored. |
| AC4 | Under company prefix `1_`, a declaration naming `rbac_record_owner` produces `1_rbac_record_owner` with no `1_0_` remnant. |
| AC5 | A module's rule fragment returning empty causes that clause to be omitted and the remaining clauses to still be correctly parenthesised. |
| AC6 | No generated statement contains a comma-join or a `WITH` (both break `prefixTables()`). **[V — regex at `FaDbAdapter.php:56`]** |

## 8. Explicitly unverified

| Item | Status |
|---|---|
| The precise builder API that carries the declared table | **Not designed.** §2 is illustrative; the extension point itself is open. **Q-ACL-010-1.** |
| Whether a declaration belongs in `TableDefinition` or in module code | Not decided here; touches OD-3 in [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md). |
| Whether the ~1,510 existing call sites can be migrated incrementally or need a single cutover | **[UNVERIFIED]** — depends on how many already pass through the builder at all. |
| Whether `FaDbAdapter`'s `prefixTables` regex mangles a `CASE` expression containing the token `TABLE` or a string literal containing `FROM` | **[UNVERIFIED]** — this is a genuine risk for the column mask and is not covered by ACs above. **Q-ACL-010-2.** |

## 9. Related

- [BR-ACL-010](./BR-ACL-010-event-driven-ownership.md) R1
- [FR-ACL-010-02](./FR-ACL-010-02-row-and-column-predicates.md)
- [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) §2.2, §2.4