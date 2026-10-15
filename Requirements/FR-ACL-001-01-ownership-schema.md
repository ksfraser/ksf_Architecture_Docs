# FR-ACL-001-01 — Record ownership schema

@BABOK Related: BR-ACL-001, BABOK 8.2 Solution Analysis, 8.3 Solution Design
Status: **Proposed**
Module: `ksf_FA_RBAC` (`sql/install.sql`)
Date: 2026-10-14

> **Documentation only.** No schema was created, altered, or dropped. All DDL below is
> a proposal. Live verification was read-only (`SHOW CREATE TABLE`, `SHOW INDEX`,
> `SELECT COUNT(*)`, `information_schema`).

---

## 1. The problem this schema solves

BR-ACL-001 §2.3 requires three principal levels — **Owner**, **Group**, **Other** —
against one record, where Owner is single-valued and Group is multi-valued.

A single polymorphic "one row per grant" table cannot carry that shape. It has to
encode a 1-of-N cardinality in a column that is either nullable (D3: then "no group"
is indistinguishable from "unspecified") or non-nullable (then a record with no groups
cannot exist). It also fuses *identity* with *capability*, which forces a capability
change to be a mass `UPDATE` over records rather than a single policy write (D4).

**Therefore: separate tables per cardinality, plus a policy table per resource class.**

| Table | Cardinality per record | Answers |
|---|---|---|
| `0_rbac_record_owner` | **exactly ≤ 1** | "Who owns this?" |
| `0_rbac_record_group` | **0 … N** | "Which groups may see this?" |
| `0_rbac_group_policy` | 0 … N per *(group, resource)* | "What may that group do to that kind of record?" |
| `0_rbac_record_exception` | 0 … N | "Does this one record differ from its group policy?" |

## 2. Verified starting point

Live schema `ksf_fa` on `ksfii_app-mariadb` (MariaDB 10.11.14-ubu2204), 2026-10-14.
**[V throughout §2.]**

```
CREATE TABLE `0_rbac_record_access` (
  `id`          int(11) unsigned NOT NULL AUTO_INCREMENT,
  `module`      varchar(64) NOT NULL,
  `record_type` varchar(64) NOT NULL,
  `record_id`   int(11) unsigned NOT NULL,
  `team_id`     varchar(64) NOT NULL COMMENT 'FK to 0_rbac_teams.id',
  `projection`  varchar(32) NOT NULL DEFAULT 'public',
  `can_view`    tinyint(1) NOT NULL DEFAULT 0,
  `can_edit`    tinyint(1) NOT NULL DEFAULT 0,
  `can_delete`  tinyint(1) NOT NULL DEFAULT 0,
  `can_export`  tinyint(1) NOT NULL DEFAULT 0,
  `can_print`   tinyint(1) NOT NULL DEFAULT 0,
  `can_invite`  tinyint(1) NOT NULL DEFAULT 0,
  `can_restore` tinyint(1) NOT NULL DEFAULT 0,
  `granted_by`  varchar(64) DEFAULT NULL,
  `granted_at`  datetime NOT NULL DEFAULT current_timestamp(),
  `expires_at`  datetime DEFAULT NULL,
  `inactive`    tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `record_lookup` (`module`,`record_type`,`record_id`,`inactive`),
  KEY `team_lookup`   (`team_id`,`inactive`),
  KEY `expiry`        (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
```

`SHOW INDEX` confirms `Non_unique = 1` on all three keys — **`record_lookup` is not
unique**, contrary to the premise this FR was written against. See BR-ACL-001 §3.1.

Related existing tables:

```
0_rbac_teams:          id varchar(64) PK, display_name, team_type varchar(32),
                       owner_id varchar(64) NULL, auto_managed, requires_approval,
                       inactive, created_at, updated_at
                       KEY team_type (team_type, inactive)
                       KEY owner_id  (owner_id, inactive)

0_rbac_team_members:   id, team_id varchar(64), user_id varchar(64), role,
                       approved, approved_by, approved_at, added_by, added_at,
                       removed_by, removed_at, inactive
                       UNIQUE KEY team_user_inactive (team_id, user_id, inactive)
                       KEY user_id  (user_id, inactive)
                       KEY approved (team_id, approved, inactive)

0_rbac_audit_log:      id, action, actor_id, target_id, module, record_type,
                       record_id, details TEXT, ip_address, created_at
```

