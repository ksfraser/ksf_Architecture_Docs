# UC-EM-001 — A customer emails support, copying their spouse

@BABOK Related: BR-EM-001, FR-EM-001-01, FR-EM-001-02, FR-EM-001-03, FR-EM-001-04
Status: **Proposed**
Module: `ksf_FA_EmailManager`
Date: 2026-10-11

---

## 1. Narrative

> **The user's exact scenario:** a customer emails the support address, and copies
> their spouse on the message.

**Primary actor:** Alice Nguyen — an existing customer, contact person on debtor
`ACME-001` (3). Her spouse Bob Nguyen has never corresponded before and is not yet a
contact in FA.
**Secondary actor:** the ksf support mailbox `support@ksfraser.com`
(`0_ksf_em_accounts` id 1).
**Supporting actors:** the sync worker; the addressee resolver; an automated
reply-drafting module.

**Trigger:** Alice sends an email to `support@ksfraser.com`, copying `bob@acme.com`,
about a duplicated invoice, and attaches a PDF of the statement.

**Preconditions (verified shape of the FA data):**

```
0_debtors_master      debtor_no 3 = 'Acme Pty Ltd'          (3 rows total)
0_crm_persons         id 12, name 'Alice Nguyen', email 'alice@acme.com'
                      linked: add_crm_contact('customer','general', 3, 12)
                      -> 0_crm_contacts row: person_id 12, type 'customer',
                         action 'general', entity_id 3
0_crm_accounts        id 1, email_address 'support@ksfraser.com',
                      server_host <imap>, sync_folder 'INBOX'
0_crm_persons         NO row for 'bob@acme.com'
```

---

## 2. Main success scenario

### Step 1 — Sync picks up the message

`sync_email_account(1)` connects to IMAP, reads `UIDVALIDITY` (**9001**), reads its
stored cursor (**last UID 4120**), and searches `UID 4121:*`. It finds UID 4121 and
stops — it does **not** re-walk the mailbox.

*Entities:* `0_ksf_em_accounts`, `0_ksf_em_inbound_emails`

### Step 2 — Cheap duplicate check

Message-ID is `<20261011.abc123@acme.com>`. A lookup on
`(account_id, message_id)` finds nothing; neither does the `content_hash` fallback.
Proceed.

*If it had matched,* the system would update `uid`/`uidvalidity`/`synced_at` and stop —
no body fetch. This is the dedupe that makes re-running safe, and the content
persistence that makes server-side deletion harmless.

### Step 3 — Persist the message

Insert into `0_ksf_em_inbound_emails`:

| Column | Value |
|---|---|
| `account_id` | `1` |
| `message_id` | `20261011.abc123@acme.com` (normalised — `<>` stripped) |
| `subject` | `Duplicate charge on invoice 4471` |
| `from_address` | `alice@acme.com` |
| `from_name` | `Alice Nguyen` |
| `received_date` | `2026-10-11 09:14:22` (from the `Date` header) |
| `body_text` | decoded plain-text body (**LONGTEXT**) |
| `body_html` | decoded HTML body (**LONGTEXT**) |
| `raw_headers` | the full RFC822 header block (**MEDIUMTEXT**) |
| `raw_source` | the complete RFC822 blob (**LONGTEXT**) |
| `uid` | `4121` |
| `uidvalidity` | `9001` |
| `content_hash` | `sha256(...)` |
| `in_reply_to` | *(null — new thread)* |
| `thread_id` | `20261011.abc123@acme.com` |
| `is_processed` | `0` |
| `synced_at` | now |

→ new row **id 8812**.

### Step 4 — Recursive MIME walk

The message is `multipart/mixed` → [`multipart/alternative` (text/plain + text/html),
`application/pdf`]. The walk **recurses**; the current code would not have found the
bodies. All three parts are fetched with `imap_fetchbody()` and
content-transfer-decoded.

### Step 5 — Persist the attachment

The PDF, `Acme_Statement_2026-09.pdf`, 44 210 bytes:

1. `company/0/attachments/` does not exist yet → **create it plus the `index.php`
   redirect guard** (FA only does this in its own web page).
2. Write the bytes to `company/0/attachments/<random_id()>`. The on-disk name is
   generated, never the sender's.
3. `add_attachment(300 /* email.message */, 8812, 'Duplicate charge on invoice 4471',
   'Acme_Statement_2026-09.pdf', <random_id>, 44210, 'application/pdf')`
   → row **id 55** in `0_attachments`, retrievable through FA's own
   `admin/attachments.php?vw=55`.
4. Insert the link row into `0_fa_attachments`:
   `source_type='email'`, `kind='message'`, `source_id=8812`, full filename,
   `fa_source_ref=55`.
5. Update `0_ksf_em_inbound_emails.attachments` with the cached manifest.

*Entities:* `0_attachments`, `0_fa_attachments`

