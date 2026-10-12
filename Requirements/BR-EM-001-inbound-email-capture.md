# BR-EM-001 — Capture inbound email as a first-class business record

@BABOK Related: BABOK 5.3 Business Requirements Analysis, 7.3 Solution Analysis
Status: **Proposed — awaiting business sign-off**
Module: `ksf_FA_EmailManager` (module code `EM`)
Date: 2026-10-11
Research basis: live integration database (`ksfii_app-mariadb`, DB `ksf_fa`) and
`ksf_Infrastructure/FA/2.4.3` source tree, read 2026-10-11.

---

## 1. Business Need

Inbound email to a support or sales address is, today, the single most common way a
customer initiates a commercial conversation. It arrives with the customer's
identity already attached (their real From address), it arrives with context (the
subject, the body, often a document), and it is frequently copied to other people
who then become participants in the business relationship.

In FrontAccounting today, that message has **no home**. The people who write it
inbound paper correspondence or paste it into a note; the mail server holds it
until a retention policy deletes it; and nothing in FA can answer "what did this
customer actually send us in March?"

The business need is therefore not "read email". It is:

> **A message sent to the business is a business record from the moment it arrives,
> independent of whether the mail server still has it.**

## 2. The decision this requirement rejects

The conventional, and specifically the **SuiteCRM**, approach to inbound email is a
**pointer log**. SuiteCRM fetches from IMAP, resolves the sender to a contact, and
writes a lightweight activity row carrying the `message_id`, subject, sender and a
timestamp. It deliberately does **not** store the body. The message body remains a
concern of the mail server; the CRM keeps only the evidence that *a* message
existed.

**That approach is rejected here.** Its failure mode is not hypothetical:

- Mail servers apply retention policies. A 30-day deletion policy means the pointer
  survives and the content does not. The record becomes un-actionable retroactively,
  with no warning and no way to detect the loss.
- A user who deletes or moves the message in their own mail client — or a mail
  client configured to expunge on IMAP close — destroys the business record from
  outside the business system, without any audit trail and without an error.
- Anything downstream (an LLM summarising a thread, a support agent drafting a
  reply, an audit of what a customer was told) has to go back to the mail server,
  which is a different system with a different availability profile and a
  different retention policy.

### 2.1 This rejection is not theoretical — the anti-pattern is already in this codebase

`ksf_FA_CRM/includes/EmailImportService.php` is exactly the pattern being rejected.
It imports over IMAP and writes a row carrying:

```php
'email_message_id' => $email_data['message_id'],   // EmailImportService.php:166
```

into `0_ksf_crm_communications` — a CRM activity log whose `message` column holds a
body copy that is derived from `imap_body()` on the *whole* message and whose
`email_message_id` is the pointer. This is the SuiteCRM shape.

**Recommendation:** retire `EmailImportService` and have CRM read the EmailManager
record instead. See [FR-EM-001-04](./FR-EM-001-04-future-actions.md) §6.

Note that `EmailImportService` is also **inert**: verified on 2026-10-11 that no
file in any module references `EmailImportService` or `processEmailImport`; it
queries `TB_PREF . "fa_crm_contacts"` and `TB_PREF . "fa_crm_communications"`,
**neither of which exists** on the live database (the tables actually created by
`ksf_FA_CRM/sql/*.sql` are `0_ksf_crm_contacts` and `0_ksf_crm_communications`); and
it calls `update_email_sync_time()`, which **is not defined anywhere** in the
tree. It is dead, broken code that nonetheless documents the wrong architecture.

### 2.2 What we do instead

We store **the message itself**: headers, both bodies, attachments, the full raw
RFC822 source, and a stable identity that lets us recognise the same message again
without trusting the mail server to still have it. The mail server becomes a
**transport**, not a system of record.

## 3. Business Requirement

**BR-EM-001:** The system shall capture every inbound message addressed to a
configured mailbox as a **self-sufficient, persisted record owned by the business**,
such that the complete, accurate content of the message — headers, both body
representations, every attachment, and the raw source — remains fully available to
users and to downstream automation **for the entire retention period of the
business, regardless of any retention, deletion or expiry applied by the mail
server, and regardless of any deletion performed by a user in a mail client.**

The record shall be the **anchor** for everything derived from the message —
contact resolutions, attachments, and any downstream artefact such as a reply
draft, a support ticket, a task or an automated analysis.

## 4. Explicitly in scope

| # | In scope | Requirement |
|---|---|---|
| 1 | Full content capture, mail-server-independent | BR-EM-001 |
| 2 | Attachment persistence | FR-EM-001-02 |
| 3 | Resolution of **every** addressee to a contact, sender included | FR-EM-001-03 |
| 4 | Linking the message to sender contact, the contact's debtor, the team's own address, and all To/Cc/Bcc recipients | FR-EM-001-03, UC-EM-001 |
| 5 | The record as an extensibility anchor for LLM drafts, tickets, tasks and any future artefact | FR-EM-001-04 |

## 5. Explicitly out of scope

These belong to other modules by prior architecture decision (CampaignBuilder =
outbound journey automation; the planned **MailingList** module = subscribers and
open/click/read tracking; EmailManager = inbound only):

- Subscriber lists, double opt-in, unsubscribe tokens — `0_ksf_em_mailing_lists`, `0_ksf_em_subscribers`
- Campaign assembly and fan-out — `pages/campaigns.php`
- Outbound SMTP delivery
- Open / click / read tracking

See [Inbound_Email_Architecture.md](./Inbound_Email_Architecture.md) §7 for the
move-out inventory.

## 6. Verification method

Every factual claim in this document and in the documents it references was
checked against one of these sources. Claims that could **not** be verified are
marked **[UNVERIFIED]** and listed in
[Inbound_Email_Architecture.md](./Inbound_Email_Architecture.md) §9.

| Source | Used for |
|---|---|
| `podman exec ksfii_app-mariadb mysql … ksf_fa` (live integration DB) | table existence, column existence, row counts |
| `ksf_Infrastructure/FA/2.4.3/` source | FA core entity model, attachment mechanism |
| `ksf_Infrastructure/fa_modules/ksf_FA_EmailManager/` | current implementation |
| `ksf_Infrastructure/fa_modules/ksf_FA_Attachments/` | attachment reuse precedent |

## 7. Risks if this requirement is not met

| Risk | Consequence |
|---|---|
| Mail server retention expires | Silent, retroactive loss of customer correspondence |
| User expunges from their mail client | Undetected destruction of a business record |
| LLM/agent has no stable input | Automation cannot be made reproducible or auditable |
| Downstream artefacts orphaned | Tickets and drafts cannot be traced back to what prompted them |

## 8. Traceability

| Artefact | Type | Relates to |
|---|---|---|
| FR-EM-001-01 | Functional | BR-EM-001 |
| FR-EM-001-02 | Functional | BR-EM-001 |
| FR-EM-001-03 | Functional | BR-EM-001 |
| FR-EM-001-04 | Functional | BR-EM-001 |
| UC-EM-001 | Use case | BR-EM-001, all four FRs |

## 9. Open questions

See [Inbound_Email_Architecture.md](./Inbound_Email_Architecture.md) §10 for the
consolidated list. The ones that could change this requirement's scope:

- **Q1** — Should the mail server be cleared after capture (copy-then-delete)? This
  is the operational proof of BR-EM-001 but is a policy decision with mailbox-size
  and user-expectation consequences.
- **Q7** — Should the full raw RFC822 source be retained in addition to the parsed
  fields? Recommended yes; it is the only way to re-parse if the MIME walker is
  later found to be incomplete.