**All four tables hold 0 rows.** **[V]**
**No PHP in the tree references `0_rbac_record_access`.** `ksf_FA_RBAC/src/` contains
`Storage/FaRoleStorage.php`; there is no `FaRecordAccessRepository` and no
`FaTeamRepository`. **[V]**

### 2.1 Principal key: `0_users.user_id`, **not** `0_users.id` **[V]**

```
0_users:  id       smallint(6)   PRI  auto_increment
          user_id  varchar(60)   UNI
```

`0_rbac_teams.owner_id` and `0_rbac_team_members.user_id` both carry
`COMMENT 'FK to 0_users.id'`. **That comment is wrong** — `0_users.id` is a
`smallint`. The RBAC column types (`varchar(64)`) match `0_users.user_id varchar(60)`,
which is the key FA uses for the acting user. **All principal columns in the schema
below are `VARCHAR(64)` referencing `0_users.user_id`, and their `COMMENT`s say so.**
Getting this wrong produces a silent `smallint`/`varchar` join that drops rows.

## 3. Design

### 3.1 `0_rbac_record_owner` — the Owner axis

```sql
CREATE TABLE IF NOT EXISTS `0_rbac_record_owner` (
    `id`             INT(11) UNSIGNED NOT NULL AUTO_INCREMENT,
    `module`         VARCHAR(64)      NOT NULL,
    `record_type`    VARCHAR(64)      NOT NULL,
    `record_id`      INT(11) UNSIGNED NOT NULL,
    `owner_id`       VARCHAR(64)      NOT NULL
                     COMMENT 'FK to 0_users.user_id (NOT 0_users.id, which is smallint)',
    `ownership_type` VARCHAR(32)      NOT NULL DEFAULT 'user'
                     COMMENT 'user | team | role | service_account',
    `acquired_at`    DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `acquired_by`    VARCHAR(64)      NULL DEFAULT NULL
                     COMMENT 'FK to 0_users.user_id',
    PRIMARY KEY (`id`),
    UNIQUE KEY `record_owner_lookup` (`module`, `record_type`, `record_id`),
    KEY `owner_lookup`      (`owner_id`, `module`, `record_type`),
    KEY `owner_acquired`    (`owner_id`, `acquired_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**Cardinality: hard-enforced at most one live owner per record**, by
`UNIQUE (module, record_type, record_id)`. There is deliberately **no `inactive`
column in this table** — see §4.

`ownership_type` exists so ownership can be held by a *team* or a *role* (a shared
account) rather than a person, without a second table. It is not a polymorphic FK and
is not enforced as one; it is a declaration of how `owner_id` should be read. This is
the one place where a polymorphic column survives, and it survives because the
cardinality is 1 and the lookup is always on `record_id`, never on `owner_id`
authoritatively. **[D]**

### 3.2 `0_rbac_record_group` — the Group axis

```sql
CREATE TABLE IF NOT EXISTS `0_rbac_record_group` (
    `id`           INT(11) UNSIGNED NOT NULL AUTO_INCREMENT,
    `module`       VARCHAR(64)      NOT NULL,
    `record_type`  VARCHAR(64)      NOT NULL,
    `record_id`    INT(11) UNSIGNED NOT NULL,
    `group_id`     VARCHAR(64)      NOT NULL
                   COMMENT 'FK to 0_rbac_teams.id',
    `group_kind`   VARCHAR(32)      NOT NULL DEFAULT 'team'
                   COMMENT 'team | project | ad_hoc | service_account | org_unit',
    `access_level` VARCHAR(16)      NOT NULL DEFAULT 'read'
                   COMMENT 'read | write | admin',
    `granted_by`   VARCHAR(64)      NULL DEFAULT NULL
                   COMMENT 'FK to 0_users.user_id',
    `granted_at`   DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `expires_at`   DATETIME         NULL DEFAULT NULL,
    `retired_at`   DATETIME         NULL DEFAULT NULL,
    `live_flag`    TINYINT(1)       NULL DEFAULT NULL
                   COMMENT 'NULL = live; set to 1 on retirement. Enables unlimited
                            history with exactly one live row per (record, group).',
    PRIMARY KEY (`id`),
    UNIQUE KEY `record_group_lookup` (`module`, `record_type`, `record_id`, `group_id`, `live_flag`),
    UNIQUE KEY `id_live`             (`id`, `live_flag`),
    KEY `group_lookup`   (`group_id`, `live_flag`, `module`, `record_type`),
    KEY `record_lookup`  (`module`, `record_type`, `record_id`, `live_flag`),
    KEY `expiry`         (`expires_at`),
    KEY `kind_lookup`    (`group_kind`, `live_flag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