### Step 6 — Resolve every addressee

Insert into `0_ksf_em_addressees`, three rows:

| # | role | address | person_id | contact_id | debtor_no | match_method | conf. |
|---|---|---|---|---|---|---|---|
| 1 | `from` | `alice@acme.com` | **12** | **30** | **3** | `exact_email` | 1.00 |
| 2 | `to` | `support@ksfraser.com` | NULL | NULL | NULL | `account_self` | 1.00 |
| 3 | `cc` | `bob@acme.com` | **13** *(created)* | NULL | NULL | `created_new` | 0.90 |

How each resolves:

- **Alice** → exact match on `0_crm_persons.email` gives person 12. From person 12,
  `SELECT entity_id FROM 0_crm_contacts WHERE person_id = 12 AND type = 'customer'
  AND action = 'general'` returns **3**, which is the debtor number. *(This is the
  inversion required by FR-EM-001-03 §3.1. The current code instead queries
  `debtors_master.email`, a column that does not exist — verified live, ERROR 1054.)*
- **support@ksfraser.com** → matches `0_ksf_em_accounts.email_address`, so it is
  **our own address**. `match_method = 'account_self'`. **No person is created** — the
  support team's address is recorded, not personified. This satisfies requirement 4's
  "the support team's own email address".
- **Bob** → no `crm_persons` row has this email, so `add_crm_person()` creates
  **person 13** with the email and the `From`-derived display name, and **no
  `crm_contacts` row**. Bob is therefore a known person with **no debtor**. That is
  the correct, safe outcome: he is captured and linkable later, but no financial
  record was invented for him.

Set `0_ksf_em_inbound_emails.debtor_no = 3` (from the `from` addressee) and
`contact_id = 30`.

*Entities:* `0_ksf_em_addressees`, `0_crm_persons`, `0_crm_contacts` (read),
`0_debtors_master` (read via the contact, **not** queried by email)

### Step 7 — Dispatch `email_received`

`hook_invoke_all('email_received', ['email_id' => 8812, 'account_id' => 1,
'from' => 'alice@acme.com', 'debtor_no' => 3, 'contact_id' => 30])`.

**Fired after resolution**, so a subscriber has the debtor and contact — unlike the
current `save_inbound_email()`, which fires it from inside the INSERT while both are
still NULL.

### Step 8 — Routing

`0_ksf_em_routes` matches `to_address` `support` with no keyword constraint →
`action = 'ticket'`. `0_ksf_em_inbound_emails.routing_action = 'ticket'`.

### Step 9 — A reply is drafted by an automated system

An AI-drafting module subscribes to `email_received`. It reads `body_text`, the
`from` addressee, the account's reply address, `debtor_no = 3`, and the attachment
row — **without connecting to IMAP and without re-parsing MIME**.

It inserts one artefact row:

| Column | Value |
|---|---|
| `email_id` | `8812` |
| `artefact_type` | `draft` |
| `owner_module` | `ksf_FA_AIDraft` |
| `artefact_ref` | `draft-9f3c2a71` |
| `artefact_id` | NULL |
| `status` | `draft` |
| `created_by` | `llm:anthropic:claude-sonnet-4` |
| `payload` | `{model, prompt, response, token_usage}` |

`hook_invoke_all('email_artefact_created', …)` fires.

### Step 10 — The ticket is raised

A support-ticket module creates its ticket against debtor **3** and contact **30**,
then registers it as a **second** artefact row:
`artefact_type='ticket'`, `artefact_ref='TKT-2026-0042'`, `artefact_id=<its row>`.

Note: the current `em_create_ticket_from_email()` inserts into
`{TB_PREF}fa_st_tickets`, **which does not exist** on the live DB. This step depends
on open question **Q3** being resolved.

### Step 11 — A human reviews

A support agent opens the inbox:

- sees the message, rendered from `body_html` with `body_text` as fallback;
- sees **Alice (Acme Pty Ltd, debtor 3)**, **Bob (contact, no account)**, and
  **support@ksfraser.com (this account)** as the addressees;
- sees the PDF, downloadable via FA's own endpoint;
- sees the draft with its model attribution, edits it, and sends it.

Sending records a third artefact row (`artefact_type='reply_sent'`), and the draft
row is marked `status='superseded'`. Nothing is deleted.

### Step 12 — The mail server is cleaned up

Only after Step 3 has committed, the message is deleted or moved server-side. The
FA record, its bodies, its raw source, its attachment file and all three artefact
rows remain fully readable.

*This step is what makes BR-EM-001 observable. It is currently a policy decision, not
implemented — see open question **Q1**.*

---

## 3. Post-conditions

