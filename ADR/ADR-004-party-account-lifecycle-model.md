# ADR-004 — The party / person / account lifecycle model

**Status:** Accepted (requirements stage). Implementation pending; the CRM-facing
requirement set is `BR-CRM-011` and `FR-CRM-011-001…008`.
**Date:** 2026-10-20
**Relates to:** ADR-001, ADR-002, ADR-003; `AGENTS_ARCH.md` §12.2;
`Party_Account_Model_2026-10.md` (the design);
`Contact_Ambiguity_Review_2026-10.md`; `Contact_Access_Inventory_2026-10.md`

---

## Context

FA 2.4.3 owns the contact registry: `0_crm_persons` (a person), `0_crm_contacts`
(the person↔entity relation) and `0_crm_categories` (the `(type, action)`
catalogue) — `sql/alter2.3.sql:161-219`. It owns the account: `0_debtors_master`
(`sql/en_US-new.sql:585-605`) and `0_cust_branch` (`:549-570`). The owner
decision of 2026-10 (`AGENTS_ARCH.md` §12.2) is that a module reaches FA core's
data through FA core's functions and through the shared contact resolver.

Under that decision the estate has a single contact registry and a single
account registry, and **no** model for the things the business actually asks
about:

- one human being wearing several hats (customer, supplier, user, employee);
- a household as a trading identity;
- an account that is merged, split, spun off or sold;
- a person who belongs to several organisations;
- a second contact record for the same human being, deliberately or by mistake.

The owner's reasoning, in their own words, is reproduced in
`~/Documents/ksf_FA_CRM/ProjectDcs/PARTY-ACCOUNT-MODEL-NOTES.md` §1. The
worked design is `Party_Account_Model_2026-10.md`.

## Problem

The estate is answering four different questions with one record type. The
consequences are measured, not theoretical:

1. **One human being is several `0_crm_persons` rows.** FA's customer screen
   writes two relations for one person row (`sales/manage/customers.php:121-126`)
   and the branch screen writes another person row
   (`sales/manage/customer_branches.php:99-105`). Nothing links them.
2. **FA has no data-level clone of anything.** There is no `copy_customer`, no
   `clone_debtor`, no `duplicate_branch`; a whole-tree search returns only
   `copy_file` (`includes/main.inc:335`), `copy_files` (`includes/main.inc:318`),
   `url_copy` (`includes/remote_url.inc:79`), the cart and credit-note copies,
   the admin security-role clone (`admin/security_roles.php:141-162`) and the
   generic CRUD "Clone" action (`includes/ui/class.crud_view.inc:303-304`,
   `includes/ui/simple_crud_class.inc:201-227`). **Every clone must be built.**
3. **FA has no notion of party, household, family, ownership or account
   relationship.** A whole-tree grep of the FA schema for `crm_*` returns exactly
   `crm_categories`, `crm_contacts`, `crm_persons`; there is no `party`,
   `household`, `family` or `ownership` table.
4. **Five CRM screens read FA's person table with columns it does not have**
   (`first_name` / `last_name`; FA has `name` / `name2`,
   `sql/alter2.3.sql:190-207`) and die loudly:
   `ksf_FA_CRM/includes/crm_relationships_db.inc:60` and `:123-125`,
   `ksf_FA_CRM/pages/contact_relationships.php:121-122`,
   `ksf_FA_CRM/pages/life_events.php:104`,
   `ksf_FA_CRM/pages/person_account_roles.php:126`.
