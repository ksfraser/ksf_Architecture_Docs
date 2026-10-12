# EmailManager — Debtor Resolution Fix & Data-Model Decision

@BABOK Related: BR-EM-001, FR-EM-001-03, BABOK 8.3 Solution Design, BABOK 8.4 Solution Architecture
Status: **Implemented (verified)**
Module: `ksf_FA_EmailManager`
Environment: Integration — container `ksfii_app-fa` (PHP 7.4.33), DB `ksfii_app-mariadb`, schema `ksf_fa`
Date: 2026-10-11

Files changed (exactly two, both under the bind-mounted deploy tree):

- `fa_modules/ksf_FA_EmailManager/includes/em_db.inc` — `find_debtor_by_email()` rewritten
- `fa_modules/ksf_FA_EmailManager/includes/em_routing.inc` — null coercion at the call site

---

## 1. The verified bug

`em_db.inc:241-248` queried a column that does not exist and never has:

```php
$sql = "SELECT debtor_no FROM " . TB_PREF . "debtors_master
    WHERE email = " . db_escape($email_address) . " LIMIT 1";
```

Reproduced against the live integration DB (`ksf_fa`):

```
SELECT debtor_no FROM 0_debtors_master WHERE email='x@y.com' LIMIT 1;
-> ERROR 1054 (42S22): Unknown column 'email' in 'WHERE'
```

Confirmed the column is absent, and that its absence is not an artefact of a partial
schema load — stock FA 2.4.3 `debtors_master` has exactly 16 columns:

```
debtor_no, name, debtor_ref, address, tax_id, curr_code, sales_type, dimension_id,
dimension2_id, credit_status, payment_terms, discount, pymt_discount, credit_limit,
notes, inactive
```

**Consequence:** `em_find_customer_match()` raised a DB error, so
`process_inbound_email()` could not complete on a stock install. Inbound mail was
never linked to a debtor.

---

## 2. The fix — invert the lookup, use the FA-native path

The bug was an inverted assumption, not a missing column. FrontAccounting does not
store email on the debtor. Email lives on the **person**, and the person is linked to
the debtor through the **contact** xref. So the debtor must be *derived*, never looked
up directly.

### Before

```sql
SELECT debtor_no FROM 0_debtors_master WHERE email = '<escaped>' LIMIT 1
```

### After

```sql
SELECT c.entity_id FROM 0_crm_contacts c
INNER JOIN 0_crm_persons p ON p.id = c.person_id
WHERE c.type = 'customer'
  AND p.email = '<escaped>'
  AND p.inactive = 0
ORDER BY c.id ASC LIMIT 1
```

In the file's own style — `TB_PREF` concatenation, one `db_escape()` on the single
user-supplied value, one `db_query()`, `db_fetch_assoc()`, `null` on no-match:

```php
function find_debtor_by_email($email_address)
{
    if (!is_string($email_address)) return null;

    $email_address = trim($email_address);

    // An empty address would otherwise match a person row whose email column
    // is blank and resolve to that person's debtor.
    if ($email_address === '') return null;

    $sql = "SELECT c.entity_id FROM " . TB_PREF . "crm_contacts c
        INNER JOIN " . TB_PREF . "crm_persons p ON p.id = c.person_id
        WHERE c.type = 'customer'
        AND p.email = " . db_escape($email_address) . "
        AND p.inactive = 0
        ORDER BY c.id ASC LIMIT 1";
    $result = db_query($sql, "Could not find debtor");
    $row = db_fetch_assoc($result);

    if (!$row || $row['entity_id'] === null || $row['entity_id'] === '') {
        return null;
    }

    return $row['entity_id'];
}
```

### Why this is the relationship FA itself defines

FA writes customer contacts as `add_crm_contact('customer', 'general', $debtor_no, $person_id)`
(`sales/manage/customers.php:126`), i.e. for `type = 'customer'` the `entity_id` **is**
`0_debtors_master.debtor_no`. The corrected query reads exactly that edge.

Four deliberate design points:

