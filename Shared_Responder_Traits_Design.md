# Shared Responder Traits — what belongs in a trait, and what must not

**Date:** 2026-10-14
**Status:** DESIGN RECOMMENDATION. **Nothing in this document is implemented.**
**Scope:** the ACL responder layer described in
[`Requirements/BR-ACL-010-event-driven-ownership.md`](./Requirements/BR-ACL-010-event-driven-ownership.md),
[`Requirements/FR-ACL-010-04-ownership-transitions-and-provenance.md`](./Requirements/FR-ACL-010-04-ownership-transitions-and-provenance.md)
and [`ACL_Two_Approaches.md`](./ACL_Two_Approaches.md); the existing
`ksfraser/traits` package; and the capability contract just landed in
`ksf_FA_Calendar` (`BR-CAL-010` / `FR-CAL-010-001`).
**Tag key:** **[V]** verified against source or a live run. **[D]** proposed
design. Untagged statements are decisions or reasoning.

---

## 0. Read this first

The question — "should shared ACL responders be traits?" — has a short answer
that the rest of this document justifies:

> **The *registration* half of a responder is mechanical and belongs in a trait.
> The *decision* half carries the record type's business meaning and must stay a
> concrete class in the module that owns the record.**

Everything else here is (a) how to draw that line without guessing, (b) where the
mechanical half should live, and (c) why the tempting middle position — a
"generic ACL responder base class" — is the worst of the three options.

---

## 1. The line, stated precisely

A responder has four separable parts. Only two of them are module-agnostic.

| Part | Example | Mechanical? | Home |
|---|---|---|---|
| **1. Identity** — "I am `ksf_FA_Sales`, and I answer for `sales_order` and `sales_invoice`." | `$this->aclRecordTypes()` | **Yes.** A list of strings. No policy in it. | **Trait.** |
| **2. Dispatch shape** — "answer `null` when the record type is not mine; hand the rest to my policy method." | `aclHandlesType()`, `null` for not-mine | **Yes.** Identical in every module, including the `null` convention of `hook_invoke_first`. | **Trait.** |
| **3. Registration** — "register a handler for the named lifecycle event `orphaned_record`." | `$this->registerAclResponder('orphaned_record', ...)` | **Mostly yes**, with one hard constraint: the *event name* is data, not behaviour. | **Trait, with validation.** |
| **4. Policy** — "invoices never transfer ownership." "an orphaned sales order escalates to the account manager, an orphaned *task* does not." | `aclCanTransferOwnership()` | **No.** This is the module's business. | **Concrete class, in `ksf_FA_Sales`.** |

The test for part 4 is short and worth stating because it is what keeps this
from drifting: **if a sentence expressing the rule would have to name a table,
a status, or a workflow meaning in order to make sense, it is not mechanical.**
"Invoices never transfer ownership" fails that test (it names a document type
and a policy). "Return null when the record type is not in my list" passes it
without naming anything at all.

`ksf_FA_Calendar` demonstrates the same split in a different domain, which is
why it is a useful precedent: `CalendarEntryCreateRequest::SUPPORTED_FIELDS`
(a list — mechanical, now a trait-shareable constant) and
"a follow-up task gets `source_type = 'task'`" (a decision — stays in Calendar).

### 1.1 Why part 4 must not be a trait

`ksfraser\Traits\AttachmentOperationsTrait` **[V — `ksfraser/traits` v1.4.0,
consumed by `FA_Calendar_Module.php:41`; commit `9bb6516` in
`ksf_FA_Calendar` replaced an in-module copy]** is the correct shape: the
operations (`addAttachment`, `removeAttachment`, `getAttachments`) are one set of
steps applied identically to every attachment in the system. Nothing in it says
what an attachment *means*.

An ACL policy is the opposite. `aclCanTransferOwnership()` has a different answer
per record type, and the answer is the module's. Putting it in a shared trait
means the trait has to ask "what type is this?" and branch — and once the trait
branches on record type it is a policy engine wearing a trait's clothes, with
all of a trait's discoverability problems and none of a policy engine's
structure.

---

## 2. What goes in the shared trait, concretely **[D]**

Proposed shape (illustrative, **[D]** — this is not an API):

```php
namespace Ksfraser\Traits\Acl;

/**
 * The mechanical half of an ACL responder.
 *
 * Supplies: identity (which record types you answer for), the null convention,
 * and named-event registration. Does NOT supply any policy: every
 * acl*Policy() method must be implemented by the using class.
 */
trait AclResponderTrait
{
    /** @return string[] Record types this responder owns, e.g. ['sales_invoice'] */
    abstract protected function aclRecordTypes(): array;

    /** @return string[] Lifecycle event names this responder registers for. */
    abstract protected function aclResponderEvents(): array;

    /**
     * The FA hook. Returns null when the record type is not ours, so
     * hook_invoke_first moves on. Policy is delegated to aclRespond().
     */
    public function acl_respond(&$data, $opts = []) { /* ... */ }

    /** Implemented by the module. Must return null for "not my concern". */
    abstract protected function aclRespond(string $event, array $data, array $opts);

    protected function aclHandlesType(?string $recordType): bool { /* ... */ }
    protected function registerAclResponder(string $event, string $hook): void { /* ... */ }
}
```

