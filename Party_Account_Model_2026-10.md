# Party & Account Domain Model — Design Document

**Date:** 2026-10-20
**Status:** **Design proposal — nothing implemented, no production code changed.**
**Owner input:** the estate owner's verbal reasoning on party/contact/account
overloading (reproduced in §1.1).
**Governing decisions:** `AGENTS_ARCH.md` §12.2 (native FA data access; the shared
contact resolver) · `Contact_Access_Inventory_2026-10.md` (144 contact-access sites)
· `Contact_Ambiguity_Review_2026-10.md` (11 ambiguities, recommended rulings)
**Companion documents:** this file is the *design*; the *requirements* it is
traceable to are named in §7 and are **not yet written**.

---

## 0. How to read this document

Three kinds of statement appear here and are marked throughout:

| Marker | Meaning |
|---|---|
| **[FA]** | FrontAccounting 2.4.3 already does this. Verified against the source at `ksf_Infrastructure/FA/2.4.3/`, cited `file:line`. |
| **[BUILD]** | We must write it. FA 2.4.3 has no equivalent. |
| **[OPEN]** | Not decided. A product decision or a data migration is required before it can be implemented. |

Every claim about FA is checked against a file. Where FA's behaviour is unclear or
where I could not verify something, this document says so explicitly rather than
assuming.

**FA source tree used for verification:** `/home/kevin/Documents/ksf_Infrastructure/FA/2.4.3/`
(FA version file: `version.php`). All line numbers below refer to that tree.

**The single most important finding of this document** is in §4.1 and is stated here
up front so nobody skims past it:

> FA 2.4.3 has **no data-level clone** for a debtor, a branch, a contact, or a person.
> There is no `copy_customer`, no `clone_debtor`, no `duplicate_branch`. The only
> `clone` in the whole FA tree is a *security-role* clone in the admin UI
> (`admin/security_roles.php:141-162`) and a generic CRUD "Clone" action
> (`includes/ui/class.crud_view.inc:303`, `includes/ui/simple_crud_class.inc:201-226`)
> which re-opens the current record's form fields as a new record — and that
> `simple_crud_class` has **no consumer anywhere in the FA tree**, and neither the
> customer screen (`sales/manage/customers.php`) nor the branch screen
> (`sales/manage/customer_branches.php`) wires any clone affordance.
> **Every clone in this model is therefore [BUILD].**

---

## 1. The vocabulary

### 1.1 The owner's reasoning, and the defect it identifies

> "A physical person can be a customer, a supplier, a user and an employee. So we
> overloaded the PERSON definition."
>
> "A customer (debtor) can be either a company, a family or an individual."
>
> "An individual is a family case with 1 family member (contact)."
>
> "A single person getting married would be similar to a corporate merger or
> buyout — the company name might change but the contact details shouldn't,
> except maybe for position/title? Of course it could also involve
> address/phone/email updates but that can happen outside of a 'merger'
> (marriage)."
>
> "One case we haven't considered/discussed is divorce — splitting an account
> into 2."
>
> "Companies can split off subsidiaries and then possibly sell them."
>
> "Families could shed children as they become adults — they should then have
> their own accounts."
>
> "So we should have a way to soft link debtors."
>
> "People should be able to be associated to multiple organizations anyway — a
> person who is a customer, but who is also on the board of directors of a
> charity or two — so permit the person to be associated rather than requiring
> a duplicate record."
>
> "Of course, wearing the different hats they could have different emails and
> phone numbers, so maybe clone the person but have a link pointing out that it
> is the same person in a different role."

The defect is not that FA has too many columns. It is that **one record type is
made to answer four different questions**: *who is this human being*, *what is
this commercial identity*, *what is this legal/social entity*, and *what is the
role this entity or person plays on this account*. Four questions, four
concepts.

### 1.2 The four concepts

#### PERSON — the physical human being

> **A PERSON is the identity of a human being. It carries no contact details, no
> commercial terms, and no roles.**

A PERSON is *the same human being* regardless of which hats they wear. The
overload the owner identified is precisely that FA's one row has to be "the
customer" and "the employee" and "the supplier" simultaneously, and therefore has
to hold one set of email/phone/address that is correct for none of them.

**The properties that make a PERSON a PERSON:**

| Property | Meaning |
|---|---|
| Identity | Given name, family name, reference, date of birth. |
| Lineage | Which other PERSON it absorbed (a merge), or which PERSON absorbed it. |
| Lifecycle | `active` / `merged` / `deceased`. **Not** FA's `inactive` flag (see §4.4). |
| Cards | Which FA contact records carry this human being's details, and in which role (§4.2). |

**What a PERSON deliberately does not have:** email, phone, fax, address,
company, payment terms, credit limit. Those belong to a *card* (a role-scoped
contact record) or to an *account*.

**Where it lives:** a new table, `0_ksf_common_persons`, owned by
`ksf_FA_Common` **[BUILD]**. It is an *identity* registry, not a *contact*
registry — it does not replace FA's `0_crm_persons`, which remains the only
contact registry in the estate (`AGENTS_ARCH.md` §12.2).

#### PARTY — a legal or social entity that can hold roles

> **A PARTY is a legal or social entity that can hold commercial and social
> roles: a company, a household (family), a sole trader, a trust.**

A PARTY is what an *account* is booked against when the customer is an
organisation, a family, or a single person acting commercially. It has a name, a
type, a tax identity and a lifecycle.

**PARTY is deliberately distinct from PERSON:**