| Choice | Reason |
|---|---|
| `c.type = 'customer'` | Not every contact is a debtor. `cust_branch.entity_id` is a **branch** number and `supplier.entity_id` is a supplier number — either would be silently written into `debtor_no`. |
| `p.inactive = 0` | Mirrors `find_contact_by_email()`; do not match archived people. |
| `ORDER BY c.id ASC` | The sibling `find_contact_by_email()` uses `LIMIT 1` with no `ORDER BY`, making multi-match resolution non-deterministic. Ordering makes this path repeatable. |
| Empty-string guard | Verified live: the one `crm_persons` row (`id=5`) has `email` of **length 0**. Without the guard, an empty inbound From address would match that blank-email person and resolve to their debtor. |

`action` is **not** filtered on: `customer` has four valid actions
(`general`/`order`/`delivery`/`invoice`) and all four legitimately point at a debtor.
Filtering on `action='general'` would under-resolve.

### Explicitly not done

**No `email` column was added to `0_debtors_master`.** That is the core data-model
constraint, not an oversight — see §4.

---

## 3. Caller handling — no match is normal, not exceptional

`em_find_customer_match()` (`em_db.inc`) was already null-safe: it passes both lookups
straight into the returned array. Its only caller is `process_inbound_email()`.

Audited every consumer of the two values:

| Consumer | Handling | Verdict |
|---|---|---|
| `em_routing.inc` `UPDATE ... SET debtor_no` | guarded by `if ($debtor_no)` | already safe |
| `em_routing.inc` `UPDATE ... SET contact_id` | guarded by `if ($contact_id)` | already safe |
| `em_routing.inc` `em_create_ticket_from_email($id, $debtor_no, $contact_id)` | **was unguarded** | fixed |
| `em_routing.inc` `em_create_opportunity_from_email(...)` | **was unguarded** | fixed |
| `process_inbound_email()` return array | passes the value through | safe |

The two entity creators declare `INT` parameters with default `0` and feed them
straight to `db_escape()`. A `null` reaching them would be coerced to the empty string
and written into an integer column. Fixed at the call site with `?? 0`:

```php
$entity_id = em_create_ticket_from_email($email_id, $debtor_no ?? 0, $contact_id ?? 0);
```

`process_inbound_email()` now completes with `debtor_no = null` and simply leaves the
linkage columns unset, which is the correct outcome for an unknown sender.

---

## 4. The satellite-table principle, as applied

The standing decision:

> Module tables duplicating a FrontAccounting core table must NOT exist — use the
> native FA table. **Exception:** if a module genuinely needs to collect information
> native FA does not store, that data belongs in a **separate satellite table keyed by
> the FA core id**, never by duplicating the core table's rows.

**How this fix applies it:** the module needed email → debtor resolution, but the
information it needed (`email`) **already existed natively**, in `0_crm_persons`, joined
to `0_debtors_master` through `0_crm_contacts`. There was no new information to
collect, so the correct action was to **read the native path and change zero schema** —
which is what this fix does. The tempting shortcut (ALTER `debtors_master` to add
`email`) would have created a module-maintained copy of data FA already owns, and a
second source of truth for customer email that could drift from `crm_persons`.