5. **FA's own UI already produces the duplicate the model must distinguish.**
   The contact panel ships a "Clone" button (*"Edit new record with current
   data"*, `includes/ui/simple_crud_class.inc:227`, action at `:188-193`),
   reached through `includes/ui/contacts_view.inc:12,18` and instantiated at
   `sales/manage/customers.php:363`, `sales/manage/customer_branches.php:321`
   and `purchasing/manage/suppliers.php:323`. It creates an **unlinked**
   duplicate, with no marker and no way to say "same human, different role".

## Decision

### 1. Four concepts, and the estate's five terms are not one

| Concept | Answers | Lives in |
|---|---|---|
| **PERSON** | *who is this human being?* | the shared package's person registry (proposed `0_ksf_common_persons`) |
| **PARTY** | *what legal or social entity is this?* | the shared package's party registry (proposed `0_ksf_common_parties`, `0_ksf_common_party_members`) |
| **ACCOUNT** | *who do we trade with?* | **FA's `0_debtors_master`** — not replaced, not copied |
| **ACCOUNT-PARTY ROLE** | *in what capacity?* | the shared package's role index (proposed `0_ksf_common_account_roles`) |
| *(CARD)* | *which role-scoped contact record carries this human's details?* | **FA's `0_crm_persons`** — one human may have several |

**An individual is a household of one member.** That is an invariant on the
party, not a fifth kind of entity. It is the owner's own rule and it is
enforceable.

**This is an addition to the ambiguity review's vocabulary, not a replacement.**
Ambiguity 1 ruled that *"contact" means a person, and only a person*; that
ruling stands. The decision adds one distinction **above** it: one human being
may be recorded by more than one contact record. It needs one sentence in
`AGENTS_ARCH.md` §12.2 so that a module author does not read "a contact" as
"the person" (**OQ-H**).

### 2. Seven lifecycle operations, one per thing the business actually does

MERGE (variants `marriage`, `corporate`, `buyout`, `rename`), SPLIT, SPIN-OFF
(with a later sale), PROMOTE, SOFT LINK, ASSOCIATE / DISSOCIATE, and
CLONE-WITH-LINK.

Three rules hold across all seven:

1. **A merge changes identity, not contact details.** The account name may
   change; a title may change; the email, phone and address of the people
   involved do **not**. The owner's words: *"the company name might change but
   the contact details shouldn't, except maybe for position/title"* and *"that
   can happen outside of a 'merger' (marriage)"*.
2. **An absorbed account is deactivated, never deleted.** FA's
   `delete_customer()` (`sales/includes/db/customers_db.inc:53-61`) deletes the
   debtor **and** its `customer`-type contacts, which destroys the ledger
   context the soft link exists to preserve. Deactivation uses FA's own
   `update_record_status()` (`includes/db/sql_functions.inc:58-63`, auto-loaded
   at `includes/main.inc:18`) and is reversible.
3. **Identity moves; transactions never do.** FA has no ledger-level merge or
   split, and no requirement in this set invents one.

### 3. The seven operations live in one shared package, and the CRM consumes them

Implementation home: the `ksfraser/ksf-fa-common` package, namespace
`ksfraser\FrontAccounting\Common\Party\`. That is consistent with
`AGENTS_ARCH.md` §12.2's rule that a shared seam is never gated on another
module's activation, and with the ambiguity review's ambiguity-3 ruling that
there is exactly **one** contact seam.

New contracts: `PersonDirectoryInterface`, `PartyDirectoryInterface`,
`AccountResolverInterface`, `AccountDirectoryInterface`,
`AccountLifecycleInterface`, and the hook seams `ksf_account_resolve`,
`ksf_party_resolve`, `ksf_account_lifecycle`.

**The existing `ContactResolverInterface` is composed, never re-implemented.**
It keeps its seven methods, its `ksf_contact_resolve` hook, its `Contact` value
object and its three implementations.

### 4. The CRM's requirements are written against the contracts, not the tables

The shared design document fixes a proposed table layout
(`0_ksf_common_*`, in `ksf_FA_Common`). A parallel sweep is renaming every
`0_fa_*` table in the estate to `0_ksf_<module>_*` right now, and the proposed
layout has not been ratified into requirements. **The CRM's requirement set
therefore names the contracts**, and names no `0_fa_*` table. The CRM's own
tables (`0_ksf_crm_*`) are named, because they exist and have schema.

### 5. The CRM is where the supersession is written down

`0_ksf_crm_person_account_roles` and `0_ksf_crm_account_relationships` are
**superseded** by the shared role index and the shared link index. The
repointing order is fixed: **repoint the CRM's pages first, then retire the
tables.** Retiring a live table first loses the rows.

The CRM's `is_primary` columns (`sql/ksf_crm_person_account_roles.sql:21`) are
**not** carried over — per ambiguity 8 the estate has no primary-contact
concept.

### 6. The incomplete handling is written down, with degradation rules

The model is deliberately incomplete in nine places. Each has a **degradation
rule**, because a screen that shows something *wrong* is worse than one that
shows something incomplete. The CRM-facing note is
**`~/Documents/ksf_FA_CRM/ProjectDcs/PARTY-ACCOUNT-MODEL-INCOMPLETE-HANDLING.md`**
and it is the authoritative place for the CRM's rendering rules.

## Alternatives considered

### A. Keep duplicate person records (the status quo, and the owner's other reading)

**What it is.** Do not build a person anchor. Each hat keeps its own
`0_crm_persons` row, and the estate simply does not know they are the same
human being.

**Why it was rejected.** It is the defect, not a solution. FA already produces
two or three rows per human today, and nothing links them, so the estate cannot
answer "are these the same person?" — which is the question that stops the same
person being invoiced twice, mailed twice and counted twice in the loyalty
balances. It also cannot express *"the same person in a different role"*, which
the owner explicitly asked for.

**What it costs.** Nothing to build. That is its only merit, and it is
incompatible with every one of the seven operations the owner named.

**When it would be the right answer.** If the estate had no shared
person-resolution need at all — one customer per human being, one hat each, no
households, no boards, no merges. That is not the estate.

### B. A single `crm_persons` row per human, with the roles as columns

**What it is.** Extend FA's person row with `is_customer`, `is_supplier`,
`is_employee`, `is_director`, each holding a contact detail set.

**Why it was rejected.** It is the overload the owner named, in a new coat. A
person who is a customer at one address and a director at another needs **two
sets of contact details**, and a row can only hold one. It also requires an
ALTER of FA core, which `AGENTS_ARCH.md` §12.2 forbids in spirit and the
decision on `0_ksf_crm_contacts` forbade in practice.

**What it costs.** One ALTER, one row per person, and every question of the form
"which email do we use for this hat?" becomes a special case.

### C. Put the person anchor in the CRM's own table

**What it is.** `0_ksf_crm_persons` beside FA's `0_crm_persons`.

**Why it was rejected.** It creates a **second contact registry** — the exact
defect `AGENTS_ARCH.md` §12.2 exists to end, and the exact defect that
`0_ksf_crm_contacts` was deprecated for. It also gates a shared seam on the CRM
module's activation, which §12.2 forbids.

**What it costs.** A migration, and a permanent second place to look.

### D. Put the model in a new standalone package

**What it is.** A `ksf_party` Composer package, separate from
`ksf-fa-common`.

**Why it was rejected.** It would be a **second seam** for the same data, which
is what ambiguity 3 was raised about and ruled against. `ksf-fa-common` is
already loadable everywhere and already owns the contact resolver; the party
model is the same kind of thing.

**What it costs.** One more package edge, one more version to bump, and a
package that has to be a dependency of everything that uses the resolver.

### E. Build the seven operations inside the CRM

**What it is.** The CRM owns the party/account tables and the merge/split/spin-off
code directly.

**Why it was rejected.** The operations are **platform contracts**: HRM, Sales,
EmailManager and the WooCommerce sync all need to observe an account merge. If
the CRM owns them, every consumer is gated on the CRM's activation — the rule
§12.2 states a shared seam must never violate. It also puts a *platform* schema
in a *business* module, which is the same class of mistake as putting a contact
registry in the CRM.

**What it costs.** Nothing up front; the cost is paid by every consumer.

### F. Do nothing about the account lifecycle; only separate the concepts

**What it is.** Build the person/party/role separation and leave merge, split,
spin-off, promote and link unimplemented.

**Why it was rejected** as a *complete* answer, and **accepted** as a *staged*
one. The separation without the operations leaves the estate unable to record
the six of the seven things the owner named. But the operations that need a
product decision (transaction re-pointing, balances on a divorce, GL separation
on a spin-off) **cannot be shipped whole** while those decisions are open.

**What it costs.** Nothing; this is the staging plan, and it is the reason the
requirement set marks the undecided parts explicitly rather than guessing.

### G. Move transactions when accounts merge

**What it is.** Rewrite `debtor_trans`, `cust_allocations`, sales orders and
credit notes so the surviving account owns everything.

**Why it was rejected *for now*.** It is a large, irreversible migration across
every report in the estate, and it is a **product** decision — the owner has not
said which account's history a merged account should carry. The absorbed account
is retired rather than deleted and the `successor` link records the history,
which keeps two account histories legible without changing a single number.

**When to revisit.** As a separate project, with the reports re-checked, after
**OQ-B** is answered.

## Consequences

- **Eight new tables** are proposed in the shared package
  (`0_ksf_common_persons`, `_person_cards`, `_parties`, `_party_members`,
  `_accounts`, `_account_roles`, `_account_links`, `_account_events`), and the
  package's install path must create them.
- **The resolver contract grows by four sibling methods** across two new
  contracts, and the package's published version takes a major bump.
- **Five CRM screens stop dying** and start rendering, once their person lookups
  go through the shared seams.
- **Two live CRM tables are retired**, in the order: repoint the pages, then
  retire the tables. Their `is_primary` columns are dropped with them.
- **The CRM's own `0_ksf_crm_life_events` and `0_ksf_crm_contact_relationships`
  are re-pointed** from FA's `crm_persons.id` (a card) to the root person id —
  but only after the root person exists for every person those tables reference.
- **The estate's person identity gains a second id space.** Every satellite
  table that means *"the human being"* must key on the person id; every table
  that means *"the contact record for a role"* keys on the card id. A table
  that has not been classified is a latent bug.
- **The estate keeps two account histories across a merge**, until **OQ-B** is
  answered. That is a visible cost, and the successor/predecessor links are what
  make it legible.
- **The registry is company-scoped**, so the same human in two companies is two
  persons. That is almost certainly wrong for a multi-company estate, and
  retro-fitting a global registry after two companies have each seeded their own
  roots is a painful merge of identities. **Decide before the first
  multi-company deployment** (**OQ-F**).
- **The reconciliation job becomes a standing cost.** It reports probable
  duplicates (FR-CRM-011-008) and role/link drift (**I7**). It reports; it does
  not repair.
- **The shared model's schema is a proposal, not a ratified schema.** The CRM's
  requirements name the contracts for exactly that reason. If the table layout
  changes, the CRM requirements do not.

## What is explicitly INCOMPLETE

The model is deliberately incomplete in nine places. The canonical list and its
degradation rules are in `Party_Account_Model_2026-10.md` §6.4; the CRM-facing
rendering rules are in
**`~/Documents/ksf_FA_CRM/ProjectDcs/PARTY-ACCOUNT-MODEL-INCOMPLETE-HANDLING.md`**.

| # | What is incomplete | The degradation rule, in one line |
|---|---|---|
| **I1** | Person → account for pre-existing data | state **"unseeded"** — never an empty list that means "no links" |
| **I2** | No primary contact | list the account's contacts; do not mark one |
| **I3** | No FA representation of party or family | party screens are ours alone; show nothing rather than half a hierarchy |
| **I4** | No ledger-level merge/split | the merge/split screens **warn** that balances stay where they are |
| **I5** | `0_users` is not linked by FA | our link is ours to keep; drift is reported |
| **I6** | The resolver cannot see relation-less people | read the **person directory**, not the resolver, where unlinked people must be visible |
| **I7** | Our role rows can drift from FA's relations | a reconciliation job reports orphans; FA's own deletes remove relations behind our back |
| **I8** | Cloned accounts do not stay in step | the outcome states which fields were copied and which were left to the operator |
| **I9** | The registry is company-scoped | every person screen states the company |

**Seven open questions remain**, and each blocks a specific operation:
**OQ-A** (may a merge delete?), **OQ-B** (transactions), **OQ-C** (balances on a
divorce), **OQ-D** (GL separation on a spin-off), **OQ-E** (move or clone on a
promotion), **OQ-F** (global or company-scoped registry), **OQ-G** (where life
events live), **OQ-H** (the `AGENTS_ARCH.md` §12.2 sentence), **OQ-I** (may a
merge change contact details). The CRM's copy of these is in
`PARTY-ACCOUNT-MODEL-NOTES.md` §8; the shared copy is in
`Party_Account_Model_2026-10.md` §9.

**What is safe to build now.** The vocabulary; the empty tables; the read
contracts; lazy root-person creation; ASSOCIATE; SOFT LINK; CLONE-WITH-LINK;
MERGE with variant `rename`; retiring an account (deactivate, not delete); the
reconciliation job; and capturing roles on newly created accounts. What is not:
the full merge, the split with balances, the spin-off with its GL separation,
and the promotion's commercial treatment. `Party_Account_Model_2026-10.md` §6.2
and §6.3 give the item-by-item list.

## Cross-references

**The two views, and how they are kept from drifting.**

| | Shared view | CRM view |
|---|---|---|
| Design | `Party_Account_Model_2026-10.md` (this directory) | `~/Documents/ksf_FA_CRM/ProjectDcs/PARTY-ACCOUNT-MODEL-NOTES.md` |
| Requirements | `Requirements/BR-COM-010`, `Requirements/FR-COM-010-001…014`, `Requirements/UC-COM-010-001…007` — **proposed in the design's §7.2 and NOT YET WRITTEN** | `~/Documents/ksf_FA_CRM/ProjectDcs/BR-CRM-011-party-account-lifecycle.md`, `FR-CRM-011-001…008`, `UC-CRM-011-001…007` |
| Incomplete handling | design §6.4 | `~/Documents/ksf_FA_CRM/ProjectDcs/PARTY-ACCOUNT-MODEL-INCOMPLETE-HANDLING.md` |
| Open questions | design §9 (`OQ-1…OQ-9`) | notes §8 (`OQ-A…OQ-I`) |
| Decision | this file | referenced by BR-CRM-011 and by every FR in the set |

**The requirement set in `Requirements/` does not yet contain the COM-010
files.** Verified 2026-10-20: `Requirements/` holds `BR-ACL-001`, `BR-ACL-010`,
`BR-CAL-010`, `BR-EM-001`, the `FR-ACL-*` / `FR-CAL-*` / `FR-EM-*` sets,
`UC-EM-001` and `OPEN-QUESTIONS.md` — and no `COM-010` file. The shared
design's own header says its requirement set "are **not yet written**". **This
ADR therefore records a decision whose shared requirement set is still to be
written**, and the CRM's set is the first written expression of it. When the
COM-010 files are written they must be consistent with `BR-CRM-011`; when the
CRM's set changes, this ADR and the shared design must be updated in the same
commit.

**Other governing documents:** `AGENTS_ARCH.md` §12.2 (native FA data access;
the shared contact resolver) · `Contact_Ambiguity_Review_2026-10.md` (the eleven
ambiguities and their recommended rulings — this decision contradicts **none**
of them) · `Contact_Access_Inventory_2026-10.md` (144 contact-access sites
across 46 repositories) · `Table_Naming_Audit_2026-10.md` (the `0_fa_*`
problem).

**Two corrections to the shared design document**, both verified 2026-10-20 and
both recorded in `PARTY-ACCOUNT-MODEL-NOTES.md` §7:

1. The design's §0 says the generic CRUD class `simple_crud_class` "has **no
   consumer anywhere in the FA tree**". It does: `includes/ui/contacts_view.inc:12`
   includes it and `:18` declares `class contacts extends simple_crud`, and that
   view is instantiated at `sales/manage/customers.php:363`,
   `sales/manage/customer_branches.php:321` and `purchasing/manage/suppliers.php:323`.
   The **conclusion is unchanged** — there is no data-level clone function of
   any kind, so every clone is built — but FA *does* ship a UI-level **"Clone
   this contact"** button (`includes/ui/simple_crud_class.inc:227`), which makes
   the probable-duplicate rule operational rather than theoretical.
2. The design's §6.5 says the CRM's `0_ksf_crm_person_account_roles` is read
   through `0_fa_crm_person_account_roles`, "which was never created". That was
   true when the ambiguity review was written and is **stale**: `ksf_FA_CRM`
   commit `3353165` (2026-10-19 22:14) renamed every `0_fa_crm_*` reference to
   `0_ksf_crm_*`. Both tables now have schema and are live. The supersession
   plan stands, but it is a **migration with real rows**, not a bug fix.

---

*Accepted 2026-10-20 from the estate owner's party/contact/account reasoning.
Verified against FA 2.4.3 at `ksf_Infrastructure/FA/2.4.3/` and against
`ksf_FA_CRM` `main` at `3353165`. **No production code was modified, no test
suite was run, and no FA table was written to.***