This is the table that carries R4 (many groups per record). The uniqueness story is
the interesting part and is specified in §4.

`access_level` here is a **coarse per-membership level** (`read`/`write`/`admin`) that
narrows the group's policy (below). It is deliberately *not* the seven
`can_*` booleans of `0_rbac_record_access`: those belong to the policy table.

### 3.3 Groups are orthogonal to the org chart

`group_kind` is recorded on the **membership row**, not on the group, because the same
group can carry different kinds in different contexts (a project team used as an org
team in a payroll record). `group_kind = 'project'` is asserted by
`ksf_FA_ProjectManagement`; `= 'org_unit'` by `ksf_FA_HRM`. The ACL layer **stores**
the kind and **never queries the owning module** to resolve a group (R5).

`0_rbac_teams` is retained as the group *catalogue* and is not modified by this FR.
Whether it should instead absorb all five kinds is open question **Q1**.

### 3.4 `0_rbac_group_policy` — what a group may do

```sql
CREATE TABLE IF NOT EXISTS `0_rbac_group_policy` (
    `id`          INT(11) UNSIGNED NOT NULL AUTO_INCREMENT,
    `group_id`    VARCHAR(64)      NOT NULL
                  COMMENT 'FK to 0_rbac_teams.id',
    `module`      VARCHAR(64)      NOT NULL,
    `record_type` VARCHAR(64)      NOT NULL,
    `row_level`   VARCHAR(16)      NOT NULL DEFAULT 'other'
                  COMMENT 'owner_only | group | other | none',
    `can_view`    TINYINT(1)       NOT NULL DEFAULT '0',
    `can_edit`    TINYINT(1)       NOT NULL DEFAULT '0',
    `can_delete`  TINYINT(1)       NOT NULL DEFAULT '0',
    `can_export`  TINYINT(1)       NOT NULL DEFAULT '0',
    `can_print`   TINYINT(1)       NOT NULL DEFAULT '0',
    `can_invite`  TINYINT(1)       NOT NULL DEFAULT '0',
    `can_restore` TINYINT(1)       NOT NULL DEFAULT '0',
    `inactive`    TINYINT(1)       NOT NULL DEFAULT '0',
    `updated_by`  VARCHAR(64)      NULL DEFAULT NULL
                  COMMENT 'FK to 0_users.user_id',
    `updated_at`  DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `policy_lookup` (`group_id`, `module`, `record_type`, `inactive`),
    KEY `resource_lookup` (`module`, `record_type`, `inactive`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

The seven `can_*` columns are **carried over unchanged from `0_rbac_record_access`**
so the capability vocabulary is not re-invented. What changes is their *grain*: they
are now keyed by `(group, module, record_type)` — **one row per policy** — instead of
one row per record. Changing what a group may do is now a single `UPDATE`.

`row_level` is the Other-axis posture and is the state BR-ACL-001 R6 requires to be
defined rather than implied: `none` = this group sees nothing of this resource;
`other` = this group sees records with no owner and no groups; `group` = plus records
it is attached to; `owner_only` = plus records it owns.

### 3.5 `0_rbac_record_exception` — the per-record override

```sql
CREATE TABLE IF NOT EXISTS `0_rbac_record_exception` (
    `id`            INT(11) UNSIGNED NOT NULL AUTO_INCREMENT,
    `module`        VARCHAR(64)      NOT NULL,
    `record_type`   VARCHAR(64)      NOT NULL,
    `record_id`     INT(11) UNSIGNED NOT NULL,
    `group_id`      VARCHAR(64)      NOT NULL
                    COMMENT 'FK to 0_rbac_teams.id',
    `effect`        VARCHAR(8)       NOT NULL DEFAULT 'deny'
                    COMMENT 'deny | allow',
    `can_view`      TINYINT(1)       NOT NULL DEFAULT '0',
    `can_edit`      TINYINT(1)       NOT NULL DEFAULT '0',
    `can_delete`    TINYINT(1)       NOT NULL DEFAULT '0',
    `can_export`    TINYINT(1)       NOT NULL DEFAULT '0',
    `can_print`     TINYINT(1)       NOT NULL DEFAULT '0',
    `can_invite`    TINYINT(1)       NOT NULL DEFAULT '0',
    `can_restore`   TINYINT(1)       NOT NULL DEFAULT '0',
    `reason`        VARCHAR(255)     NULL DEFAULT NULL
                    COMMENT 'required by the compliance retention rule',
    `granted_by`    VARCHAR(64)      NULL DEFAULT NULL
                    COMMENT 'FK to 0_users.user_id',
    `granted_at`    DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `expires_at`    DATETIME         NULL DEFAULT NULL,
    `live_flag`     TINYINT(1)       NULL DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `exception_lookup` (`module`, `record_type`, `record_id`, `group_id`, `effect`, `live_flag`),
    KEY `group_lookup`  (`group_id`, `live_flag`),
    KEY `record_lookup` (`module`, `record_type`, `record_id`, `live_flag`),
    KEY `expiry`        (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Deliberately **the rarest table**. A per-record capability table is the thing that
made `0_rbac_record_access` unmaintainable, so this one is bounded to the genuinely
irreducible cases (a litigation hold, a PIPEDA erasure carve-out, a single disputed
record) and every row carries a `reason`.

## 4. Uniqueness strategy — and the correction to the premise

### 4.1 The brief's stated blocker does not exist **[V]**

The premise was that `record_lookup`'s **UNIQUE** index on
`(module, record_type, record_id, inactive)` permits one ACL row per record and must be
dropped. It is **not unique** (`Non_unique = 1`, §2). **Nothing needs to be dropped.**
The correct framing is the inverse of the one in the brief:

> Multiple groups per record are **already** expressible. What is missing is any
> guarantee that they are expressible **cleanly** — without duplicates, without the
> Owner axis, and without policy fused to record.

So FR-ACL-001-01 does not "drop a UNIQUE index". It creates new tables with correct
constraints and retires a table that has no consumer.

### 4.2 The `inactive`-in-unique-key trap, and `live_flag`

FA's existing soft-delete idiom is `UNIQUE (…, inactive)` — visible in
`0_rbac_team_members.team_user_inactive`. This permits **one** live row (`inactive=0`)
and **one** retired row (`inactive=1`). A second retirement collides with error 1062.
For membership tables that hold history this is a latent bug, not a feature. **[A —
SQL semantics; not executed against this server]**

The new tables use `live_flag TINYINT(1) NULL DEFAULT NULL`:

- a **live** row has `live_flag IS NULL`;
- a **retired** row has `live_flag = 1` (or the retiring timestamp).

MariaDB/InnoDB unique indexes do not treat `NULL` values as equal to one another, so
`UNIQUE (module, record_type, record_id, group_id, live_flag)` permits **exactly one
live row** per `(record, group)` and **any number** of retired rows. **[A]** This is
the standard "nullable sentinel" uniqueness trick; it should be confirmed by
execution on this server before it is relied on (open question **Q5** — I did not
create a table to test it).

`id_live UNIQUE (id, live_flag)` is required so that `live_flag` is a genuine index
member and not a trailing free-text column the optimizer ignores.

`0_rbac_record_owner` needs no `live_flag`: ownership transfer is an **`UPDATE`** of
the single row, with the before/after written to `0_rbac_audit_log`. History lives in
the audit log, not in the ownership table. Simpler, and it makes
`UNIQUE (module, record_type, record_id)` an absolute, error-enforced guarantee of R3.

## 5. What happens to `0_rbac_record_access` **[D]**

| Question | Answer | Basis |
|---|---|---|
| Does it have data? | **No** — 0 rows | **[V]** |
| Does it have code? | **No** — no PHP reference anywhere in the tree | **[V]** |
| Does it have requirements? | **Yes** — `ksf_FA_RBAC/ProjectDcs/FR-001-001-Access_Repository.md` and `BR-001-Access_Control.md` describe it | **[V]** |
| Action | **Drop**, superseded by `0_rbac_record_owner` + `0_rbac_record_group` + `0_rbac_group_policy` | [D] |

**Sequence:**

1. Create the four new tables. Additive, zero-risk, reversible.
2. Ship the builder support (FR-ACL-001-02, FR-ACL-001-03).
3. **Only then** drop `0_rbac_record_access`, in a *separate, later* commit, with the
   `ProjectDcs/FR-001-001-Access_Repository.md` and `BR-001-Access_Control.md` marked
   superseded in the same commit.

Steps 1→3 are deliberately separated so that dropping is never in the same change that
introduces the replacement.

> **Installer constraint.** Per `AGENTS.md` and confirmed by reading
> `admin/db/maintenance_db.inc:337`, module `sql/*.sql` files use the literal `0_`
> prefix — `{TB_PREF}` and `@TB_PREF@` do **not** work on the FA install path. All DDL
> above follows that convention. The DROP must **not** go in `sql/install.sql`:
> `DROP TABLE IF EXISTS` is in `db_import`'s allow-list, but a drop inside an install
> script re-runs on every upgrade. Drop it in a documented one-off migration, or by
> application code, and confirm `uninstall_extension()` does not try to reverse it.

## 6. Access-level resolution **[D]**

Given principal P and record R, the levels are evaluated in a fixed order and the
first match wins:

| Order | Level | Predicate |
|---|---|---|
| 1 | **Exception (deny)** | A `0_rbac_record_exception` row with `effect='deny'` for any group of P. **Deny is checked first and is absolute.** |
| 2 | **Owner** | `0_rbac_record_owner.owner_id = P.user_id` and the owning group's policy grants the capability. |
| 3 | **Group** | A live `0_rbac_record_group` row for R and any group of P, with `access_level` ≥ the required level. |
| 4 | **Other** | The `row_level` of P's group policy for `(module, record_type)` is `other`. |

Notes:

- **Deny-first is a decision with a cost.** A deny exception cannot be overridden by
  ownership, which means "the owner's own record is denied to them" is expressible —
  correct for erasure carve-outs, wrong if misused. It is proposed because PIPEDA/GDPR
  erasure requests are the driving requirement and those are absolute.
- **Owner is not automatically privileged.** Level 2 consults the owning group's
  policy for the capability, so an owner can still be denied `can_export`.
- `inactive` is **not** a security dimension. `0_users` has no active flag checked by
  this design **[UNVERIFIED — FA's own session logic decides user validity, see Q6]**,
  and FA's soft-delete `inactive` flags are used here only to retire rows, never to
  revoke access to a still-live user.

## 7. Index justification

Every index above exists to serve one of exactly two access paths. No other access
pattern is intended.

**Path 1 — per-record expansion** (FR-ACL-001-02 §3, the `EXISTS` form). Given
`(module, record_type, record_id)`, find the groups:

| Table | Index | Prefix used |
|---|---|---|
| `0_rbac_record_owner` | `record_owner_lookup` | `(module, record_type, record_id)` — full, unique |
| `0_rbac_record_group` | `record_lookup` | `(module, record_type, record_id, live_flag)` |
| `0_rbac_record_exception` | `record_lookup` | `(module, record_type, record_id, live_flag)` |

**Path 2 — per-group expansion** ("which records may group G see?"). Given a user's
group ids, find every record:

| Table | Index | Prefix used |
|---|---|---|
| `0_rbac_record_group` | `group_lookup` | `(group_id, live_flag, module, record_type)` |
| `0_rbac_record_owner` | `owner_lookup` | `(owner_id, module, record_type)` |

`group_lookup` deliberately leads with `group_id` rather than the record triple,
because the predicate is driven from the **principal** outward (FR-ACL-001-02 §4), not
from the record outward. Leading with `(module, record_type, record_id)` there would
make the principal-side probe a full scan.

**Group membership** (`user_id → groups`) is served by the existing
`0_rbac_team_members.user_id (user_id, inactive)` index and is read once per request
into the policy cache — it is never part of the data query. That is what keeps the
cost at one query per request (FR-ACL-001-02 §4).

**Expiry.** `expiry (expires_at)` on `0_rbac_record_group` and
`0_rbac_record_exception` is for a sweeper job, not for the read path. The read
predicate carries `expires_at IS NULL OR expires_at > NOW()` as a residual filter; an
expired-but-not-yet-swept row is filtered, not indexed-out. **[A]**

## 8. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | Two inserts of `0_rbac_record_group` for the same `(module, record_type, record_id, group_id)` with `live_flag = NULL` → the second fails with **1062**. |
| AC2 | Retiring that row (`live_flag = 1`), then re-granting → **succeeds**. Retiring the first row twice → **succeeds** (this is the case FA's `inactive`-in-unique-key idiom fails). |
| AC3 | Two inserts of `0_rbac_record_owner` for the same `(module, record_type, record_id)` → the second fails with **1062**. |
| AC4 | A record may have rows in `0_rbac_record_group` for three distinct `group_id`s and all three are simultaneously live. |
| AC5 | `EXPLAIN` on the Path-2 probe (`group_lookup` prefix) uses the index and shows **no full table scan**, on a representative `ksf_fa` table. |
| AC6 | Joining `0_rbac_record_owner.owner_id` against `0_users.user_id` returns rows; joining against `0_users.id` returns none. This is the §2.1 regression guard. |
| AC7 | Inserting a group with `group_kind = 'project'` requires no row in the org-chart tables. |
| AC8 | Dropping `0_rbac_record_access` causes no PHP fatal in any module. |

## 9. Out of scope

- **`0_rbac_teams` and `0_rbac_team_members`.** Retained unmodified. Whether they
  should absorb all `group_kind` values is **Q1**.
- **`0_rbac_audit_log`.** Reused for grant/revoke/transfer events; not restructured.
  It has no index on `record_id`; if it becomes an audit *search* surface rather than a
  write-sink it will need one **[flagged, not designed]**.
- **The `projection` column.** `0_rbac_record_access.projection VARCHAR(32) NOT NULL
  DEFAULT 'public'` is declared and has no implementation
  (`Column_Level_ACL_Design.md` §3.3). It is **not** carried forward into
  `0_rbac_record_group`; column projection belongs to FR-ACL-001-04.
- **Foreign keys.** FA's `db_import` runs `SET foreign_key_checks=0` around every
  import (`maintenance_db.inc:311`) and `db_export` warns about ring constraints
  (`maintenance_db.inc:804`). No `FOREIGN KEY` constraint is declared — FA's `0_*`
  tables do not use them either. Referential integrity is application-enforced and is
  stated as a **rule**, not a constraint:

  | Rule | Enforcement |
  |---|---|
  | R-FK1 | `0_rbac_record_owner.owner_id` must exist in `0_users.user_id` | application, at write |
  | R-FK2 | `0_rbac_record_group.group_id` must exist in `0_rbac_teams.id` | application, at write |
  | R-FK3 | `0_rbac_record_exception.group_id` must exist in `0_rbac_teams.id` | application, at write |

## 10. Explicitly unverified

| Item | Status |
|---|---|
| The `live_flag NULL`-in-unique-index behaviour on MariaDB 10.11.14 | **[UNVERIFIED]** — no table was created. Standard SQL and InnoDB semantics say `NULL`s are distinct in a unique index; AC1/AC2 must be executed before this schema is adopted. **Q5.** |
| `EXPLAIN` plans for Paths 1 and 2 on real `ksf_fa` tables | **[UNVERIFIED]** — no index was created, so no plan was observed. AC5 requires execution. |
| Whether `ownership_type` as a non-enforced polymorphic column is acceptable, vs a second owner table | **[D — decision, not verified]** |
| Correctness of `0_users.user_id` as the acting-user key under FA's session handling | **[PARTIALLY VERIFIED]** — the column and its `UNIQUE` are confirmed **[V]**; that FA always populates `$_SESSION['wa_current_user']->user_id` and nothing else is the identity is **[UNVERIFIED]** (Q6). |
| Any statement about table row counts or timings | **None made.** No timing was taken; none should be quoted. |
| Whether `0_rbac_audit_log` needs an index on `record_id` | **[FLAGGED, NOT DESIGNED]** |

## 11. Related

- [BR-ACL-001](./BR-ACL-001-record-ownership-and-access-control.md) — R2, R3, R4, R5, R6
- [FR-ACL-001-02](./FR-ACL-001-02-row-acl-predicate.md) — consumes these indexes
- [FR-ACL-001-03](./FR-ACL-001-03-two-stage-enforcement-migration.md)
- [FR-ACL-001-04](./FR-ACL-001-04-column-axis-views.md)
- [OPEN-QUESTIONS.md](./OPEN-QUESTIONS.md) — Q1, Q5, Q6
- `ksf_FA_RBAC/sql/install.sql:60-83` — the DDL this supersedes
- `ksf_FA_RBAC/ProjectDcs/FR-001-001-Access_Repository.md` — superseded by §5