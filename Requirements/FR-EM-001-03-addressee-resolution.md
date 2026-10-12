# FR-EM-001-03 — Resolve addressees to contacts

@BABOK Related: BR-EM-001, FR-EM-001-01, BABOK 8.3 Solution Design
Status: **Proposed**
Module: `ksf_FA_EmailManager`
Date: 2026-10-11

---

## 1. Requirement being satisfied

> "Resolve addressees to CONTACTS: match an existing contact by email address, or
> create one. A support request must produce an email record that links: the SENDER's
> contact, that contact's ASSOCIATED DEBTOR, the support team's own email address, and
> every other recipient (including CC and BCC) as contacts."

This FR makes that operable. Two structural consequences are load-bearing:

- **Every** addressee (From, To, Cc, Bcc, Reply-To) must be individually linked to
  a contact. That is a **one-to-many** relationship, so it cannot live in the
  `to_address VARCHAR(255)` / `cc_addresses TEXT` columns — those are free text and
  cannot be joined, indexed, or attached to a person. Hence a new table.
- The **debtor** is derived *through* the contact, never by looking up an email
  against a debtor table. See §3 — the current code does the latter and it is broken.

## 2. The FA contact model (verified)

Verified against `FA/2.4.3/sql/en_US-new.sql`, `FA/2.4.3/includes/db/crm_contacts_db.inc`,
and the live `ksf_fa` database.

### 2.1 `0_crm_persons` — the person, and the only place an email lives

```
id, ref(30), name(60), name2(60), address(tinytext),
phone(30), phone2(30), fax(30), email(100), lang(5), notes(tinytext), inactive
KEY ref(ref)          <-- NO index on email
```

Verified live: 1 row. Verified: **no index on `email`** — every lookup by email is a
full table scan.

### 2.2 `0_crm_contacts` — the person→entity xref

```
id, person_id, type(20), action(20), entity_id(11)
KEY type(type, action)
```

`type` and `action` are FKs into `0_crm_categories`; `entity_id` is "entity id in
related class table" (column comment). **The contact row carries no email.**

### 2.3 The customer↔contact link

Canonical call, verified at `sales/manage/customers.php:126`:

```php
add_crm_contact('customer', 'general', $selected_id /* debtor_no */, $pers_id);
```

So for a customer: **`type = 'customer'`, `action = 'general'`,
`entity_id = 0_debtors_master.debtor_no`.**
Also at `customers.php:124` and `customer_branches.php:105`:
`('cust_branch', 'general', <branch_no>, <person_id>)`.

Seeded `0_crm_categories` (verified, `en_US-new.sql:427-439`):
`cust_branch/{general,invoice,order,delivery}`, `customer/{general,order,delivery,invoice}`,
`supplier/{general,order,delivery,invoice}`.
**There is no `case`/`support` category** — see open question **Q6**.

Verified live data, illustrating the shape:

```
person 5 "test"  ->  crm_contacts id 1: cust_branch/general, entity_id 1
                 ->  crm_contacts id 2: customer/general,    entity_id 3   (debtor_no 3)
```

`0_debtors_master` has **3 rows**.

### 2.4 The APIs

- `add_crm_person($ref, $name, $name2, $address, $phone, $phone2, $fax, $email, $lang, $notes, $cat_ids, $entity)`
- `add_crm_contact($type, $action, $entity_id, $person_id)`
- `get_crm_persons($type, $action, $entity, $person, $unique)` — joins all three tables
- `get_crm_person($id)` — includes `get_person_contacts($id)`

> **`crm_contacts.id` ≠ `crm_persons.id`.** `find_contact_by_email()` in the current
> code returns `c.id` — the **xref row id**. That is correct for "which contact link",
> but it is NOT the person id, and the two must not be confused downstream. The new
> addressee table stores **both**, explicitly named.

## 3. Critical verified defect: debtor-by-email is impossible today

`em_db.inc:241-248`:

```php
function find_debtor_by_email($email_address) {
    $sql = "SELECT debtor_no FROM " . TB_PREF . "debtors_master WHERE email = " . db_escape($email_address) . " LIMIT 1";
```

**`0_debtors_master` has no `email` column.**

Verified two ways on the live integration DB (2026-10-11):

```
SHOW COLUMNS FROM 0_debtors_master;
-> debtor_no, name, debtor_ref, address, tax_id, curr_code, sales_type,
   dimension_id, dimension2_id, credit_status, payment_terms, discount,
   pymt_discount, credit_limit, notes, inactive          (16 columns, no `email`)

SELECT debtor_no FROM 0_debtors_master WHERE email='a@b.c';
-> ERROR 1054 (42S22): Unknown column 'email' in 'WHERE'
```