Had the module genuinely needed to store something FA does not (e.g. "email → this
person is a billing contact, not a shipping contact"), the correct shape would be a
separate table keyed by the core id, e.g. `0_ksf_em_contact_roles(person_id, role)` —
never a second copy of contact rows.

---

## 5. Duplicate-of-core-table findings — REPORTED, NOT DELETED

Per instruction, nothing was dropped. One finding needs a decision.

### Finding 1 — `0_ksf_crm_contacts` duplicates `0_crm_contacts` — **decision needed**

| | |
|---|---|
| Module table | `0_ksf_crm_contacts` |
| Core table it duplicates | `0_crm_contacts` |
| Row count | **0** |
| Created | 2026-09-30 04:49:53 |
| Core table created | 2026-09-16 15:24:22 (2 rows) |

Schema confirmed as a **row-level duplicate** of the native xref — it stores the
person's details inline instead of joining to `crm_persons`:

```
id, debtor_no, contact_role_id, first_name, last_name, title, department, phone,
mobile, email, address, notes, is_primary, inactive, created_at, updated_at
```

versus the native `0_crm_contacts`, which is only a xref and carries **no** email:

```
id, person_id, type, action, entity_id
```

The duplication is the textbook failure mode: **both tables have an `email` column
meaning different things.** `0_ksf_crm_contacts.email` is the contact's address;
`0_crm_persons.email` is FA's authoritative person address. This is almost certainly
what produced the original bug — someone reached for `debtors_master.email`, a third
place where email was assumed to live.

Not deleted. The table is still **wired into live code**, so removing it is a
separate, larger change:

- `ksf_FA_CRM/sql/ksf_crm_contacts.sql` — creates it on activate
- `ksf_FA_CRM/hooks.php:104` — `'ksf_crm_contacts.sql' => array('ksf_crm_contacts')` in the install map
- `ksf_FA_CRM/src/.../Repository/ContactsRepository.php:25` — `$table = 'ksf_crm_contacts'`
- `ksf_FA_CRM/src/.../Service/ContactsService.php:74` — `'table' => '0_ksf_crm_contacts'`
- `ksf_FA_CRM/src/.../Controller/ContactsTabController.php`, `ContactOptionsService.php`
- asserted as the expected table name by `ksf_FA_CRM/tests/Unit/RepositoryTableNameTest.php:36`

Note `ContactOptionsService.php:13` and `ksf_FA_Notes/includes/entity_types.inc:60`
already describe it as "legacy" and deliberately route around it — so the migration
is partly done, but not finished.

**Recommendation (for decision, not action):** retire `0_ksf_crm_contacts`; repoint
`ContactsRepository`/`ContactsService` at the native `crm_persons` + `crm_contacts`
path, and if the extra fields are genuinely needed, move them to a satellite table
keyed by `crm_contacts.id`. The table is empty, so no data migration is at risk.

### Finding 2 — EmailManager's own five tables: no duplicates

Audited all five `ksf_FA_EmailManager` tables against the full core table list:

| Module table | Rows | Duplicates a core table? |
|---|---|---|
| `0_ksf_em_accounts` | 1 | **No** — mailbox/IMAP config; no core equivalent |
| `0_ksf_em_inbound_emails` | 0 | **No** — FA has no inbound mail store |
| `0_ksf_em_mailing_lists` | 0 | **No** — no core equivalent |
| `0_ksf_em_routes` | 0 | **No** — routing rules; no core equivalent |
| `0_ksf_em_subscribers` | 0 | **No** — list subscription state |

`0_ksf_em_subscribers` deserves a note but is **not** a duplicate: a subscriber is a
*list membership* (an email opted into a mailing list), which FA does not model
anywhere. It carries optional `debtor_no`/`contact_id` references — correctly
*pointing at* core ids rather than copying core rows.

**Conclusion: EmailManager itself owns no duplicate-of-core tables.** The duplicate is
`0_ksf_crm_contacts`, which belongs to `ksf_FA_CRM` and is merely adjacent to this fix.

---

## 6. Verification

All checks run against the live integration stack.

### 6.1 Syntax

`php -l` run on **both** the host (8.1.18) and inside the real container (7.4.33):

```
No syntax errors detected in includes/em_db.inc
No syntax errors detected in includes/em_routing.inc
```

### 6.2 The corrected SQL executes; no ERROR 1054

Direct against `ksf_fa` — the raw query is valid and returns data:

```
SELECT c.entity_id ... WHERE c.type='customer' AND p.email='' AND p.inactive=0;
-> entity_id=3, contact_id=2, person_id=5, type=customer      (mysql_exit=0)
```

Negative case — unknown address returns an empty set, **no error**, `mysql_exit=0`.

### 6.3 The real PHP function against the real DB

A throwaway harness bootstrapped FA's own DB layer inside `ksfii_app-fa`
(`connect_db.inc`, `errors.inc`, live `config_db.php` credentials) and called the
**actual** `find_debtor_by_email()` / `em_find_customer_match()`.

The live DB has only one `crm_persons` row and its `email` is empty, so a true
positive needed a real person. A second harness seeded one **inside a transaction and
rolled back** — plus a `cust_branch` contact to prove the type filter works:

| Case | Expected | Got | Result |
|---|---|---|---|
| `find_debtor_by_email(positive.proof@acme.example)` | `"3"` | `string(1) "3"` | **PASS** |
| `em_find_customer_match(...)` | debtor+contact both set | `"3"` / `"3"` | **PASS** |
| same address, person set `inactive=1` | `NULL` | `NULL` | **PASS** |
| person with **only** a `cust_branch` contact | `NULL` | `NULL` | **PASS** |
| unknown address | `NULL` | `NULL` | **PASS** |
| `''` / `'   '` / `null` / `12345` | `NULL`, no throw | `NULL` | **PASS** |
| `O'Brien' OR '1'='1` | `NULL`, query survives | `NULL` | **PASS** |
| `find_contact_by_email` (unchanged) | `NULL` | `NULL` | **PASS** |

Note the `cust_branch`-only case: the seeded person had a branch contact pointing at
`entity_id = 1`, and the query correctly returned `NULL` rather than debtor `1`.

**DB restored exactly as found:** `crm_persons`=1, `crm_contacts`=2, `debtors_master`=3,
0 `EMPROOF` rows. Harness files deleted from the container.

### 6.4 Site health

```
root=200
inbox=200  accounts=200  campaigns=200  mailing_lists=200
```

`http://localhost:8090/` stays **200**; all four EmailManager pages still respond 200
(FA's login redirect to anonymous requests, as expected).

### 6.5 Change scope

Confirmed by `find -mmin` and `stat` that exactly **two** files were modified
(`em_db.inc`, `em_routing.inc`, both 02:09). The `pages/*.php` files also appear in a
60-minute window but carry timestamps of **01:31** — they predate this work and were
not touched. `hooks.php` was **not** modified; no git command was run.

---

## 7. Residual issues — reported, deliberately NOT fixed here

Found while reading call sites; each is a separate decision. Out of scope for a narrow
bug fix.

1. **`0_fa_st_tickets` does not exist.** `em_create_ticket_from_email()` inserts into
   `TB_PREF . "fa_st_tickets"` (`em_routing.inc:71`) — unsuppressed. Verified absent
   from the core table list. So the default `'ticket'` routing action still fails at
   the insert step. Previously masked because the query died *earlier*, at debtor
   resolution; this fix unblocks that path and therefore **exposes** it.
2. **`0_crm_opportunities` does not exist.** `em_create_opportunity_from_email()`
   inserts there. It is `@`-suppressed and returns `0`, so it degrades quietly.
3. **`find_contact_by_email()` is non-deterministic** — `LIMIT 1` with no `ORDER BY`,
   and no `type` filter, so it can return a supplier or branch contact. Left alone to
   keep this change narrow; the new debtor query does not depend on it.
4. **`em_routing.inc:102`** passes bare `CURDATE()` as a value inside a
   `db_escape()`-style concatenation — a SQL function, not an escaped literal. Works,
   but is inconsistent with the surrounding style.
5. **No index on `0_crm_persons.email`** — every lookup is a full table scan. Harmless
   at 1 row; worth noting as volume grows.

---

## 8. Traceability

| Artefact | Reference |
|---|---|
| This document | BR-EM-001, FR-EM-001-03, BABOK 8.3 / 8.4 |
| Defect analysis (pre-existing) | `ksf_Architecture_Docs/Requirements/FR-EM-001-03-addressee-resolution.md` §3 |
| Wider analysis (pre-existing) | `ksf_Architecture_Docs/Requirements/Inbound_Email_Architecture.md` §5.1 (defect **B2**) |
| `EmailManager_Analysis.md:199-200` | Listed this as a defect but judged contact resolution sound overall — that judgement was **half wrong** (correct on `find_contact_by_email`, wrong on the debtor half) |