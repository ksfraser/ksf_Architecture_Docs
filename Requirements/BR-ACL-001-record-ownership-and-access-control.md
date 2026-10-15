# BR-ACL-001 — Record ownership and row-level access control

@BABOK Related: BABOK 8.1 Solution Strategy, 8.2 Solution Analysis, 9.1 Requirements Analysis
Status: **Proposed**
Module: `ksf_FA_RBAC` (schema owner), all `ksf_FA_*` modules (consumers)
Date: 2026-10-14
Scope: **row axis only.** The column axis is a separate axis; see
[FR-ACL-001-04](./FR-ACL-001-04-column-axis-views.md) and
[`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md).

> **Documentation only.** Nothing in this document is implemented. No production
> code was written, no schema was changed, and no commit was made in producing it.

---

## 1. Business driver

FrontAccounting's native security model is **page-level**. Every page declares one
security area (`SA_<thing>`) in its `$page_security` variable and the user must hold
the matching role permission to load it. That is a *function-level* control: it answers
"may this user open the Contacts list?", never "which of the 40,000 contacts may this
user see?".

The business need is the second question, and it is not hypothetical:

- **Segregation of duties.** A sales user may see their own accounts and their team's
  accounts, but not the whole book.
- **Payroll and HR confidentiality.** `ksf_FA_HRM` payroll data has a materially
  different sensitivity class from the rest of the system, and different *rows*
  (department, cost centre, individual) as well as different columns.
- **Project and campaign confidentiality.** A campaign's contact list is commercially
  sensitive before launch; before the launch date only the campaign's team may read it.
- **Regional and legal-entity separation** (PIPEDA / GDPR context). The same table
  holds records that different data controllers may lawfully see.

All of these are **row** problems. They cannot be expressed by adding more
`SA_*` security areas, because the answer depends on the *row*, not the page.

## 2. What is decided

### 2.1 Two orthogonal axes, not one

Access control on this system has **two independent axes**, and they are enforced by
different mechanisms because they fail differently:

| Axis | Question | Mechanism | Enforced by | FR |
|---|---|---|---|---|
| **Column** | "May this user *see the value* of this field?" | Views per sensitivity class | MariaDB | FR-ACL-001-04 |
| **Row** | "May this user *see this record*?" | Ownership + group-membership tables joined into the query | The query builder | FR-ACL-001-01, FR-ACL-001-02 |

They compose. A caller must be entitled to **both** the view (column axis) and the
row (row axis). Neither substitutes for the other: a masked view still returns every
row, and a row predicate still returns every column of the rows it admits.

### 2.2 The column axis is expressed as views, per sensitivity class **[D]**

Separate views per sensitivity class (e.g. a PIPEDA/GDPR view, a mailing-address view,
a core view). Views are joinable, so **a caller joins only the views it is entitled
to**.

This is the structural answer to the inference-oracle problem documented in
[`Column_Level_ACL_Design.md`](../Column_Level_ACL_Design.md) §2.3: because a caller
*must name the view* in order to get a column out of it, and because joining a view is
an explicit act, a column cannot leak through a join the caller did not intend. The
residual oracles that remain (`ORDER BY`/`AVG`/`COUNT` against a masked view) are
enumerated in `ACL_Two_Approaches.md` §1.3 and are **not** closed by this BR.

### 2.3 The row axis is UNIX-like ownership **[D]**

> A record has **an owner**, and may belong to **several groups**.
> Access is computed at three levels: **Owner**, **Group**, **Other**.

- **Owner** — exactly one owning identity per record. This is the UNIX `-rw-r--r--`
  owner bit: a small, always-present, fast-path claim.
- **Group** — zero to *many* group memberships per record. This is the group bit.
- **Other** — everyone else. Governed by a *default*, not by a per-record row. A
  record with no ownership and no groups is not "unprotected by accident"; it falls
  to the declared default posture (see FR-ACL-001-01 §6 and open question **Q2**).

Consequences that are requirements, not implementation notes:

1. **A record may belong to many groups simultaneously.** This is the property the
   current `0_rbac_record_access` design cannot state cleanly (see §3).
2. **Ownership is single-valued; group membership is multi-valued.** They are
   different cardinalities and therefore belong in **different tables** (FR-ACL-001-01).
3. **"Other" needs no per-record rows.** There is no table that enumerates the users
   who may read a record. Absence of an ownership row and absence of a group row means
   "falls to the default", and the default is a per-(module, record_type, group)
   policy row, not a per-record row.

### 2.4 Groups are orthogonal to the org chart **[D]**

A "group" is **any grouping**, and a record may be attached to several:

| `group_kind` | Meaning | Populated by |
|---|---|---|
| `team` | A team in the org chart | `ksf_FA_Teams` / `0_rbac_teams` with `team_type` in (`explicit`, `org_direct`, `org_indirect`) |
| `project` | A project or engagement | `ksf_FA_ProjectManagement` |
| `ad_hoc` | A hand-made list with no org meaning | the ACL admin UI |
| `service_account` | A non-human identity | system |
| `org_unit` | A cost centre / department | `ksf_FA_HRM` |

This is a deliberate non-decision about group *semantics*. The ACL layer stores the
membership and the entitlement; it does not own the group's lifecycle, does not
replicate the org chart, and must not be the reason a project team cannot exist.

**Requirement R5:** creating a group of any `group_kind` shall not require an entry in
the org chart, and the ACL layer shall not query the org chart to resolve a group.

## 3. Why the existing schema cannot carry this **[V]**

Verified against the live Integration database (`ksfii_app-mariadb`,
MariaDB 10.11.14, schema `ksf_fa`) on 2026-10-14.

### 3.1 Correction to the premise: there is no UNIQUE index

The brief this BR answers stated that
`0_rbac_record_access.record_lookup` is **`UNIQUE`** on
`(module, record_type, record_id, inactive)` and that this unique index "permits only
one ACL row per record" and so blocks multi-group membership.

**That is not what is on the server.** `SHOW INDEX FROM 0_rbac_record_access` returns:

```
Table                   Non_unique  Key_name         Seq_in_index  Column_name
0_rbac_record_access    1           record_lookup    1             module
0_rbac_record_access    1           record_lookup    2             record_type
0_rbac_record_access    1           record_lookup    3             record_id
0_rbac_record_access    1           record_lookup    4             inactive
```

`Non_unique = 1` on every `record_lookup` row. It is a plain `KEY`, matching
`sql/install.sql:80` (`KEY record_lookup (...)`, not `UNIQUE KEY`). The live DDL
agrees: `SHOW CREATE TABLE 0_rbac_record_access` emits `KEY \`record_lookup\`
(\`module\`,\`record_type\`,\`record_id\`,\`inactive\`)` **[V]**.

**Consequence:** there is no unique constraint to drop, and multiple groups per record
are *already* physically expressible in the table as it stands. The blocker is
different — and in some ways worse, because it is silent:

| # | Actual defect | Verified |
|---|---|---|
| **D1** | **No uniqueness at all.** Nothing stops N duplicate rows for the same `(record, team)`. Re-granting a capability silently inserts a second row rather than failing, and the predicate will then count the record twice. | `SHOW INDEX`, `SHOW CREATE TABLE` **[V]** |
| **D2** | **No `user_id` column.** Ownership by a *user* cannot be recorded at all; the only principal column is `team_id`. The Owner axis of §2.3 is unexpressible. | Column list **[V]** |
| **D3** | **`team_id` is `NOT NULL`.** There is no way to express "this record has no group membership" or "this record is owned but belongs to no group". A NULL-valued principal is impossible. | `SHOW CREATE TABLE` **[V]** |
| **D4** | **Identity and capability are fused in one row.** `team_id` says *who*; `can_view`/`can_edit`/`can_export`/… say *what*. That forces a capability bit to be duplicated per record, so a policy change is an `UPDATE` across every record of every group rather than one policy row. It also means "no row" has to mean two different things — "denied everything" or "not yet classified". | Column list **[V]** |
| **D5** | **`inactive` is in the only record lookup key.** The soft-delete idiom `UNIQUE (…, inactive)` (as also used in `0_rbac_team_members.team_user_inactive`) permits exactly **one** live row and exactly **one** retired row. Archiving the same record twice collides on error 1062. Here it is merely a non-unique index, so the failure mode is instead *unbounded duplicates*. | **[V]** + `[A]` SQL semantics |
| **D6** | **Dead.** No PHP in the tree references the table. `ksf_FA_RBAC/src/Ksfraser/FrontAccounting/Rbac/` contains `Storage/FaRoleStorage.php` only — there is no `FaRecordAccessRepository`, no `FaTeamRepository`, and no code path that writes a row. The table is declared DDL and requirements (`ProjectDcs/FR-001-001-Access_Repository.md`) with no implementation behind it. | `find`/`grep` over the tree, vendor excluded **[V]** |

All four tables are **empty** (0 rows in `0_rbac_teams`, `0_rbac_team_members`,
`0_rbac_record_access`, `0_rbac_audit_log`) **[V]**, so §3's defects have no data at
risk and the migration in FR-ACL-001-01 is not a data migration.

### 3.2 A second, quieter defect in the existing schema **[V]**

`0_rbac_teams.owner_id` and `0_rbac_team_members.user_id` are both declared
`VARCHAR(64) NOT NULL COMMENT 'FK to 0_users.id'`.

**The comment names the wrong column.** On the live database:

```
0_users:  id  smallint(6)  PRI  auto_increment
          user_id  varchar(60)  UNI
```

`0_users.id` is a `smallint`; the natural, unique, human-supplied key that FA's own
session code uses as the acting user is `0_users.user_id varchar(60)`. The column
*types* in RBAC (`varchar(64)`) match `user_id`, not `id` — so the schema is right and
only the comment is wrong.

**This is load-bearing for FR-ACL-001-01 and is recorded as a required correction**:
the owner principal column throughout the new schema is `VARCHAR(64)` referencing
**`0_users.user_id`**, and every `COMMENT` must say so. An implementer who trusts the
existing comment will join on `smallint` and get silent row loss.

## 4. Requirements

| ID | Requirement |
|---|---|
| **R1** | The system shall distinguish a **column axis** (which field values a principal may see) from a **row axis** (which records a principal may see), and shall require both to be satisfied. |
| **R2** | Every row-ACL decision shall be expressible in terms of **Owner**, **Group**, or **Other**. No other principal category shall exist. |
| **R3** | A record shall have **at most one** owner at any time. |
| **R4** | A record shall be attachable to **many** groups at the same time, and membership of one group shall be independent of membership of any other. |
| **R5** | A group shall be any grouping — team, project, ad-hoc list, service account, org unit — and its kind shall be recorded on the membership, not inferred from the org chart. |
| **R6** | The "Other" level shall be governed by a **policy** keyed on group + resource, not by per-record rows. Absence of an ownership row and of any group row shall be a defined state, not an undefined one. |
| **R7** | Row-ACL evaluation shall cost **one data query per request**, not one per record and not one per module. (FR-ACL-001-02) |
| **R8** | Enforcement shall be introduced in **two stages**, with the first stage explicitly *not* enforcement. (FR-ACL-001-03) |
| **R9** | Native FrontAccounting core shall **not** be modified. FA's own 870 `db_query(` call sites are out of scope permanently. |
| **R10** | Row-ACL **write** paths (INSERT/UPDATE/DELETE) are in scope for *authorisation of the operation* but the row predicate itself is a **read** construct. Whether write paths are policed at all is open question **Q4**. |

## 5. Non-goals

- **Column-level ACL design.** Owned by FR-ACL-001-04 and the two prior design
  documents. BR-ACL-001 states only that the column axis exists and is orthogonal.
- **Modifying FA core** (R9).
- **Authentication.** Unchanged.
- **Retro-fitting the 304 files of legacy `db_query(` call sites by hand.** They are
  handled mechanically (Stage 1) or by module migration (Stage 2); see FR-ACL-001-03.
- **Encrypting data at rest.** A separate concern; `ACL_Two_Approaches.md` OD-6 notes
  `ksf_db_security/Encrypted/EncryptedFields.php` for a separate evaluation.

## 6. Traceability

| This BR | Satisfied by | Verifying UT |
|---|---|---|
| R1 | FR-ACL-001-04 (column axis), FR-ACL-001-02 (row axis) | UT-ACL-001-004-001… |
| R2, R3, R4, R6 | FR-ACL-001-01 §3 (tables) | UT-ACL-001-001-001… |
| R5 | FR-ACL-001-01 §3.3 (`group_kind`) | UT-ACL-001-001-004 |
| R7 | FR-ACL-001-02 §4 | UT-ACL-001-002-001 |
| R8 | FR-ACL-001-03 | UT-ACL-001-003-001 |
| R9 | FR-ACL-001-03 §3 (scope) | — (scope statement) |
| R10 | FR-ACL-001-02 §6 (open) | — (open question Q4) |

**Unit tests are not yet written.** This BR is a design artefact; the `UT-ACL-*`
identifiers are reserved so the RTM can be generated from `@BABOK Related:` annotations
when the implementation lands. Per `AGENTS.md`, the RTM is generated, not hand-written,
so no separate RTM file is produced here.

## 7. Explicitly unverified

| Item | Status |
|---|---|
| Whether any business user actually requires the **row** axis today (as opposed to the page-level model sufficing) | **[UNVERIFIED]** — no stakeholder statement is in evidence. R1–R7 are written as decided, per instruction, but the *business* case for R2–R6 is asserted, not sourced. |
| Row counts for any table that would be row-ACL-managed. The performance argument in FR-ACL-001-02 §4 is plan-shape only; **no timing was taken and none should be quoted.** | **[UNVERIFIED]** |
| Whether `0_rbac_teams` / `0_rbac_team_members` should be retained, replaced, or absorbed. They are empty and have no PHP consumer either, but `0_rbac_team_members` has a genuine `UNIQUE (team_id, user_id, inactive)` that the *membership* side of FR-ACL-001-01 reuses. | **[UNVERIFIED — open question Q1]** |
| Any runtime behaviour through FA. Everything below was verified by raw `mariadb` client or by reading source. No view, no predicate, and no ownership row has been exercised through a FA page. | **[UNVERIFIED]** |

## 8. Related

- [FR-ACL-001-01 — Ownership schema](./FR-ACL-001-01-ownership-schema.md)
- [FR-ACL-001-02 — Row ACL predicate](./FR-ACL-001-02-row-acl-predicate.md)
- [FR-ACL-001-03 — Two-stage enforcement migration](./FR-ACL-001-03-two-stage-enforcement-migration.md)
- [FR-ACL-001-04 — Column axis views](./FR-ACL-001-04-column-axis-views.md)
- [OPEN-QUESTIONS.md](./OPEN-QUESTIONS.md)
- [`ACL_Two_Approaches.md`](../ACL_Two_Approaches.md) — the column-axis design this
  BR's row axis composes with
- [`Column_Level_ACL_Design.md`](../Column_Level_ACL_Design.md) — inference-oracle matrix
- [`Explicit_Column_ACL_API.md`](../Explicit_Column_ACL_API.md) — the app-layer API