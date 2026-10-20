# Contact-Ambiguity Decision Review — `ksf_FA_*` / `ksf_*` contact data

**Date:** 2026-10-19
**Status:** **decision paper — nothing has been implemented, no source file was modified**
**Companion (evidence):** [`Contact_Access_Inventory_2026-10.md`](./Contact_Access_Inventory_2026-10.md) — 144 contact-access sites across 46 repositories
**Companion (table provenance):** [`Table_Naming_Audit_2026-10.md`](./Table_Naming_Audit_2026-10.md)
**Governing decision:** `AGENTS_ARCH.md` §12.2 — *Native FA data access: the shared contact resolver* (owner decision, 2026-10)
**The artefact being ruled on:** `ksfraser\FrontAccounting\Common\ContactResolver\Contract\ContactResolverInterface` — `ksf_FA_Common/src/ContactResolver/` (7 methods, 3 implementations, 7 hook operations)

This document is written for the **owner**, who will rule on each ambiguity. It is
not an implementation plan. Each section states the competing definitions with
verified `file:line` evidence, who is affected, what breaks under each reading, a
recommended ruling with its cost, the alternative and its trigger condition, and
whether the ruling can safely be made now or needs a data migration later.

---

## 0. How to read this

### 0.1 The eleven ambiguities and where the inventory records them

The inventory's §7 lists **ten** numbered ambiguities (`7.1`–`7.10`). The eleventh
is not in §7: it is the **debtor/account seam** decision, which the inventory
records twice outside §7 — in §5.1 (*"This is a contract decision, not a migration
detail"*) and in §8 (*"Decision needed: either a second seam for the debtor record,
or the resolver grows a debtor accessor"*). It is the largest bucket in the estate
(32 sites, 19 repositories) and it is the one that changes the resolver contract
most. It is included here as ambiguity **4**.

Two adjacent open contract questions from the inventory's §8 ride with it and are
recorded in §4.4 rather than as separate rulings: *"list all persons, including
relation-less ones"* and *"category **names**, not just ids"*.

| # | This review | Inventory | Short name | Already settled? |
|---|---|---|---|---|
| 1 | §1 | §7.1 | "contact" = person / relation / type | — |
| 2 | §2 | §7.2 | "customer" = account or person | partly (§6.1 of FR-CRM-007-002) |
| 3 | §3 | §7.3 | two overlapping seams (+ two more found) | **conflicts with an APPROVED FR** |
| 4 | §4 | §5.1 + §8 | the debtor/account seam (**the eleventh**) | — |
| 5 | §5 | §7.4 | branch vs customer contact | — |
| 6 | §6 | §7.7 | "employee" — two models | **mostly settled** (FR-CRM-007-002 §6.3) |
| 7 | §7 | §7.8 | four names for "lead" | **settled** (FR-CRM-007-002 §3.3) |
| 8 | §8 | §7.5 | "primary contact" has no FA representation | — |
| 9 | §9 | §7.6 | contact roles lose their defaults | — |
| 10 | §10 | §7.9 | two Notes implementations | — |
| 11 | §11 | §7.10 | inactive-person semantics | de facto, needs ratifying |

### 0.2 The resolver contract as it stands

`ksf_FA_Common/src/ContactResolver/Contract/ContactResolverInterface.php` declares
exactly seven methods:

| Method | Line | Shape |
|---|---|---|
| `findById(int $personId): ?Contact` | :61 | one person by `0_crm_persons.id` |
| `findByEmail(string $email, bool $includeInactive = false): array` | :76 | every person matching an address |
| `findByCustomer(string $debtorNo, ?string $action = null): array` | :87 | the **contacts of** a debtor |
| `findByEntity(string $type, string $entityId, ?string $action = null): array` | :99 | the contacts of any entity |
| `findContactById(int $contactId): ?Contact` | :112 | one `0_crm_contacts` relation row |
| `listContactCategoryIds(int $personId): array` | :123 | `0_crm_categories.id` values |
| `search(string $query, int $limit = 20, bool $includeInactive = false): array` | :134 | name / email / phone search |

Three implementations: `FaContactResolver` (FA runtime, native functions only —
`FaContactResolver.php:67`), `InMemoryContactResolver` (tests / standalone), and
`ContactResolver` (front door: `ksf_contact_resolve` hook first, fallback second —
`ContactResolver.php:49`, `Contract/ContactResolverHookContract.php:51`).

**What the contract deliberately does not have**, verified by reading it in full:
no debtor/account accessor, no `findByRef()`, no `findByType()`, no way to list a
person's *relation rows* (`listContactCategoryIds()` returns **category** ids, not
relation ids — the interface says so explicitly at :114-118), no primary-contact
flag, and no write methods (though `InMemoryContactResolver` implements
`addPerson()` at :63 and `addContact()` at :81 — writes the contract does not
declare).

### 0.3 Two failure modes, and they are not the same

Every "what breaks" below is classified as **silent** or **loud**. The estate has
a documented history of silent failures, so this distinction is the most important
thing to carry out of this document. Three distinct mechanisms, all verified:

| Mechanism | Behaviour on a bad table / column | Source |
|---|---|---|
| `db_query($sql, "message")` | **LOUD.** `check_db_error()` → `display_db_error()` → `end_page(); exit;`. The page ends with a DB error. | `FA/2.4.3/includes/db/connect_db_mysqli.inc:88-90`; `includes/errors.inc:225-250` |
| `db_query($sql)` (no message) | **SILENT.** `db_query()` returns `false`; the error check never runs. Reads come back empty, writes go nowhere. | `connect_db_mysqli.inc:88-90` — *"check_db_error() only fires when the caller passes a message"* |
| `$db->query($sql)` (raw `mysqli`) | **SILENT.** `$db` is a `mysqli` handle (`connect_db_mysqli.inc:32`); `mysqli_query` returns `false`; `db_fetch(false)` warns and the loop ends → an **empty list**. | `connect_db_mysqli.inc:32`; module code, e.g. `ksf_FA_Roster/includes/roster_db.inc:65` |

`frindly_db_error()` (`includes/errors.inc:214-223`) only special-cases
duplicate-key errors, so a missing-table or missing-column error under the first
mechanism **does** print the message.

**This produces a correction to the inventory, which stated that the three
`debtors_master WHERE email` lookups "fail silently and return nothing".** They do
not. All three pass an error message and therefore fail **loudly** — the page dies
with a DB error:

* `ksf_FA_Customer/src/Customer/Services/CustomerService.php:59` — `db_query($sql, 'Could not query customer by email')`
* `ksf_WP_CustomerPortal/ksf-customer-portal.php:205` — `db_query($sql, "Could not find debtor")`
* `ksf_WP_CustomerPortal/includes/services/class-ksf-woo-sync.php:264` — `db_query($sql, "Could not find debtor")`

The **silent** ones are different: `ksf_FA_AsteriskPBX/includes/asterisk_db.inc:125`
(`$db->query`), `ksf_FA_CRM/includes/EmailImportService.php:134,142`
(`db_query($sql)` with no message), and `ksf_Marketing/src/Ksfraser/Marketing/LeadScoring.php:29,75`
(`db_query($sql)` with no message). The practical consequence is the opposite of
what the inventory assumed: the *loud* sites are already visible to users and are
the easy ones to find; the *silent* sites are the dangerous ones.

### 0.4 What is already settled — do not re-open these

| Question | Settled by | Date | Effect on this review |
|---|---|---|---|
| Which contact store is authoritative? | `AGENTS_ARCH.md` §12.2 | 2026-10 | FA's `0_crm_persons` + `0_crm_contacts` + `0_crm_categories`. `0_ksf_crm_contacts` is **deprecated**: *"Do not use it, do not read it, do not write it, do not migrate data into it, and do not re-create it."* This **closes** open question **Q13** in `Requirements/FR-EM-001-03-addressee-resolution.md:312,314-339`. |
| Must modules go through FA's native functions? | `AGENTS_ARCH.md` §12.2 | 2026-10 | *"Use NATIVE FA FUNCTION CALLS to access native FA data."* Applies to every FA core table. |
| Must a module go through the shared resolver? | `AGENTS_ARCH.md` §12.2 | 2026-10 | *"a module must go through the contact resolver … it must not query a contact table itself."* |
| May the seam be gated on another module's activation? | `AGENTS_ARCH.md` §12.2 | 2026-10 | **No.** *"A shared seam must never be gated on another module's activation."* This is the constraint that decides ambiguity 6. |
| The debtor is derived **through** the contact, never by querying a debtor's email | `Requirements/FR-EM-001-03` §3.1 | 2026-10-11 | *"The contact is the email authority. The debtor is derived through the contact."* Decides half of ambiguity 2 and half of ambiguity 4. |
| A retired (inactive) person is not an email match | `Requirements/FR-EM-001-03` §5.1, R3 (:197) | 2026-10-11 | Confirms the resolver's existing default. See ambiguity 11. |
| I/F/B classification belongs to the **debtor**, not the person | `ksf_FA_CRM/ProjectDcs/BR-CRM-009` §"The correction" | 2026-09 | Confirms that "account" and "person" are different subjects with different attributes. See ambiguity 2. |
| What is a lead? | `ksf_FA_CRM/ProjectDcs/FR-CRM-007-002` §3.3 | 2026-09 (APPROVED) | See ambiguity 7 — **already answered**. |
| HRM's employee identity | `ksf_FA_CRM/ProjectDcs/FR-CRM-007-002` §6.3 | 2026-09 (APPROVED) | See ambiguity 6 — **mostly answered**. |

### 0.5 Corrections to the inventory found while verifying

Verified against the files, not against the inventory's prose:

1. **§7.2 / §8 — the three debtor-by-email lookups are loud, not silent.** See §0.3.
2. **§7.10 — `ksf_FA_CRM`'s `ContactOptionsService` already excludes inactive people by default.** `src/FrontAccounting/CRM/Service/ContactOptionsService.php:31,60,78` default `$activeOnly = true`; the filter is applied at :102. It *can* list all (`:154` honours an `active_only` option), but the default agrees with the resolver. The real gap for the CRM picker is different and worse — see **ambiguity 2** below.
3. **§7.3 — the `fa-classes` repositories are not "a second path to the same data"; they are the *only* path that exposes three things the resolver does not.** `CrmPersonRepository::findByRef()` and `findActive()` and `CrmContactRepository::findByPerson()` / `findByType()` have no resolver equivalent. See **ambiguity 3** below.
4. **§7.7 — the estate's ten `0_hr_employees` readers are not "pointed at a table that will never be populated"; they are pointed at a table that never existed, and their pickers therefore return empty, so their own `employee_id` columns hold no valid ids.** See **ambiguity 6** below.
5. **§7.8 — the four "lead" names are not four competing concepts. Three are the same concept under three wrong table names; the fourth (`0_marketing_contacts`) is a marketing contact, not a lead.** See **ambiguity 7** below.
6. **§7.9 — `ksf_FA_Notes`'s old implementation is not dead code.** `includes/links_db.inc:9` `require_once`s it, and the file's own header (:5-6) says it *"exists for modules that expect to include('links_db.inc') separately."* It is an advertised integration point, currently with no consumer in the estate.
7. **§8 — there are a **fourth** and **fifth** contact seam, not two.** See **ambiguity 3** below.
8. **§4 — a sixth failure class the inventory does not catalogue: five `0_crm_persons`
   sites query `first_name` / `last_name`, columns FA's person table does not
   have.** FA's person table has `name` and `name2`
   (`FA/2.4.3/sql/alter2.3.sql:190-208`). The CRM's flat vocabulary comes from its
   own retired table `0_ksf_crm_contacts`, which declares `first_name` /
   `last_name` (`ksf_FA_CRM/sql/ksf_crm_contacts.sql:12-13`). The contaminated
   sites are `ksf_FA_CRM/includes/crm_relationships_db.inc:60` and `:125`,
   `ksf_FA_CRM/pages/contact_relationships.php:121-122`,
   `ksf_FA_CRM/pages/life_events.php:104`, and
   `ksf_FA_CRM/pages/person_account_roles.php:126`. All five use
   `db_query($sql, "…")` with a message, so they fail **LOUD** — but the
   inventory classifies the same files as merely "HAND_ROLLED — FA core table,
   reached by raw SQL; `get_crm_person()` covers it", which understates the
   defect: they do not merely re-implement a function, they address columns
   that do not exist. `ksf_FA_CRM/pages/org_chart.php:127-128` shows the estate
   knows better — it uses `p_a.name` / `p_b.name` correctly.
9. **§7.7 — the estate moved while this review was being written.** Between
   20:54 and 21:06 on 2026-10-19, seven modules replaced `0_hr_employees` with
   module-local employee directories (`ksf_FA_Leave` `320f48c`, `ksf_FA_Performance`
   `e4207bc`, `ksf_FA_Roster` `d53cd03`, `ksf_FA_Teams` `f7b73c8`,
   `ksf_FA_Timesheets` `c5f481f`, `ksf_FA_Training` `0a6c08a`,
   `ksf_FA_TravelExpense` `394a2ea`), and `ksf_FA_ProjectManagement` has an
   uncommitted change to the same effect. The inventory's §7.7 no longer
   describes the tree. See **ambiguity 6** below.

---

## 1. Ambiguity 1 — "contact" means three different things

### The competing definitions

**(a) A person** — one row of FA's `0_crm_persons`
(`FA/2.4.3/sql/alter2.3.sql:190-208`: `id, ref, name, name2, address, phone, phone2,
fax, email, lang, notes, tmp_id, tmp_class, inactive`). This is what the resolver's
`Contact` value object carries (`ksf_FA_Common/src/ContactResolver/Contact.php:39-117`).

**(b) A person↔entity relation** — one row of `0_crm_contacts`
(`alter2.3.sql:211-219`: `id, person_id, type, action, entity_id`). The resolver
exposes it as a *second id on the same value object*: `Contact::getId()` is the
person id, `Contact::getContactId()` is the relation id (`Contact.php:124,225`), and
the interface warns at :102-110 that they *"are different numbers in different tables
and must not be confused."*

**(c) A contact *type*** — a **name**, not a record. `ksf_FA_Common`'s own
`0_ksf_contact_types` table (`ksf_FA_Common/sql/install.sql:16-23`) has columns
`name, label, module, description, created_at` and **no id of any person**;
`src/ContactType/ContactTypeRegistry.php:36` names it, :133 inserts
`INSERT IGNORE` rows of name/label/module/description, :247-255 creates the table.
Its own comment calls the rows *"Machine name (e.g. fa_user, employee, resource,
team)"*. The table's own `COMMENT` is *"Platform-level contact type definitions"*.

