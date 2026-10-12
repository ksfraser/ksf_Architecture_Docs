# FR-EM-001-04 — The email record as the anchor for downstream action

@BABOK Related: BR-EM-001, BABOK 8.3 Solution Design, 9.3 Solution Delivery
Status: **Proposed**
Module: `ksf_FA_EmailManager`
Date: 2026-10-11

---

## 1. Requirement being satisfied

> "FUTURE-PROOFING IS MANDATORY: the model must support a support agent or automated
> system acting on a message — an LLM drafting a reply, creating a support ticket, or
> any other downstream action. Design the record so that derived artefacts (drafts,
> tickets, tasks) attach to the email record rather than requiring re-parsing."

The operative words are **"any other"** and **"rather than requiring re-parsing"**. The
requirement is therefore not "support LLM drafts" — it is *an open extension point
that a future module can use without a change to EmailManager's schema or code*.

## 2. Why the current model cannot do this

`0_ksf_em_inbound_emails` has exactly **one** artefact slot:

```
routing_action      VARCHAR(20)     'ticket' | 'opportunity' | 'lead'
linked_entity_id    INT(11)
linked_entity_type  VARCHAR(20)
KEY idx_routing (routing_action, linked_entity_id)
```

Written by `process_inbound_email()` (`em_routing.inc:31-52`). This supports exactly
**one** downstream artefact of exactly **one** shape. It cannot hold a draft *and* a
ticket *and* a classification *and* a sent reply. It cannot record who created what, or
when, or the model/prompt behind an LLM run. It is the SuiteCRM "one pointer per
message" shape and it is what BR-EM-001 rejects.

Verified further: the two targets it points at **do not exist**.

| Target | Referenced at | Exists on live DB? |
|---|---|---|
| `{TB_PREF}fa_st_tickets` | `em_routing.inc:71` | **No** |
| `{TB_PREF}crm_opportunities` | `em_routing.inc:92` | **No** (`0_ksf_crm_opportunities` exists, different name) |

There is **no support/ticket module in the org at all** — a scan of
`ksf_Infrastructure/fa_modules/` found nothing matching `sup|tick|help|case|serv`.
So the "support ticket" artefact has **no home module today**. This is open question
**Q3** and it is a decision the user must make before this FR can be completed.

## 3. Requirements

### FR-EM-001-04-1 — A generic, open artefact registry

Every derived artefact shall be recorded in a single module table, keyed to the
email, with **no fixed enumeration of artefact types**.

### `0_ksf_em_artefacts`

| Column | Type | Purpose |
|---|---|---|
| `id` | INT PK AI | |
| `email_id` | INT NOT NULL | FK → `0_ksf_em_inbound_emails.id` — **the anchor** |
| `artefact_type` | VARCHAR(32) | **free text, no ENUM** — `'draft'`, `'ticket'`, `'task'`, `'reply_sent'`, `'classification'`, `'summary'`, `'meeting'`, `'note'`, `'llm_run'`, … |
| `owner_module` | VARCHAR(64) | the module that owns the artefact — `ksf_FA_Tickets`, `ksf_FA_Calendar`, … |
| `artefact_ref` | VARCHAR(64) | **opaque, stable, human-quotable** key: `'TKT-2026-0042'`, `'draft-<uuid>'` |
| `artefact_id` | INT NULL | the row id in the owner's table; NULL for artefacts with no row of their own (an LLM run, a summary) |
| `status` | VARCHAR(32) | `'draft'`, `'sent'`, `'open'`, `'closed'`, `'superseded'`, `'failed'` — free text |
| `created_by` | VARCHAR(64) | FA user_id, or `'system'`, or `'llm:<provider>:<model>'` |
| `payload` | JSON NULL | the prompt/response for an LLM run; the ticket snapshot; the draft body |
| `created_at`, `updated_at` | TIMESTAMP | |

Indexes: `(email_id)`, `(artefact_type)`, `(owner_module, artefact_ref)` UNIQUE,
`(status)`.

**Why `artefact_type` must be `VARCHAR`, not an `ENUM`:** an `ENUM` makes adding a
new artefact kind a schema migration plus a code change in EmailManager. That is
precisely the coupling BR-EM-001 forbids. A `VARCHAR` with a registry constant list in
*consuming* code keeps EmailManager stable while new consumers appear.

**Verified precedent for JSON columns:** `0_fa_attachments` already uses
`backend_meta JSON` and `details JSON` (`ksf_FA_Attachments/sql/install.sql:22-24,33`),
so the server supports them. *(The JSON-column availability is inferred from the
module's own DDL; the live server's version was not checked. See §8.)*

### FR-EM-001-04-2 — Artefacts are appended, never overwritten

An artefact row is **immutable except for `status` and `updated_at`**. A new draft
superseding an old draft creates a **new row** with `status = 'superseded'` on the
old one. The full history of what an agent did to a customer's message is therefore
retained — which is a governance requirement once an LLM is writing to customers.

### FR-EM-001-04-3 — No re-parsing is ever required