Three properties that make it safe rather than merely convenient:

1. **It cannot be half-used.** The trait's policy method is `abstract`, so PHP
   refuses to instantiate a class that uses the trait without implementing the
   decision. A shared trait that supplied *default* policy would be the failure
   mode in §5.
2. **It cannot answer for a record type it did not declare.** `acl_respond()`
   checks `aclRecordTypes()` first and returns `null`. **[D]** This is the
   `null`-means-"not handled" convention of `hook_invoke_first`
   (`includes/hooks.inc`) **[V — see `AGENTS_ARCH.md` §10/§11]**, expressed once
   rather than restated in each module's hook body.
3. **Registration validates.** `registerAclResponder()` rejects an event name
   that is not in `aclResponderEvents()`, and every module implementing
   `FR-ACL-010-04` declares the same event vocabulary. A typo in an event name
   becomes an exception at activation, not a responder that silently never fires.

### 2.1 What it deliberately does not contain

| Not in the trait | Why |
|---|---|
| Column/row predicate SQL | That is `ksf-common-db` (`QueryBuilder`), and `ACL_Two_Approaches.md` §2.1–§2.3 puts it in one place already. A second mechanism beside the builder is the drift risk §7 of that document describes. |
| Provenance recording | Schema of `0_rbac_*_provenance` is not settled (FR-ACL-001-01); a trait that stamps provenance before the schema exists is a guess. |
| Escalation / notification | Workflow semantics. Belongs to the workflow module, and per `README.md` standing decision #3 the responder **returns data** and the consumer renders. |
| Any table name, column name, or status constant | The moment a shared trait names `sales_order`, `ksf_FA_Sales` is no longer optional to change it. |

---

## 3. Where it lives, and why **[D]**

**Recommendation: `ksfraser/traits`, not a new package, not `ksf-common-db`, not
`ksf_FA_Common`.**