Also verified that **no module adds it**: grepped every `FA/2.4.3/sql/alter*.sql` and
every `fa_modules/*/sql/*.sql` — there is no `ALTER TABLE ... ADD email` against
`debtors_master` anywhere in the tree.

**Consequence:** `em_find_customer_match()` raises a DB error, so
`process_inbound_email()` **cannot complete on a stock install**. The
`EmailManager_Analysis.md` verdict that contact resolution is *"YES, in the FA
module"* is correct about `find_contact_by_email()` (which correctly joins
`crm_contacts ⋈ crm_persons`) but **wrong about the debtor half**.

`find_contact_by_email()` itself is sound, with two caveats: it does not filter by
`crm_contacts.type`, so it can return a **supplier** or **branch** contact; and it
uses `LIMIT 1` with no `ORDER BY`, making multi-match resolution **non-deterministic**.

### 3.1 Required inversion

> **The contact is the email authority. The debtor is derived through the contact.**

```
person_id  <- 0_crm_persons.email  (normalised match)
debtor_no  <- 0_crm_contacts.entity_id
             WHERE person_id = ? AND type = 'customer' AND action = 'general'
```

This removes the broken query entirely, removes the need to alter an FA core table,
and is the relationship FA itself defines. **This is the recommended approach.**

## 4. The addressee table

### `0_ksf_em_addressees`

| Column | Type | Notes |
|---|---|---|
| `id` | INT PK AI | |
| `email_id` | INT NOT NULL | FK → `0_ksf_em_inbound_emails.id`, indexed |
| `role` | ENUM(`from`,`to`,`cc`,`bcc`,`reply_to`,`return_path`) | |
| `ordinal` | TINYINT | position within the role, preserves header order |
| `address` | VARCHAR(255) | as it appeared in the header |
| `address_normalized` | VARCHAR(255) | lowercased, trimmed |
| `display_name` | VARCHAR(255) | the `Personal` part, if present |
| `bcc_source` | ENUM(`envelope`,`header`,`unknown`) | see FR-EM-001-01 C1 |
| `person_id` | INT NULL | → `0_crm_persons.id` |
| `contact_id` | INT NULL | → `0_crm_contacts.id` (**not** the person id) |
| `debtor_no` | INT NULL | denormalised copy for list-view performance |
| `match_method` | ENUM(`exact_email`,`normalized_email`,`subaddress_stripped`,`person_only`,`ambiguous`,`created_new`,`none`,`account_self`) | |
| `match_confidence` | DECIMAL(3,2) | 1.00 exact … 0.00 unresolved |
| `candidates` | JSON NULL | **all** matching person ids when ambiguous |
| `is_resolved` | TINYINT(1) | 1 when `person_id` is set |
| `is_created` | TINYINT(1) | 1 when this resolution created a `crm_persons` row |
| `created_at`, `updated_at` | TIMESTAMP | |

Indexes: `(email_id)`, `(address_normalized)`, `(person_id)`, `(debtor_no)`,
UNIQUE `(email_id, role, ordinal)`.

### 4.1 A separate candidate table, or JSON?

`candidates JSON` is recommended for the first iteration because ambiguity is rare
and the list is short. If triage volume grows, promote it to
`0_ksf_em_addressee_candidates(addressee_id, person_id, score)`.
**This is a deliberate deferral, not an oversight.**

## 5. Resolution rules

### FR-EM-001-03-1 — Normalisation

Before any comparison, normalise: `strtolower(trim($addr))`. Apply `imap_utf8()`
(already used in the sibling `EmailFetchService`) so that RFC 2047 encoded display
names decode correctly.

**Plus-addressing:** `john+support@acme.com` should *optionally* match
`john@acme.com`, but at **lower confidence** (`match_method = 'subaddress_stripped'`,
`match_confidence = 0.60`), never at full confidence. Whether to attempt this at
all is open question **Q11** — a `+tag` frequently denotes a *different* intent
(routing), and silently matching can be wrong.

### FR-EM-001-03-2 — Match or create

For each addressee, in order:

| Step | Test | Outcome |
|---|---|---|
| R1 | Address equals `0_ksf_em_accounts.email_address` for the receiving account | `match_method = 'account_self'`, no person created — this is **our own** address (requirement 4's "the support team's own email address") |
| R2 | Exact match on `0_crm_persons.email` (normalised), `inactive = 0` → exactly 1 | `exact_email`, confidence `1.00` |
| R3 | Same, but `inactive = 1` | **do not match**; treat as `none` and create (see §5.1) |
| R4 | Sub-address-stripped match, if enabled | `subaddress_stripped`, confidence `0.60` |
| R5 | Exact match → **more than one** person | `ambiguous`, `person_id = NULL`, `candidates = [ids]`, requires triage (§6) |
| R6 | No match | **create** a `crm_persons` row (§5.1), `match_method = 'created_new'`, confidence `0.90` (high confidence the *person row* is right; the identity is unverified) |

Only after `person_id` is determined is `debtor_no` derived (§3.1). Note R2–R4
deliberately run against `crm_persons` alone — a person can be known without having a
debtor, and that is a valid, useful outcome.

### FR-EM-001-03-3 — Creation of an unmatched person (match-or-create)

When R6 fires, create via `add_crm_person()`:

| Parameter | Value |
|---|---|
| `$ref` | a generated ref, **unique** (core has `KEY ref`, not `UNIQUE`) |
| `$name` | the display name, else the local-part, else the address — `VARCHAR(60)`, truncate |
| `$email` | the address — **`VARCHAR(100)`, truncate at 100** |
| `$notes` | a provenance marker, e.g. `Created from inbound email #<id> (<message-id>)` |
| `$cat_ids` / `$entity` | **`null`** — no `crm_contacts` row |

**The new person is unlinked.** It has no `crm_contacts` row, therefore no debtor,
therefore no financial exposure. It is visible and linkable by a user later via
`get_person_contacts()` / `add_crm_contact()`.

**The system shall NOT auto-create a `debtors_master` row.** Creating a *financial
customer record* from an inbound email is a credit and exposure decision, not a
data-capture decision. **See open question Q2.**

### FR-EM-001-03-4 — Multiple matches

When more than one `crm_persons` row shares the address (common: a shared household
address, or one person linked as both customer and supplier):

- The system **MUST NOT** auto-select. The current `LIMIT 1` with no `ORDER BY` is
  non-deterministic and must be replaced.
- Set `person_id = NULL`, `is_resolved = 0`, `match_method = 'ambiguous'`,
  `match_confidence` = `1.00 / candidate_count` (or a documented decay), and store
  **all** candidates in `candidates`.
- The email **is still persisted and still usable.** Ambiguity in addressee
  resolution must never block capture — that would defeat BR-EM-001.
- The inbox UI surfaces ambiguous addressees for triage; triage sets `person_id`,
  optionally `add_crm_contact('customer','general',<debtor>,<person_id>)`, and sets
  `is_resolved = 1`.

### FR-EM-001-03-5 — No match at all beyond creation

If person creation is disabled by policy, or fails, the addressee row is still
written with `person_id = NULL`, `match_method = 'none'`, `is_resolved = 0`.
**The email is always persisted.**

### 5.1 Inactive persons

`crm_persons.inactive = 1` means the person is retired. Matching an inbound email to
a retired person silently attributes new correspondence to someone who may have
left. Recommendation: **skip inactive persons in R2/R4** and record
`match_method = 'none'` with a note, so the message is still captured but visibly
unattributed. If the business prefers otherwise (e.g. an archive mailbox), this is a
one-line policy change.

## 6. The four links requirement 4 demands

On a message from `alice@acme.com` to `support@ksfraser.com` copying `bob@acme.com`:

| # | Required link | Where it lives |
|---|---|---|
| 1 | **The sender's contact** | `0_ksf_em_addressees` row, `role='from'`, `person_id` + `contact_id` |
| 2 | **That contact's associated debtor** | same row, `debtor_no`, derived via `crm_contacts(type='customer')` |
| 3 | **The support team's own email address** | `0_ksf_em_addressees` row, `role='to'`, `match_method='account_self'` — it resolves to `0_ksf_em_accounts`, **not** to a person. It is recorded, not personified |
| 4 | **Every other recipient, incl. Cc and Bcc** | one row per addressee for `to`, `cc`, `bcc`, each with its own `person_id` |

Additionally, the email row itself carries the **resolved case debtor**
(`0_ksf_em_inbound_emails.debtor_no`, already present), taken from the `from`
addressee — the business context of the message. This is the value a ticket or
invoice would use.

**Note on "the support team's own email address":** the account row
(`0_ksf_em_accounts`) already has `email_address`, `debtor_no` and `contact_id`
columns, so the team's own address can optionally be tied to an FA user or an
internal person. Verified live: 1 account, `test@ksfraser.com`, with `debtor_no` and
`contact_id` both NULL.

## 7. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | An unknown sender is captured, and exactly one new `0_crm_persons` row exists with that email and **no** `crm_contacts` row. |
| AC2 | A sender already linked via `add_crm_contact('customer','general',3,<pid>)` resolves to that exact `person_id` **and** `debtor_no = 3`. |
| AC3 | Two persons sharing one email yield `person_id IS NULL`, `match_method='ambiguous'`, and `candidates` listing both — and **no** `0_debtors_master` query is ever issued. |
| AC4 | An inactive person is not auto-matched. |
| AC5 | The `To` address matching the account's `email_address` yields `account_self` and creates no person. |
| AC6 | A message with 1 From, 2 To, 3 Cc produces **6** addressee rows. |
| AC7 | `process_inbound_email()` completes on a stock install without a DB error (the §3 defect is gone). |
| AC8 | A 120-character email address is truncated to 100 for `crm_persons.email` without error, with the full value retained in `0_ksf_em_addressees.address`. |
| AC9 | Resolution is deterministic across 100 repeated runs. |

## 8. Performance

`0_crm_persons.email` has **no index** (verified) and `0_ksf_em_accounts` is tiny, so
R1 is trivial and R2–R5 are full scans of `crm_persons`.

**Requirement:** EmailManager shall add an index on `0_crm_persons(email)` via its
own `sql/` upgrade file, guarded by an information_schema check. This is an
`ALTER TABLE` on an **FA core table** and therefore needs the org's explicit
approval. Until then, resolution cost is O(contacts) per addressee — acceptable at
current scale (1 person row), not at scale. **Flagged, not silently assumed.**

## 9. Open questions specific to this FR

| # | Question |
|---|---|
| **Q2** | Should an unknown sender ever be auto-created as a **debtor/customer**? **Recommend: no** — unlinked person only. |
| **Q6** | There is no `crm_categories` row for a support/case contact type. Should one be registered (via `0_ksf_crm_contacts`'s `retag_contact_types.sql` convention) so support contacts are distinguishable? |
| **Q11** | Enable sub-address (`+tag`) stripping? **Recommend: yes, at reduced confidence**, off by default. |
| **Q12** | Approve adding an index to `0_crm_persons.email`? |
| **Q13** | Which contact store is authoritative — see §10. |

## 10. Fork in the road: two contact stores exist

**This is the most important unresolved decision in this document.**

| | FA core `0_crm_persons` + `0_crm_contacts` | `0_ksf_crm_contacts` (ksf_FA_CRM) |
|---|---|---|
| Shape | person + xref `(person_id, type, action, entity_id)` | flat: `debtor_no` + `email` directly |
| Verified live rows | **1 person, 2 contacts** | **0 rows** |
| Debtor link | indirect, via `type='customer'`, `entity_id=debtor_no` | **direct FK column** |
| Email index | **none** | `KEY idx_debtor_no`, `KEY idx_is_primary` — no email index either |
| Email column width | `VARCHAR(100)` | `VARCHAR(100)` |
| Used by FA core UI | **yes** (`get_crm_persons()` is core API) | no |
| Extensibility | `crm_categories` allows new type/action pairs | fixed columns |
| Existing inbound code | `find_contact_by_email()` (correct, joins properly) | `EmailImportService` — **queries a table name that does not exist** |

`EmailImportService::findContactByEmail()` targets `TB_PREF . "fa_crm_contacts"`, but
`ksf_FA_CRM/sql/ksf_crm_contacts.sql` creates **`0_ksf_crm_contacts`**. Verified live:
`0_fa_crm_contacts` **does not exist**. The CRM's contact DAO is therefore broken in
the same way EmailManager's debtor lookup is.

**Recommendation: use FA core `crm_persons`/`crm_contacts`.** It is the model FA
itself defines and renders, it holds the only real data, it is extensible through
`crm_categories`, and `EmailImportService` must be retired regardless. But the
`ksf_FA_CRM` store is a defensible alternative with a *direct* debtor link, and
choosing it would avoid the (politically sensitive) core-table index. **This needs
the user's decision — Q13.**

## 11. Unverified

| Item | Status |
|---|---|
| Production FA schema — whether a downstream install added `debtors_master.email` | **[UNVERIFIED]** — verified absent on the integration DB and absent from every `.sql` in the tree; a manual production ALTER cannot be ruled out |
| Whether `crm_persons.ref` is unique in production | **[UNVERIFIED]** — core defines `KEY ref`, not `UNIQUE`; generated refs must be collision-safe regardless |
| Whether ksf_FA_CRM's `0_ksf_crm_contacts` is populated in UAT/prod | **[UNVERIFIED]** — empty on integration |

## 12. Related

- [BR-EM-001](./BR-EM-001-inbound-email-capture.md) §4 items 3 and 4
- [UC-EM-001](./UC-EM-001-support-request.md) — the worked end-to-end example
- [FR-EM-001-01](./FR-EM-001-01-message-persistence.md)
- [Inbound_Email_Architecture.md](./Inbound_Email_Architecture.md)