Every consumer **MUST** be able to do its work from the persisted email record and
its `0_ksf_em_artefacts` rows alone, without connecting to a mail server and without
re-implementing MIME parsing.

Concretely, this requires the record to expose, without re-parsing:

| Consumer needs | Available from |
|---|---|
| the text to summarise or reply to | `body_text` / `body_html` |
| who to reply to | the `role='from'` addressee row |
| who to include | `role='to'/'cc'` addressee rows |
| which account to reply from | `account_id` → `0_ksf_em_accounts.email_address` |
| the business context | `debtor_no` on the email row |
| attachments to cite | `0_attachments` + `0_fa_attachments` (FR-EM-001-02) |
| thread context | `in_reply_to`, `thread_id`, `References` |
| original formatting fidelity | `raw_source` |

### FR-EM-001-04-4 — Provenance of automated action

Every artefact row **MUST** record `created_by`. When an automated system (in
particular an LLM) produces an artefact, `created_by` **MUST** identify the
provider and model, e.g. `llm:anthropic:claude-sonnet-4`, and `payload` **MUST**
retain the input and output.

**Rationale:** once an automated system can create a ticket from a customer's email
and draft a reply the customer may receive, the organisation needs an answer to
*"what did the system do, on whose instruction, from what input"* that does not
depend on a vendor's logs. This is BABOK 7.3 *System Integrity*.

### FR-EM-001-04-5 — Event dispatch at the right lifecycle points

FA's dispatcher (`includes/hooks.inc`: `hook_invoke`, `hook_invoke_all`,
`hook_invoke_first`, `hook_invoke_last`) shall be fired at these points, each with
the resolved `email_id` in the payload so no consumer needs to re-query or re-parse:

| Event | When | Payload minimum |
|---|---|---|
| `email_received` | **after** the message and all addressees are persisted | `email_id`, `account_id`, `from`, `debtor_no`, `contact_id` |
| `email_addressees_resolved` | after resolution, before routing | `email_id`, per-addressee `match_method` |
| `email_artefact_created` | after each artefact row is written | `email_id`, `artefact_type`, `artefact_id`, `artefact_ref`, `created_by` |
| `email_processed` | when triage/routing completes | `email_id`, `routing_action` |

**Ordering constraint:** `email_received` must fire **after** addressee resolution,
not before. The current `save_inbound_email()` (`em_db.inc:133`) fires
`email_received` from inside the INSERT, when `debtor_no` and `contact_id` are still
NULL — so any consumer that reacts to it has nothing to react with. **This is a
correctness fix, not a nicety.**

*Verified defect in the existing dispatcher:* `em_dispatch_event()`
(`em_db.inc:10-22`) first probes a `Ksfraser\Event\EventManager` that is not
installed, then falls back to `add_hook()` — **which is not an FA function**. FA
dispatches via `hook_invoke_all()` in `includes/hooks.inc`. The fallback is dead code
that would fatal if reached. `grep` for a function `add_hook` in FA core returns
nothing. **The dispatcher must be rewritten onto `hook_invoke_all()`.**

### FR-EM-001-04-6 — Per-record lifecycle hooks

EmailManager shall register itself into ksf_FA_Common's workflow hook scheme so that
record-level lifecycle points are available to other modules:

```
registerWorkflowType('email.message', 'em_email');
```

yielding `em_email_before_save`, `em_email_after_save`, `em_email_before_delete`,
`em_email_after_delete`, `em_email_new`, `em_email_edited`, dispatched through
`hook_invoke_all()`.

*Verified:* `WorkflowHooksTrait` and `CrudOperationsTrait` exist in ksf_FA_Common at
`ksfraser\FrontAccounting\Common\Traits\`, and `hook_invoke_all` is the FA-native
dispatcher (`includes/hooks.inc`). Adoption outside ksf_FA_Common's own tests and
`ksf_FA_HRM/hooks.php` is currently minimal, so this is a **convention to adopt**,
not an established framework to plug into. Flagged accordingly.

### FR-EM-001-04-7 — Deprecate the single-artefact columns

`linked_entity_id` / `linked_entity_type` / `routing_action` **MUST** become
deprecated read-only conveniences pointing at the *primary* artefact row, or be
dropped. They shall not be written by new code.

They are retained in the schema in this design because they are indexed
(`idx_routing`) and existing code (`process_inbound_email`, `pages/inbox.php`) reads
them. **Flagged as a decision — see Q14.**

## 4. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | A support ticket can be registered against an email in one INSERT into `0_ksf_em_artefacts` with `artefact_type='ticket'`, **without any change to EmailManager's code or schema**. |
| AC2 | Adding a new artefact type `'invoice_dispute'` works with zero code and zero migration. |
| AC3 | Two drafts of the same reply produce **two** artefact rows; the first is marked `superseded`; neither is deleted. |
| AC4 | An LLM-drafted reply records `created_by = 'llm:<provider>:<model>'` and `payload` containing both the prompt and the response. |
| AC5 | A consumer subscribing to `email_received` receives `debtor_no` and `contact_id` **populated**, not NULL. |
| AC6 | Deleting the message from the mail server and disabling the account still leaves every artefact fully readable. |
| AC7 | Every artefact for a given email is enumerable with a single indexed query. |
| AC8 | No consumer anywhere in the codebase calls `imap_*` to read a message that has already been captured. |

## 5. Worked example — LLM reply draft

```
1. A message arrives from alice@acme.com, To support@ksfraser.com, Cc bob@acme.com.
2. EmailManager persists the message, the 3 addressee rows, and 1 attachment.
   alice -> person 12, contact 30, debtor 3      (matched, confidence 1.00)
   bob   -> created_new, person 13, unlinked    (confidence 0.90)
   support -> account_self                     (no person)