| Candidate | Verdict |
|---|---|
| **New package** (`ksfraser/ksf-acl`) | **Rejected for now.** A package is justified by a second consumer needing the same *contract*. Today the contract is an FA hook signature plus a `null` convention, both of which live in FA core — so the trait would have exactly one consumer and would be a package with a `.php` file in it. Revisit when a second module ships a second responder and both are demonstrably the same shape. |
| **`ksf_FA_Common`** | **Rejected.** It is FA-module-flavoured by name and by namespace (`ksfraser\FrontAccounting\Common\`), and it is being hollowed out into a no-op module shell precisely so this kind of shared logic stops accumulating there **[V — `AGENTS.md`, "ksf_FA_Common is now a pure Composer/Packagist package"]**. Putting ACL responder mechanics back would reverse that decision. |
| **`ksf-common-db`** | **Rejected.** Its stated boundary is a transport-agnostic data dictionary + query builder (`ksfraser\CommonDb\Contract\DbConnectionInterface` and up) **[V — `AGENTS.md`, "ksf_common_db package — implemented"]**. A hook-shape trait is not a database concern. |
| **`ksfraser/traits`** | **Accepted.** It already exists, already hosts `AttachmentOperationsTrait` for exactly this kind of module-agnostic operation set, and is already a dependency of `ksf_FA_Calendar` **[V — `composer.json` `"ksfraser/traits": "^1.3"`]**. The three-repo convention is respected because the trait contains **no** `ksf_X` business logic: it is consumable by `ksf_X` (business), `ksf_X_UI` (which today holds no policy, only views), and `ksf_FA_X` alike, which is precisely what makes it a trait rather than a service. |

**On the three-repo convention** (`ksf_X` business / `ksf_X_UI` / `ksf_FA_X`):
the trait does not belong to any of the three, and that is the point. If it did,
it would be in `ksf_X`. What it *is* is the part of `ksf_X`'s ACL responder that
survives deletion of every record-type-specific rule — so the correct place for
the residue is the shared library, and the correct place for the residue's
*companion tests* is likewise the shared library, with one integration test per
module asserting that module's policy.

---

## 4. The trait's counterpart: what each module still owes

Using `AclResponderTrait` is cheap; **not using it is not free**, and that is the
point worth stating to anyone tempted to write the trait and stop there:

- Every module with ACL-managed records must still declare its record types and
  its events. A module that does not is simply absent from the responder set —
  and, per `BR-ACL-010` R7, *absence* is one of the three causes of orphaned
  records. A shared trait cannot fix a module that never opted in.
- The module must implement the policy methods concretely, and those are the
  lines a reviewer reads. Review effort does not move into the trait; it stays
  where the meaning is.
- The `null` return is a **claim** ("not my concern"), not a formality. `null`
  from `acl_respond()` when the record type *is* in `aclRecordTypes()` is a bug
  that looks like a non-participation. **[D]** Guard it: the trait should raise
  rather than return `null` in that case, because the two cases are
  indistinguishable at the dispatch site and only one of them is correct.

---

## 5. The failure mode of over-using traits here

This is the section to read if you remember nothing else.

**The failure mode is that a trait accumulates business rules by accretion, and
because a trait is *not* an object, nothing forces the accretion to be visible.**

The mechanism, in order:

1. **It starts honest.** `AclResponderTrait` contains only dispatch shape. Two
   modules use it. It looks like a proven abstraction.
2. **`SalesAclResponderTrait` needs one exception.** Invoices never transfer
   ownership — but that is the *Sales* rule, so it lands in `ksf_FA_Sales`, not
   in the trait. Good. (This is the discipline working.)
3. **A second module needs a similar exception.** HRM also has a record type that
   never transfers. Now there are two identical rules in two modules. The pull
   is irresistible and wrong: they look the same *today* and are different facts.
   Moving them into the trait makes the trait's name a lie (`Acl` is no longer
   "dispatch shape") and couples HRM's ownership rules to Sales' release cycle.
4. **The trait now branches on record type.** It needs to know `sales_invoice`
   exists. It now depends on a vocabulary it does not own, and the modules now
   depend on each other through it. A change to Sales' document types breaks
   HRM's build.
5. **The branches are untestable in isolation.** "Test the trait" means "test it
   as used by each module", so the apparent unit-test coverage is a fiction: the
   shared code has no shared test, only N copies.
6. **The failure is silent by construction.** There is no type error, no missing
   method, no failing assertion. There is a responder in `ksf_FA_HRM` that
   silently stops transferring ownership for invoices because someone moved a
   condition into a trait and nobody re-read the diff — it is a *policy* change
   dressed as a refactor, in a file whose name suggests it could not possibly
   contain policy.

Three specific trip-wires to watch for, all of which are the same mistake wearing
different clothes:

- **A trait method that takes a record type as a parameter.** That is a dispatch
  table; it belongs in the policy layer.
- **A trait method that returns a SQL fragment.** That is the query builder's
  job, and duplicating it is exactly the bypass class `ACL_Two_Approaches.md`
  §1.2 enumerates (hand-written SQL reaching `db_query()` without passing
  `QueryBuilder::toSql()`).
- **A trait that any module can use with a one-line `use`.** Mechanical enough
  for that is not worth sharing; it is a function, and a function in a namespace
  is cheaper to read than a trait.

The mitigation is a rule, not vigilance:

> **A trait in this system may not contain a conditional whose branch depends on
> a value the trait does not own** — a record type, a table name, a status, a
> module name. If it needs one to decide anything, it is policy, and policy lives
> in the module.

---

## 6. Summary

| Question | Answer |
|---|---|
| Which responder behaviours are genuinely mechanical? | Declaring which record types you answer for; returning `null` for the rest; registering a handler for a named lifecycle event; the `hook_invoke_first` null convention. |
| Which must stay concrete? | Everything that decides: what "transfer ownership" means for a document type, what counts as orphaned, who escalates, what provenance to write. |
| Where does the trait live? | `ksfraser/traits`, alongside `AttachmentOperationsTrait`. Not a new package (one consumer), not `ksf_FA_Common` (being deliberately emptied), not `ksf-common-db` (wrong boundary). |
| How does it fit the three-repo convention? | It is the residue of `ksf_X` after its record-specific rules are deleted, so it belongs to none of the three and to all of them. |
| What is the over-use failure mode? | Business rules accrete into a trait by duplication-and-deduplication, and a policy change then hides inside a refactor in a file whose name says it cannot hold policy. |

## 7. Related

- [`Requirements/BR-ACL-010-event-driven-ownership.md`](./Requirements/BR-ACL-010-event-driven-ownership.md) — R7 (three causes of orphaned records, one of which is non-participation), R8 (the action axis is an application-boundary check, not a SQL predicate)
- [`Requirements/FR-ACL-010-04-ownership-transitions-and-provenance.md`](./Requirements/FR-ACL-010-04-ownership-transitions-and-provenance.md) — transitions as registered responders; `null` = not my concern
- [`ACL_Two_Approaches.md`](./ACL_Two_Approaches.md) — why predicate SQL must not be duplicated outside `QueryBuilder::toSql()`
- [`README.md`](./README.md) — standing decisions #2 and #3 (no cross-module table access; responders return data, consumers render)
- `ksf_FA_Calendar/src/Ksfraser/FA/Calendar/Capability/` — the same split, in a different domain: a published field *list* (mechanical) alongside a rule about what a task *is* (a decision)