**The collision is real and is not hypothetical.** `ksf_FA_Common` ships **two
sibling namespaces** that both use the word "contact":
`ksfraser\FrontAccounting\Common\ContactResolver\` (people) and
`ksfraser\FrontAccounting\Common\ContactType\` (type names). Seven repositories
read or write `0_ksf_contact_types`:

| Repository | Where | Types registered |
|---|---|---|
| `ksf_FA_Common` | `sql/install.sql:16`; `src/ContactType/ContactTypeRegistry.php:36` | creates the table |
| `ksf_FA_Common_repo` | `sql/install.sql:16,26-33`; `src/ContactType/ContactTypeRegistry.php:34` | seeds `fa_user`, `crm_contact`, `resource`, `ad_hoc` |
| `ksf_FA_CRM` | `sql/retag_contact_types.sql:3-5` | `crm_contact`, `lead`, `opportunity` |
| `ksf_FA_HRM` | `sql/retag_contact_types.sql:3-5` | `employee`, `team`, `job_applicant` |
| `ksf_FA_RBAC` | `sql/retag_contact_types.sql:3`; `hooks.php:116-135` | `fa_user` |
| `ksf_FA_Assets` | `sql/retag_contact_types.sql:3` | `resource` |
| `ksf_FA_Calendar` | `sql/retag_contact_types.sql:3-4`; `hooks.php:61-70` | `invitee`, `ad_hoc` |

And FA has a **third** meaning of the same word in the same three tables:
`0_crm_contacts.type` / `0_crm_categories.type` is a *foreign key to a category
row* (`alter2.3.sql:214`, `:163`), seeded with 12 values
(`sql/en_US-new.sql:427-439`): `cust_branch`, `customer`, `supplier` × `general`,
`order`, `delivery`, `invoice`. Three modules add their own:
`ksf_FA_RBAC/sql/install.sql:110-115` (`('user','general','System User',…)`),
`ksf_FA_HRM/sql/crm_categories.sql:5-8` (`employee/general`, `employee/emergency`,
`employee/dependent`).

So the word "contact type" currently denotes at least **three** different things:
an FA category (`crm_categories.type`), a platform actor-type label
(`ksf_contact_types.name`), and a `crm_contacts.type` value.

### Who is affected

* **8 sites / 7 repositories** on the `0_ksf_contact_types` side (the inventory's intent **I10**).
* The entire resolver surface: every one of the 7 contract methods and all 7 hook operations (`ContactResolverHookContract.php:67-85`) use the word "contact" for a **person**, and `findByEntity(string $type, …)` takes a parameter named *type* that means FA's `crm_contacts.type` — a **third** sense of "type" in the same call.
* `Contact::getType()` / `getAction()` (`Contact.php:194,204`) return FA's category type/action.
* Indirectly **all 144 inventory sites**, because a module author choosing between "the contact" and "the contact type" has no written rule.

### What breaks if we pick wrong

* **Silent wrong answer** — the most likely failure. A module needs a *label* for a
  filter and reaches for the resolver, which returns a **person**; or a module
  needs a person and reaches into `ContactTypeRegistry`, which returns a **string**.
  Neither errors. `ContactTypeRegistry::getAll()` returns labels with no person
  attached, so a filter built on it matches nothing.
* **Loud error** — if a resolver method were extended to "resolve a contact type",
  it would have to return either a person or a label; a type mismatch in a
  `findByEntity('employee', $id)` call would surface as a confusing empty list
  rather than a type error.
* The name collision also creates a **false equivalence**: the `employee` row in
  `0_ksf_contact_types` and the `employee/general` row in `0_crm_categories` look
  like the same thing. They are not — one is a label owned by HRM, the other is an
  FA category row that gates what a `crm_contacts` row of type `employee` means.

### Recommended ruling

> **In this estate, "contact" means a person, and only a person.** A "contact
> relation" is the `0_crm_contacts` row and is always called a *relation* or a
> *link*. A "contact type" is always called a **category** when it means FA's
> `crm_categories`, and an **actor type** when it means `0_ksf_contact_types`.

Three concrete actions follow:

1. **Rename the namespace and the table of the type registry** so it can never be
   confused with a person: `ksfraser\FrontAccounting\Common\ContactType\` →
   `…\ActorType\`, and `0_ksf_contact_types` → `0_ksf_actor_types`. The
   inventory already proposes the table rename (`Contact_Access_Inventory_2026-10.md:468`).
2. **Rename the resolver's `type` parameter** to `categoryType` (or `contactType` →
   `entityType`) in `ContactResolverInterface::findByEntity()` and in
   `ContactResolverHookContract::OP_BY_ENTITY`'s argument key, so the wire format
   says which of the three senses it means.
3. **Reserve the word "type" for FA's `crm_categories.type`** — the only sense
   that appears as a column in FA core.

**Cost:** a rename of one namespace and one table in `ksf_FA_Common` + the 6
consumer repos, plus the 7 `retag_contact_types.sql` files and the `hooks.php`
registration calls in RBAC (:116-135), CRM, HRM, Assets, Calendar. The table holds
**labels only**, so the rename is a `RENAME TABLE` plus a namespace move — **no
data migration of substance**, but it *is* a schema change to a table with a live
`retag`/`unregister` lifecycle, so it must be sequenced against module activation.

### The alternative, and when to pick it instead

**Alternative:** keep both names and add a written glossary to `AGENTS_ARCH.md`
that forbids the ambiguous uses, without renaming anything.

**Pick this when** the owner wants zero schema churn before UAT and the glossary
is enough to stop new misuse. The cost of *not* renaming is permanent: the
collision stays in the code, and the next module author repeats the mistake. The
inventory ranked this ambiguity **highest** for danger (`Contact_Access_Inventory_2026-10.md:459`).

### Can it be ruled now?

**Yes — with one caveat.** The *ruling* can be made now and it costs nothing to
apply to code. The **table rename** touches a live table with an
activate/deactivate lifecycle (`ContactTypeRegistry::unregisterModule()` at
`ContactTypeRegistry.php:163`), so the rename is best done as part of the
migration wave, not as a standalone pre-UAT change. **No data migration** is
implied: the table holds labels, not records.

### Resolver contract impact

**Yes, small.** `findByEntity(string $type, …)` → `findByEntity(string $entityType, …)`
is a parameter rename; PHP has no named arguments before 8.0 and the estate's floor
is PHP 7.3 (`AGENTS_ARCH.md` §1), so **positional callers are unaffected** — this
is a documentation and hook-wire change, not a signature change. The hook
argument key `'type'` → `'entity_type'` in `ContactResolverHookContract::OP_BY_ENTITY`
*is* a wire change: any external listener reading `$data['arguments']['type']`
must be updated. No listener exists in the estate today.

---

## 2. Ambiguity 2 — "customer" means the account *or* the human being

### The competing definitions

**(a) The account (a billing record).** `0_debtors_master` — sixteen columns
(`FA/2.4.3/sql/en_US-new.sql:585-605`): `debtor_no, name, debtor_ref, address,
tax_id, curr_code, sales_type, dimension_id, dimension2_id, credit_status,
payment_terms, discount, pymt_discount, credit_limit, notes, inactive`.
**No `email` column. No `phone` column.** It has a `name` — a display name — which
is why 32 sites across 19 repositories reach for it to render a customer's name.

**(b) The human being.** A `0_crm_persons` row, reached from the account through
`0_crm_contacts` where `type = 'customer'` and `entity_id = <debtor_no>`. That
pairing is FA's own: `FA/2.4.3/sales/manage/customers.php:126` calls
`add_crm_contact('customer', 'general', $selected_id, $pers_id)`.

**Four sites conflate them by asking the account for a column it does not have:**

| Repository | Site | Statement | Actual failure |
|---|---|---|---|
| `ksf_FA_Customer` | `src/Customer/Services/CustomerService.php:59` | `SELECT * FROM debtors_master WHERE email = …` | **LOUD** — `db_query($sql, 'Could not query customer by email')` |
| `ksf_WP_CustomerPortal` | `ksf-customer-portal.php:205` | `SELECT debtor_no FROM debtors_master WHERE email = … LIMIT 1` | **LOUD** — `db_query($sql, "Could not find debtor")` |
| `ksf_WP_CustomerPortal` | `includes/services/class-ksf-woo-sync.php:264` | same | **LOUD** — `db_query($sql, "Could not find debtor")` |
| `ksf_FA_AsteriskPBX` | `includes/asterisk_db.inc:125` | `SELECT debtor_no, name, phone FROM debtors_master WHERE phone = …` | **SILENT** — `$db->query()`; empty `customers` list |

`0_debtors_master` has no `email` and no `phone`; **no module adds one** — verified
against every `FA/2.4.3/sql/alter*.sql` and every `fa_modules/*/sql/*.sql`
(also recorded at `Requirements/FR-EM-001-03:100-116`).

**One module already documents the correct inversion.** `ksf_FA_EmailManager/includes/em_db.inc:260-283`:

```
find_debtor_by_email()  →  SELECT c.entity_id FROM crm_contacts c
                            INNER JOIN crm_persons p ON p.id = c.person_id
                            WHERE c.type = 'customer' AND p.email = … AND p.inactive = 0
```

with the docblock at :242-259 spelling out why the account cannot be asked
directly. Its sibling `find_contact_by_email()` (:286-296) returns
`c.id` — the **relation** id, not the person id, a distinction the
requirements document calls out explicitly (`Requirements/FR-EM-001-03:86-89`).

### Who is affected

* **32 sites / 19 repositories** read the *account* record (the inventory's intent **I1**) — the largest single bucket.
* **11 sites / 6 repositories** want "the person behind a customer" (**I2**).
* **8 sites / 6 repositories** want a lookup *by email* (**I5**) — of which the 3 broken debtor-by-email sites above are the ones that are visibly broken today.
* **8 sites / 4 repositories** in `ksf_FA_CRM` alone render a debtor's name via raw SQL: `pages/dashboard.php:116`, `Repository/CommunicationsRepository.php:101`, `Repository/ContactsRepository.php:111`, `Repository/CustomersRepository.php:47,68`, `Repository/LeadsRepository.php:98`, `Repository/MeetingsRepository.php:116`, `Repository/OpportunitiesRepository.php:111`, `Repository/QuotesRepository.php:132`, `Service/DebtorOptionsService.php:102`.

### What breaks if we pick wrong

* **Silent wrong answer (the account as a person).** A module that resolves a
  "customer" to a `debtors_master` row and then reads `email`/`phone` off it gets
  a field that does not exist — or, worse, a module that treats the *account name*
  as a *person name* renders "ACME Corporation" in a "contact name" column. The
  second failure is invisible: no error, wrong label.
* **Silent wrong answer (the person as the account).** A module that resolves a
  `0_crm_persons` row and treats it as a debtor has no `debtor_no`, no
  `credit_limit`, no balance — and if it joins `debtors_master` on `name`, it
  fans out across every homonymous account.
* **Loud error.** The three `WHERE email` sites above. These are the *easy*
  failures: a user sees a DB error page. They should be fixed first precisely
  because they are visible.

### Recommended ruling

> **"Customer" is always the account** (`0_debtors_master`, keyed by `debtor_no`).
> A human being behind an account is a **contact** (a `0_crm_persons` row linked
> by a `0_crm_contacts` row of `type = 'customer'`). The link direction is
> *account → contacts*, never *contact → account*, and never *"customer" meaning
> both*.

This is **already the direction of the approved requirements**:
`Requirements/FR-EM-001-03` §3.1 (*"The contact is the email authority. The
debtor is derived through the contact."*) and
`ksf_FA_CRM/ProjectDcs/BR-CRM-009` (*"I/F/B is a property of `debtors_master`
rows, **not** of `crm_persons` rows"*). The ruling ratifies them; it does not
invent them.

The rule in force should be the resolver's own, which is already correct:
`findByCustomer(string $debtorNo)` returns the **contacts of** an account
(`FaContactResolver.php:141-144` → `findByEntity('customer', $debtorNo, …)`).
The name is misleading — `findByCustomer` sounds like "find the customer" and
means "find the customer's contacts". Rename it to
`findContactsOfCustomer()` (or `findAccountContacts()`) at the same time as the
account accessor in ambiguity 4, so the two names cannot be confused.

**Cost:**
* The **naming** part is free — a method rename on the contract, and it is
  source-compatible only for callers using positional arguments.
* The **behavioural** part costs **19 repositories**: the 32 `0_debtors_master`
  sites either call FA's `get_customer()` / `get_customer_name()` /
  `get_customer_details()` / `get_customer_by_ref()` (all native, all available —
  `AGENTS_ARCH.md` §12.2's function table), or go through a new account accessor
  (ambiguity 4). Nineteen repositories each hand-writing `SELECT … FROM
  0_debtors_master` is the duplication §12.2 exists to stop.
* **No data migration.** The ambiguity is a vocabulary and access-path problem,
  not a data problem.

### The alternative, and when to pick it instead

**Alternative:** treat "customer" as a polymorphic term meaning "either the
account or its contacts", and introduce a single call that returns whichever
layer the caller wants (e.g. `findCustomer($id)` returning a union).

**Pick this when** the majority of callers really do want "the account *and* its
people together" and the owner wants one call for a customer screen. It costs a
union return type on the contract, and it re-blurs exactly the distinction
`FR-EM-001-03` §3.1 and `BR-CRM-009` went out of their way to draw. Not
recommended: the union return type is the thing that produced the four broken
`WHERE email` queries in the first place.

### Can it be ruled now?

**Yes.** No migration, no schema change, no data dependency. It is the cheapest
ruling in the set and it unblocks ambiguity 4.

### Resolver contract impact

**Yes.** `findByCustomer()` should be renamed (see above) and an **account**
accessor added — see ambiguity 4, §4.4.

---

## 3. Ambiguity 3 — two (in fact four) overlapping contact seams

### The competing definitions

**Seam A — `ksfraser/ksf-fa-common` → `ContactResolverInterface`** (the sanctioned
one). Storage: **native FA functions only** (`FaContactResolver.php:10-15`).
Methods: `findById`, `findByEmail`, `findByCustomer`, `findByEntity`,
`findContactById`, `listContactCategoryIds`, `search`.

**Seam B — `ksfraser/fa-classes` → `CrmPersonRepository` / `CrmContactRepository`.**
Storage: **raw SQL** over `0_crm_persons` / `0_crm_contacts`
(`ksf_FA_Classes/src/FrontAccounting/Repository/CrmPersonRepository.php:13`
`protected $tableName = 'crm_persons';`; `CrmContactRepository.php:13`
`'crm_contacts'`).

**Seam C — `ksfraser/ksf_gpg` → `ksfraser\GPG\Contracts\ContactResolverInterface`**
(`ksf_GPG/src/Contracts/ContactResolverInterface.php:15`). A different interface
with a different shape: `(contactType, contactId) → email`.

**Seam D — a fourth, inline copy** in
`ksf_FA_GPG/pages/key_management.php:167-180` (`get_contact_email()`), a
hand-maintained duplicate of Seam C's table map.

Seams C and D are **both broken in the same way**: the map is

```
'customer' => 0_debtors_master, id_col debtor_no,  email_col email    ← no email column
'supplier' => 0_suppliers,      id_col supplier_id, email_col email   ← no email column
'employee' => 0_crm_persons,    id_col person_id,   email_col email   ← no person_id column
```

(`ksf_FA_GPG/src/Adapter/FAContactResolver.php:20-24`, and the same map duplicated
at `pages/key_management.php:167-180`). Verified against the schemas:
`0_debtors_master` has no `email` (`sql/en_US-new.sql:585-605`);
`0_suppliers` has no `email` — it has `contact VARCHAR(60)`, a free-text contact
*name* (`sql/en_US-new.sql:1691-1706`); `0_crm_persons`'s primary key is `id`,
not `person_id` (`sql/alter2.3.sql:191`). So **all three entries in Seam C/D's map
address a column that does not exist**, and `FAContactResolver::resolveEmail()`
passes an error message (`db_query($sql, "Could not resolve contact email for GPG")`)
— so it fails **LOUD**.

### The two seams the inventory named, side by side

| | `ksf-fa-common` (A) | `fa-classes` (B) |
|---|---|---|
| Storage | native FA functions only | raw SQL over `0_crm_persons` / `0_crm_contacts` |
| By id | `findById()` | `findById()` (`CrmPersonRepository.php:14`) |
| By email | `findByEmail()` | `findByEmail()` (`:26` — `AND inactive = 0`) |
| By entity | `findByEntity($type, $entityId, $action)` | `findByEntity($type, $action, $entityId)` — **argument order differs** |
| By ref | — | `findByRef()` (`:19`) |
| List active | — | `findActive()` (`:36`) |
| By person | — | `findByPerson()` (`CrmContactRepository.php:19`) |
| By type | — | `findByType()` (`CrmContactRepository.php:29`) |
| Writes | none (by design) | none (hazard **H2**, `ksf_FA_CRM/ProjectDcs/NATIVE-FA-CONTACTS-REFERENCE.md:333`) |

Note the **argument-order difference** on `findByEntity`: A is
`(type, entityId, action)`, B is `(type, action, entityId)`. A caller that copies
one into the other gets a query for the wrong entity **or the wrong action** — and
because `get_crm_persons()` silently falls back to `action = 'general'`
(`FA/2.4.3/includes/db/crm_contacts_db.inc:115-116`), the wrong-action case
returns a **plausible-looking wrong answer**.

### The decisive fact: two documented decisions contradict each other

`ksf_FA_CRM/ProjectDcs/FR-CRM-007-002-shared-persons-contacts-layer.md` is marked
**"APPROVED — requirements ratified 2026-09"**, and §3.1 says:

> *"**Data access goes through the `ksfraser/fa-classes` DTO/DAO layer, not raw SQL.**"*
> *"The new `PersonsRepository` is a thin **SRP translator** that composes those
> repositories … and issues **no SQL of its own** against `crm_*`."*

`NATIVE-FA-CONTACTS-REFERENCE.md:336` (hazard H5) likewise gives the mitigation
*"Use the `fa-classes` repositories (typed DTOs) instead"*.

`AGENTS_ARCH.md` §12.2 (owner decision, **2026-10**, one month later) says the
opposite:

> *"**The shared seam: a module must go through the contact resolver.** Any module
> that needs a contact must call the **shared contact resolver** in `ksf_FA_Common`
> — it must not query a contact table itself."*

**Two ratified documents mandate different seams.** The owner's decision is later
and is the governing one (the inventory's header names it "Governing decision"),
so `FR-CRM-007-002` §3.1 and `NATIVE-FA-CONTACTS-REFERENCE.md` H5 are **stale and
must be corrected** — but they are APPROVED requirements and were written
deliberately. They cannot simply be ignored; they need an explicit superseding
note.

### Who is affected

* **3 repositories vendor `fa-classes`**: `ksf_FA_CRM` (`composer.json:8`),
  `ksf_FA_DataIntegrity` (`composer.json:14`), `ksf_FA_InvoiceAllocation` (`composer.json:14`).
* **The 2 repositories that own the other two seams**: `ksf_FA_GPG` (Seams C and D),
  `ksf_gpg` (Seam C's interface).
* Every module that migrates onto the resolver later: the inventory's §6.1/§6.2
  split — **7 already depend on `ksf-fa-common`** (`ksf_FA_CRM`, `ksf_FA_Calendar`,
  `ksf_FA_HRM`, `ksf_FA_Notes`, `ksf_FA_ProjectManagement`, `ksf_FA_Square`,
  `ksf_FA_SuggestedPurchaseOrder`) and **37 need `composer require`**.
* Circular-dependency risk: `ksf_FA_DataIntegrity` vendors both `fa-classes` and
  `ksf-modules-dao` (`composer.json:14`), so making `fa-classes` depend on
  `ksf-fa-common` is a new edge in the graph.

### What breaks if we pick wrong

* **Silent wrong answer** — the "second, parallel, silently divergent path"
  the inventory names (`Contact_Access_Inventory_2026-10.md:507-509`). Concrete
  divergences already present between A and B: B's `search()` (`CrmPersonRepository.php:41-50`)
  matches `name / ref / email` and **not phone**; A's `search()`
  (`FaContactResolver.php:307`) matches `name, name2, email, phone, phone2, ref`
  — so the same search term returns different sets depending on which seam the
  module reached for. B's `findByEmail()` filters `inactive = 0`; A's takes a
  flag. B's `findByEntity()` takes `(type, action, entity)`; A takes
  `(type, entity, action)`.
* **Loud error** — if both seams are loaded and both register a class of the same
  name, a redeclaration fatal. `ksf_FA_Common` already ships a canonical
  `src/autoload.php` and the duplicate-class-load hazard is documented in
  `AGENTS.md` ("Cross-module activation hazard — duplicate ksf-fa-common class load").
  Different namespaces (`FrontAccounting\Repository` vs
  `ksfraser\FrontAccounting\Common\ContactResolver\Contract`) mean the *classes*
  do not collide today; the collision risk is at the **concept** level, not the
  class level, which is worse.
* **Loud error** — `FAContactResolver` (Seam C) fails loudly on every call
  because every column in its map is wrong.

### Recommended ruling

> **There is exactly one contact seam: `ksf-fa-common`'s `ContactResolverInterface`.**
> `fa-classes`' `CrmPersonRepository` / `CrmContactRepository` are **deprecated**
> and must be **deleted**, not delegated to. `ksf_gpg`'s and `ksf_FA_GPG`'s
> resolvers are **retired** in favour of the shared seam.

Three supporting decisions:

1. **Delete, don't delegate.** `AGENTS_ARCH.md` §12.2 already uses the word
   *retired* for `0_ksf_crm_contacts` and forbids building a replacement. The same
   treatment applies here. Delegation (`fa-classes` → resolver) would make
   `fa-classes` depend on `ksf-fa-common` — a new package edge, and it keeps
   the second seam alive as an indirection that the §12.2 rule is trying to
   eliminate.
2. **Before deleting `fa-classes`' repositories, close the three gaps** they
   currently cover and the resolver does not: `findByRef(person)`,
   `findByType(type)`, and **a way to list a person's relation rows**. The third
   is the important one: `listContactCategoryIds()` returns *category* ids, not
   relation ids — the interface says so at :114-118 — so **the resolver currently
   cannot answer "which entities is this person linked to?"** at all.
   `CrmContactRepository::findByPerson()` (`CrmContactRepository.php:19`) can.
   `CrmContactRepository::findPersonContacts()` (:31) can, and returns the
   person's name and email alongside — a shaped result the resolver's `Contact`
   already carries.
3. **Retire the GPG seams** and repoint `ksf_FA_GPG` at the shared resolver.
   This requires the **account** accessor (ambiguity 4) and the **supplier**
   accessor (`findByEntity('supplier', …)`, already on the contract) to replace
   the table map. `ksf_FA_GPG/src/Adapter/FAContactResolver.php` and
   `ksf_FA_GPG/pages/key_management.php:167-180` both go.

**Cost:**
* `ksf_FA_Classes`: delete `CrmPersonRepository`, `CrmContactRepository`, and
  their DTOs, or keep them as deprecated shims for one release. `ksf_FA_CRM`,
  `ksf_FA_DataIntegrity`, `ksf_FA_InvoiceAllocation`: drop the `fa-classes`
  dependency, or keep the dependency but stop using those two repositories.
* The resolver contract grows by **three** methods (see *The two seams the inventory named, side by side* above) and possibly by
  the account accessor (ambiguity 4). That is a **published package** —
  `ksfraser/ksf-fa-common` is on Packagist — so the contract change is a
  **major-version bump**, and every module that vendors it must re-resolve.
* **Supersede two approved documents:** `FR-CRM-007-002` §3.1 and
  `NATIVE-FA-CONTACTS-REFERENCE.md` H5 need an explicit "superseded by
  `AGENTS_ARCH.md` §12.2 (2026-10)" banner, and their `PersonsRepository`
  composition plan (§3.1) needs rewriting.
* **No data migration.**

### The alternative, and when to pick it instead

**Alternative (a):** `fa-classes` wins — the resolver is built **on** the
`fa-classes` repositories, and `ksf-fa-common` becomes a thin façade over them.

**Pick this when** the owner prefers the `fa-classes` DTOs (typed, testable,
injected-adapter) and does not want to grow the `ksf-fa-common` contract, and
**when** `ksf_fa_common`'s published-package contract can be changed without
breaking 44 consumers' `composer.lock`s. Against it: §12.2 says the resolver
*is* the seam, and `fa-classes`' repositories are raw SQL against FA core tables,
which is what §12.2 forbids.

**Alternative (b):** keep both, but mandate that **`fa-classes`' repositories
delegate to the resolver** so there is one *implementation* and two *names*.

**Pick this when** the owner wants to avoid a big-bang deletion. It costs a new
package dependency edge (`fa-classes` → `ksf-fa-common`) and the circular risk
the inventory names (`Contact_Access_Inventory_2026-10.md:437-441`), and it still
leaves a second name to reach for.

### Can it be ruled now?

**Yes** — the ruling itself is free. The *deletions* are best sequenced **after**
the resolver grows the three missing methods (ambiguity 3, "supporting decision 2"),
otherwise `ksf_FA_CRM` loses `findByPerson()` with nothing to replace it. So:
**rule now, execute after the contract change lands.** No data migration either way.

### Resolver contract impact

**Yes — the largest contract change in the set.** `+ findByRef(int|string $ref): ?Contact`,
`+ findRelationsByPerson(int $personId): Contact[]` (relation rows, not category ids),
`+ findByType(string $type): Contact[]`. Plus the account accessor from ambiguity 4.

---

## 4. Ambiguity 4 — the account is not a contact: the debtor seam *(the eleventh ambiguity)*

> The inventory's §7 lists ten ambiguities. This is the eleventh, recorded by the
> inventory in **§5.1** and in the **§8** table rather than in §7.

### The competing definitions

**(a) The resolver is about *contacts*; the account is FA's business.**
`AGENTS_ARCH.md` §12.2 lists `get_customer()`, `get_customer_name()`,
`get_customer_contacts()`, `get_customer_details()` as native functions, and the
resolver contract — read in full — has **no account accessor at all**. The
inventory says this is *"a deliberate omission (the resolver is about contacts)"*
(`Contact_Access_Inventory_2026-10.md:612`).

**(b) The account belongs in the resolver, because the *person* cannot be reached
without it.** The native relation query `get_crm_persons()` is a **comma-join**
(`FA/2.4.3/includes/db/crm_contacts_db.inc:89-91`:
`FROM crm_persons p, crm_categories t, crm_contacts r WHERE …`), i.e. an INNER
JOIN. A person with **no** contact relation is **invisible** to it. And the
resolver's own class docblock states the consequence
(`FaContactResolver.php:33-41`):

> *"FA's native CRM functions never expose `crm_contacts.entity_id` … The relation
> can therefore only be resolved **DEBTOR → CONTACTS**, never **PERSON → DEBTOR**,
> without writing SQL against an FA core table. That direction is deliberately
> absent from the contract."*

So under reading (a), **three of the estate's four broken debtor-by-email lookups
cannot be expressed through the resolver at all** — they need the inversion the
contract deliberately omits.

### Who is affected

* **32 sites / 19 repositories** — the inventory's intent **I1**, the largest bucket.
* The 3 visibly broken `debtors_master WHERE email` sites (`ksf_FA_Customer:59`,
  `ksf_WP_CustomerPortal:205` and `:264`) — which need **person → contact → debtor**.
* `ksf_FA_EmailManager/includes/em_db.inc:260-283` — the one working implementation of that inversion, which the resolver cannot replace.
* `ksf_FA_GPG` — Seam C's `'customer'` entry maps to `0_debtors_master`.
* `ksf_FA_Square/src/Services/SquareInvoiceService.php:443` — the customer's name from `0_debtors_master`.

### What breaks if we pick wrong

* **Silent wrong answer.** A migration that replaces `SELECT … FROM 0_debtors_master`
  with a resolver call **cannot be written at all** for I1 — there is no method.
  The temptation is to route I1 through `findByCustomer()` and get **contacts where
  the account was wanted**. A module rendering a customer's *name* would then show
  a *person's* name. There is no error; the screen simply shows the wrong thing.
  This is the single most likely way to get this migration wrong.
* **Loud error.** `get_customer($id)` on a non-existent id returns `false`, and
  FA's `get_customer_name()` handles it — so an I1 migration routed to FA's native
  functions is safe.
* **Silent wrong answer, second form.** If the account accessor is added to the
  resolver but implemented as a raw `SELECT … FROM 0_debtors_master` inside
  `FaContactResolver`, the resolver stops being "native functions only" and
  re-opens the §12.2 breach it was created to close — while still *looking*
  compliant to callers.

### Recommended ruling

> **Two seams, with a hard boundary: `ContactResolverInterface` resolves *people
> and their relations*; a new `AccountResolverInterface` resolves *accounts*.**
> The account accessor is added **as a separate contract**, not as extra methods
> on `ContactResolverInterface`.

Reasons:

* The boundary is not cosmetic — it is **FA's own**. `0_debtors_master` is a
  ledger account; `0_crm_persons` is a person. They have different lifecycles,
  different owners, different attributes (`credit_limit`, `balance` vs
  `email`, `phone`), and `BR-CRM-009` already treats them as different subjects
  with different attributes (I/F/B on the debtor; consent on either).
* Keeping them apart means the resolver stays true to §12.2's *"must not query a
  contact table itself"* and *"no SQL against FA core tables"* — the account
  accessor can be implemented natively (`get_customer()`, `get_customer_name()`,
  `get_customer_details()`, `get_customer_by_ref()`) and satisfy the same rule.
* **One new contract, not one new interface per concept.** `AccountResolverInterface`
  with `findById(int $debtorNo): ?Account` and `findByEmail(string $email): ?Account`
  (the latter implemented as *person → contact → debtor*, per
  `FR-EM-001-03` §3.1) covers I1 and the three broken sites in one shape.

**Cost:**
* New interface + `FaAccountResolver` in `ksf_FA_Common/src/AccountResolver/`,
  plus an `InMemoryAccountResolver` for parity and a hook operation
  (`ksf_account_resolve`) for non-FA platforms.
* **19 repositories** move their 32 `0_debtors_master` reads onto it.
* The `findDebtorByEmail()` inversion needs a person→relation→debtor walk.
  FA's native functions expose `entity_id` **only** through `get_crm_persons()`
  (which joins on `crm_categories`, so the category row must exist) — the
  resolver's `findByEntity('customer', $debtorNo)` returns the **persons**, not
  the debtor_no. So `findByEmail → debtor_no` is *not* expressible with FA native
  functions alone: **it needs the `entity_id`, which native functions do not
  return** (`FaContactResolver.php:33-39` says exactly this). The practical
  implementation is: `findByEmail($email)` → for each person, `findByEntity('customer', …)`
  → but that goes the wrong way. **The inversion must be done by `ksf_FA_Common`
  with one guarded SQL read of `0_crm_contacts.entity_id`**, which §12.2 permits
  only because *"the 'no raw SQL' rule is owned by that module, so it may make an
  exception for itself"* — the inventory's own words at
  `Contact_Access_Inventory_2026-10.md:607`. **This must be an explicit,
  documented exception, not a silent one.**
* `ksf_FA_EmailManager`'s working `find_debtor_by_email()` becomes a duplicate
  and should be retired in favour of the new seam.
* **No data migration** — this is an access-path change.

### The alternative, and when to pick it instead

**Alternative (a):** one contract. Add `findAccountById()`, `findAccountByEmail()`
to `ContactResolverInterface` itself.

**Pick this when** the owner wants the absolute minimum ceremony — one interface
to learn, one thing to inject. Cost: the resolver stops being "about contacts",
and `Contact` (the value object) would have to carry account fields, or a second
value object `Account` would have to appear in the same package anyway. The
contract grows two method families on one interface where the estate's
vocabulary has just been narrowed by ambiguity 1 and 2. **Not recommended**, but
it is the cheaper ceremony if the owner prioritises call-site brevity.

**Alternative (b):** no new contract — I1 modules call FA's `get_customer()` /
`get_customer_name()` directly, and the "account seam" is simply *"FA's functions,
called directly"*.

**Pick this when** the owner accepts that the resolver covers people only and
wants I1 handled by a straight native-function migration, with **no** new
interface. This is the cheapest possible path for the 32 I1 sites and it honours
§12.2 completely. Its cost: `ksf_FA_Customer:59` and the two WordPress sites
still need person→contact→debtor, which **no native FA function provides** — so
either those three keep hand-rolled SQL (with the §12.2 breach that implies) or
the estate accepts that they are the only exception. That exception should be
written down either way.

### Can it be ruled now?

**Yes**, but the *implementation* of `findAccountByEmail()` needs one careful
decision before it is safe: whether `ksf_FA_Common` is permitted the one raw read
of `crm_contacts.entity_id` that the inversion requires. **That is a policy
decision, not a migration.** No data migration is implied.

### 4.4 Two adjacent contract questions riding with this ruling

The inventory's §8 records two more "Decision needed" items that are not §7
ambiguities but that belong to the same contract decision. They are recorded
here so they are not lost, and they should be ruled at the same time.

**(a) The resolver cannot list people who have no contact relation.**
`findByEmail()` and `search()` both work through
`get_crm_persons(null,null,null,null,true)` (`FaContactResolver.php:292`), an
INNER JOIN — so a person with **no** `0_crm_contacts` row is invisible. That
includes every employee (§6) and every person created by the inbound-email
match-or-create flow, which *deliberately* creates an unlinked person
(`Requirements/FR-EM-001-03` §5.1: *"The new person is unlinked"*).
`ksf_FA_CRM`'s `ContactOptionsService` lists `0_crm_persons` directly and
therefore **can** see them — so the CRM's picker cannot be reproduced by the
resolver today. The inventory names the fix: *"Either `ksf_FA_Common` gains a
`listAllPersons()` that reads `0_crm_persons` directly (the 'no raw SQL' rule is
owned by that module, so it may make an exception for itself), or FA gains a
person-by-email function."* **Recommendation:** the first — a
`listAllPersons(bool $includeInactive = false): Contact[]` method, implemented in
`FaContactResolver` with the one guarded SQL read that `ksf_FA_Common` is
entitled to make. **This is the same exception the `findAccountByEmail()`
inversion needs**, so both can be authorised by one ruling.

**(b) The resolver returns category *ids* with no names.**
`listContactCategoryIds()` (`ContactResolverInterface.php:123`) returns
`0_crm_categories.id` values. `ksf_FA_RBAC/hooks.php` needs the **names** to
render a filter. The native `get_crm_categories()` /
`get_crm_category_name()` are available (`AGENTS_ARCH.md` §12.2's function
table). **Recommendation:** add `listCategories(bool $includeInactive = false):
array` returning `['id' => …, 'type' => …, 'action' => …, 'name' => …,
'description' => …]`, and/or `getCategoryName(int $id): ?string`. This also
serves ambiguity 9, where the CRM's role catalogue becomes `crm_categories`
rows — the names are then the role names.

### Resolver contract impact

**Yes.** Either `+2` methods on `ContactResolverInterface` (alternative a), or a
**new sibling contract** `AccountResolverInterface` with 2 methods (recommended).
The recommended option does **not** change `ContactResolverInterface` at all — it
adds a second contract alongside it. That is a smaller, safer break for the 44
consumers of the published package.

Plus, from §4.4: **+1** method (`listAllPersons()`) and **+1** method
(`listCategories()` / `getCategoryName()`).

---

## 5. Ambiguity 5 — an account's contact set includes its branches

### The competing definitions

`0_crm_contacts.type` distinguishes `'customer'` (`entity_id` = a `debtor_no`)
from `'cust_branch'` (`entity_id` = a **branch_code**). Three modules pick
differently:

| Module | Site | Behaviour |
|---|---|---|
| `ksf_FA_Square` | `src/Services/SquareInvoiceService.php:469-472` | tries `type = 'customer'` **first** |
| `ksf_FA_Square` | `src/Services/SquareInvoiceService.php:482-485` | falls back to `type = 'cust_branch'` **with `c.entity_id = $debtorNo`** |
| `ksf_FA_EmailManager` | `includes/em_db.inc:270-273` | filters `c.type = 'customer'` **only** — and says so in the docblock (:251-252): *"Filtering on type also stops a cust_branch/supplier row (whose entity_id is a branch or supplier number, not a debtor_no) being returned."* |
| `ksf_FA_Customer` | `src/Customer/Services/CustomerService.php:463,465` | **writes both** — `add_crm_contact('cust_branch','general',$branchId,$personId)` and `add_crm_contact('customer','general',$customerId,$personId)` |

FA's own convention is in `sales/manage/customers.php:124,126`: both relations
are written for the same person.

**The Square fallback is wrong, and it fails silently.** `cust_branch`'s
`entity_id` is a **branch_code**, not a debtor_no — `0_cust_branch`'s primary key
is `branch_code` (`FA/2.4.3/sql/en_US-new.sql:549-551`) and FA writes
`add_crm_contact('cust_branch','general',$selected_branch,$pers_id)` with the
*branch* id (`sales/manage/customers.php:124`). So Square's fallback compares a
**debtor number against a branch code**: it matches only by numerical coincidence.

**FA already has the answer.** `get_branch_contacts($branch_code, $action = null,
$customer_id = null, $default = true)`
(`FA/2.4.3/sales/includes/db/branches_db.inc:181-206`) returns the **union**:
`cust_branch` rows for that branch **and** `customer` rows for that debtor
(:192-197), with the action filter relaxed to `action OR action = 'general'`
(:199-200). It also joins only `crm_persons` and `crm_contacts` — **not
`crm_categories`** — so it does not require a category row to exist.

### Who is affected

* **3 sites / 3 repositories** on the branch-contact intent (**I13**): `ksf_FA_Square`, `ksf_FA_EmailManager`, `ksf_FA_Customer`.
* **11 sites / 6 repositories** want "the person behind a customer" (**I2**) — the set whose composition is in question.
* `ksf_FA_RBAC/hooks.php:535` — the branch-ownership filter, which joins `cust_branch` on `debtor_no` (the correct direction) and so already treats branch and account as linked.

### What breaks if we pick wrong

* **Silent wrong answer.** If the ruling is "the account's contact set is
  `type = 'customer'` only", then a customer who is only linked to their
  **branch** — which is exactly what `ksf_FA_Customer:463` writes, and what
  `customer_branches.php:105` writes — has **no contacts** from the account's
  point of view. An invoice addressed to that customer finds no email address and
  goes out blank or undelivered. This is the Square scenario exactly.
* **Silent wrong answer, the other way.** If the ruling is "the union", then a
  module that wanted *only* the debtor-level contact (Square's first choice,
  EmailManager's explicit filter) now gets a branch contact as well and may pick
  the wrong email — the branch's, not the customer's.
* **Loud error.** `get_branch_contacts()` is not auto-loaded: it lives in
  `sales/includes/db/branches_db.inc`, which `includes/main.inc` does not include.
  A module calling it without `include_once` gets a PHP fatal
  `Call to undefined function get_branch_contacts()`. The resolver's
  `ensureNativeFunctions()` (`FaContactResolver.php:394-414`) currently includes
  **only** `includes/db/crm_contacts_db.inc` — so the resolver cannot call
  `get_branch_contacts()` today either.

### Recommended ruling

> **There is no single "the customer's contacts" set. There are three named
> sets, and callers must say which:**
> * `findByCustomer($debtorNo)` → the account's **debtor-level** contacts (`type = 'customer'`). *Keep as is.*
> * `findByEntity('cust_branch', $branchCode)` → a branch's contacts. *Already on the contract.*
> * `findAccountContacts($debtorNo)` → **the union**, implemented over FA's
>   `get_branch_contacts($branchCode, null, $debtorNo)` for each of the debtor's
>   branches. **New.**

`get_branch_contacts()` is the native precedent for the union and should be used
rather than re-implemented — it also happens to be the only native function that
does not need a `crm_categories` row, and it does not inherit the
`action = 'general'` fallback.

**Cost:**
* **+1 method** on the contract (`findAccountContacts`) — or, if the owner prefers
  not to grow the contract, the union can be expressed by the caller as
  `findByCustomer($no)` ∪ `findByEntity('cust_branch', …)` over
  `get_cust_branch()`'s branches — but that pushes the branch enumeration onto
  every caller. One method is cheaper.
* `FaContactResolver::ensureNativeFunctions()` must additionally
  `include_once` `sales/includes/db/branches_db.inc` (and, for the
  `get_customer_contacts()` improvement below, `sales/includes/db/customers_db.inc`).
  Both are pure function-definition files, so a guarded include is safe.
* **Two live bugs fixed as a side effect:** Square's `cust_branch` fallback
  (which compares a branch code to a debtor number) and the `lang = 'C'` loss —
  `findByCustomer()` currently goes through `get_crm_persons()`, which does **not**
  normalise the demo `lang = 'C'` to `''`; `get_customer_contacts()` does
  (`FA/2.4.3/sales/includes/db/customers_db.inc:157-158`). The inventory flags
  this at `Contact_Access_Inventory_2026-10.md:614`.

### The alternative, and when to pick it instead

**Alternative:** keep the two sets separate and **ban** the union — every module
must choose `customer` or `cust_branch` explicitly, and the modules that want
"who do I email for this invoice" must ask FA's own `get_branch_contacts()`
directly.

**Pick this when** the owner is uneasy about a union returning people who are
linked to a *sibling* branch and not the account in question. It costs no
contract change, but it leaves Square's semantics unrepresented and keeps
`get_branch_contacts()`'s per-caller `include_once` burden in eight or more
places. It also loses the `lang = 'C'` normalisation benefit.

### Can it be ruled now?

**Yes.** No migration. The union is a **read**; it changes no stored data. (Note
that if the owner later wants *writes* — attaching a person to an account *or* a
branch — that is intent **I6**, which §5.1 of the inventory says is deliberately
**not** on the read-only contract, and writes must go through
`add_crm_contact()` / `delete_crm_contact()` directly.)

### Resolver contract impact

**Yes — +1 method**, `findAccountContacts(string $debtorNo): Contact[]`, and two
additional `include_once`s in `ensureNativeFunctions()`.

---

## 6. Ambiguity 6 — "employee": a person plus an employment record, or a table?

### The competing definitions

**(a) A flat table `0_hr_employees`** (or `0_employee`, `0_employees`,
`0_ksf_employee`, `0_ksf_employees`). **No schema in the estate creates any of
them, and FA does not expose them.** Ten repositories read one of them:

| Repository | Site(s) | Shape | Failure mode |
|---|---|---|---|
| `ksf_FA_AsteriskPBX` | `includes/asterisk_db.inc:21,86` | `LEFT JOIN hr_employees emp ON e.employee_id = emp.id` | **SILENT** — `$db->query`; employee name `NULL` |
| `ksf_FA_Leave` | `includes/leave_db.inc:54,80` | `LEFT JOIN hr_employees e ON r.employee_id = e.id` | **SILENT** |
| `ksf_FA_Roster` | `includes/roster_db.inc:38,65` | `LEFT JOIN hr_employees e`; picker `SELECT id, name FROM hr_employees WHERE active = 1` | **SILENT** — picker empty |
| `ksf_FA_Teams` | `includes/teams_db.inc:19,64` | `LEFT JOIN hr_employees m ON t.manager_id = m.id` | **SILENT** |
| `ksf_FA_Timesheets` | `includes/timesheet_db.inc:45,75` | `LEFT JOIN hr_employees e ON t.employee_id = e.id` | **SILENT** |
| `ksf_FA_Training` | `includes/training_db.inc:57` | `LEFT JOIN hr_employees emp ON e.employee_id = emp.id` | **SILENT** |
| `ksf_FA_TravelExpense` | `includes/travel_db.inc:20,38` | `LEFT JOIN hr_employees e ON t.employee_id = e.id` | **SILENT** |
| `ksf_FA_Performance` | `includes/performance_db.inc:1` | `LEFT JOIN hr_employees e ON r.employee_id=e.id` | **SILENT** |
| `ksf_FA_ProjectManagement` | `includes/PMContainer.php:189,210,222`; `includes/pm_db.inc:256` | `0_employee` / `0_employees` | **LOUD** — `PMContainer.php:192-194` throws `ProjectException("Employee not found: …")`; `pm_db.inc:256` is an INNER JOIN → **empty team list** |
| `ksf_FA_HRM` | `import.php:33,43,47`; `includes/import.php:34,42,46` | `0_ksf_employee` / `0_ksf_employees` | **LOUD** — `db_query` with a message |

(The inventory's §5 records **I11 as "11 sites / 11 repositories"**; I could
verify **10 repositories** by name — the eleventh may be a site counted twice.
The number is not load-bearing.)

**(b) The FA-native shape** — a `0_crm_persons` row, a `0_crm_categories` row of
type `employee`, and a **satellite employment table**. Only `ksf_FA_HRM` has it:
`0_hrm_contacts_employment` with `person_id` and a real foreign key
`CONSTRAINT fk_employment_person FOREIGN KEY (person_id) REFERENCES 0_crm_persons(id)
ON DELETE CASCADE` (`ksf_FA_HRM/sql/fa_contacts_employment.sql:31`), plus
`0_hrm_contacts_pii`, `0_hrm_contacts_banking`, departments, positions, grades,
pay elements, payroll.

### The decisive evidence — and a problem the inventory missed

`FR-CRM-007-002` §6.3 (APPROVED, 2026-09) already rules on the employee model:

> *"**HRM employees** — *resolved.* HRM keeps its **own** `persons` identity as the
> system of record and xrefs a native `crm_persons` row; HRM does not migrate.
> Merging employee identity into CRM is HRM's call, not CRM's."*

That is exactly what `ksf_FA_HRM` implements today:
`src/Repository/EmployeeRepository.php:22` joins `hrm_contacts_employment` to
`crm_persons cp ON e.person_id = cp.id`.

**But there is a gap the inventory did not identify, and it is the important
finding here.** HRM never calls `add_crm_person()` or `add_crm_contact()` —
grepping the whole of `ksf_FA_HRM` for either returns **nothing**. Its own
e2e harness inserts the person directly (`ksf_FA_HRM/e2e_hrm_event_windows.php:91-94`:
`INSERT INTO crm_persons (ref, name, email, inactive) VALUES …`) and then creates
**no** `0_crm_contacts` row at all (`:99-102` inserts only the employment row).
An employee is therefore **a person with no contact relation**.

**Consequence:** because `get_crm_persons()` is an INNER JOIN over `crm_contacts`
(`FA/2.4.3/includes/db/crm_contacts_db.inc:89-91`), **an employee is invisible to
the shared resolver.** `findByEmail()` and `search()` both work through
`get_crm_persons(null,null,null,null,true)` (`FaContactResolver.php:292`) — a
full scan of exactly the relation-less-blind set. So the ruling "the employee is
a person" is **true and simultaneously unusable through the seam**.

HRM's own repository proves the point: `EventEmployeeMembershipRepository::findPersonsByEmails()`
(`src/Repository/EventEmployeeMembershipRepository.php:65`) queries
`crm_persons LEFT JOIN hrm_contacts_employment` **directly** — a path the
resolver cannot reproduce. HRM has a working employee-by-email lookup that the
sanctioned seam cannot serve.

### The estate has moved while this review was being written — read this first

**Between 20:54 and 21:06 on 2026-10-19 — while this document was being
drafted — seven of the ten modules were changed**, each in its own commit with
the message *"resolve employee names from a module-owned directory table"*:

| Module | Commit | New table |
|---|---|---|
| `ksf_FA_Leave` | `320f48c` (20:54) | `0_ksf_leave_employees` |
| `ksf_FA_Performance` | `e4207bc` (20:56) | `0_ksf_performance_employees` |
| `ksf_FA_Roster` | `d53cd03` (20:59) | `0_ksf_roster_employees` |
| `ksf_FA_Teams` | `f7b73c8` (21:02) | `0_ksf_teams_employees` |
| `ksf_FA_Timesheets` | `c5f481f` (21:03) | `0_ksf_timesheets_employees` |
| `ksf_FA_Training` | `0a6c08a` (21:04) | `0_ksf_training_employees` |
| `ksf_FA_TravelExpense` | `394a2ea` (21:06) | `0_ksf_travelexpense_employees` |
| `ksf_FA_ProjectManagement` | **uncommitted working-tree change** at the time of writing | `0_ksf_projectmanagement_employees` (`sql/install.sql:224`) |

Each commit's reasoning is sound and cites `AGENTS_ARCH.md` §12.2 correctly: the
`0_hr_employees` table never existed, the failure was silent, and *"reaching into
another module's table would gate this module on that module being activated"*.
**These fixes should stand.** The table above is the *current* state of
ambiguity 6, not the state the inventory recorded.

**But the ruling below is now urgent, not academic**, because of two facts about
what was built:

1. **The new directories are flat name/email tables with no link to FA.**
   `0_ksf_travelexpense_employees` is
   `id, name, email, active, created_at` (`ksf_FA_TravelExpense/sql/install.sql:132-140`);
   `0_ksf_projectmanagement_employees` is
   `employee_id, first_name, last_name, email, job_title, department, active`
   (`ksf_FA_ProjectManagement/sql/install.sql:224-236`). **Neither carries a
   `person_id`.** So an employee entered in `0_ksf_travelexpense_employees` is
   **not** an FA person, is **not** reachable through the resolver, and is a
   **separate record from the same human being** in every other module. One
   person who travels, is rostered, is on a team and is in training is now
   **seven employees**.
2. **The PM table uses `first_name` / `last_name`** — the same flat vocabulary
   that already broke five CRM queries against `0_crm_persons` (§0.5 item 8).
   The estate is re-importing that vocabulary into new tables.

The de-facto outcome of the last hour is therefore **alternative (a)** in this
document — *"each keeps a local employee table"* — applied to seven modules at
once, without a decision. **The ruling this section recommends exists to decide
whether that is the permanent answer or an interim step.**

### Who is affected

* **11 sites / 11 repositories** per the inventory's **I11**; **10 repositories**
  verified by name. **Seven now have a local directory table** (see above);
  `ksf_FA_AsteriskPBX` (still `0_hr_employees` at `includes/asterisk_db.inc:21,86`),
  `ksf_FA_HRM` (`0_ksf_employee` / `0_ksf_employees` at `includes/import.php:34,42,46`)
  and `ksf_FA_ProjectManagement`'s `PMContainer.php:189,210,222` (`0_employee`)
  remain on the old names.
* Every module whose `employee_id` column holds a value it can no longer interpret (see **ambiguity 6**, *Who is affected*).
* The resolver's `findByEmail()` and `search()` — both are blind to employees.

### What breaks if we pick wrong

* **Silent wrong answer (the worst case in the estate).** If the ten modules are
  repointed at HRM's `0_hrm_contacts_employment` by *id*, the ids are **not
  comparable**: `0_hrm_contacts_employment`'s key is `employment_id`; the modules'
  `employee_id` columns were populated (if ever) from `hr_employees.id`, a table
  that never existed. Joining `employee_id = employment_id` will usually match
  **the wrong person** if the id spaces overlap — a payroll or leave record
  attributed to the wrong human being.
* **Silent wrong answer (the realistic case).** The ten modules' pickers queried
  `0_hr_employees` and therefore returned **empty**, so their `employee_id` columns
  hold `NULL`/`0`. Today they render a row with a `NULL` employee name and no
  one notices.
* **Silent wrong answer (the resolver case).** A module that adopts the resolver
  to look up an employee by email gets **nothing**, because employees have no
  contact relation — while `ksf_FA_HRM` alone can still do it. The seam looks
  broken.
* **Silent wrong answer (the new-directory case).** If the seven module-local
  directories become permanent, then the employee identity is **dispersed across
  seven tables with no shared key**, and the estate has created the *same*
  dispersion it is trying to remove for contacts — a second, quieter copy of
  the ambiguity this review exists to settle. Two consequences follow: (a) a
  person cannot be matched across modules (a leave request and a travel request
  for the same human being cannot be joined), and (b) a directory row has no
  `inactive` flag and no employment status, so "is this person still here?"
  has no single answer.
* **Loud error.** `ksf_FA_ProjectManagement/includes/PMContainer.php:192-194`
  throws `ProjectException("Employee not found: $employeeId")` — the only loud
  site in this set, and the only one that would have surfaced the problem.

### Recommended ruling

> **An employee is a `0_crm_persons` row plus an employment record. There is no
> `0_hr_employees` table and there never will be, and there must not be eight
> module-local replacements for it either.**
>
> **The seven module-local directories that were just created are the right
> *interim* fix and should stay. They must, however, be given a `person_id`
> column before they are allowed to become permanent**, so that the identity
> they hold can later be repointed at the person without a data migration.

Three parts:

1. **The module-local directories stay, but they must hold a `person_id`.**
   Each of `0_ksf_leave_employees`, `0_ksf_performance_employees`,
   `0_ksf_roster_employees`, `0_ksf_teams_employees`,
   `0_ksf_timesheets_employees`, `0_ksf_training_employees`,
   `0_ksf_travelexpense_employees` and `0_ksf_projectmanagement_employees`
   gains a nullable `person_id INT NULL` (FK-shaped, pointing at
   `0_crm_persons.id`). The row is then *a reference to an FA person*, not a
   copy of one. This is a **one-column ALTER on eight new tables** — cheap, and
   it makes the interim state reversible. **This is the single highest-value
   decision in this section**, because it costs almost nothing now and prevents
   a hard migration later.
2. **The three stragglers are finished the same way.**
   `ksf_FA_AsteriskPBX` (`includes/asterisk_db.inc:21,86`),
   `ksf_FA_ProjectManagement/includes/PMContainer.php:189,210,222` (`0_employee`),
   and `ksf_FA_HRM/includes/import.php:34,42,46` (`0_ksf_employees`) still read
   names that do not exist. They follow the same pattern as their seven
   siblings — **or**, better, they adopt the `person_id` shape directly, because
   they are the ones where no directory has been created yet and the cost is
   lowest.
3. **Make employees visible to the shared resolver**, by having HRM create a
   `0_crm_contacts` row of type `employee` when it creates an employment record:
   `add_crm_contact('employee', 'general', <employment_id>, <person_id>)`. The
   category already exists (`ksf_FA_HRM/sql/crm_categories.sql:6`:
   `('employee','general','Employee',…)`), and FA's native
   `add_crm_contact()` writes the row with full transaction semantics. After
   that, `findByEmail()` and `search()` see employees, because the resolver's
   scan is relation-based. **This is the one change that makes the ruling
   usable.** Note `0_crm_categories` has `UNIQUE KEY(type, action)`
   (`alter2.3.sql:170`) and HRM already seeds `employee/general`, so no duplicate
   category is created. This is **independent of parts 1 and 2** and can be done
   on its own — it makes the shared seam able to answer the employee intent at
   all.

**Cost:**
* **8 tables** gain a `person_id` column (a one-column `ALTER` each, all on
  tables created in the last hour, so no data at risk).
* **3 repositories** finish the job (`ksf_FA_AsteriskPBX`, `ksf_FA_ProjectManagement`,
  `ksf_FA_HRM`).
* `ksf_FA_HRM` gains an `add_crm_contact()` call and a backfill for existing
  employment rows.
* **A data migration for the `0_crm_contacts` backfill** if any employment rows
  exist in UAT/prod: `INSERT INTO 0_crm_contacts (person_id, type, action, entity_id)
  SELECT person_id, 'employee', 'general', employment_id FROM 0_hrm_contacts_employment
  WHERE NOT EXISTS (…)`. **This is the one ruling in the set that implies a data
  migration** — and it is idempotent, so it can run pre- or post-UAT.
* The eight directories' `employee_id`/`id` columns hold **no valid values
  today** (their pickers never worked), so **their** data migration is a no-op —
  but this must be *verified per environment* before it is asserted, because a
  hand-seeded row could exist.
* The resolver contract needs **no change** for part 3 — `add_crm_contact()` is a
  native write, and the resolver stays read-only.

### The alternative, and when to pick it instead

**Alternative (a):** each module keeps its own local employee table and the
resolver ignores employees entirely. **This is what seven modules have just done,
de facto.**

**Pick this when** the owner decides these are really "staffing" tools (Roster,
Teams, Training, Timesheets, Leave, Travel, Performance) whose notion of an
employee is a *shift slot*, not an HRM record, and cross-module coupling to HRM
is unacceptable. The seven commits that have already landed are consistent with
this reading and cite §12.2 correctly.

**But it needs one amendment to be safe, and that amendment is the ruling this
section recommends:** the local directories must carry a `person_id`. Without
it, the estate has eight employee registries with no shared key, and the same
person is eight employees — which is the dispersion the shared resolver was
created to end, reproduced for employees. **If the owner rules for alternative
(a), the `person_id` column is non-negotiable**; the rest of alternative (a) is
already in the tree.

**Alternative (b):** the ten modules are repointed at `0_hrm_contacts_employment`
by `employment_id`.

**Pick this when** every one of the ten modules genuinely needs employment
attributes (department, grade, leave balance) and not just a name. Cost: a hard
dependency on HRM's activation, which §12.2 forbids for a *shared seam* — though
note that rule governs the seam, not a module's own screen. If the owner takes
this option, the HRM tables must be declared as **optional** with a graceful
degradation path, and the `employee_id` values must be confirmed to be
`employment_id`s — which today they are not, because no picker ever produced
them.

### Can it be ruled now?

**The ruling: yes, now — and it is more urgent than it was an hour ago**, because
seven modules have already chosen (a) by default. The `person_id` amendment is
cheap **only while those tables are empty**, which is true today and will not be
true once anyone enters an employee. Rule before that happens.

The `0_crm_contacts` backfill needs a data migration, but it is **idempotent**
and can run pre-UAT (on an empty estate it is a no-op) and re-run post-UAT. The
`person_id` column additions are **safe before UAT** precisely because the
directories hold no valid values today — **but that must be verified per
environment first**, not assumed.

### Resolver contract impact

**No contract change**, provided HRM creates the `0_crm_contacts` row for
employees. If the owner rules for alternative (a) *without* the `person_id`
amendment, the resolver explicitly **ignores** employees and no contract change
is needed — but the estate keeps nine employee models and the modules must build
their own employee pickers, which they currently do not have.

**If the owner wants the resolver to serve the employee intent directly** (a
person looked up as an employee), the contract would need **one** new method —
`findByCategory(string $type): Contact[]` — which FA's native functions cannot
provide either, because `get_crm_persons()` filters on `crm_categories` and
employees would have to be linked by `type = 'employee'` **and** `entity_id` =
their employment id. That is exactly what part 3's `add_crm_contact()` call
enables. **It is therefore worth ruling on whether the resolver should grow that
method at the same time as part 3 — it is the one place where the employee
intent can enter the sanctioned seam instead of bypassing it.**

---

## 7. Ambiguity 7 — "lead": four names, one concept

### The competing definitions

| # | Name | Where | Reality |
|---|---|---|---|
| 1 | `0_ksf_crm_leads` | `ksf_FA_CRM/sql/ksf_crm_leads.sql:8` | **Created.** Keyed by `debtor_no` (UNIQUE), with `lead_source`, `lead_status`, `rating`, `annual_revenue`, `employee_count`, `industry`, `website`, `phone`, `email`, `address`, `assigned_to`, `campaign_id`, `converted_date`, `converted_to_debtor_no` |
| 2 | `0_fa_crm_leads` | `ksf_FA_CRM/includes/crm_db.inc:1788,1823,1832,1841,1869,1873,1890,1914`; `pages/leads.php:174` | **Never created.** Same module, same concept, wrong name |
| 3 | `0_crm_leads` | `ksf_FA_AsteriskPBX/includes/asterisk_db.inc:116` | **Never created.** Guarded by `table_exists('crm_leads')` (:115) — so it is **SILENT** |
| 4 | `0_marketing_contacts` + `0_marketing_lead_scores` | `ksf_Marketing/src/Ksfraser/Marketing/DripCampaigns.php:140`; `LeadScoring.php:29,75,194` | **Never created** — `ksf_Marketing` has **no `sql/` directory at all**. `db_query($sql)` with **no message** (:29, :75) → **SILENT** |

**Inside `ksf_FA_CRM` alone the split is live:** `pages/dashboard.php:103` counts
`0_ksf_crm_leads`, `src/.../LeadsService.php:69` and `Repository/LeadsRepository.php:25`
read `0_ksf_crm_leads` — while `includes/crm_db.inc` and `pages/leads.php:174` read
`0_fa_crm_leads`. **The dashboard shows a number; the leads page shows nothing.**
The page's query is `db_query($sql, "Could not get leads")` — **LOUD** — so the
leads page dies with a DB error rather than showing an empty list.

### The concept is already defined

`FR-CRM-007-002` §3.3 (APPROVED, 2026-09) answers this exactly:

> *"**A lead** is a `debtors_master` row (a prospective account — a 'baby company')
> that is **not yet an active customer**, plus **one or more attached contacts**
> (native `crm_persons` linked via `crm_contacts`, `type='customer'`/`'cust_branch'`,
> `action='general'`)."*
> *"Lead-specific workflow data (status, source, rating, assigned_to, campaign)
> stays in `0_fa_crm_leads`, **keyed by `debtor_no`**."*
> *"Rich firmographics (revenue/employees/industry/website) belong on the
> **account** (customer), not the contact."*

And `BR-CRM-009` (ratified) carries the same through as Business Requirement 1.

Note the requirement's own table name is `0_fa_crm_leads` — the **wrong** name,
by the same `0_fa_*` error the table-naming audit catalogues. The concept is
right; the table name in the requirement is stale and must be corrected to
`0_ksf_crm_leads`.

### Who is affected

* **5 sites / 3 repositories** on the lead intent (**I16**): `ksf_FA_CRM`, `ksf_FA_AsteriskPBX`, `ksf_Marketing`.
* `0_ksf_contact_types` also carries a **`lead`** type label (`ksf_FA_CRM/sql/retag_contact_types.sql:4`) — a fifth appearance of the word.

### What breaks if we pick wrong

* **Silent wrong answer.** `ksf_Marketing`'s lead scoring writes to a table that
  never existed, with `db_query($sql)` and **no error message** — so points
  accumulate nowhere and the score is always null. Nothing says so.
* **Loud error.** `ksf_FA_CRM/pages/leads.php` — DB error page.
* **Silent wrong answer.** If a lead is decided to be "a person with a `lead`
  category", then a lead is **not a debtor** and the four `debtor_no`-keyed
  workflows (conversion, rating, assignment, campaign) have nowhere to live.
  If a lead is decided to be "a debtor", then the estate has a lead that is
  *also* a customer account, and the "not yet an active customer" qualifier has
  to be enforced somewhere — nothing in `0_debtors_master` marks it.

### Recommended ruling

> **Ratify `FR-CRM-007-002` §3.3: a lead is a prospective *account*
> (`0_debtors_master` row) with attached contacts. Lead workflow data lives in
> the module-owned table `0_ksf_crm_leads`, keyed by `debtor_no`. A lead is NOT
> a person, and a lead is NOT a contact type.**

Actions:

1. **Fix the two wrong names inside `ksf_FA_CRM`**: `includes/crm_db.inc` and
   `pages/leads.php` must read `0_ksf_crm_leads`. (This is part of the
   `0_fa_*` → `0_ksf_*` rename wave, `Table_Naming_Audit_2026-10.md`.)
2. **`ksf_FA_AsteriskPBX`**: `0_crm_leads` → the same table, or drop the lead
   lookup. Its `table_exists('crm_leads')` guard (:115) must become
   `table_exists('ksf_crm_leads')`.
3. **`ksf_Marketing`**: `0_marketing_contacts` / `0_marketing_lead_scores` are a
   **marketing contact list**, not a lead store. Either give the module its own
   correctly-named schema (`0_ksf_marketing_contacts`) or repoint it at the CRM's
   lead table. Note the module has **no `sql/` directory**, so it currently has
   no schema at all — this is a gap in the module, not an ambiguity.
4. **Correct the stale table name** in `FR-CRM-007-002` §3.3 (`0_fa_crm_leads` →
   `0_ksf_crm_leads`) so the requirement stops contradicting the schema.
5. **Remove the `lead` label** from `0_ksf_contact_types`? — **No.** Leave it:
   it is an *actor-type* label and after ambiguity 1 it no longer collides with
   a person. Under the ruling, a lead is an account, and the CRM's actor-type
   `lead` is a legitimate label for "a person acting as a lead". Keep it, but
   document that it is an actor type.

**Cost:** 3 repositories change; 1 requirement document is corrected; **no
migration** (the CRM's leads table exists and is keyed by `debtor_no` already).
`ksf_Marketing` needs a schema written, which is new work rather than a rename.

### The alternative, and when to pick it instead

**Alternative:** a lead is a **person** — a `0_crm_persons` row with a `lead`
category, so the resolver can find it.

**Pick this when** the owner wants leads to be marketable contacts (consent,
email campaigns) and does not want to create a `0_debtors_master` row for a
prospect who has never been billed. Cost: it contradicts
`FR-CRM-007-002` §3.3 (an APPROVED requirement) and it moves the firmographics
onto the wrong subject — `BR-CRM-009` is explicit that firmographics belong on
the account. It also requires a `crm_categories` row of type `lead` and a
`crm_contacts` row, which nothing currently creates.

### Can it be ruled now?

**Yes** — it is already answered; this is a ratification plus a rename wave.
**No migration.** The only new work is `ksf_Marketing`'s missing schema.

### Resolver contract impact

**None**, under the recommended ruling (a lead is an account, and the account
accessor from ambiguity 4 covers it). Under the alternative, the resolver would
need a way to find people by category — which it does not have (§4.4).

---

## 8. Ambiguity 8 — "primary contact" has no representation in FA

### The competing definitions

**FA has no primary-contact concept.** `0_crm_contacts` is
`id, person_id, type, action, entity_id` (`alter2.3.sql:211-219`) — no flag, no
ordinal, no uniqueness. `0_crm_categories` has none either
(`alter2.3.sql:161-172`).

**The CRM's own deprecated table has one.** `0_ksf_crm_contacts`
(`ksf_FA_CRM/sql/ksf_crm_contacts.sql:8`) declares
`` `is_primary` TINYINT(1) DEFAULT 0 `` with `KEY idx_is_primary`, and
`ksf_FA_CRM/includes/crm_db.inc:207-215` implements:

```php
function get_primary_contact($debtor_no) {
    $sql = "SELECT c.*, r.role_name FROM " . TB_PREF . "fa_crm_contacts c
        LEFT JOIN " . TB_PREF . "crm_contact_roles r ON c.contact_role_id = r.id
        WHERE c.debtor_no = " . db_escape($debtor_no) . " AND c.is_primary = 1 AND c.inactive = 0
        LIMIT 1";
```

Note: that reads **`0_fa_crm_contacts`** — the table that never existed — so the
function fails **LOUD** today (`db_query($sql, "Could not get primary contact")`).
The `is_primary` **column** exists only in `0_ksf_crm_contacts`, which is
deprecated and holds **0 rows** (the inventory records the live-DB check:
`SELECT COUNT(*) FROM 0_ksf_crm_contacts;` → 0 rows,
`Contact_Access_Inventory_2026-10.md:696-699`).

Elsewhere in the CRM the flag is used as a **sort key and a display hint**, not a
lookup: `crm_db.inc:191` (`ORDER BY c.is_primary DESC, c.last_name, c.first_name`),
`crm_ui.inc:118` (`if ($contact['is_primary'])`).

**And the flag is triplicated.** Three CRM-owned tables declare an `is_primary`
column, each with a *different* subject:

| Table | Declared | Semantics | Code that reads it |
|---|---|---|---|
| `0_ksf_crm_contacts` | `sql/ksf_crm_contacts.sql:21` (`KEY idx_is_primary`) | "this contact is the customer's primary contact" | `crm_db.inc:191,207-215` — but against **`0_fa_crm_contacts`**, which never existed |
| `0_ksf_crm_contact_accounts` | `sql/ksf_crm_contact_accounts.sql:12` | "this contact is primary **for this account**" | `crm_db.inc:1939-1978` — but against **`0_fa_crm_contact_accounts`**, which never existed |
| `0_ksf_crm_person_account_roles` | `sql/ksf_crm_person_account_roles.sql:21` | "this person holds the **primary role** in this account" | `pages/person_account_roles.php:126,129` — but against **`0_fa_crm_person_account_roles`**, which never existed |

All three are **loud** failures today (every one of the code sites uses
`db_query($sql, "…")` with a message).

`FR-CRM-007-002` §3.1 and §4 do **not** carry a primary-contact concept forward.
Its migration step (:223) links each migrated contact to *"the account's **primary
branch**"* — i.e. it substitutes **branch** for **primary contact**. The
requirement never mentions `is_primary`. `Architecture.md:179` documents the column
as *"Primary contact flag"* in the old table.

### Who is affected

* The CRM's contacts tab and anything that renders "the customer's main contact": `ksf_FA_CRM/includes/crm_db.inc:191,207-215`, `includes/crm_ui.inc:118`, `pages/person_account_roles.php:32,36,59,110,140`.
* Indirectly **11 sites / 6 repositories** on the "person behind a customer" intent (**I2**) — any of them that needs a *default* contact.
* `ksf_FA_Square/src/Services/SquareInvoiceService.php:469-472` — its `LIMIT 1` with no `ORDER BY` is exactly the "first contact" question, answered arbitrarily.

### What breaks if we pick wrong

* **Silent wrong answer — the dangerous kind.** If "the customer's primary
  contact" becomes "the first contact returned", then the invoice recipient
  changes depending on the query plan. `get_crm_persons()` orders by
  `contact_id` (`crm_contacts_db.inc:111`), so "first" means "lowest relation
  id" — deterministic in practice, but it means the *oldest link*, not the
  *designated contact*. Two customers, one invoice each, one to a spouse and one
  to a child, and the estate mails whoever was linked first. **No error.**
* **Silent wrong answer, the other way.** If FA's model is declared "no primary
  concept, full stop", then a screen that shows a primary contact shows an
  arbitrary one, and the business cannot correct it — because there is nowhere
  to store the correction.
* **Loud error.** If the resolver contract grows `isPrimary` but FA cannot supply
  it, then `FaContactResolver` would have to fabricate the value — a resolver
  that guesses is worse than one that admits it cannot.

### Recommended ruling

> **This is a requirements question, not a technical one.** FA's model has no
> primary-contact concept and the owner decision (§12.2) forbids adding one to
> FA core. The CRM's requirement set (`FR-CRM-007-002`) already migrated the
> concept to *branch-scoped entry* rather than *primary contact*, and does not
> carry `is_primary` forward.

Recommended ruling: **the estate has no "primary contact" concept.** The
designated-recipient question is answered at the **account** level, not the
contact level, and the nearest existing mechanism is `get_branch_contacts()`
(ambiguity 5), which returns the branch's contacts and the account's contacts —
not a designated one.

If the business genuinely needs "the one contact to bill", that is a **new
requirement** and it needs a **CRM-owned satellite table**, e.g.
`0_ksf_crm_account_contacts (debtor_no, person_id, is_primary)` with
`UNIQUE (debtor_no, is_primary)`-style enforcement — because it cannot live in
FA core and it cannot live in `0_crm_contacts`.

**Cost:**
* **If the answer is "no primary concept":** drop `get_primary_contact()` from
  `crm_db.inc`, drop the `is_primary` reads from the CRM's UI
  (`crm_ui.inc:118`) and from `pages/person_account_roles.php:129,140`, and
  replace the "primary contact" display with "the account's contacts, listed".
  Note that the `is_primary` column also exists on the two **created** CRM tables
  `0_ksf_crm_contact_accounts` and `0_ksf_crm_person_account_roles`, so the
  ruling also decides whether those columns are dropped, kept, or repurposed.
  Cheap; no migration; **but it is a visible product regression** and needs a
  requirement note saying so.
* **If the answer is "the CRM needs one":** a new CRM-owned table + a lookup +
  a rule for what happens when two are marked primary. That is a **new
  requirement document**, and it must be written before the code.
* **Resolver contract:** if a primary notion is introduced, `Contact` must grow
  an `isPrimary` field (`Contact.php:91-117,264-280`) and the contract must
  either expose it or not. Under the recommended ruling, **no contract change**.

### The alternative, and when to pick it instead

**Alternative:** model "primary" as a **`crm_categories` action** — a person's
relation to an account with `action = 'primary'` instead of `action = 'general'`.

**Pick this when** the owner wants the designation to live in FA's own store and
to be visible in FA's native contact screens. Cost: FA's category set is
`UNIQUE KEY(type, action)` (`alter2.3.sql:170`) and is seeded per
type/action (`sql/en_US-new.sql:427-439`); adding a `primary` action means adding
category rows in every company, and `get_crm_persons()`'s `action` filter plus
its silent `general` fallback (`crm_contacts_db.inc:115-116`) would need the
designation to be the *primary* action to be found at all. It also re-introduces
the "one action per person per entity" limitation that a satellite table does
not have. **Not recommended**, but it is the only option that keeps the
designation inside FA's store.

### Can it be ruled now?

**The technical parts: yes, now.** The **product** parts ("does the business
need a designated billing contact?") are a requirements question and need
written requirements — see §14. If the answer is "yes, we need one", the CRM
satellite table is a **fresh table**, so there is **no migration** — but the
existing `0_ksf_crm_contacts.is_primary` values (0 rows today) would need to be
carried across, and that migration is only meaningful if the CRM's contacts
table ever holds data.

### Resolver contract impact

**None under the recommended ruling.** Under the "CRM needs one" ruling: `Contact`
grows an `isPrimary` field, and the resolver would have to source it — which FA
cannot, so the value would come from the CRM's satellite table, outside the
resolver. The cleanest form is: **the resolver does not model "primary"**; a CRM
service joins its own table.

---

## 9. Ambiguity 9 — a contact role carries defaults that FA cannot store

### The competing definitions

**The CRM's role catalogue carries defaults.**
`ksf_FA_CRM/includes/crm_db.inc:429-437`:

```php
function add_contact_role($role_name, $description, $default_phone = null, $default_email = null) {
    $sql = "INSERT INTO " . TB_PREF . "crm_contact_roles
        (role_name, description, default_phone, default_email) VALUES (...)";
```

and `update_contact_role()` (:440-449) writes the same two columns.
`0_crm_contact_roles` is **never created** by any schema in the estate — verified
across `ksf_FA_CRM/sql/`, `ksf_FA_Common/sql/`, `ksf_FA_Common_repo/sql/`. So
`add_contact_role()` fails **LOUD** (`db_query($sql, "Could not add contact role")`),
and `get_contact_roles()` (:457-464) fails **LOUD** too.

**FA's category catalogue cannot carry defaults.** `0_crm_categories` is
`id, type, action, name, description, system, inactive`
(`alter2.3.sql:161-172`) — no default phone, no default email, and the seeded
rows (`sql/en_US-new.sql:427-439`) confirm it.

**The critical observation, which the inventory does not make: the defaults are
never read.** Grepping the estate, `default_phone` / `default_email` appear in
**exactly 6 places, all in `ksf_FA_CRM`, and all of them are the two INSERT/UPDATE
statements above.** Nothing anywhere reads a role's defaults and applies them to a
contact. The feature is **write-only dead code** — there is no behaviour to
preserve and no data to migrate.

### Who is affected

* `ksf_FA_CRM` only: `includes/crm_db.inc:429-449` (write), `:457-464` (list),
  and the `LEFT JOIN crm_contact_roles r ON c.contact_role_id = r.id` at
  `:186,200,210,431,442,454,460,725,789` and `includes/crm_ui.inc:381` — all of
  which join a table that does not exist and therefore fail **LOUD**.
* Indirectly: the whole CRM contact model, because the *role* concept is the
  thing that would carry the defaults.

### What breaks if we pick wrong

* **Loud error** throughout the CRM: every `LEFT JOIN crm_contact_roles` fails
  (`db_query` with a message). The CRM's contact list is broken today.
* **Silent wrong answer** — the one to watch for. If the ruling is "roles become
  `crm_categories` rows", then a category row's `description` field is the only
  free-text slot left. If the owner decides to *encode* the default phone and
  email into `description` (e.g. `"Role | +1-555-0100 | billing@example.com"`),
  the estate gets a **parseable-string** anti-pattern that silently breaks on the
  first role whose description contains a pipe.
* **Silent wrong answer** — if the ruling is "roles are dropped entirely", then
  any business rule that lived in a role ("billing contacts prefer the shared
  billing@ address") is lost silently, because it was never implemented in the
  first place.

### Recommended ruling

> **A contact role becomes an FA `crm_categories` row (a `type`/`action` pair with
> a `name` and a `description`). The per-role *defaults* are dropped — not
> migrated, because they were never read.**

Supporting reasoning:

1. `AGENTS_ARCH.md` §12.2 already names `add_crm_category`,
   `update_crm_category`, `get_crm_categories`, `get_crm_category`,
   `get_crm_category_name`, `delete_crm_category`, `is_crm_category_used` as the
   native functions for exactly this catalogue. Using them is the rule, not an
   exception.
2. The defaults are **provably dead**: six references, all writes, zero reads
   (§9 above). Nothing to migrate.
3. The estate already has a place for "what address should we use for this
   purpose": `0_crm_categories` has `UNIQUE KEY(type, name)`
   (`alter2.3.sql:171`) and `UNIQUE KEY(type, action)` (:170), so a role maps
   cleanly onto a `(type, action)` pair — e.g. `('customer','billing')`.
4. If a business *does* need a shared default address per role, the correct
   home is **not** the category row and **not** a string in a description. It is
   either (a) a real contact — a `0_crm_persons` row linked to the account with
   the relevant action — or (b) a module-owned satellite table
   (`0_ksf_crm_role_defaults`). Option (a) is the FA-native one and needs no
   new table: the shared billing mailbox *is* a person.

**Cost:**
* `ksf_FA_CRM`: replace `crm_contact_roles` with `crm_categories` in the nine
  `crm_db.inc` sites (:186, :200, :210, :431, :442, :454, :460, :725, :789) and
  `includes/crm_ui.inc:516`, and migrate the role names to `crm_categories` rows.
  `0_crm_contact_roles` is never created, so **there is nothing to migrate** —
  the roles exist only as PHP function signatures.
* **No data migration.**
* One FAQ/requirement note: "roles with default contact details" becomes
  "a shared contact person attached to the account", which is a *behavioural*
  change that the CRM's requirements should record (currently `FR-CRM-007-002`
  does not mention roles at all).

### The alternative, and when to pick it instead

**Alternative:** keep a CRM-owned role catalogue with defaults, as
`0_ksf_crm_contact_roles (role_name, description, default_phone, default_email)`,
and link contacts to it with `role_id` — i.e. the CRM's model, correctly named.

**Pick this when** the business needs per-role default contact details that are
*not* expressible as a real person — for example a role that carries a
*procedure* ("role=escalation, default phone=after-hours desk, email=duty@…")
rather than an address. Cost: a CRM-owned table, and a second role catalogue
alongside FA's categories — but note it is **CRM-owned**, so it does not violate
§12.2 (which governs FA core tables). The distinction from the recommended ruling
is: **does a role have defaults, or does a role have a shared contact?**

### Can it be ruled now?

**Yes** — the technical ruling is free and needs no migration. The *business*
question ("do we need default details per role?") is a requirements question; if
the answer is yes, the satellite table is new and there is still no migration.

### Resolver contract impact

**None directly.** But see §4.4: the resolver's `listContactCategoryIds()` returns
ids with **no names**, and `ksf_FA_RBAC/hooks.php` needs names to render a
filter. The *category-name* accessor is the contract item that the role question
points at, and it is needed independently (§4.4).

---

## 10. Ambiguity 10 — two Notes implementations, one retired table

### The competing definitions

**`ksf_FA_Notes` (current) — two implementations side by side:**

| | New | Old |
|---|---|---|
| File | `includes/ksf_notes_db.inc`, `includes/ksf_notes_link_db.inc` | `includes/notes_db.inc` |
| Tables | `0_ksf_Notes`, `0_ksf_Notes_link` (`sql/ksf_notes.sql`, `sql/ksf_notes_link.sql`) | `0_fa_crm_notes`, `0_fa_note_links` |
| Loaded by | `hooks.php:71-73`; `pages/notes.php:34`; `tests/bootstrap.php:73` | `includes/links_db.inc:9` (`require_once`) — **not** by `hooks.php` |
| Functions | `notes_prepare`, `notes_sql_insert`, `notes_write`, `notes_get`, … | `add_note`, `get_note`, `get_notes`, `update_note`, `delete_note`, `search_notes`, `link_note`, … |
| Status | the live implementation | still present, and **advertised as an integration point** |

**The old implementation is not dead code.** `includes/links_db.inc:5-9`:

> *"Functions are defined in notes_db.inc; this file exists for modules that
> expect to include('links_db.inc') separately."*

No module in the estate currently includes it — but it is a published entry point.

**`ksf_FA_Notes/sql/install.sql:4` still runs `ALTER TABLE 0_fa_crm_notes`** — on
activation, against a table that **has never existed**. The same file creates
`0_fa_note_links` (`:9`) — the *old* link table, while the live implementation
uses `0_ksf_Notes_link`. So the module's activation script creates the wrong
tables and alters a phantom one.

**`ksf_Notes` (the older twin) writes `0_fa_crm_notes` in eight places**:
`src/ksfraser/Notes/Service/NoteService.php:29,49,70,90,104,117,142,164`.

**And there is a precedent for the mistake.** `ksf_FA_Notes/tests/Unit/NotesSqlTest.php`
class docblock:

> *"These replace a previous suite that asserted only `function_exists()`, **which
> stayed green while every query it targeted a nonexistent table**."*

and the current test asserts at :96 that the SQL *"must not touch the retired table"*.

### Who is affected

* **3 sites / 2 repositories** on the notes intent (**I14**): `ksf_FA_Notes`, `ksf_Notes`.
* `ksf_FA_Notes`'s own activation script (`sql/install.sql:4`) — every activation.
* Any future module that includes `ksf_FA_Notes/includes/links_db.inc`.

### What breaks if we pick wrong

* **Loud error** — `ksf_FA_Notes`'s `ALTER TABLE 0_fa_crm_notes` on a fresh
  activation. Whether this aborts the activation depends on FA's `db_import()`
  behaviour; if it aborts, **the module cannot be activated at all**; if it is
  tolerated, the module activates with the wrong link table and every
  note-to-record link fails later.
* **Silent wrong answer.** `ksf_Notes`'s `NoteService` calls `db_query($sql)`
  — I verified no error message on the eight sites — so every write goes nowhere
  and every read comes back empty. **A note created in `ksf_Notes` vanishes.**
  This is precisely the `ksf_FA_Mail` failure mode the table-naming audit
  documents.
* **Silent wrong answer.** If the old `ksf_FA_Notes/includes/notes_db.inc` is
  reachable (via `links_db.inc`) and a module calls `add_note()`, the note is
  written to `0_fa_crm_notes` — a table that does not exist — **while the module
  believes it was saved**.

### Recommended ruling

> **One notes implementation: `ksf_FA_Notes`'s `0_ksf_Notes` + `0_ksf_Notes_link`,
> module-owned. The retired `0_fa_crm_notes` code and table are deleted, not
> left in place. `ksf_Notes` (the older twin) is retired in favour of
> `ksf_FA_Notes`.**

This is already the module's own position — `NotesSqlTest.php:96` calls
`0_fa_crm_notes` *"the retired table"* and the inventory's classification list
marks both `0_fa_crm_notes` sites **DEPRECATED**
(`Contact_Access_Inventory_2026-10.md:96-97`).

Actions:
1. **Delete** `ksf_FA_Notes/includes/notes_db.inc` and `includes/links_db.inc`
   (or reduce `links_db.inc` to a deprecation shim that throws), and remove the
   `ALTER TABLE 0_fa_crm_notes` and `CREATE TABLE 0_fa_note_links` from
   `sql/install.sql:4,9`.
2. **Retire `ksf_Notes`** — it is a separate, older repository
   (`src/ksfraser/Notes/Service/NoteService.php`), writing to a table that has
   never existed. Either delete it or repoint it at `0_ksf_Notes`. Check first
   whether `ksf_Notes` is actually activated anywhere — `ksf_FA_Notes` is the
   live one.
3. **Keep notes module-local.** FA has no notes concept, so this is a legitimate
   module-owned table. `0_ksf_Notes_link.entity_id` is `VARCHAR(64)` and
   `entity_type` is a registry key — the design already anticipates heterogeneous
   targets (`sql/ksf_notes_link.sql` lists the eight possible targets).

**Cost:** 2 repositories; a deleted file that is an advertised integration point
(so any external consumer must be told); **no data migration** — both tables are
empty of live data by construction (`0_fa_crm_notes` never existed;
`0_ksf_Notes` is the only table with rows).

### The alternative, and when you would pick it instead

**Alternative:** keep both `ksf_FA_Notes` and `ksf_Notes` alive, and have
`ksf_Notes` be a thin façade over `ksf_FA_Notes`'s tables.

**Pick this when** `ksf_Notes` has consumers outside this estate (it is a
published package?) or when the two modules are in fact different products with
different owners. Cost: the façade must be maintained, and the estate keeps a
"two implementations of notes" ambiguity alive. Check `ksf_Notes`'s git remote
and Packagist status before ruling.

### Can it be ruled now?

**Yes** — deletion of dead code, no data dependency. **Do it before UAT**: the
`ALTER TABLE` in `install.sql` is an activation-time hazard, and the whole point
of the ruling is that the module activates cleanly on a fresh install.

### Resolver contract impact

**None.** Notes are module-local records that *reference* a person by id; the
resolver supplies the person, the note module supplies the link.

---

## 11. Ambiguity 11 — inactive-person semantics

### The competing definitions

| Position | Where | Behaviour |
|---|---|---|
| **Exclude inactive by default** | `FaContactResolver.php:109` (`findByEmail`), `:256` (`search`) — `includeInactive` defaults to `false` | a retired person is not a match unless the caller asks |
| **Exclude inactive, always** | `ksf_FA_Classes/src/FrontAccounting/Repository/CrmPersonRepository.php:26` (`AND inactive = 0`), `:41-50` (`AND inactive = 0`) | no way to ask for inactive people at all |
| **Exclude inactive by default, configurable** | `ksf_FA_CRM/src/FrontAccounting/CRM/Service/ContactOptionsService.php:31,60,78` — `$activeOnly = true`; filter at `:102`; hook override at `:154` | matches the resolver's default |
| **Include everything** | `ksf_FA_HRM/src/Repository/LookupRepository.php:101` — `getCrmPersons()`: `SELECT id, name FROM crm_persons ORDER BY name`, **no inactive filter** | lists retired people; `personOptions()` at `:114` **does** filter `inactive = 0` — HRM is internally inconsistent |
| **Exclude inactive** | `ksf_FA_EmailManager/includes/em_db.inc:274,294` — `AND p.inactive = 0` | matches the resolver |
| **Exclude inactive** | `Requirements/FR-EM-001-03` R3 (:197) and §5.1 (:250-255) | *"a retired (inactive) person is not a match unless the caller asks for inactive people explicitly"* |

The resolver's behaviour is **already the majority behaviour** (4 of 6 positions,
including the written requirement). The `includeInactive` flag already exists on
both `findByEmail()` and `search()` (`ContactResolverInterface.php:76,134`).

### Who is affected

* The resolver's two list-ish methods, and every module that adopts them.
* `ksf_FA_HRM/src/Repository/LookupRepository.php:101` — the one outlier.
* `ksf_FA_CRM`'s contact picker — which, as §0.5 notes, has a *different* gap
  (relation-less people), not an inactive gap.

### What breaks if we pick wrong

* **Silent wrong answer.** If "exclude inactive" is ruled wrong and the
  default flips to "include", then `findByEmail()` starts matching a person who
  left the company, and an inbound email is attributed to a retired human being.
  `FR-EM-001-03` §5.1 calls this out explicitly: *"Matching an inbound email to
  a retired person silently attributes new correspondence to someone who may
  have left."* **No error.**
* **Silent wrong answer.** If "exclude inactive" is kept but a caller is not
  given the flag, a legitimate lookup for a *historical* record (a leave request
  for a departed employee, a tax invoice for a closed account's contact) returns
  nothing. HRM's `getCrmPersons()` is that call site today.
* **Loud error.** None. There is no mechanism by which this fails loudly.

### Recommended ruling

> **Inactive means inactive by default. The resolver's existing
> `includeInactive = false` default stands and is ratified. A caller that needs
> a retired person passes `includeInactive = true` explicitly — and that call
> site must say so in a comment.**

This aligns the resolver with:
* the written requirement (`FR-EM-001-03` §5.1, AC4 at :286 — *"An inactive
  person is not auto-matched"*), and
* three of the four existing implementations.

**Cost:**
* `ksf_FA_HRM/src/Repository/LookupRepository.php:101` (`getCrmPersons()`) must
  be changed — either to filter `inactive = 0`, or to be renamed to
  `getAllCrmPersons()` with the intent documented. Note HRM's own
  `personOptions()` (:114) already filters, so the fix is to make the two
  consistent. **Small.**
* **One consequence must be handled explicitly:** FA's `get_crm_persons()` has
  **no inactive filter** (`FA/2.4.3/includes/db/crm_contacts_db.inc:87-119`), so
  an inactive person **is** returned by `findByEntity()` and `findByCustomer()`.
  The resolver's `includeInactive` flag therefore only applies to
  `findByEmail()` and `search()`. **This asymmetry must be documented at the
  seam**, or callers will assume the flag is global. It is a real gap in the
  current contract: `findByCustomer()` and `findByEntity()` have no
  `includeInactive` parameter at all.
* **No migration.**

### The alternative, and when to pick it instead

**Alternative:** make the inactive policy **per call site** with no default — the
contract requires every caller to pass `includeInactive` explicitly (no default
value), so no policy is baked in.

**Pick this when** the estate cannot agree that "exclude inactive" is right
globally — for example if a finance module needs retired contacts and a
marketing module must not have them. Cost: every caller must make a conscious
choice, which is good hygiene but changes 7 call sites' signatures and the hook
wire (`'include_inactive'` is already in the payload, so the wire does not change).
This is a defensible, slightly more expensive version of the recommendation.

### Can it be ruled now?

**Yes** — a signature-level decision on a read-only contract, no migration.

### Resolver contract impact

**None if the recommendation stands** (the flag already exists). **Yes if the
alternative is taken**: `includeInactive` becomes a required parameter on
`findByEmail()` and `search()`. **Additionally — and independently of the ruling
— the contract should gain `includeInactive` on `findByCustomer()` and
`findByEntity()`** so the asymmetry disappears; that is a contract change worth
making either way.

---

## 12. Summary table

| # | Ambiguity | Recommended ruling | Cost | Blocking? |
|---|---|---|---|---|
| 1 | "contact" = person / relation / type | "contact" = a person only. Rename `0_ksf_contact_types` → `0_ksf_actor_types` and the `ContactType` namespace → `ActorType`. "Type" = FA's `crm_categories.type`. | 7 repos; 1 table rename (labels only); namespace move | **Blocking** — Tier 0 |
| 2 | "customer" = account or person | "customer" = the account (`0_debtors_master`). The person behind it is a contact. Link direction: account → contacts. Ratifies `FR-EM-001-03` §3.1 and `BR-CRM-009`. | 19 repos move 32 sites to native functions; 1 method rename | **Blocking** — Tier 0 |
| 3 | Two (really four) contact seams | One seam: `ksf-fa-common`'s resolver. Delete `fa-classes`' two repositories; retire GPG's two seams. Supersede `FR-CRM-007-002` §3.1 and `NATIVE-FA-CONTACTS-REFERENCE.md` H5. | 5 repos; resolver contract **+3 methods**; published-package major bump; 2 approved docs to supersede | **Blocking** — Tier 0 |
| 4 | The debtor/account seam (the eleventh) | A **separate** `AccountResolverInterface` (2 methods), not more methods on the contact contract. `findByEmail → debtor_no` needs **one documented exception** for `ksf_FA_Common` to read `crm_contacts.entity_id`. Plus §4.4: `listAllPersons()` and `listCategories()` | New package area; 19 repos; `ksf_FA_EmailManager` duplication retired; **+2 contract methods** | **Blocking** — Tier 1 (depends on 2 and 3) |
| 5 | Branch vs customer contact | Three named sets. Keep `findByCustomer()` (debtor-level). Add `findAccountContacts()` = the union, over native `get_branch_contacts()`. | **+1 method**; 2 extra `include_once`s; fixes Square's branch-code bug and the `lang='C'` loss | Tier 1 (depends on 2) |
| 6 | Employee: person or table | An employee is a **person** plus an employment record. The **seven module-local directories just created stay as the interim fix**, but each must gain a `person_id` column so the identity can later be repointed at the person. HRM must create a `crm_contacts` row of type `employee` so the resolver can see employees at all. | 8 tables gain a column; 3 repos finish the job; **+1 idempotent data migration**; possibly **+1 contract method** (`findByCategory`) | **Urgent** — 7 modules have already chosen by default |
| 7 | Lead: four names | **Already settled** (`FR-CRM-007-002` §3.3): a lead is a prospective **account** with attached contacts; workflow data in `0_ksf_crm_leads` keyed by `debtor_no`. Ratify + fix the two wrong names + give `ksf_Marketing` a schema. | 3 repos; 1 requirement doc corrected; no migration | Tier 2 — largely settled |
| 8 | Primary contact | A **requirements question**. Recommended: the estate has no primary-contact concept; the CRM's requirement already migrated it to branch-scoped entry. If the business needs one, it is a CRM-owned satellite table — FA core cannot hold it. | Drop `get_primary_contact()` + the `is_primary` UI, or write a new requirement + a new table | Tier 2 — **requirements** |
| 9 | Contact role defaults | Roles become `0_crm_categories` rows. The per-role **defaults are dropped** — they were never read (6 references, all writes). | `ksf_FA_CRM` only, ~12 join sites; no migration | Tier 2 — **requirements** for the "do we need them?" half |
| 10 | Two Notes implementations | One: `ksf_FA_Notes`'s `0_ksf_Notes` + `0_ksf_Notes_link`. Delete the retired code and the `ALTER TABLE 0_fa_crm_notes`; retire `ksf_Notes`. | 2 repos; delete an advertised entry point; no migration | Independent — do it **before UAT** |
| 11 | Inactive-person semantics | Inactive is excluded by default. Ratify the resolver's existing flag. Document that `findByCustomer()`/`findByEntity()` have **no** inactive filter, and add the flag there. | 1 repo (`ksf_FA_HRM`); optional contract symmetry change | Independent |

**Contract impact in one line:** rulings **3**, **4**, **5** change the contract;
**3** is the largest (+3 methods on `ContactResolverInterface`, a published-package
major bump, 2 approved documents to supersede); **4** is the one whose *main*
recommendation — a separate `AccountResolverInterface` — can be satisfied
**without** changing `ContactResolverInterface` at all, though its two §4.4
companions do add two methods. **6** may add a seventh (`findByCategory()`).

---

## 13. Decision order

### Tier 0 — must be ruled first; everything else depends on these

1. **Ambiguity 1** ("contact" = a person). Fixes the vocabulary every other
   ruling is written in. Costs nothing to rule; the *rename* can be sequenced
   later.
2. **Ambiguity 2** ("customer" = the account). Distinguishes the account from
   the person, which ambiguity 4 (the debtor seam) and ambiguity 5 (the contact
   set) both presuppose. Already ratified by two documents — cheap.
3. **Ambiguity 3** (one seam). Decides **which code** the other rulings land in.
   If this is ruled after ambiguities 4 and 5, those two have to be re-specified
   against the wrong seam.

### Tier 1 — depend on Tier 0

4. **Ambiguity 4** (the debtor/account seam). Needs 2 (account ≠ person) and 3
   (which package hosts the new contract). *This is the one to rule immediately
   after Tier 0, because it is the largest contract change and has the longest
   lead time.*
5. **Ambiguity 5** (branch vs customer contact set). Needs 2. The union is
   expressible over native `get_branch_contacts()` only once the native includes
   are settled.
6. **Ambiguity 6** (the employee). Mostly settled already
   (`FR-CRM-007-002` §6.3); what remains is the adoption decision for the ten
   readers **and** the `crm_contacts` backfill, which is idempotent and can be
   done at any time. **Now the most time-sensitive ruling in the set: seven
   modules created module-local employee directories between 20:54 and 21:06 on
   2026-10-19, and the `person_id` amendment is cheap only while those tables
   are empty.**

### Tier 2 — depend on Tier 1, or are requirements questions

7. **Ambiguity 7** (lead) — already answered; ratify and fix the names. No
   dependencies.
8. **Ambiguity 8** (primary contact) — needs a written requirement before it can
   be implemented either way.
9. **Ambiguity 9** (role defaults) — needs a written requirement for the "do we
   need them?" half; the technical half is independent.

### Independent — can be ruled in any order, at any time

* **Ambiguity 10** (Notes) — depends on nothing. It is also the one with a
  **deadline**: the `ALTER TABLE 0_fa_crm_notes` in `ksf_FA_Notes/sql/install.sql:4`
  is an activation-time hazard on every fresh install. **Rule and fix it before
  UAT**, whatever else is still open.
* **Ambiguity 11** (inactive) — depends on nothing. The contract already has the
  flag; this is a ratification plus one repo's consistency fix.

**Suggested sequence for a single decision session:** 1 → 2 → 3 → 4 → 5 → 6, then
7 → 8 → 9 in parallel with 10 and 11. That is **six decisions in one session**
(they are the ones that are load-bearing), with **five** that can be delegated.

**One exception, and it is time-sensitive:** ambiguity **6** should be taken
**first, ahead of 1-5**, if a session is possible today. Seven modules created
module-local employee directories between 20:54 and 21:06 on 2026-10-19, and the
`person_id` amendment (ambiguity 6, *Recommended ruling*) is cheap **only while those tables are empty**.
Every day they stay empty, the amendment is a one-column `ALTER`; the first day
someone types an employee into a roster, it becomes a data migration across
eight tables. The other ten ambiguities have no clock.

---

## 14. Requirements questions vs technical questions

Five of the eleven are **not** technical. A code convention cannot settle them;
they need written requirements, and the code follows.

| # | Question | Why it is a requirements question | Where the requirement must live |
|---|---|---|---|
| **4** | Does the estate want an **account** accessor as a shared seam? | The answer determines whether 19 repositories get one contract to call or a rule to call FA's functions directly. It is an estate-wide interface commitment, not an implementation detail. | A new BR in `ksf_Architecture_Docs/Requirements/`, referenced by `AGENTS_ARCH.md` §12.2 |
| **8** | Does the business need a **designated primary contact**? | "Primary contact" is a business concept ("who do we bill?") with no FA representation. Whether the estate needs it is a product decision. | `ksf_FA_CRM/ProjectDcs/` — a new BR/FR beside `BR-CRM-009`; the CRM's own requirement set already migrated the concept away (§4 step 2 of `FR-CRM-007-002`) |
| **9** | Do contact roles need **default contact details**? | "Should a billing role carry a shared phone/email?" is a business rule. The *technical* part (roles become `crm_categories` rows) is settled; the *business* part is not. | `ksf_FA_CRM/ProjectDcs/` — note that the current CRM requirement set does not mention roles at all |
| **7** | Is a lead an **account** or a **person**? | Already answered (`FR-CRM-007-002` §3.3). It is a requirements question that has **already been asked and answered** — it only needs ratification and a stale table-name correction. | `ksf_FA_CRM/ProjectDcs/FR-CRM-007-002` §3.3 — correct `0_fa_crm_leads` → `0_ksf_crm_leads` |
| **11** | Is an inactive person a valid match for a **historical** lookup? | The resolver's default is settled by `FR-EM-001-03` §5.1. What is *not* settled is the estate-wide rule for the two methods (`findByCustomer`, `findByEntity`) that currently have no inactive filter at all — that is a policy question, and it is the one that actually needs writing down. | `ksf_Architecture_Docs/Requirements/` — or a note in `AGENTS_ARCH.md` §12.2 |

**Ambiguities 1, 2, 3, 5, 6 and 10 are technical** — they are settled by
convention and by the existing approved requirements, and the rulings above can
be applied as written.

---

## 15. Lateral findings — not ambiguities, but found while verifying

These are outside the eleven, are **not** decisions for this review, and are
recorded so they are not lost.

1. **`ksf_FA_Common/src/template_hooks.php` is a PHP parse error** and it lives
   under the PSR-4 root of a published package. `php -l` reports
   `syntax error, unexpected token "<", expecting ")" in … on line 48`
   (`define('SS_ksf_FA_<Module>', <section_num> << 8);`). This is hazard **H6**
   in `ksf_FA_CRM/ProjectDcs/NATIVE-FA-CONTACTS-REFERENCE.md:337`, still open.
   Any tool that scans `src/` for PHP — a scanner, a `PluginRegistry::discover()`,
   a `require` — fatals. **This is a landmine on the sanctioned seam itself** and
   should be fixed independently of this review (rename to
   `template_hooks.php.dist`).
2. **`ksf_FA_GPG`'s two resolvers are broken for every contact type** — all three
   entries in the table map address a column that does not exist
   (`0_debtors_master.email`, `0_suppliers.email`, `0_crm_persons.person_id`).
   `0_suppliers` has a `contact VARCHAR(60)` column — a free-text contact
   *name*, not an address (`FA/2.4.3/sql/en_US-new.sql:1691-1706`).
3. **`ksf_FA_Square`'s branch fallback compares a debtor number to a branch
   code** (`src/Services/SquareInvoiceService.php:482-485`). `cust_branch`'s
   `entity_id` is a `branch_code` (`0_cust_branch`'s primary key,
   `FA/2.4.3/sql/en_US-new.sql:549-551`), not a `debtor_no`.
4. **`ksf_FA_CRM` has a live two-name split on leads**: the dashboard and the
   repository read `0_ksf_crm_leads`; `includes/crm_db.inc` and `pages/leads.php`
   read `0_fa_crm_leads`, which never existed.
5. **`ksf_FA_Notes/sql/install.sql:4`** still runs `ALTER TABLE 0_fa_crm_notes`
   on every activation.
6. **`ksf_Marketing` has no `sql/` directory at all**, and its two lead-scoring
   queries use `db_query($sql)` with **no error message** — a silent write
   failure.
7. **`ksf_FA_Common`'s `InMemoryContactResolver` implements `addPerson()` (:63)
   and `addContact()` (:81)**, which are **not on the contract**. The in-memory
   implementation is a strict superset of the interface — a divergence that will
   confuse the first caller who writes against the concrete class instead of the
   interface.
8. **`get_crm_persons()` selects `t.*, p.*, r.id as contact_id`**
   (`FA/2.4.3/includes/db/crm_contacts_db.inc:89-91`) — `id`, `type`, `action`,
   `name` and `inactive` all collide between the category row and the person
   row (hazard **H5**). The resolver already works around it by reading
   `person_id`/`contact_id` (`FaContactResolver.php:200-214`). **Any module that
   adopts `get_crm_persons()` directly inherits the hazard** — another reason the
   resolver is the right seam, and another reason the alternative in ambiguity 3
   (build the resolver on `fa-classes`) is unattractive.
9. **`get_crm_persons()` silently falls back to `action = 'general'`**
   (`crm_contacts_db.inc:115-116`): a query for a customer's *invoice* contact
   that finds nothing returns the customer's *general* contact, and the caller
   cannot tell the difference. The resolver inherits this. It must be documented
   at the seam (the inventory flags it at `Contact_Access_Inventory_2026-10.md:625`).
10. **Five CRM sites query `0_crm_persons.first_name` / `last_name`, columns FA's
    person table does not have** — FA has `name` and `name2`
    (`FA/2.4.3/sql/alter2.3.sql:190-208`). The sites are
    `ksf_FA_CRM/includes/crm_relationships_db.inc:60` and `:125`,
    `ksf_FA_CRM/pages/contact_relationships.php:121-122`,
    `ksf_FA_CRM/pages/life_events.php:104`, and
    `ksf_FA_CRM/pages/person_account_roles.php:126`. The vocabulary is
    contaminated from the CRM's own flat, retired contact table
    `0_ksf_crm_contacts` (`sql/ksf_crm_contacts.sql:12-13`). All five fail
    **LOUD** today. `ksf_FA_CRM/pages/org_chart.php:127-128` uses `p_a.name` /
    `p_b.name` correctly, so the estate already knows the right shape — the
    contact resolver (`findById()`, which returns `name`/`name2`) is the fix.

---

*Review produced 2026-10-19. **No source file in any repository was modified.**
Every code claim in this document was checked against the file cited; where this
review contradicts the inventory, the contradiction is stated explicitly with the
evidence, in §0.3, §0.5, and in the relevant section.*