3. hook_invoke_all('email_received', {...debtor_no: 3, contact_id: 30...})
4. An AI-drafting module reacts. It reads body_text, the from-addressee, the
   account's reply address and the debtor from the email record. It NEVER
   connects to IMAP.
5. It INSERTs one artefact row:
   email_id=8812, artefact_type='draft', owner_module='ksf_FA_AIDraft',
   artefact_ref='draft-9f3c…', status='draft', created_by='llm:anthropic:claude-sonnet-4',
   payload={model, prompt, response, temperature, token_usage}
6. hook_invoke_all('email_artefact_created', {...})
7. A human reviews in the inbox UI, edits, and sends. A second artefact row
   (artefact_type='reply_sent') records what was actually sent. The draft row is
   marked 'superseded'. Both are retained.
```

## 6. Retirement of the CRM pointer path

`ksf_FA_CRM/includes/EmailImportService.php` is the SuiteCRM-style pointer importer
described in [BR-EM-001 §2.1](./BR-EM-001-inbound-email-capture.md#21-this-rejection-is-not-theoretical--the-anti-pattern-is-already-in-this-codebase).

**Requirement:** it **shall be deleted**, and CRM shall read the EmailManager record
via the artefacts table instead.

**However, three capabilities in it must be preserved first**, or functionality is
lost:

| Capability | Location | Disposition |
|---|---|---|
| Recursive MIME walk + transfer decoding | `parseParts()` `:236-265`, `decodeContent()` `:319-329` | Lift into EmailManager (FR-EM-001-01 §3, FR-EM-001-02 §3.1) |
| ICS detection and parsing | `getICSParts()` `:214-234`, `parseICSContent()` `:353-416` | Lift (FR-EM-001-02 §4.4) |
| Meeting creation from ICS | `createOrUpdateMeetingFromICS()` `:439-474` | Reimplement against `0_ksf_crm_meetings` after the DELETE, or move to the CRM module (Q9) |

**Verified:** the class is currently referenced by nothing. It queries two
non-existent tables and calls one undefined function, so nothing depends on it.

## 7. Out of scope

- Deciding *what* an LLM should be prompted to do. EmailManager provides the anchor
  and the provenance; the prompt belongs to the consuming module.
- The contents of the draft body.
- Ticket lifecycle, SLAs, assignment — owned by the (not-yet-identified) ticket module.
- Sending the reply. FA has a mailer (`includes/mail/*.inc`, `email_send()`); whether
  EmailManager or CampaignBuilder owns outbound transport is a separate decision
  (**Q8**).

## 8. Unverified

| Item | Status |
|---|---|
| Live server supports `JSON` columns | **[UNVERIFIED]** — inferred from `0_fa_attachments`' DDL; server version/`sql_mode` not inspected |
| Existence of a support-ticket module | **[UNVERIFIED]** — none found under `ksf_Infrastructure/fa_modules/`; a private/undeployed module could exist elsewhere |
| `WorkflowHooksTrait` adoption depth | **[UNVERIFIED]** — trait exists and is documented in `AGENTS_ARCH`; only minimal adoption was observed |
| Whether FA core defines a function `add_hook` | **Verified absent** from `FA/2.4.3` — the `em_dispatch_event` fallback is dead |

## 9. Open questions

| # | Question |
|---|---|
| **Q3** | **Which module owns the support ticket artefact?** `0_fa_st_tickets` does not exist and no ticket module is present. Options: (a) create a new `ksf_FA_Tickets` module, (b) use `ksf_FA_CRM`'s opportunity/case, (c) EmailManager owns a minimal ticket table. **Recommend (a)**, since requirement 5 explicitly names tickets. |
| **Q8** | Who owns outbound transport — EmailManager, CampaignBuilder, or `ksf_FA_Mail`? Affects whether `reply_sent` is recorded by EmailManager or its caller. |
| **Q14** | Keep `linked_entity_id`/`linked_entity_type` as a de facto primary-artefact pointer, or drop them? |
| **Q15** | Does an LLM artefact require human approval before it can become customer-visible? Recommend **yes** — `status='draft'` is never actionable until a named user promotes it. |

## 10. Related

- [BR-EM-001](./BR-EM-001-inbound-email-capture.md) §2.1 — the pattern being retired
- [FR-EM-001-01](./FR-EM-001-01-message-persistence.md)
- [UC-EM-001](./UC-EM-001-support-request.md)
- [Inbound_Email_Architecture.md](./Inbound_Email_Architecture.md)