| # | Post-condition |
|---|---|
| PC1 | `0_ksf_em_inbound_emails` row 8812 is complete and self-sufficient. |
| PC2 | Three `0_ksf_em_addressees` rows exist, each with its resolution provenance. |
| PC3 | `0_crm_persons` gained exactly one row (Bob, id 13) and **no** `crm_contacts` row. |
| PC4 | Alice's message resolves to person 12 → contact 30 → **debtor 3**. |
| PC5 | `company/0/attachments/<random_id>` holds the PDF; `0_attachments` id 55 and the `0_fa_attachments` link row both exist. |
| PC6 | Three artefact rows exist against email 8812, in order, none deleted. |
| PC7 | **No `0_debtors_master` row was created.** |
| PC8 | Deleting the message from the mail server changes nothing. |
| PC9 | A subsequent sync run inserts **zero** rows. |

## 4. The four links requirement 4 demands, evidenced

| Required link | Where it is | Value here |
|---|---|---|
| The **sender's contact** | addressee row 1 | `person_id 12`, `contact_id 30` |
| **That contact's associated debtor** | addressee row 1, via `crm_contacts(type='customer').entity_id` | `debtor_no 3` (Acme Pty Ltd) |
| **The support team's own email address** | addressee row 2, `match_method='account_self'` | `support@ksfraser.com`, linked to `0_ksf_em_accounts` id 1, **not** personified |
| **Every other recipient incl. Cc and Bcc** | addressee rows 2 and 3 | `to` → account_self; `cc` → Bob, person 13 created |

## 5. Alternate / extension flows

### 5a — Bob already exists as a contact

If `bob@acme.com` already resolves, step 6 returns `exact_email` at confidence 1.00,
`is_created = 0`, and **no** `crm_persons` row is added.

### 5b — Ambiguity (two persons share Alice's address)

If both Alice and a colleague `alice@acme.com` existed, step 6 **must not** pick one.
Addressee row 1 gets `person_id = NULL`, `match_method = 'ambiguous'`,
`candidates = [12, 44]`, `is_resolved = 0`.

**The message is still fully persisted and still usable** — capture never blocks on
resolution, because blocking would defeat BR-EM-001. `debtor_no` on the email row is
left NULL and a human triages in the inbox UI.

*This is where the current `LIMIT 1` with no `ORDER BY` would have silently picked one
of the two, non-deterministically.*

### 5c — Bob replies with his own account open

A later message from `bob@acme.com` resolves to person 13. An operator links him:
`add_crm_contact('customer', 'general', 3, 13)`. Future messages then resolve to
**debtor 3**. The linkage is a one-time human action; the resolver does the rest.

### 5d — No Bcc is visible

If a third person were blind-copied, IMAP exposes them only via `Delivered-To` /
`X-Original-To`. If absent, no `bcc` row exists and `bcc_source` records
`unknown`. **The system must not present an incomplete Bcc list as complete.**

### 5e — Oversize attachment

If the PDF were 30 MB against a 25 MB cap, it is recorded in the manifest as
`SKIPPED (oversize)` and is visible as such in the UI. The email still persists.
It is **not** silently dropped.

### 5f — Support address is a personal one

If Alice writes to `kevin@ksfraser.com` rather than `support@`, R1 does not match, so
resolution creates/looks up a **person** for Kevin. `account_self` applies only to
addresses registered in `0_ksf_em_accounts`. *(If team addresses should resolve to
FA users rather than persons, that is a small extension — flagged, not built.)*

### 5g — Malformed message

If `Message-ID` is absent, step 2's message-id lookup finds nothing and the
`content_hash` identifies it instead. The message is accepted, not rejected.
If parsing throws mid-MIME-walk, the failure is logged, the run continues, and
`synced_at`/`uid` are **not** advanced past that message, so the next run retries it.

---

## 6. Traceability

| Step | Requirement |
|---|---|
| 1, 2 | FR-EM-001-01-4, FR-EM-001-01-5 |
| 3, 4 | FR-EM-001-01-1, -2, -3, -6 |
| 5 | FR-EM-001-02-1, -2, -3 |
| 6 | FR-EM-001-03-2, -3, -4 |
| 7 | FR-EM-001-04-5 |
| 8 | existing `0_ksf_em_routes` |
| 9, 10, 11 | FR-EM-001-04-1, -3, -4 |
| 12 | BR-EM-001 §3 |
| all | FR-EM-001-01-7 (error isolation) |

**Entities named in this use case, all verified present on the live integration DB:**

`0_ksf_em_accounts` · `0_ksf_em_inbound_emails` · `0_ksf_em_addressees` (new) ·
`0_ksf_em_artefacts` (new) · `0_ksf_em_routes` · `0_attachments` · `0_fa_attachments` ·
`0_crm_persons` · `0_crm_contacts` · `0_debtors_master` · `0_crm_categories`

**Named but NOT existing** (open questions Q3/Q6): `fa_st_tickets`, a support/case
`crm_categories` row.