| | PERSON | PARTY |
|---|---|---|
| What it is | a human being | an entity that can hold roles |
| Can it hold a *commercial* role? | no — only via an ACCOUNT it is linked to | yes |
| Examples | "Jane Smith" | "Smith Family", "Acme Ltd", "J. Smith (sole trader)" | 
| Contact details | never | never (the entity's contact details live on its cards) |

A PERSON can be a **member of** a PARTY (spouse of, child of, director of,
shareholder of). That relationship is many-to-many and is what makes "a person
who is a customer and also on the board of a charity" expressible without a
duplicate record — the owner's second-to-last bullet.

**Where it lives:** `0_ksf_common_parties` + `0_ksf_common_party_members`
**[BUILD]**. FA 2.4.3 has **no** party/household/family concept anywhere —
verified: a whole-tree grep of the FA source for `crm_` table names returns
exactly `crm_categories`, `crm_contacts`, `crm_persons`, and no `party`,
`household` or `family` table exists. This is the most genuinely new part of the
model.

#### ACCOUNT — the commercial identity

> **An ACCOUNT is a commercial identity that the business trades with. It has
> branches, contact terms, credit terms, a currency and a ledger.**

**An ACCOUNT is FA's own debtor record.** It is *not* replaced, *not*
re-implemented and *not* copied into a table of ours. **[FA]**

* `0_debtors_master` — `debtor_no` PK, 16 columns: `debtor_no, name, debtor_ref,
  address, tax_id, curr_code, sales_type, dimension_id, dimension2_id,
  credit_status, payment_terms, discount, pymt_discount, credit_limit, notes,
  inactive` (`sql/en_US-new.sql:585-605`). `UNIQUE KEY debtor_ref`.
* `0_cust_branch` — `branch_code` + `debtor_no` composite PK (`sql/en_US-new.sql:549-551`).
* `0_suppliers` — the supplier-side commercial identity (`sql/en_US-new.sql:1691`),
  a **separate table** from `debtors_master`, with `contact VARCHAR(60)` as a
  free-text contact *name* and no email/phone column.

We add a **satellite**, `0_ksf_common_accounts`, that points at those FA rows
and adds the three things FA cannot model: which PARTY the account belongs to,
the account's lifecycle status (`active`/`merged`/`split`/`closed`), and a stable
internal id that our link and role tables can key on without touching FA core.

#### ACCOUNT-PARTY ROLE — the link that says who holds which hat

> **An ACCOUNT-PARTY ROLE is the link that says: this PERSON (or this PARTY)
> holds this role on this account.**

Roles: `customer_contact`, `billing_contact`, `supplier_contact`, `employee`,
`director`, `owner`, `shareholder`, `family_member`, `signatory`, `trustee`.

This is the only place where a role lives. It is the answer to "a physical person
can be a customer, a supplier, a user and an employee" — the four hats are four
rows in one table, each scoped to its own account.

**Where it lives:** `0_ksf_common_account_roles` **[BUILD]**.

### 1.3 The four concepts side by side

| | PERSON | PARTY | ACCOUNT | ACCOUNT-PARTY ROLE |
|---|---|---|---|---|
| Question answered | *Who is this human being?* | *What entity is this?* | *Who do we trade with?* | *In what capacity?* |
| Cardinality | one human being | one entity | one commercial identity | one (subject, role, account) triple |
| Key | `0_ksf_common_persons.id` | `0_ksf_common_parties.id` | `0_debtors_master.debtor_no` (+ our `id`) | `0_ksf_common_account_roles.id` |
| Contact details | **never** | **never** | never (FA has no email/phone columns) | via the linked card |
| Commercial terms | never | never | **yes** (credit limit, terms, currency) | never |
| Lives in FA core? | no — FA's `0_crm_persons` is a *card* | no | **yes** | no |
| Many-to-many with? | PARTY (membership), ACCOUNT (role) | PERSON (membership), ACCOUNT (via `party_id`) | PERSON/PARTY (role) | — |

### 1.4 Why PERSON must not be overloaded — the concrete failure it prevents

FA's own screens already create **one person row per contact**, not one per
human being:

* `sales/manage/customers.php:121-126` — `add_crm_person(...)` then
  `add_crm_contact('cust_branch','general',$branch,$pers_id)` **and**
  `add_crm_contact('customer','general',$debtor_no,$pers_id)`. One person, two
  relations.
* `sales/manage/customer_branches.php:99-105` — creates **another** person row
  for the branch contact, with `add_crm_person($_POST['contact_name'], …)`.

So a customer who is invoiced at two branches, or who is both a customer and a
supplier, is **two or three `0_crm_persons` rows** today. Nothing links them.
That is the overload in its purest form: the estate cannot answer "are these the
same person?" — and the owner's "clone the person but have a link pointing out
that it is the same person in a different role" is exactly the repair.

Under this model:

* the **PERSON** is the anchor (one row per human being);
* each FA `0_crm_persons` row is a **CARD** for that person, carrying the
  contact details for one hat;
* the card↔person mapping is `0_ksf_common_person_cards`.

**The vocabulary of §1.2 does not contradict ambiguity 1** of the review
("'contact' means a person and only a person"). We keep that ruling: a
**contact** is a person-record, never a type and never a relation. What this
document adds is a distinction *above* it: the estate now recognises that **one
human being may be recorded by more than one contact record**, and names the
human being **PERSON** and the role-scoped record **CARD**. That is an addition
to the vocabulary, not a redefinition of "contact". It does, however, need one
sentence added to `AGENTS_ARCH.md` §12.2 so that a module author knows that
"a contact" is not necessarily "the person" — flagged as **[OPEN] OQ-1** in §9.

### 1.4a How the owner's "hats" map onto the model

| Hat | Where the role lives | FA support |
|---|---|---|
| customer | ACCOUNT-PARTY ROLE `customer_contact` on a customer ACCOUNT | **[FA]** `add_crm_contact('customer','general',$debtor_no,$person_id)` (`includes/db/crm_contacts_db.inc:251`) |
| supplier | ACCOUNT-PARTY ROLE `supplier_contact` on a supplier ACCOUNT | **[FA]** `add_crm_contact('supplier','general',$supplier_id,$person_id)`; FA seeds `supplier/{general,order,delivery,invoice}` categories (`sql/alter2.3.sql:174-186`) |
| user | `fa_user_id` on the PERSON | **[FA]** `0_users` (`sql/en_US-new.sql:2062`) — **no** link to `0_crm_persons` exists in FA, so the link is ours **[BUILD]** |
| employee | PARTY membership `member_role='employee'` in the employing organisation + HRM's employment satellite | **[FA]** `0_crm_categories` already seeds `employee/general` in HRM (`ksf_FA_HRM/sql/crm_categories.sql:5-8`); **[BUILD]** the membership row and the `fa_user_id` link |
| director / owner | PARTY membership `member_role='director'\|'owner'` in the company PARTY | **[BUILD]** — FA has no such concept; can be expressed FA-natively as a `0_crm_contacts` row of a new category type (see §3.4) |
| family member | PARTY membership `member_role='spouse'\|'child'\|'member'` in a household PARTY, plus ACCOUNT-PARTY ROLE `family_member` on the household's ACCOUNT | **[BUILD]** — no FA equivalent at all |

---

## 2. How individuals and families fit

### 2.1 The individual is a family of one

The owner's rule — *"An individual is a family case with 1 family member
(contact)"* — is implemented literally:

* A **household PARTY** (`party_type='household'`) has one or more **members**.
* A **single individual** is a household PARTY with exactly **one** member.

To keep that rule enforceable rather than aspirational, `party_type` carries
`'individual'` as a first-class value, with the invariant:

> **`party_type='individual'` ⟺ exactly one member row, whose `member_role` is
> `'member'`.**

The two readings are interchangeable, and the model does not force a choice
between them at the data level: a household that happens to have one member
*is* an individual. The `party_type` value exists so that screens can say
"Individual" vs "Family" without counting members at query time, and so that the
invariant can be checked.

### 2.2 Where the spouse and the child appear

Neither the spouse nor the child is a field on the family account. Each is:

1. a **PERSON** of their own (`0_ksf_common_persons`);
2. a **member** of the household PARTY (`0_ksf_common_party_members`,
   `member_role='spouse'` / `'child'`);
3. a **holder of a role** on the household's ACCOUNT
   (`0_ksf_common_account_roles`, `role_code='family_member'`), optionally
   scoped to a branch (`branch_code`).

The spouse is usually also a **card** on the household account — a separate
`0_crm_persons` row linked by `add_crm_contact('customer','general',$debtor_no,…)`
— so the household receives mail at the shared address and the spouse receives
mail at their own. That is the *card* concept doing its job: one human being's
details in two places is two cards of one person, not two people.

### 2.3 The family shedding a child who becomes an adult

The owner's third-from-last bullet. The sequence:

```
1. CHILD is born / joins:  PARTY(household) --member(child, member_role='child')
                            ACCOUNT(home)     --role(child, 'family_member')
                            CARD(child)       -> 0_crm_persons row

2. CHILD turns 18 and needs their own account:      [PROMOTE, §3.4]
   a. new PARTY(party_type='individual') created, with the child as its single member
   b. new ACCOUNT created in FA (add_customer + add_branch)  [FA primitives]
   c. ACCOUNT-PARTY ROLE(child, 'family_member') on the old account -> status='ended',
      end_date = promotion date
   d. ACCOUNT-PARTY ROLE(child, 'customer_contact') on the new account created
   e. the child's CARD is MOVED to the new account, or CLONED (clone-with-link)
      depending on whether the child's email/phone is their own or the family's
   f. optional ACCOUNT_LINK(new, old, 'split_from') so the household account
      still shows "our son has his own account now"

3. The membership in the household PARTY may persist (the child still lives
   there) while the ACCOUNT relationship ends. Membership and account role are
   different facts with different end dates.
```

The split between "lives at home" (party membership) and "trades with us as a
separate customer" (account role) is what makes step 2 possible without
destroying the family record.

### 2.4 How this maps onto FA branches

FA's branch (`0_cust_branch`) is a *delivery/billing location of one account*.
The estate must not use it as a family member — a branch is not a person and a
person is not a branch.

The mapping the model uses:

| Family concept | Model | FA representation |
|---|---|---|
| The household | ACCOUNT (`debtors_master`) + PARTY (household) | one debtor, its default branch |
| The family's address | the ACCOUNT's branch address + the cards' addresses | `0_cust_branch.br_address`, `0_crm_persons.address` |
| A family member | PERSON + card + ACCOUNT-PARTY ROLE | a `0_crm_persons` row linked by `add_crm_contact('customer', …)` |
| A family member who trades separately | their own ACCOUNT | a second `debtors_master` row |
| A branch of the household (e.g. "the cottage") | a FA branch | `0_cust_branch` |

**[FA]** note: a customer normally needs a branch — FA's customer screen
auto-creates one when the company preference `auto_create_branch` is set
(`sales/manage/customers.php:111-119`) and the branch screen is the mandatory
child record (`sales/manage/customer_branches.php`).
So every ACCOUNT this model creates gets at least one branch, and the branch's
`debtor_no` is what the account's contacts are attached to *in addition to* the
debtor-level relation. This is exactly the two-relations-per-person pattern at
`sales/manage/customers.php:124-126`, and exactly the ambiguity the review
raises at §5 (branch contact vs customer contact). Our role table can carry
`branch_code` so that "the contact for the cottage branch" is expressible
without inventing a FA column.

---

## 3. Account lifecycle operations

Seven operations. Each is specified as: **inputs → preconditions → effects →
what FA does natively → what we build**.

### 3.0 Summary

| # | Operation | One-line spec |
|---|---|---|
| 1 | **MERGE** | Fold account B into account A: contacts move, A is renamed, B is retired and soft-linked to A. |
| 2 | **SPLIT** | One account becomes two: a new account is created, selected branches/contacts move, a `split_from` link is written. |
| 3 | **SPIN-OFF** | A company separates a subsidiary into its own account and (optionally) sells it; ownership and `spin_off`/`sold` links are recorded. |
| 4 | **PROMOTE** | A family member (or any member) leaves the household account and gets an account of their own. |
| 5 | **SOFT LINK** | Declare a typed, dated, reversible relationship between two accounts without moving any data. |
| 6 | **ASSOCIATE** | Attach a person to a party (board member, shareholder, employee) with a role and optional role-scoped contact card. |
| 7 | **CLONE-WITH-LINK** | Copy a person's contact record for a different hat and record the shadow→root link. |

### 3.1 What FA 2.4.3 gives us, and what it does not

**[FA] — available primitives, verified:**

| Native function | Location | What it gives |
|---|---|---|
| `add_customer(14 args)` | `sales/includes/db/customers_db.inc:13` | creates a `debtors_master` row. **Returns nothing** — the caller must read `db_insert_id()` (FA's own code does exactly that at `sales/manage/customers.php:109`) |
| `update_customer(15 args)` | `sales/includes/db/customers_db.inc:30` | updates name/ref/address/tax_id/currency/dimensions/credit status/terms/discounts/credit limit/sales type/notes. **Does not carry `inactive`** |
| `delete_customer($id)` | `sales/includes/db/customers_db.inc:53` | deletes the debtor **and** its `customer`-type contacts (`delete_entity_contacts('customer',…)`) inside a transaction |
| `add_branch(...)` / `update_branch(...)` / `delete_branch(...)` | `sales/includes/db/branches_db.inc:12/39/65` | branch CRUD; `delete_branch` also removes `cust_branch`-type contacts |
| `add_crm_person(...)` | `includes/db/crm_contacts_db.inc:13` | creates a person row; **returns the new id** |
| `update_crm_person(...)` | `includes/db/crm_contacts_db.inc:43` | updates a person and their contact categories |
| `add_crm_contact($type,$action,$entity_id,$person_id)` | `includes/db/crm_contacts_db.inc:251` | creates a person↔entity relation |
| `delete_crm_contact($id)` / `delete_crm_contacts(...)` | `includes/db/crm_contacts_db.inc:263/272` | removes relations |
| `delete_entity_contacts($class,$entity)` | `includes/db/crm_contacts_db.inc:176` | removes every relation of an entity, and cleans up persons left with no contacts |
| `add_crm_category` / `update_crm_category` / `get_crm_categories` / `get_crm_category_name` | `includes/db/crm_contacts_db.inc:191/202/222/238` | the category catalogue |
| `get_customer($id)` / `get_customer_name` / `get_customer_details` / `get_customer_by_ref` / `get_customer_contacts` | `sales/includes/db/customers_db.inc:118/127/66/179/151` | reads of the account |
| `get_crm_persons($type,$action,$entity,$person,$unique)` | `includes/db/crm_contacts_db.inc:87` | the relation query — **an INNER JOIN over `crm_contacts`** (`:89-91`), so a person with no relation is invisible |
| `get_branch_contacts($branch,$action,$customer,$default)` | `sales/includes/db/branches_db.inc:181` | branch contacts **union** customer contacts, and (with `$default=true`) returns the one FA considers the default for that action |
| `get_cust_branch($customer,$branch)` / `get_branch($id)` / `get_sql_for_customer_branches($customer)` | `sales/includes/db/branches_db.inc:96/82/142` | branch reads |
| `update_record_status($id,$status,$table,$key)` | `includes/db/sql_functions.inc:58` (**auto-loaded**, `includes/main.inc:18`) | sets a record's `inactive` flag — **this is how FA's own customer screen deactivates a customer** (`sales/manage/customers.php:94-95`), and therefore how an account is retired |

**[FA] — the two gaps that matter here:**

1. **No clone of anything** (§0). A clone must be composed from the primitives
   above.
2. **FA's native functions never expose `crm_contacts.entity_id`**
   (`get_crm_persons` selects `t.*, p.*, r.id AS contact_id`;
   `get_crm_contact` selects `t.type, t.action, p.*, r.person_id, r.id` —
   `includes/db/crm_contacts_db.inc:89-91`, `:291-301`). So the relation can be
   walked **account → contacts** but never **person → accounts**, without raw
   SQL. This is the gap the review records at §4.

**A gap that is *not* there.** `update_customer()` does not carry the
`inactive` column, and the only two statements in the FA tree that touch
`debtors_master` are the INSERT and the UPDATE in `customers_db.inc` — but
**retiring an account does not need a raw UPDATE**. FA ships
`update_record_status($id,$status,$table,$key)` (`includes/db/sql_functions.inc:58`,
auto-loaded by `includes/main.inc:18`), and its own customer screen uses it
that way (`sales/manage/customers.php:94-95`). Deactivating a debtor is
therefore **[FA]**, and no exception to §12.2 is required for it.

**[BUILD] — the composition layer we need:**

| Component | Why |
|---|---|
| `cloneContactCard()` | No FA clone; §3.7 |
| `cloneAccount()` | No FA clone; used by SPLIT and SPIN-OFF (§3.2, §3.3) |
| `moveContact()` | `add_crm_contact` + `delete_crm_contact` are native, but the *decision* + the audit row are ours |
| `retireAccount()` | a thin wrapper over `update_record_status()` — the FA-native flag plus our `account_status` row |
| Role/link/event bookkeeping | our tables |
| Reconciliation job | our tables can drift from FA's relations |

### 3.2 MERGE

**Covers:** marriage (two individuals become one household account); corporate
merger or buyout (one company absorbs another); brand rename (same account,
new name).

**Inputs** (`MergeRequest`):
`survivingAccountId`, `absorbedAccountId`, `variant` (`marriage` | `corporate`
| `buyout` | `rename`), `newName?`, `newRef?`, `movedContactIds[]`,
`titleChanges[{personId,title}]`, `reason`, `actor`, `effectiveDate`.

**Preconditions**
1. Both accounts exist in `0_ksf_common_accounts` and are distinct.
2. The surviving account is not already `merged`/`split`/`closed`.
3. The absorbed account has no operation in flight (no pending split/spin-off).
4. Every `movedContactIds[]` entry is a contact of the **absorbed** account.
5. No contact of the absorbed account is simultaneously a contact of the
   surviving account *with the same role* — a conflict that must be resolved
   explicitly (rule: the surviving account's role wins; the absorbed row is
   ended, not duplicated).
6. `newRef`, if given, is not already in `0_debtors_master.debtor_ref`
   (**[FA]** `UNIQUE KEY debtor_ref`, `sql/en_US-new.sql:604`).

**Effects**
* **Name / ref:** `update_customer()` on the surviving account with the new
  name/ref **[FA]**. Contact details are **not** touched — the owner's point:
  "the company name might change but the contact details shouldn't".
* **Title / position:** `update_crm_person()` per affected card **[FA]** — this
  is the one contact field a merge may legitimately change, and it is changed
  on the *card*, not on the PERSON.
* **Contacts:** for each moved contact, `add_crm_contact()` on the surviving
  account then `delete_crm_contact()` on the absorbed one **[FA] primitives**;
  the *choice* of what moves, and the audit row, are **[BUILD]**.
* **Address / phone / email:** **not** changed by the merge. The owner's second
  sentence — "it could also involve address/phone/email updates but that can
  happen outside of a 'merger' (marriage)" — is honoured literally: **the merge
  operation does not carry a contact-details edit.** Such an edit is an
  ordinary card update, done separately, and is auditable as such.
* **Account lifecycle:** the surviving account stays `active`. The absorbed
  account is **deactivated, not deleted** — `update_record_status($debtor_no, 1,
  'debtors_master', 'debtor_no')` **[FA]** (`includes/db/sql_functions.inc:58`,
  the same call FA's own customer screen makes at
  `sales/manage/customers.php:94-95`) — and our satellite marks it `merged`
  with `merged_into_account_id` set **[BUILD]**. `delete_customer()` is **not**
  used: it would delete the absorbed account's contacts and destroy the ledger
  context the soft link is supposed to preserve.
* **Soft link:** `ACCOUNT_LINK(absorbed, surviving, 'successor')` and
  `ACCOUNT_LINK(surviving, absorbed, 'predecessor')` **[BUILD]**.
* **Events:** one `ACCOUNT_EVENT` row per merge **[BUILD]**.
* **Transaction re-pointing:** **NOT DONE** — see §6.3 and **[OPEN] OQ-4**.

**Marriage specifically.** Marriage is a MERGE of two *individual* accounts into
one *household* account. The two individuals are already two PERSONs; the merge
creates the household PARTY, adds both as members (`member_role='spouse'` for
one, `'member'` for the other), and merges the two accounts into one debtor.
**The two PERSONs are not merged** — two human beings remain two human beings.
This is the clearest illustration of why PERSON and PARTY must be separate: a
marriage changes the *party structure* and the *account*, not the *persons*.

**Corporate merger / buyout.** Same mechanics on the account side, plus: the
absorbed company PARTY is marked `merged` with `merged_into_party_id` set, and
its directors/owners become members of the surviving party (with
`end_date` on their old membership rows) — **[BUILD]**.

**Brand rename.** The degenerate case: `variant='rename'`, no contacts moved, no
account retired. Only `update_customer()` is called **[FA]**. **This is the only
merge variant that is safe to implement and ship now** (§6.2).

### 3.3 SPLIT

**Covers:** divorce (one household account becomes two); a subsidiary leaving
the group (handled by SPIN-OFF, §3.3); a family member leaving (handled by
PROMOTE, §3.4).

**Inputs** (`SplitRequest`):
`sourceAccountId`, `newAccountName`, `newAccountRef`, `newPartyType`
(default `individual`), `keepBranchCodes[]`, `movedContactIds[]`,
`keepBalanceOnSource` (default `true`), `reason`, `actor`, `effectiveDate`.

**Preconditions**
1. The source account exists and is `active`.
2. `newAccountRef` is unique in `0_debtors_master` **[FA]**.
3. `keepBranchCodes[]` are branches of the source account.
4. The source account has at least one branch that stays (FA invoices against a
   branch) **[FA]** `sales/includes/db/branches_db.inc` / the sales screens.
5. `movedContactIds[]` are contacts of the source account.

**Effects**
1. **New account:** `add_customer()` **[FA]** → read the new `debtor_no` with
   `db_insert_id()` **[FA]** (`db_insert_id` at
   `includes/db/connect_db_mysqli.inc:173`). `add_customer()` takes 14
   arguments and **returns nothing** (`customers_db.inc:13-28`) — the clone must
   supply every field (dimensions, credit status, terms, discounts, sales type)
   explicitly. **[BUILD]** for the copy of those fields.
2. **New branch:** `add_branch()` for the moved branch(es) **[FA]**.
3. **New party + membership:** `PARTY(newAccountName, party_type='individual')`
   with the moving person as its single member; the source's household party
   loses that member or marks the membership `end_date` **[BUILD]**.
4. **Contacts:** two strategies, chosen per contact:
   * **MOVE** — `delete_crm_contact()` on the source, `add_crm_contact()` on
     the new account **[FA] primitives**. Use when the contact's details are
     the moving person's alone.
   * **CLONE-WITH-LINK** (§3.7) — keep the source's card, create a card for the
     new account. Use when the details are **shared** (the family mailbox) and
     the business wants the history to remain visible on both accounts.
   *Default: CLONE for contacts whose email is shared with a person remaining
   on the source account; MOVE otherwise.* **[BUILD]** — the rule is ours; FA
   has no opinion.
5. **Old account:** stays `active`; the moved branch is deleted with
   `delete_branch()` (**[FA]**, which also removes its `cust_branch` contacts).
6. **Link:** `ACCOUNT_LINK(new, source, 'split_from')` **[BUILD]**.
7. **Balances:** **the balance stays on the source account by default**
   (`keepBalanceOnSource=true`). No transaction rows are touched. **[OPEN]
   OQ-5** — the commercial treatment of a divorce (who keeps the credit limit,
   who keeps the debt) is a product decision, and FA gives us no ledger-level
   merge/split at all.

**What "soft link" means for a split:** the two accounts remain **independent
commercial identities**. The link records the historical fact ("these two
accounts were one until 2026-03-14") and makes the pair discoverable from both
sides. It does **not** mean shared balances, shared credit, or shared
branches.

### 3.4 SPIN-OFF

**Covers:** "Companies can split off subsidiaries and then possibly sell them."

**Inputs** (`SpinOffRequest`):
`sourceAccountId`, `newAccountName`, `newAccountRef`, `newPartyName`,
`movedBranchCodes[]`, `movedContactIds[]`, `ownershipPercent?`,
`soldToPartyId?`, `saleDate?`, `reason`, `actor`.

**Preconditions** — as SPLIT, plus: the source account's PARTY is a company
(`party_type='company'`); the new PARTY is created as a company.

**Effects**
1. New ACCOUNT + branches + party, as in SPLIT **[FA primitives + BUILD]**.
2. Ownership: the source party's membership in the new party is recorded as
   `member_role='shareholder'` with `ownership_percent` **[BUILD]**. (FA has no
   ownership concept; the CRM's declared-but-unread
   `0_ksf_crm_account_relationships.ownership_pct`
   (`ksf_FA_CRM/sql/ksf_crm_account_relationships.sql`) shows the shape the
   estate already had in mind — but that table is superseded, see §6.5.)
3. **The sale:** `ACCOUNT_LINK(new, source, 'spin_off')` with `effective_date`
   = separation date; and, if sold, `ACCOUNT_LINK(new, buyerPartyAccountId,
   'sold')` with `effective_date` = sale date **[BUILD]**. The sold entity
   stays in FA with its own account; **it is not deleted** — FA has no
   "sold" state and deletion would destroy its ledger.
4. **The ledger:** the spun-off company's branches must post to **its own** GL
   accounts (`sales_account`, `receivables_account`,
   `sales_discount_account`, `payment_discount_account`,
   `0_cust_branch`). `add_branch()` takes all of them as arguments
   **[FA]**, so the separation is possible — but **which** GL accounts the new
   company posts to is an accounting decision we cannot make. **[OPEN] OQ-6.**

**Distinction from SPLIT:** SPLIT divides one *household* into two households
and involves no ownership. SPIN-OFF separates a *company* from a company and
involves ownership and possibly a third party (the buyer). The mechanical steps
overlap; the semantics differ, so they are separate operations with separate
requirements.

### 3.5 PROMOTE

**Covers:** "Families could shed children as they become adults — they should
then have their own accounts."

**Inputs** (`PromoteRequest`):
`householdAccountId`, `personId`, `newAccountName`, `newAccountRef`,
`contactStrategy` (`move` | `clone`), `keepHouseholdMembership` (default
`true`), `reason`, `actor`.

**Preconditions**
1. The person is a member of the household PARTY and holds a
   `family_member` ACCOUNT-PARTY ROLE on the household ACCOUNT.
2. `newAccountRef` is unique **[FA]**.

**Effects**
1. New ACCOUNT (individual) + default branch **[FA primitives]**.
2. New PARTY `party_type='individual'` with the person as its single member
   **[BUILD]**.
3. The `family_member` role on the household account is **ended**
   (`status='ended'`, `end_date`) — not deleted, so the history survives
   **[BUILD]**.
4. A `customer_contact` role is created on the new account **[BUILD]**.
5. The person's card is MOVED (delete+add) or CLONED (§3.7) per
   `contactStrategy` **[FA primitives + BUILD]**.
6. If `keepHouseholdMembership`, the party membership row stays with
   `member_role` unchanged; the *account* relationship is what ended. If not,
   the membership is ended too.
7. Optional `ACCOUNT_LINK(new, household, 'split_from')` **[BUILD]**.

### 3.6 SOFT LINK

**Covers:** "So we should have a way to soft link debtors."

**What links to what.** Three kinds of link, and they are not the same thing:

| Link | Between | Stored? | Why |
|---|---|---|---|
| **Structural** — successor/predecessor, spin-off, split-from, sold | ACCOUNT ↔ ACCOUNT | **yes**, in `0_ksf_common_account_links` | historical/commercial facts FA cannot hold; they need dates and types |
| **Shared subject** — two accounts touched by the same person or party | ACCOUNT ↔ ACCOUNT (via a shared PERSON/PARTY) | **derived**, not stored | it is a *query* over `0_ksf_common_account_roles`; storing it would create a third thing to keep in sync |
| **Card link** — two FA person rows that are the same human being | CARD ↔ CARD | **yes**, in `0_ksf_common_person_cards` | the root↔shadow mapping (§3.7) |

**Inputs** (`AccountLinkRequest`): `fromAccountId`, `toAccountId`, `linkType`,
`effectiveDate?`, `endDate?`, `notes`.

**Preconditions:** both accounts exist; the pair+type is not already linked
(**[BUILD]** unique key); `linkType` is one of the catalogue values.

**Effects**
1. Insert the link row **[BUILD]**.
2. Optional **breadcrumb in FA**: append a line to the surviving account's
   `notes` via `update_customer()` **[FA]** — note that `update_customer()`
   rewrites the whole row, so the implementation must read the current row
   (`get_customer()`), concatenate, and write back **[BUILD]**. This is
   cosmetic-but-useful: FA's own customer screen then shows the link without
   our module being installed.
3. **How it is queried** — the three queries the model must support:
   * *direct*: `SELECT * FROM 0_ksf_common_account_links WHERE from_account_id = ?`
   * *transitive*: a recursive walk over `link_type='successor'` to answer "is B
     the successor of A, possibly through C?"
   * *by shared subject*: `SELECT DISTINCT account_id FROM
     0_ksf_common_account_roles WHERE subject_kind='person' AND subject_id = ?`
     — this is the "shared person" soft link, derived **[BUILD]**.

### 3.7 CLONE-WITH-LINK

**Covers:** "wearing the different hats they could have different emails and
phone numbers, so maybe clone the person but have a link pointing out that it
is the same person in a different role."

**Inputs** (`CloneCardRequest`):
`rootPersonId`, `sourceCardCrmPersonId?` (defaults to the person's primary
card), `scopeRole` (the new hat: `customer`, `supplier`, `employee`,
`board_member`, …), `overrides{email, phone, phone2, fax, address, name?,
name2?, notes?}`, `targetAccountId?`, `targetPartyId?`.

**Preconditions**
1. The root PERSON exists.
2. `scopeRole` is supplied and non-empty — a shadow without a role is a
   mistake, not a clone (**[BUILD]** validation).
3. The overrides differ from the source card in at least one contact field
   (**[BUILD]** validation — see "legitimate vs mistake" below).

**Effects**
1. `add_crm_person($ref, $name, $name2, $address, $phone, $phone2, $fax,
   $email, $lang, $notes)` — the **native** person creation, which **returns
   the new id** **[FA]** (`includes/db/crm_contacts_db.inc:13-41`).
2. Insert `0_ksf_common_person_cards(root_person_id, new_crm_person_id,
   card_kind='shadow', scope_role)` **[BUILD]**.
3. If `targetAccountId`: `add_crm_contact('customer','general',$debtor_no,
   $new_id)` (or the appropriate category type) **[FA]**.
4. If `targetPartyId`: `add_crm_contact(<party_member type>, <action>,
   $party_id, $new_id)` **[FA]** — see §3.8.
5. Event row **[BUILD]**.

**Link direction.** The row always points **shadow → root**:
`0_ksf_common_person_cards.person_id` is the **root** PERSON and
`.crm_person_id` is the **card**. The root is the row whose `card_kind` is
`'primary'`. The direction is a tree, not a graph: there is exactly one root per
human being, and every shadow points at it. **[BUILD]**

**The "same person in a different role" marker.** Two columns together:
`card_kind` (`'primary' | 'shadow'`) and `scope_role` (the hat). A shadow with
`scope_role='supplier'` is the same human being, wearing the supplier hat.

**When a shadow is legitimate, and when it is a mistake.**

| | Legitimate shadow | Mistake |
|---|---|---|
| Same human being? | yes, provably | no — a second, different person |
| Different contact details? | **yes** — that is the whole point | no — identical email *and* phone |
| Distinct role declared? | yes (`scope_role` non-empty) | no |
| Contact history? | the shadow carries the *new* hat's correspondence | the shadow duplicates the original's history |
| Resolution | keep | **merge the cards into one** (the two rows are one human) or **re-point the second row to a different root person** |

**Rule:** a shadow whose email **and** phone **and** fax all equal the root's,
and which declares no distinct role, is a **probable duplicate** and must be
reported by the reconciliation job (§6.4) rather than silently accepted.
A shadow that differs in exactly one field — say the email — is the legitimate
"same human, work address vs home address" case.

### 3.8 ASSOCIATE

**Covers:** "a person who is a customer, but who is also on the board of
directors of a charity or two — so permit the person to be associated rather
than requiring a duplicate record."

**Inputs** (`AssociateRequest`):
`personId`, `partyId`, `memberRole` (`director`, `shareholder`, `employee`,
`trustee`, `officer`, `member`), `startDate?`, `endDate?`,
`roleScopedCard` (bool, default `false`), `roleContactOverrides?`.

**Preconditions**
1. The PERSON exists; the PARTY exists.
2. The (party, person, role) triple is not already present **[BUILD]** unique key.
3. If `roleScopedCard` is requested, the person has a primary card to clone
   from.

**Effects**
1. Insert `0_ksf_common_party_members` **[BUILD]**.
2. **FA-native expression (recommended):** create a `0_crm_contacts` row of a
   dedicated category type so that the association is visible in FA's own
   contact screens and reachable through the shared resolver:
   `add_crm_contact('party_member', $memberRole, $party_id, $person_id)`
   **[FA]** + a `0_crm_categories` row seeded with `add_crm_category('party_member',
   $memberRole, …)` **[FA]** (`crm_categories` has `UNIQUE KEY(type, action)`,
   `sql/alter2.3.sql:170`, so each (type, action) pair is one row). **[BUILD]**
   for the category seeding and for the per-role catalogue.
   *This is the FA-native answer to the review's ambiguity 9 ruling ("a contact
   role becomes an FA `crm_categories` row") and it is consistent with it.*
3. If `roleScopedCard`: run **CLONE-WITH-LINK** with `scope_role =
   'party_member:' . $memberRole` and `targetPartyId` — the board role then has
   its own email/phone, which is exactly the owner's "different hats, different
   emails" requirement **[BUILD]**.
4. Event row **[BUILD]**.

**Why this is not a duplicate record:** the person's *identity* row is shared.
A board role at a charity and a customer role at a shop are two rows in
`0_ksf_common_party_members` / `0_ksf_common_account_roles`; the human being
is one PERSON with two cards.

---

## 4. The schema

### 4.1 Ownership map

| Table | Owner | Status |
|---|---|---|
| `0_crm_persons` | **FA core** | the contact record. One row = one role-scoped **card**. Not replaced. |
| `0_crm_contacts` | **FA core** | the person↔entity relation. Not replaced. |
| `0_crm_categories` | **FA core** | the (type, action) catalogue. Extended natively with our role types. |
| `0_debtors_master` | **FA core** | **the ACCOUNT.** Not replaced, not copied. |
| `0_cust_branch` | **FA core** | the account's branches. Not replaced. |
| `0_suppliers` | **FA core** | the supplier-side ACCOUNT. Not replaced. |
| `0_users` | **FA core** | the system user. Not replaced; linked to a PERSON by our column. |
| `0_ksf_common_persons` | **ksf_FA_Common** | **new** — the PERSON identity |
| `0_ksf_common_person_cards` | **ksf_FA_Common** | **new** — card ↔ root mapping |
| `0_ksf_common_parties` | **ksf_FA_Common** | **new** — the PARTY |
| `0_ksf_common_party_members` | **ksf_FA_Common** | **new** — person ↔ party, many-to-many |
| `0_ksf_common_accounts` | **ksf_FA_Common** | **new** — the account satellite |
| `0_ksf_common_account_roles` | **ksf_FA_Common** | **new** — the ACCOUNT-PARTY ROLE |
| `0_ksf_common_account_links` | **ksf_FA_Common** | **new** — account soft links |
| `0_ksf_common_account_events` | **ksf_FA_Common** | **new** — the operation journal |

Naming convention: `0_ksf_<module>_<noun>` with `module = common`
(the `ksf_FA_Common` module code is `COM`, and its tables are already
`0_ksf_*`: `0_ksf_contact_types`, `0_ksf_notifications`, `0_ksf_wf_state` —
`ksf_FA_Common/sql/install.sql`). **`0_fa_*` is never used** (it is FA core's
reserved segment, `AGENTS_ARCH.md` §12).

### 4.2 The person side, and how it relates to FA's person table

```
0_ksf_common_persons                0_crm_persons  (FA core)
┌───────────────────────────┐        ┌───────────────────────────┐
│ id            PK          │        │ id            PK          │
│ person_ref     UNIQUE     │        │ ref, name, name2          │
│ given_name                │        │ address, phone, phone2    │
│ family_name               │        │ fax, email, lang, notes   │
│ date_of_birth             │        │ inactive                  │
│ gender                    │        └────────────▲──────────────┘
│ fa_user_id      ──────────┼──► 0_users.id    │
│ status                   │        ┌────────────┴──────────────┐
│ merged_into_person_id     │        │ 0_ksf_common_person_cards │
│ notes, created_at, upd   │        │ person_id      FK ──────────┤
└───────────────────────────┘        │ crm_person_id  FK (FA)     │
                                    │ card_kind  primary|shadow  │
                                    │ scope_role  'customer'…    │
                                    │ UNIQUE (person_id, crm_person_id) │
                                    └───────────────────────────┘
```

**Rules that make this coherent:**

1. `0_ksf_common_persons` carries **no contact columns at all**. If a column
   named `email`, `phone` or `address` is ever added to it, the model has been
   broken. **[BUILD — review rule]**
2. Every `0_crm_persons` row that the estate knows about has exactly one
   `0_ksf_common_person_cards` row: `card_kind='primary'` for the card chosen
   as the person's canonical one, `'shadow'` for the rest. **[BUILD]**
3. The root person may be created **lazily**: the first time the estate touches
   an FA person that has no root, a root is created and a primary card row is
   inserted. This is what makes the model adoptable without a big-bang
   migration. **[BUILD]**
4. `merged_into_person_id` is the PERSON-level merge lineage. It is **not** the
   same thing as a card merge and **not** the same as an account merge.

### 4.3 Column specification

All tables: `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`,
`created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`,
`updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`,
prefixed `0_` so FA's install engine (`db_import()`, which replaces only the
literal `0_` → `TB_PREF`) picks them up — see `AGENTS.md`, "SQL prefix
convention in module `sql/` files".

#### `0_ksf_common_persons`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT(11) | no | PK AI |
| `person_ref` | VARCHAR(30) | no | **UNIQUE**; our stable handle (`P-000123`) |
| `given_name` | VARCHAR(60) | no | |
| `family_name` | VARCHAR(60) | yes | |
| `date_of_birth` | DATE | yes | PII — subject to the column-level ACL design |
| `gender` | CHAR(1) | yes | |
| `fa_user_id` | SMALLINT(6) | yes | → `0_users.id`; the "user" hat. **UNIQUE** when not null |
| `status` | ENUM('active','merged','deceased') | no | default `active` |
| `merged_into_person_id` | INT(11) | yes | self-FK; PERSON merge lineage |
| `notes` | TEXT | yes | identity notes, **not** contact notes |
| `created_at`, `updated_at` | TIMESTAMP | | |

KEYS: `UNIQUE(person_ref)`, `UNIQUE(fa_user_id)`, `KEY(family_name,given_name)`,
`KEY(status)`, `KEY(merged_into_person_id)`.

#### `0_ksf_common_person_cards`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT(11) | no | PK AI |
| `person_id` | INT(11) | no | FK → `0_ksf_common_persons.id` (the ROOT) |
| `crm_person_id` | INT(11) | no | FK → FA `0_crm_persons.id` (the CARD) |
| `card_kind` | ENUM('primary','shadow') | no | default `primary' |
| `scope_role` | VARCHAR(30) | no | the hat this card carries (`customer`, `supplier`, `employee`, `party_member:director`…) |
| `status` | ENUM('active','retired') | no | default `active' |
| `notes` | TEXT | yes | |
| `created_at`, `updated_at` | TIMESTAMP | | |

KEYS: `UNIQUE(person_id, crm_person_id)`, `UNIQUE(crm_person_id)` (one root per
card), `KEY(person_id)`, `KEY(scope_role)`.
*Application rule (no partial indexes in MySQL/MariaDB): exactly one
`card_kind='primary'` row per `person_id`.*

#### `0_ksf_common_parties`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT(11) | no | PK AI |
| `party_ref` | VARCHAR(30) | no | **UNIQUE** (`PTY-000123`) |
| `name` | VARCHAR(100) | no | the entity's trading/display name |
| `party_type` | ENUM('company','sole_trader','household','individual','trust','other') | no | |
| `tax_id` | VARCHAR(55) | yes | the entity's tax identity |
| `registration_no` | VARCHAR(50) | yes | company registration number |
| `status` | ENUM('active','merged','dissolved','split') | no | default `active' |
| `merged_into_party_id` | INT(11) | yes | self-FK |
| `notes` | TEXT | yes | |
| `created_at`, `updated_at` | TIMESTAMP | | |

KEYS: `UNIQUE(party_ref)`, `KEY(name)`, `KEY(party_type)`, `KEY(status)`.

#### `0_ksf_common_party_members`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT(11) | no | PK AI |
| `party_id` | INT(11) | no | FK → parties |
| `person_id` | INT(11) | no | FK → persons |
| `member_role` | VARCHAR(30) | no | `member`,`spouse`,`child`,`parent`,`director`,`shareholder`,`employee`,`trustee`,`officer` |
| `relationship` | VARCHAR(20) | yes | relationship *to the household head* — the "family" axis, distinct from the organisational axis |
| `ownership_percent` | DECIMAL(5,2) | yes | for `shareholder` |
| `start_date` | DATE | yes | |
| `end_date` | DATE | yes | |
| `status` | ENUM('active','ended') | no | default `active' |
| `notes` | TEXT | yes | |
| `created_at`, `updated_at` | TIMESTAMP | | |

KEYS: `UNIQUE(party_id, person_id, member_role)`, `KEY(person_id)`,
`KEY(member_role)`.

#### `0_ksf_common_accounts` — the account satellite

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT(11) | no | PK AI — our stable account id |
| `account_ref` | VARCHAR(30) | no | **UNIQUE** (`ACC-000123`) |
| `fa_debtor_no` | INT(11) | yes | → FA `0_debtors_master.debtor_no` |
| `fa_supplier_id` | INT(11) | yes | → FA `0_suppliers.supplier_id` |
| `account_kind` | ENUM('customer','supplier','both') | no | default `customer' |
| `party_id` | INT(11) | yes | FK → parties: **the entity this account trades with** |
| `account_status` | ENUM('active','merged','split','closed','duplicate') | no | default `active' |
| `merged_into_account_id` | INT(11) | yes | self-FK |
| `notes` | TEXT | yes | |
| `created_at`, `updated_at` | TIMESTAMP | | |

KEYS: `UNIQUE(account_ref)`, `UNIQUE(fa_debtor_no)` (nulls are not compared by
MySQL, so supplier-only rows are unaffected), `UNIQUE(fa_supplier_id)`,
`KEY(party_id)`, `KEY(account_status)`.
*An account may have neither FA id while it is being created; exactly one must
be present once the operation completes.*

#### `0_ksf_common_account_roles` — the ACCOUNT-PARTY ROLE

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT(11) | no | PK AI |
| `account_id` | INT(11) | no | FK → accounts |
| `subject_kind` | ENUM('person','party') | no | |
| `subject_id` | INT(11) | no | → persons.id or parties.id, per `subject_kind` |
| `role_code` | VARCHAR(40) | no | `customer_contact`,`billing_contact`,`supplier_contact`,`employee`,`director`,`owner`,`shareholder`,`family_member`,`signatory`,`trustee` |
| `branch_code` | INT(11) | no | **default 0 = account-level**; otherwise → FA `0_cust_branch.branch_code` |
| `crm_contact_id` | INT(11) | yes | the FA `0_crm_contacts.id` when this role is also an FA contact relation |
| `start_date` | DATE | yes | |
| `end_date` | DATE | yes | |
| `status` | ENUM('active','ended') | no | default `active' |
| `notes` | TEXT | yes | |
| `created_at`, `updated_at` | TIMESTAMP | | |

KEYS: `UNIQUE(account_id, subject_kind, subject_id, role_code, branch_code)`,
`KEY(subject_kind, subject_id)` *(this index answers the "shared person"
query of §3.6)*, `KEY(account_id, role_code)`, `KEY(crm_contact_id)`.

**There is deliberately no `is_primary` column.** See §6.6 — ambiguity 8 of the
review ruled that the estate has no primary-contact concept, and this model does
not reopen it.

#### `0_ksf_common_account_links` — the soft links

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT(11) | no | PK AI |
| `from_account_id` | INT(11) | no | FK → accounts |
| `to_account_id` | INT(11) | no | FK → accounts |
| `link_type` | VARCHAR(30) | no | `successor`,`predecessor`,`spin_off`,`sold`,`split_from`,`duplicate_of` |
| `effective_date` | DATE | yes | |
| `end_date` | DATE | yes | |
| `is_current` | TINYINT(1) | no | default 1 |
| `notes` | TEXT | yes | |
| `created_at`, `updated_at` | TIMESTAMP | | |

KEYS: `UNIQUE(from_account_id, to_account_id, link_type)`,
`KEY(to_account_id)`, `KEY(link_type)`.

#### `0_ksf_common_account_events` — the operation journal

Append-only; the audit trail for every lifecycle operation.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT(11) | no | PK AI |
| `operation` | VARCHAR(30) | no | `merge`,`split`,`spin_off`,`promote`,`associate`,`dissociate`,`clone_card`,`link` |
| `variant` | VARCHAR(30) | yes | `marriage`,`corporate`,`buyout`,`rename` |
| `source_account_id` | INT(11) | yes | |
| `target_account_id` | INT(11) | yes | |
| `person_id` | INT(11) | yes | |
| `party_id` | INT(11) | yes | |
| `crm_person_id` | INT(11) | yes | the shadow card created, if any |
| `actor` | VARCHAR(100) | no | FA user id or 'system' |
| `reason` | VARCHAR(255) | no | free text |
| `detail_json` | TEXT | yes | the request payload |
| `created_at` | TIMESTAMP | no | |

KEYS: `KEY(operation)`, `KEY(source_account_id)`, `KEY(target_account_id)`,
`KEY(person_id)`.

**This is NOT a notes table.** Free-text notes attached to a person or contact
belong to `ksf_FA_Notes` (`0_ksf_Notes`), per ambiguity 10's ruling. Do not
reuse this table for notes.

### 4.4 Two id namespaces, and why that is the single biggest migration risk

FA's `0_crm_persons.id` and our `0_ksf_common_persons.id` are **different
numbers for different things**:

* `0_crm_persons.id` = a **card** (a role-scoped contact record);
* `0_ksf_common_persons.id` = the **human being**.

Every estate table that currently foreign-keys `crm_persons.id` must be
classified. The audit already names them:

| Table | Meaning today | Under this model |
|---|---|---|
| `0_hrm_contacts_employment` (`ksf_FA_HRM/sql/fa_contacts_employment.sql:31`, real FK to `0_crm_persons(id)` ON DELETE CASCADE) | "the person who is employed" | should become the **root person id** — the employment is about the human being, not a card |
| `0_ksf_crm_life_events` (`ksf_FA_CRM/sql/ksf_crm_life_events.sql`) | "events of this person" (MARR, DIV, BIRT, DEAT) | should become the **root person id** |
| `0_ksf_crm_contact_relationships` (`ksf_FA_CRM/sql/ksf_crm_contact_relationships.sql`) | person ↔ person | should become **root person ids** on both sides |
| `0_ksf_crm_person_account_roles` (`ksf_FA_CRM/sql/ksf_crm_person_account_roles.sql`) | person holds a role on an account | **superseded** by `0_ksf_common_account_roles` (§6.5) |
| `0_ksf_crm_account_relationships` (`ksf_FA_CRM/sql/ksf_crm_account_relationships.sql`) | account ↔ account | **superseded** by `0_ksf_common_account_links` (§6.5) |
| `0_ksf_loyalty_balances` (`ksf_FA_Loyalty/sql/ksf_loyalty_balances.sql:6,13`) | "the customer who earned loyalty" | decide: root person id if it means *the human being* |
| `fa_performance_goals` (`ksf_FA_Performance/sql/fa_performance_goals.sql:7,35` — a real FK to `0_crm_persons(id)`; note the table is created **unprefixed**, a naming defect the naming audit catalogues) | "the person whose goal this is" | root person id |
| `0_ksf_leave_employees`, `0_ksf_roster_employees`, `0_ksf_teams_employees`, `0_ksf_timesheets_employees`, `0_ksf_training_employees`, `0_ksf_travelexpense_employees`, `0_ksf_projectmanagement_employees` | flat `id, name, email, active` directories created 2026-10-19 | per ambiguity 6, each must gain a `person_id` — **verified 2026-10-20: none of them has one yet** (e.g. `ksf_FA_Roster/sql/install.sql:69-78`, `ksf_FA_TravelExpense/sql/install.sql:132-141`) — and that `person_id` must be the **root person id** |

**The rule to write down:** *a table that means "the human being" keys on the
root person id; a table that means "the contact record for a role" keys on the
card id.* Until a table is migrated, both ids exist and a reconciliation check
must be able to detect the ambiguity. **[BUILD]**

### 4.5 The company boundary — an unresolved question

FA's tables are **per company** (every table is prefixed `TB_PREF`). Our tables
are prefixed the same way, so **the person/party registry is per company**:
the same human being who is a customer in Company A and a supplier in Company
B is **two root persons** under this model.

That is almost certainly wrong for a multi-company estate, but making the
registry global means escaping FA's `TB_PREF` scheme entirely — a decision with
real consequences for backups, exports and the FA install engine. **[OPEN]
OQ-7.** Until it is decided, the model is explicitly **company-scoped** and
must say so on every screen that shows a person.

### 4.6 Company-specific notes on FA tables we do not touch

* `0_debtors_master` has **no `email` and no `phone` column**
  (`sql/en_US-new.sql:585-605`) — verified by the audit and re-verified here.
  A customer's email is reachable **only** through a contact: `0_crm_persons`
  → `0_crm_contacts` → `0_debtors_master`. **[FA]**
* `0_suppliers` has `contact VARCHAR(60)` — a free-text contact **name**, not
  an address (`sql/en_US-new.sql:1691`). **[FA]**
* `0_crm_persons` has `KEY(ref)` but **no index on `email`**
  (`sql/alter2.3.sql:206`) — every email lookup is a scan. **[FA]**

---

## 5. The operations API

### 5.1 Package and namespace

Implementation home: **`ksf_FA_Common`** (the `ksfraser/ksf-fa-common` Composer
package), new namespace `ksfraser\FrontAccounting\Common\Party\`.

This is consistent with `AGENTS_ARCH.md` §12.2: a shared seam must never be
gated on another module's activation, and `ksf-fa-common` is always loadable.
It is also consistent with the review's ambiguity-4 ruling, which recommended
that the account accessor live in `ksf_FA_Common/src/AccountResolver/`.

```
src/Party/
  Contract/
    PersonDirectoryInterface.php
    PartyDirectoryInterface.php
    AccountResolverInterface.php       <- the seam from the review's §4 ruling
    AccountDirectoryInterface.php
    AccountLifecycleInterface.php      <- the seven operations
    PartyHookContract.php              <- hook names + payload keys
  Person.php  PersonCard.php  Party.php  PartyMember.php
  Account.php  AccountRole.php  AccountLink.php  AccountEvent.php
  Request/    MergeRequest.php  SplitRequest.php  SpinOffRequest.php
              PromoteRequest.php  AccountLinkRequest.php
              AssociateRequest.php  CloneCardRequest.php
  Result/     MergeOutcome.php  SplitOutcome.php  SpinOffOutcome.php
              PromoteOutcome.php  CloneCardOutcome.php
  FaPersonDirectory.php        InMemoryPersonDirectory.php
  FaPartyDirectory.php         InMemoryPartyDirectory.php
  FaAccountResolver.php        InMemoryAccountResolver.php
  FaAccountLifecycle.php       InMemoryAccountLifecycle.php
  PersonDirectory.php  PartyDirectory.php  AccountResolver.php  AccountLifecycle.php
                               (front doors: hook dispatch, then fallback —
                                same pattern as ContactResolver.php)
```

### 5.2 Contracts

```php
interface PersonDirectoryInterface
{
    public function findById(int $personId): ?Person;
    public function findByRef(string $personRef): ?Person;
    /** Resolve the ROOT person that owns a FA contact record. */
    public function findByCard(int $crmPersonId): ?Person;
    /** All FA contact records of one human being. */
    public function listCards(int $personId): array;              // PersonCard[]
    public function createPerson(string $ref, string $givenName, ?string $familyName,
                                 ?string $dateOfBirth = null): int;
    /** PERSON-level merge: fold one identity into another. */
    public function mergePersons(int $survivorPersonId, int $absorbedPersonId,
                                 string $reason, string $actor): void;
    /** Every account this human being holds a role on. */
    public function listAccountsForPerson(int $personId): array;  // Account[]
}

interface PartyDirectoryInterface
{
    public function findById(int $partyId): ?Party;
    public function findByRef(string $partyRef): ?Party;
    public function findByName(string $name): array;              // Party[]
    public function listMembers(int $partyId): array;              // PartyMember[]
    public function listPartiesForPerson(int $personId): array;   // Party[]
    public function createParty(string $ref, string $name, string $partyType): int;
    public function addMember(int $partyId, int $personId, string $memberRole,
                              ?string $startDate = null, ?string $endDate = null): int;
    public function endMembership(int $membershipId, string $endDate, string $reason): void;
}

interface AccountResolverInterface      // the review's §4 recommended seam
{
    /** FA: get_customer($id). Ours: the account satellite. */
    public function findById(int $debtorNo): ?Account;
    /** person -> role -> account. FA cannot do this natively (entity_id is not exposed). */
    public function findByEmail(string $email, bool $includeInactive = false): ?Account;
    public function findBySupplierId(int $supplierId): ?Account;
    public function findByRef(string $accountRef): ?Account;
}

interface AccountDirectoryInterface extends AccountResolverInterface
{
    public function listRoles(int $accountId): array;             // AccountRole[]
    public function listRolesForSubject(string $subjectKind, int $subjectId): array;
    public function listBranches(int $accountId): array;           // from FA 0_cust_branch
    public function listLinks(int $accountId): array;              // AccountLink[]
    public function listAccountsForPerson(int $personId): array;
    public function listAccountsForParty(int $partyId): array;
    /** Accounts sharing a subject — the DERIVED soft link (§3.6). */
    public function listAccountsSharingSubject(string $subjectKind, int $subjectId): array;
}

interface AccountLifecycleInterface      // the seven operations
{
    public function merge(MergeRequest $r): MergeOutcome;
    public function split(SplitRequest $r): SplitOutcome;
    public function spinOff(SpinOffRequest $r): SpinOffOutcome;
    public function promoteMember(PromoteRequest $r): PromoteOutcome;
    public function linkAccounts(AccountLinkRequest $r): AccountLink;
    public function associatePerson(AssociateRequest $r): PartyMember;
    public function dissociatePerson(int $membershipId, string $reason, string $actor): void;
    public function cloneContactCard(CloneCardRequest $r): CloneCardOutcome;
}
```

**Naming note.** The review (§2) recommended renaming
`ContactResolverInterface::findByCustomer()` to
`findContactsOfCustomer()` because the name reads as "find the customer". This
model uses `AccountDirectoryInterface` for accounts and does **not** touch the
contact contract's method names — the rename is a separate change with its own
package version bump.

### 5.3 Composition with the existing `ContactResolver`

**Rule:** the party model **composes** the existing resolver; it never
re-implements it.

| Need | How it is satisfied |
|---|---|
| Read a person's name/email/phone | `ContactResolverInterface::findById($cardId)` → `Contact` **[FA]** |
| Find a person by email | `ContactResolverInterface::findByEmail()` **[FA]** |
| Search people | `ContactResolverInterface::search()` **[FA]** |
| Person → accounts | **our** `account_roles` index (FA cannot do it — `entity_id` is not exposed) |
| Account → contacts | `ContactResolverInterface::findByCustomer($debtorNo)` (debtor-level) and `findByEntity('cust_branch', $branchCode)` (branch-level) **[FA]**; the *union* is `get_branch_contacts()` **[FA]** |
| Which contact rows does a person have? | `ContactResolverInterface::findContactById()` per row; **the enumeration direction is the gap the review records at ambiguity 3** — our `person_cards` + `account_roles` give us the index FA lacks |

**What is new** (not in the resolver today, per the review's §4.4 and §5):

* `AccountResolverInterface` — the account seam (the review's recommendation).
* `AccountDirectoryInterface` — role/link/subject queries.
* `AccountLifecycleInterface` — the seven operations.
* `PersonDirectoryInterface` / `PartyDirectoryInterface` — the identity and
  party registries.
* The card↔root mapping (`person_cards`) — the thing FA has no concept of.

**What is reused unchanged:** `ContactResolverInterface` (7 methods),
`ContactResolverHookContract` (`ksf_contact_resolve`), `Contact` value object,
`FaContactResolver`, `InMemoryContactResolver`, `ContactResolver` front door.

### 5.4 Hook seams

Non-FA platforms (WordPress, Nextcloud, a standalone CLI) answer the hook
instead of implementing the FA adapter, exactly as `ksf_contact_resolve` works
today (`ksf_FA_Common/src/ContactResolver/Contract/ContactResolverHookContract.php:41-93`).

| Hook | Constant | Operations | Payload keys |
|---|---|---|---|
| `ksf_account_resolve` | `PartyHookContract::HOOK_ACCOUNT_RESOLVE` | `by_debtor_no`, `by_supplier_id`, `by_email`, `by_account_ref` | `operation`, `arguments`, `result`, `handled` |
| `ksf_party_resolve` | `PartyHookContract::HOOK_PARTY_RESOLVE` | `party_by_ref`, `party_by_name`, `parties_for_person`, `person_by_ref` | same shape |
| `ksf_account_lifecycle` | `PartyHookContract::HOOK_ACCOUNT_LIFECYCLE` | one per lifecycle operation | `operation`, `phase` (`before`\|`after`), `outcome`, `result`, `handled` |

Design rules carried over from the existing hook contract:

1. A listener that does not understand the operation leaves `handled = false`;
   the implementation falls back to its own. **[FA — existing pattern]**
2. A listener's **absence is a normal state**, never an error — the seam is
   never gated on another module's activation (`AGENTS_ARCH.md` §12.2).
3. `ksf_account_lifecycle` fires **before** and **after** every operation, so a
   consumer (CRM, Nextcloud sync, WooCommerce sync) can observe — and, by
   setting `handled`, veto — without the party model knowing it exists.

### 5.5 Table ownership summary

| Table | Written by | Read by |
|---|---|---|
| `0_ksf_common_persons` | `ksf_FA_Common` | everyone, through `PersonDirectoryInterface` |
| `0_ksf_common_person_cards` | `ksf_FA_Common` | everyone, through `PersonDirectoryInterface` |
| `0_ksf_common_parties` / `_party_members` | `ksf_FA_Common` | CRM, HRM, everyone |
| `0_ksf_common_accounts` / `_account_roles` / `_account_links` / `_account_events` | `ksf_FA_Common` | CRM, Sales, EmailManager, Square, WooCommerce |

**No module may write these tables directly** — the same rule §12.2 states for
contact tables, extended to the new ones. Direct writes are how the estate got
its 46 `WRONG_FA_TABLE` sites.

---

## 6. Migration and incomplete handling

### 6.1 What has to be built because FA has no clone

FA 2.4.3 has no data-level clone of any kind (§0). Three composites are
therefore ours:

#### `cloneContactCard(CloneCardRequest): CloneCardOutcome` **[BUILD]**

```
1. read the source card            -> get_crm_person($crmPersonId)            [FA]
2. create the new card              -> add_crm_person(...)                     [FA]
                                      (returns the new id — crm_contacts_db.inc:13)
3. link shadow -> root              -> INSERT 0_ksf_common_person_cards       [BUILD]
4. attach to the target account     -> add_crm_contact('customer','general',
                                                  $debtor_no, $newId)       [FA]
5. attach to the target party       -> add_crm_contact('party_member', $role,
                                                  $party_id, $newId)        [FA]
6. write the event row              -> INSERT 0_ksf_common_account_events     [BUILD]
```

The `ref` passed to `add_crm_person()` must be **unique per card** — FA's
`0_crm_persons.ref` has only a non-unique `KEY` (`sql/alter2.3.sql:206`), but
FA's own screens use it as a handle, so the clone must mint a distinct one
(e.g. `P-000123-S`).

#### `cloneAccount(...)` **[BUILD]**

Used by SPLIT and SPIN-OFF. Composed entirely from FA primitives:

```
1. read the source account    -> get_customer($debtorNo)          [FA]
2. create the new account     -> add_customer(...14 args...)     [FA]
                                  then db_insert_id()             [FA]
3. copy the branches          -> add_branch(...17 args...)      [FA]
4. copy / move the contacts   -> add_crm_person + add_crm_contact [FA]
5. create the party + members -> our tables                      [BUILD]
6. write role rows            -> our tables                      [BUILD]
7. write the link + event     -> our tables                      [BUILD]
```

**Two FA traps in step 2:**
* `add_customer()` **returns nothing** (`customers_db.inc:13-28`) — the caller
  must read `db_insert_id()` immediately after, as FA's own customer screen
  does (`sales/manage/customers.php:109`).
* `0_debtors_master.debtor_ref` is **UNIQUE** (`sql/en_US-new.sql:604`), so the
  clone must mint a new ref. `0_cust_branch.branch_ref` is only a `KEY`
  (`sql/en_US-new.sql:570`), so branch refs may repeat — but should not.

**Trap in step 4:** the *shared* family mailbox is one `0_crm_persons` row. If
the split needs it on both accounts, it must be **cloned** (step 4's clone),
not moved — which is exactly §3.7.

### 6.2 Safe to implement now (pre-UAT, pre-prod)

These are **additive and reversible**: they create rows in new tables, or they
call FA primitives in ways FA already supports, and they touch no existing
transaction.

| # | Item | Why it is safe |
|---|---|---|
| 1 | The vocabulary of §1 (a document, not code) | no data |
| 2 | Creating the eight `0_ksf_common_*` tables (empty) | new tables only; `ksf_FA_Common` already owns tables this way (`sql/install.sql`) |
| 3 | `PersonDirectory` / `PartyDirectory` create + read | new rows only |
| 4 | Lazy root-person creation + primary card registration | new rows only; **no** existing FA row is modified |
| 5 | `AccountResolverInterface` + `AccountDirectoryInterface` reads | read-only |
| 6 | **ASSOCIATE** | inserts membership rows; the optional FA relation row is an *addition* to `0_crm_contacts` |
| 7 | **SOFT LINK** | inserts a link row; the FA `notes` breadcrumb rewrites one account's `notes` field only |
| 8 | **CLONE-WITH-LINK** | creates a new FA person row + card row; attaches it to an account; **no existing row is changed** |
| 9 | **MERGE, variant `rename`** | `update_customer()` on one row: name/ref only |
| 10 | **Retiring an account** (deactivate, not delete) | `update_record_status()` is FA-native and auto-loaded (`includes/db/sql_functions.inc:58`); the flag is reversible |
| 11 | The reconciliation job (§6.4) | read-only |
| 12 | Role capture on **newly created** accounts (create-time population) | additive |

### 6.3 Needs a data migration or a product decision first

| # | Item | What is missing |
|---|---|---|
| 1 | **MERGE with transaction re-pointing** | FA has no ledger-level merge. Moving an account's invoices/orders/allocations means rewriting `debtor_trans.debtor_no`, `cust_allocations`, sales orders, credit notes, and re-checking every report. **Needs a product decision (OQ-4) and a migration script.** |
| 2 | **SPLIT with balances** | who keeps the balance, the credit limit, the payment terms, the branches (OQ-5) |
| 3 | **SPIN-OFF / sale** | GL account separation for the spun-off company (OQ-6); what "sold" means for the sold entity's ledger |
| 4 | **Seeding existing FA data** into `person_cards`, `account_roles`, `accounts` | a one-off, idempotent migration. **It needs to read `0_crm_contacts.entity_id`, which FA's native functions never expose** (`crm_contacts_db.inc:89-91`) — the single documented exception the review permits for `ksf_FA_Common` (§4.4). Must be run per environment and verified by row counts. |
| 5 | **Repointing module satellites** from `crm_persons.id` to the root person id (§4.4) | a semantic migration across HRM, Performance, Loyalty, CRM. Each table must be re-pointed **after** the root person exists for every person it references. |
| 6 | **Superseding the CRM's declared-but-unread tables** (§6.5) | the CRM's pages must be repointed before the old tables can be retired; `FR-CRM-007-002` is an APPROVED requirement and needs an explicit supersession note |
| 7 | **Deleting** an absorbed account rather than deactivating it | `delete_customer()` also deletes the account's `customer`-type contacts (`customers_db.inc:53-61`). Whether a merge may ever delete an account is a policy question, not a technical one (OQ-3) |
| 8 | **A designated primary contact** | ruled out by ambiguity 8 unless the business asks for it in writing (OQ-2) |
| 9 | **Cross-company person identity** | §4.5 (OQ-7) |

### 6.4 Incomplete handling — what is INCOMPLETE, and how the estate must behave

The model is deliberately incomplete in nine places. Each has a **degradation
rule**: what a screen shows when the model has no answer. A screen that shows
something *wrong* is worse than one that shows something incomplete.

| # | What is incomplete | Degradation rule |
|---|---|---|
| **I1** | **Person → account for pre-existing data.** Before seeding, our `account_roles` is empty, so "which accounts is this person on?" returns nothing for legacy records. | Callers must state "unseeded" rather than "none". The API returns an empty array plus a `seeded` flag on the directory; **never** an empty array that means "no links". |
| **I2** | **No primary contact.** Per ambiguity 8. | The designated recipient is FA's own branch/action preference (`get_branch_contacts()`, `branches_db.inc:181-217`). Screens list the account's contacts; they do not mark one. |
| **I3** | **No FA representation of party or family structure at all.** | Party/family screens are ours alone. If our tables are absent (module not deployed), the screen shows the account and its contacts — it does **not** show a half-family. |
| **I4** | **No ledger-level merge/split.** | The merge/split operations move **identity** (contacts, roles, links), never **transactions**. A screen that offers "merge these accounts" must warn that balances stay where they are. |
| **I5** | **`0_users` is not linked by FA.** | `fa_user_id` on the PERSON is our link, not FA's. Nothing in FA keeps it in step; the reconciliation job reports drift. |
| **I6** | **The shared resolver still cannot see relation-less people** (the review's ambiguity 6 gap): `get_crm_persons()` is an INNER JOIN (`crm_contacts_db.inc:89-91`), so an employee with no `crm_contacts` row is invisible to `findByEmail()`/`search()`. | Our `person_cards` index **does** know them. Any screen that must see unlinked people reads `PersonDirectoryInterface`, not the contact resolver. This model does **not** fix the resolver gap; it provides an alternative path. |
| **I7** | **Our role rows can drift from FA's relations.** FA has no foreign keys into our tables and fires no hooks on contact deletion. | A scheduled reconciliation job compares our `account_roles.crm_contact_id` set against FA's `crm_contacts` set and reports orphans. FA's `delete_crm_contact()` / `delete_customer()` / `delete_branch()` all remove relations behind our back. |
| **I8** | **Cloned accounts do not stay in step.** A clone copies `curr_code`, `tax_id`, credit terms and GL assignments **at the moment of cloning**. Later edits to the source do not propagate — deliberately. | The clone outcome must state which fields were copied and which were left to the operator. |
| **I9** | **The registry is company-scoped.** (§4.5) | Every screen that shows a person states the company. No cross-company person matching is offered, and the UI must not imply one. |

### 6.5 Where the note must live

The owner asked for **a note in the CRM module about incomplete handling**.
Three places, each with a different audience:

1. **Primary — module-facing note (the one the owner asked for):**
   `ksf_FA_CRM/ProjectDcs/PARTY-ACCOUNT-MODEL-INCOMPLETE-HANDLING.md`
   *Contents:* the nine items of §6.4; for each CRM surface that depends on the
   model (`pages/person_account_roles.php`, `pages/account_relationships.php`,
   `pages/org_chart.php`, `pages/life_events.php`, `pages/contact_relationships.php`,
   `includes/crm_relationships_db.inc`), what it renders today, what it renders
   after the model lands, and the **degradation rule** it must follow while the
   model is incomplete; the "do not implement until" markers; and the
   instruction that the CRM must read people through
   `PersonDirectoryInterface` and accounts through `AccountResolverInterface`,
   never through its own SQL.
   *Why here:* the CRM is the module that already owns the overlapping —
   and currently broken — tables, so it is where the supersession has to be
   written down.

2. **Cross-module note:**
   `ksf_Architecture_Docs/Requirements/OPEN-QUESTIONS.md` — new entries
   **Q14–Q20** for the seven open decisions listed in §9, each stating the
   recommendation, the cost of being wrong, and whether it blocks implementation.
   *Why here:* that file is already the estate's register of decisions that
   block work (it already carries the ACL questions in the same format).

3. **Package note:** `ksf_FA_Common/AGENTS_APPENDIX.md` (create if absent —
   `AGENTS.md` names `AGENTS_APPENDIX.md` as the per-repo extension file) — the
   package-local statement of which tables it owns, which invariants a
   contributor must not break (no contact columns on `0_ksf_common_persons`;
   no `is_primary` on the role table; cards point at roots, never the
   reverse), and the "no direct table writes" rule.

**Explicit supersessions this model requires.** These are the places where this
document touches ratified artefacts, and each needs the owner's sign-off:

| Artefact | Status | What happens |
|---|---|---|
| `ksf_FA_CRM/sql/ksf_crm_person_account_roles.sql` (table **is** created on activation; every CRM read site addresses `0_fa_crm_person_account_roles`, which was never created — `crm_relationships_db.inc:185-229`, `pages/person_account_roles.php:128`) | superseded | replaced by `0_ksf_common_account_roles`; the CRM pages are repointed, then the old table is retired |
| `ksf_FA_CRM/sql/ksf_crm_account_relationships.sql` | superseded | replaced by `0_ksf_common_account_links` |
| `ksf_FA_CRM/sql/ksf_crm_life_events.sql` (`person_id` → `crm_persons.id`) | re-pointed | `person_id` must become the **root person id** (§4.4) |
| `ksf_FA_CRM/sql/ksf_crm_contact_relationships.sql` (`person_a_id`/`person_b_id` → `crm_persons.id`) | re-pointed | both become root person ids |
| `ksf_FA_CRM/ProjectDcs/FR-CRM-007-002` §3.1 (the `fa-classes` seam) | already superseded | per the review's ambiguity 3; this model does not reopen it |
| `ksf_FA_CRM/ProjectDcs/BR-CRM-009` (I/F/B is a property of the debtor, not the person) | **consistent** | the ACCOUNT-PARTY ROLE keeps I/F/B-style attributes on the account, consent on the person — the model agrees |
| `AGENTS_ARCH.md` §12.2 | needs **one added sentence** | "a contact record is role-scoped; one human being may have several; the PERSON anchor is `0_ksf_common_persons`" (OQ-1) |

**Note that the CRM's `is_primary` columns are *not* carried over.** Per
ambiguity 8 the estate has no primary-contact concept, so
`0_ksf_common_account_roles` has no `is_primary`. The CRM's three `is_primary`
columns (`0_ksf_crm_contacts`, `0_ksf_crm_contact_accounts`,
`0_ksf_crm_person_account_roles`) are therefore to be dropped or repurposed when
the CRM's pages are repointed — a decision that belongs to the CRM's own
requirement set, not to this model.

### 6.6 Where this model agrees with the eleven rulings

The review's §12 summary table is the reference. This model:

* **adopts** ambiguity 1 ("contact" = a person; "type" = FA's
  `crm_categories.type`) — and **adds** the PERSON/CARD distinction on top
  (OQ-1);
* **adopts** ambiguity 2 ("customer" = the account; the person behind it is a
  contact; account → contacts, never the reverse) — the ACCOUNT-PARTY ROLE is
  a *superset* of the contact relation, and the direction rule is unchanged;
* **adopts** ambiguity 3 (one seam: `ksf-fa-common`) — this model lives there
  and adds to it; it does not create a second contact seam;
* **adopts** ambiguity 4 (**two seams**, a separate `AccountResolverInterface`
  with `findById` and `findByEmail`) — this model is where that contract lives;
* **adopts** ambiguity 5 (three named contact sets: debtor-level, branch-level,
  union) — the model adds the branch scope to the role table and does not
  replace the three sets;
* **adopts** ambiguity 6 (an employee is a person plus an employment record;
  the module-local directories stay but must gain a `person_id`) — the model
  says that `person_id` must be the **root person id**;
* **adopts** ambiguity 7 (a lead is a prospective account, workflow data in
  `0_ksf_crm_leads` keyed by `debtor_no`) — consistent; a lead is an ACCOUNT in
  our satellite once seeded;
* **adopts** ambiguity 8 (**no primary-contact concept**) — hence **no
  `is_primary`** column anywhere in the new schema;
* **adopts** ambiguity 9 (roles become `0_crm_categories` rows; the per-role
  defaults are dropped) — the model's `role_code` catalogue maps 1:1 onto
  `(type, action)` category pairs, and no default email/phone is stored;
* **adopts** ambiguity 10 (one notes implementation; `0_ksf_Notes`) — the
  model's event journal is explicitly *not* a notes table;
* **adopts** ambiguity 11 (inactive is excluded by default) — and separates FA's
  `inactive` from our `status`/`account_status` columns, which are identity
  lifecycle, not deactivation.

**No ruling is contradicted.** The one refinement (PERSON vs CARD) is an
addition to the vocabulary, flagged for the owner as OQ-1.

---

## 7. Requirements

### 7.1 Where the requirement documents live

**Decision:** the requirement documents live in
**`/home/kevin/Documents/ksf_Architecture_Docs/Requirements/`**, alongside
`BR-EM-001`, `BR-ACL-001` and `BR-CAL-010` — the estate's established home for
cross-module requirements.

Reasons:

1. The model is a **platform contract**, implemented in one package and consumed
   by many modules; the same pattern as `BR-EM-001` (implemented in
   `ksf_FA_EmailManager`, relied on by others).
2. `ksf_Architecture_Docs` is where the governing decisions already are
   (`AGENTS_ARCH.md` §12.2) and where this design document lives — one place to
   read the decision, the evidence and the requirement.
3. `ksf_FA_Common`'s own `doc/ProjectDocuments/ProjectDcs/` is **empty** (verified)
   and `doc/ProjectDocuments/RTM/` is empty too. Populating it with a *second*
   copy of the same requirement ids would create two files with one id — the
   exact class of defect this estate keeps cataloguing (four `0_fa_crm_*` names
   for one table).

**But** the package's RTM must be able to resolve the ids. The estate already
has a mechanism for exactly this: the shared architecture docs are **hardlinked**
into each repository (`AGENTS.md`: *"`AGENTS_ARCH.md` (co-located, hardlinked
into each repo)"*). The same mechanism is used here:

> The requirement files are **hardlinked** from `ksf_Architecture_Docs/Requirements/`
> into `ksf_FA_Common/doc/ProjectDocuments/ProjectDcs/`, so the package's RTM
> generator resolves `FR-COM-010-0xx` locally, with a single source of truth.

A pointer file `ksf_FA_Common/doc/ProjectDocuments/ProjectDcs/PARTY-ACCOUNT-MODEL.md`
(no requirement id) states where the authoritative files live and lists the ids.

### 7.2 The module code

`COM` — the module code already used by `ksf_FA_Common`
(`BR-COM-01` calc registry, `BR-COM-02` workflow, `BR-COM-03` notifications,
`BR-COM-04` scheduler — cited in `ksf_FA_Common/sql/install.sql:100,132,173`).

The `010` series is used for *platform capability contracts*
(`BR-ACL-010` event-driven ownership, `BR-CAL-010` capability contract,
`BR-HRM-010`). The party/account model is exactly that, and `010` is free in
the `COM` series.

**Proposed ids:**

| File | Id | Scope (one line) |
|---|---|---|
| `BR-COM-010-party-account-domain-model.md` | **BR-COM-010** | The business need: one human being wears several hats; the estate must not confuse the human, the entity, the account and the role. |
| `FR-COM-010-001-vocabulary-and-invariants.md` | FR-COM-010-001 | The four concepts, the invariants (no contact columns on a PERSON; no `is_primary`; cards point at roots), and the ban on overloading. |
| `FR-COM-010-002-person-and-card-schema.md` | FR-COM-010-002 | `0_ksf_common_persons` + `0_ksf_common_person_cards`: the PERSON identity, the card mapping, lazy root creation, merge lineage. |
| `FR-COM-010-003-party-and-membership-schema.md` | FR-COM-010-003 | `0_ksf_common_parties` + `0_ksf_common_party_members`: party types, the individual-as-family-of-one invariant, many-to-many membership. |
| `FR-COM-010-004-account-role-and-link-schema.md` | FR-COM-010-004 | `0_ksf_common_accounts`, `_account_roles`, `_account_links`, `_account_events`: the account satellite, the ACCOUNT-PARTY ROLE, the soft-link taxonomy, the journal. |
| `FR-COM-010-005-merge-operation.md` | FR-COM-010-005 | MERGE: inputs, preconditions, effects, the four variants (marriage / corporate / buyout / rename), and what a merge must **not** change. |
| `FR-COM-010-006-split-operation.md` | FR-COM-010-006 | SPLIT: the divorce case, which branches and contacts move, move-vs-clone of shared contact details, the `split_from` link. |
| `FR-COM-010-007-spin-off-operation.md` | FR-COM-010-007 | SPIN-OFF and sale: ownership recording, GL separation, the `spin_off`/`sold` links. |
| `FR-COM-010-008-promote-member-operation.md` | FR-COM-010-008 | PROMOTE: a family member leaves the household account and gets their own; membership vs account role end separately. |
| `FR-COM-010-009-associate-person-operation.md` | FR-COM-010-009 | ASSOCIATE / DISSOCIATE: many-to-many person↔party with a role, the FA-native category expression, role-scoped contact details. |
| `FR-COM-010-010-clone-contact-card-operation.md` | FR-COM-010-010 | CLONE-WITH-LINK: shadow→root direction, the `card_kind`/`scope_role` markers, and the legitimate-vs-mistake test. |
| `FR-COM-010-011-soft-link-operation.md` | FR-COM-010-011 | SOFT LINK: the three link kinds, what is stored vs derived, and the three queries the model must answer. |
| `FR-COM-010-012-resolver-composition-and-hooks.md` | FR-COM-010-012 | Composition with `ContactResolverInterface`; the new contracts; the `ksf_account_resolve`, `ksf_party_resolve`, `ksf_account_lifecycle` hooks. |
| `FR-COM-010-013-seeding-and-reconciliation.md` | FR-COM-010-013 | The one-off seed of existing FA data into the model (including the single documented `entity_id` exception), and the standing reconciliation job. |
| `FR-COM-010-014-incomplete-handling-and-degradation.md` | FR-COM-010-014 | The nine incompleteness items and their degradation rules; the CRM note's required content. |
| `UC-COM-010-001-merge-two-accounts.md` … `UC-COM-010-007-clone-a-contact-card.md` | UC-COM-010-001…007 | One use case per lifecycle operation, in the house `UC-<MODULE>-<SEQ>-<slug>.md` form. |

**Traceability.** Each class and method in `src/Party/` carries
`@BABOK Related: FR-COM-010-0xx` in its PHPDoc; each test file carries
`@BABOK Related: UC-COM-010-0xx`; the RTM is generated from those references, as
`AGENTS.md` requires. The RTM lives in
`ksf_FA_Common/doc/ProjectDocuments/RTM/` (currently empty).

### 7.3 What the requirement set must say about the open decisions

`FR-COM-010-005` (MERGE) and `FR-COM-010-006` (SPLIT) cannot be completed
without the decisions in §9; they must be written with the undecided parts
marked as `[OPEN]` and the safe scope (rename-only merge) stated explicitly, so
that the implementable subset can ship while the rest waits.

---

## 8. Implementation order (proposed)

1. **Vocabulary + requirement skeletons** (BR-COM-010, FR-COM-010-001) — a
   document, no code. Makes every later step checkable.
2. **Schema** (FR-COM-010-002…004): the eight tables, the `ksf_FA_Common`
   install path, the invariants review.
3. **Read paths** (FR-COM-010-012): `PersonDirectory`, `PartyDirectory`,
   `AccountResolver`, `AccountDirectory` + the hooks. Read-only, no risk.
4. **Write paths that are safe** (FR-COM-010-009…011): ASSOCIATE, SOFT LINK,
   CLONE-WITH-LINK, plus create-time role capture.
5. **Seeding** (FR-COM-010-013): the idempotent seeder and the reconciliation
   job. **This is the gate** — until it runs, I1 applies.
6. **CRM repointing** (FR-COM-010-014 + the CRM's own requirements): the four
   CRM pages and `crm_relationships_db.inc` move to the new model, and the
   CRM's declared-but-unread tables are retired.
7. **The operations that need decisions** (FR-COM-010-005…008): MERGE (full),
   SPLIT, SPIN-OFF, PROMOTE — after OQ-4…OQ-7 are answered.

---

## 9. Open questions for the owner

| # | Question | Recommendation | Cost of being wrong |
|---|---|---|---|
| **OQ-1** | Do we add the PERSON/CARD distinction to `AGENTS_ARCH.md` §12.2 (one sentence), so that "a contact" is not read as "the person"? | **Yes.** Without it, module authors will keep treating `crm_persons.id` as the person's id and the model will not hold. | Low cost to fix, high cost to ignore: every satellite table (§4.4) picks the wrong id space. |
| **OQ-2** | Does the business need a *designated* contact to bill? | **No** (per ambiguity 8). If yes, it is a new requirement and a new table — not a column on `0_ksf_common_account_roles`. | Adding it later means a second table; keeping it out now means a visible product gap that must be documented. |
| **OQ-3** | May a MERGE ever **delete** the absorbed account, or must it always deactivate it? | **Always deactivate.** `delete_customer()` also deletes the account's `customer`-type contacts and destroys the ledger context the soft link exists to preserve. Deactivation uses FA's own `update_record_status()` (`includes/db/sql_functions.inc:58`) and is reversible. | Deleting loses the history that the `successor`/`predecessor` link records. |
| **OQ-4** | When two accounts merge, what happens to the absorbed account's transactions? | **Do not re-point them pre-UAT.** Keep the absorbed account's transactions where they are; the absorbed account is retired, not deleted, and the `successor` link records the history. A full re-pointing is a separate, later project. | If we re-point blindly, reports change meaning. If we leave them, the estate must accept two account histories — which the soft link makes legible. |
| **OQ-5** | On a divorce split, who keeps the balance, the credit limit and the payment terms? | **The source account keeps them** (`keepBalanceOnSource=true` by default); the new account starts with the same terms and an empty ledger. | Getting this wrong creates two accounts with the same credit exposure. |
| **OQ-6** | On a spin-off, which GL accounts does the new company post to? | **Accounting decision, not ours.** Implement the operation so the GL assignment is a required input, not a default. | Wrong defaults post a subsidiary's invoices to the parent's receivables account. |
| **OQ-7** | Should the person/party registry be global (cross-company) rather than company-prefixed? | **Decide before the first multi-company deployment.** A global registry needs to escape `TB_PREF`, which is a real change to backups, exports and the install engine. | Retro-fitting a global registry after two companies have each seeded their own roots is a painful merge of identities. |
| **OQ-8** | Does `PROMOTE` move or clone the child's card by default? | **Move** when the child has their own email/phone; **clone** when the card carries the family address. Both cases are detectable from the card's fields, so the default can be a rule rather than a question. | Getting it wrong either breaks the family's correspondence or duplicates it. |
| **OQ-9** | Is the CRM's `0_ksf_crm_life_events` (MARR/DIV/BIRT/DEAT) the estate's home for life events, or does the party model own them? | **Keep them in the CRM** (they are a personal timeline, not an account operation), but re-point `person_id` to the root person id (§4.4). The party model's journal is an *account* journal and must not absorb them. | Merging them would put a personal timeline inside the platform package and re-open ambiguity 10's notes problem. |

---

## 10. Appendix — verified FA 2.4.3 source map

Every claim in this document that concerns FA traces to one of these.

| Subject | Location |
|---|---|
| `0_crm_categories` (16→12 seeded rows; `UNIQUE(type,action)`, `UNIQUE(type,name)`) | `sql/alter2.3.sql:161-172`; seeds `:174-186` |
| `0_crm_persons` (`id, ref, name, name2, address, phone, phone2, fax, email, lang, notes, tmp_id, tmp_class, inactive`; `KEY(ref)`; **no email index**) | `sql/alter2.3.sql:190-207` |
| `0_crm_contacts` (`id, person_id, type, action, entity_id`; `KEY(type,action)`) | `sql/alter2.3.sql:211-219` |
| `0_debtors_master` (16 columns; **no email, no phone**; `UNIQUE(debtor_ref)` at `:604`) | `sql/en_US-new.sql:585-605` |
| `0_cust_branch` (`branch_code` + `debtor_no` composite PK at `:569`; `KEY(branch_ref)` at `:570`) | `sql/en_US-new.sql:549-570` |
| `0_suppliers` (`contact VARCHAR(60)` = a name, not an address) | `sql/en_US-new.sql:1691-1716` |
| `0_users` (no link to `crm_persons`) | `sql/en_US-new.sql:2062` |
| `add_crm_person` (returns the new id) | `includes/db/crm_contacts_db.inc:13-41` |
| `get_crm_persons` (INNER JOIN; `ORDER BY contact_id`; silent `general` fallback) | `includes/db/crm_contacts_db.inc:87-119` |
| `get_crm_person` (by id; no join; returns `contacts` = category ids) | `includes/db/crm_contacts_db.inc:121-131` |
| `get_person_contacts` (returns **category** ids, not relation ids) | `includes/db/crm_contacts_db.inc:136-148` |
| `add_crm_contact` / `delete_crm_contact` / `delete_crm_contacts` / `delete_entity_contacts` | `includes/db/crm_contacts_db.inc:251/263/272/176` |
| `get_crm_contact` (never exposes `entity_id`) | `includes/db/crm_contacts_db.inc:291-301` |
| `add_crm_category` / `get_crm_categories` / `get_crm_category_name` | `includes/db/crm_contacts_db.inc:191/222/238` |
| `add_customer` (14 args; **returns nothing**) | `sales/includes/db/customers_db.inc:13-28` |
| `update_customer` (15 args; **no `inactive`**) | `sales/includes/db/customers_db.inc:30-51` |
| `delete_customer` (deletes the debtor + its `customer` contacts, in a transaction) | `sales/includes/db/customers_db.inc:53-61`
| `update_record_status($id,$status,$table,$key)` — sets a record's `inactive` flag; **auto-loaded** | `includes/db/sql_functions.inc:58`; loaded at `includes/main.inc:18` | |
| `get_customer` / `get_customer_name` / `get_customer_details` / `get_customer_by_ref` / `get_customer_contacts` (normalises `lang='C'`) | `sales/includes/db/customers_db.inc:118/127/66/179/151` |
| `add_branch` / `update_branch` / `delete_branch` | `sales/includes/db/branches_db.inc:12/39/65` |
| `get_cust_branch` / `get_branch` / `get_sql_for_customer_branches` | `sales/includes/db/branches_db.inc:96/82/142` |
| `get_branch_contacts` (branch ∪ customer, action-or-general, default pick) | `sales/includes/db/branches_db.inc:181-217` |
| `db_insert_id` | `includes/db/connect_db_mysqli.inc:173` |
| Customer creation writes **both** relations for one person | `sales/manage/customers.php:111-126` |
| Branch creation writes **another** person row | `sales/manage/customer_branches.php:97-105` |
| No data-level clone of a debtor/branch/contact/person | whole-tree grep of `FA/2.4.3`: only `copy_file(s)`, `copy_to/from_cart`, `copy_to/from_cn`, `url_copy`, plus the admin role clone (`admin/security_roles.php:141-162`) and the unused generic CRUD clone (`includes/ui/class.crud_view.inc:303`, `includes/ui/simple_crud_class.inc:201-226`) |
| `crm_contacts_db.inc` and `customers_db.inc` are **not** auto-loaded by `includes/main.inc` | `AGENTS_ARCH.md` §12.2 |

---

*Design document produced 2026-10-20 from the owner's party/contact/account
reasoning, verified against FA 2.4.3 at `ksf_Infrastructure/FA/2.4.3/`, and
consistent with `AGENTS_ARCH.md` §12.2, `Contact_Access_Inventory_2026-10.md` and
`Contact_Ambiguity_Review_2026-10.md`. **No production code was modified, no
test suite was run, and no FA table was written to.***
