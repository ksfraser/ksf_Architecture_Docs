# FR-EM-001-01 — Parse and persist an inbound message

@BABOK Related: BR-EM-001, BABOK 8.3 Solution Design
Status: **Proposed**
Module: `ksf_FA_EmailManager`
Depends on: FR-EM-001-02, FR-EM-001-03, FR-EM-001-04
Date: 2026-10-11

---

## 1. Current state (verified)

The existing implementation is `sync_email_account()` at
`ksf_FA_EmailManager/includes/em_routing.inc:107-189`.

What it **does** correctly:

- Guards `function_exists('imap_open')` (`:112-114`) — verified that the guard is
  present, and separately verified that the guard is **always** taken on the current
  container: `podman exec ksfii_app-fa php -m | grep -ci imap` returns `0`.
- Opens IMAP, enumerates `imap_headers()`, dedupes on `message_id` via a `SELECT`
  (`:142-145`), walks `imap_fetchstructure()->parts` for text/HTML, and persists via
  `save_inbound_email()`.
- Persists **full body content**. `save_inbound_email()` (`em_db.inc:105-136`)
  INSERTs `body_text`, `body_html`, `raw_headers`, `attachments`. The table columns
  are real and confirmed present on the live DB. **Server-side deletion does not
  lose the record** — this requirement is therefore a *strengthening*, not a
  correction, on this point.

What it does **not** do — each is a defect this FR closes:

| # | Defect | Evidence |
|---|---|---|
| D1 | **Cc and Bcc are never captured.** Only `$header->to[0]` and `$header->from[0]` are read. `cc_addresses` / `bcc_addresses` columns exist and are always NULL. | `em_routing.inc:166-173` |
| D2 | **`raw_headers` is never populated.** Column exists; nothing writes it. | `em_routing.inc:168-178` |
| D3 | **No UID / UIDVALIDITY persistence.** Sync iterates *every* header on every run; there is no cursor, so sync cost is O(mailbox size). | `em_routing.inc:130-139` |
| D4 | **Multiple recipients are collapsed.** `to_address` is `VARCHAR(255)` holding only `to[0]`. | `em_routing.inc:173`; `sql/ksf_em_inbound_emails.sql` |
| D5 | **MIME walk is shallow.** `if (isset($structure->parts))` iterates one level; nested multiparts (`multipart/mixed` inside `multipart/alternative`) are not recursed. | `em_routing.inc:152-164` |
| D6 | **Content-transfer decoding is absent.** `imap_fetchbody()` is stored raw; base64 and quoted-printable parts are never decoded. | `em_routing.inc:156-163` |
| D7 | **`TEXT` is too small.** `body_text`, `body_html`, `raw_headers` are `TEXT` (64 KB). An HTML mail with quoted history exceeds this. | `sql/ksf_em_inbound_emails.sql` |
| D8 | **No raw source retained.** The original RFC822 blob is discarded, so a parsing defect is unrecoverable. | absent |
| D9 | **`message_id` index is non-unique.** `KEY idx_message_id`, so a duplicate insert is possible under a race. | `sql/ksf_em_inbound_emails.sql` |
| D10 | **Only the top-level body part is taken** when there is no `->parts`; quoted replies are not separated from new content. | `em_routing.inc:162-164` |

## 2. Requirements

### FR-EM-001-01-1 — Full header capture

The system shall persist, for every captured message, **all** of the following,
for **every** occurrence of each (not just the first):

| Field | Source | Storage |
|---|---|---|
| Message-ID | `Message-ID` header | `message_id` |
| Subject | `Subject` | `subject` |
| From | `From` (all) | normalised rows in `0_ksf_em_addressees`, role `from` |
| To | `To` (all) | `0_ksf_em_addressees`, role `to` |
| Cc | `Cc` (all) | `0_ksf_em_addressees`, role `cc` |
| Bcc | `Delivered-To` / envelope | `0_ksf_em_addressees`, role `bcc` — **see caveat C1** |
| Reply-To | `Reply-To` | `0_ksf_em_addressees`, role `reply_to` |
| Return-Path | `Return-Path` | `0_ksf_em_addressees`, role `return_path` |
| Date | `Date` | `received_date` |
| In-Reply-To | `In-Reply-To` | `in_reply_to` (new) |
| References | `References` | `thread_id` (new, first entry) |
| — | entire RFC822 header block | `raw_headers` |

**Closes D1, D2.**

> **C1 — Bcc is not observable from headers.** RFC 5322 §3.6.3 states that blind
> copies are *not* disclosed to recipients. A Bcc is knowable only from the
> delivery envelope (`Delivered-To:`) that the receiving MTA adds, or from
> `X-Original-To` on some servers. Therefore: Bcc capture is **best-effort and
> environment-dependent**, and the system must record `bcc_source` on the addressee
> row (`envelope` | `header` | `unknown`) so that a reader can tell an
> intentionally-absent Bcc from a Bcc we simply could not see.
> **Do not build UI or logic that assumes Bcc completeness.**

### FR-EM-001-01-2 — Body capture

The system shall persist **both** `body_text` (`text/plain`) and `body_html`
(`text/html`) where both exist, each **content-transfer-decoded**, and shall not
discard one in favour of the other.

Where only one representation exists, the absent one shall be NULL — not copied
from the other.

- `body_text` → `LONGTEXT`
- `body_html` → `LONGTEXT`

**Closes D6, D7.**

### FR-EM-001-01-3 — Recursive MIME walk

The system shall walk the MIME structure **recursively**, descending into every
nested `multipart/*` node, and shall apply the rules:

| Part type | Action |
|---|---|
| `text/plain` | decode → `body_text` |
| `text/html` | decode → `body_html` |
| `text/calendar`, `text/x-vcalendar`, `.ics` filename | decode → attachment with `is_calendar = 1` |
| anything with a `Content-Disposition: attachment`, or any non-`text/*` part | **attachment** (FR-EM-001-02) |
| `text/*` inline part without a filename | body candidate, lowest priority |

**Closes D5, D10.**

*Design note:* `ksf_FA_CRM/includes/EmailImportService.php:236-265` (`parseParts`)
already contains a correct **recursive** implementation with part-number
composition (`$part_number . '.' . ($index+1)`) and transfer decoding
(`decodeContent()` handling encoding constants 3 = base64 and 4 = quoted-printable).
It is dead code in a dead class, but it is a usable reference for the recursion and
decoding rules. **Recommended: lift the recursion and decode into EmailManager and
delete `EmailImportService`** rather than writing a third variant.

### FR-EM-001-01-4 — Identity and deduplication

Every captured message shall be given **three independent identity handles**, so
that dedupe never depends on any single one being well-formed:

| Handle | Purpose | Constraint |
|---|---|---|
| `(account_id, message_id)` | Normal case; also catches the same message present in two synced folders | **UNIQUE** |
| `(account_id, uidvalidity, uid)` | IMAP-native cursor | **UNIQUE**; required for O(Δ) sync |
| `content_hash` | SHA-256 of `raw_source`; last resort when `Message-ID` is absent, malformed, or duplicated across senders | indexed, not unique |

New columns: `uid INT NULL`, `uidvalidity BIGINT NULL`, `content_hash CHAR(64) NULL`,
`in_reply_to VARCHAR(255) NULL`, `thread_id VARCHAR(255) NULL`, `synced_at DATETIME NULL`.

**Closes D3, D9.**

**Rules:**

1. `message_id` **MUST** be `UNIQUE` — the current index is non-unique.
2. `message_id` **MUST** be normalised before insert: trimmed, and stripped of any
   surrounding `<` `>`.
3. A message with an empty/absent `Message-ID` **MUST NOT** be rejected. It shall be
   accepted and identified by `content_hash`.
4. A message already present (any handle matches) **MUST** be updated, not
   re-inserted — specifically its `uid`, `uidvalidity` and `synced_at`.
5. **UIDVALIDITY is not optional.** UIDs are only meaningful within one UIDVALIDITY
   value; if the mail server rebuilds the mailbox, UIDVALIDITY changes and every
   previously stored UID becomes meaningless. Storing `uid` without `uidvalidity`
   causes silent, unbounded re-import or silent skip.

### FR-EM-001-01-05 — Sync cursor and incremental fetch

The system **MUST NOT** re-walk the whole mailbox on every sync.

Required algorithm:

```
uidvalidity := imap_get_mailbox_info(...)      // per connection
if uidvalidity != stored uidvalidity for account:
    -> UIDs are invalid. Reset the cursor. Re-walk from UID 1.
       Dedupe via message_id / content_hash prevents duplicate content.
else:
    cursor := greatest stored uid for (account, uidvalidity)
    ids    := imap_search($imap, 'UID ' . (cursor + 1) . ':*')
```

For each candidate id, perform a **cheap existence check first** (by `message_id`,
then `content_hash`); only if absent, fetch the body and MIME structure.

**Closes D3.**

*Verified constraint:* the container has no IMAP extension, so this code path has
**never been executed end-to-end** in this environment. Its correctness on real
multipart mail is unproven. See §6.

### FR-EM-001-01-06 — Raw source retention

The system shall persist the complete, unmodified RFC822 message source in a
`raw_source LONGTEXT` column.

This is the direct implementation of BR-EM-001 §2.2: it is what makes a message
**re-parseable** if the MIME walker is later found to have missed something, and it
is the ultimate fallback for any field this FR does not enumerate.

**Closes D8.** See open question **Q7** (size cap and PII policy).

### FR-EM-001-01-07 — Errors are isolated per message

A failure to parse or persist **one** message **MUST NOT** abort the sync run. The
system shall log the failure with the account id and the message identity, continue
to the next message, and report a per-run summary of `{succeeded, skipped,
failed}`.

The account's `last_sync` **MUST** be updated only for messages that actually
succeeded, so that a run which failed on message 5 does not skip messages 6..N on
the next run.

## 3. Data model changes

Applied to `0_ksf_em_inbound_emails` (`sql/ksf_em_inbound_emails.sql`):

| Change | From | To |
|---|---|---|
| `body_text` | `TEXT` | `LONGTEXT` |
| `body_html` | `TEXT` | `LONGTEXT` |
| `raw_headers` | `TEXT` | `MEDIUMTEXT` |
| `attachments` | `TEXT` | *retained as a cached manifest only* (see FR-EM-001-02 §5) |
| `to_address` | `VARCHAR(255)` | *retained for back-compat; superseded by `0_ksf_em_addressees`* |
| `message_id` | `KEY` | **`UNIQUE KEY`** |
| *(new)* | — | `uid INT`, `uidvalidity BIGINT`, `content_hash CHAR(64)` |
| *(new)* | — | `in_reply_to VARCHAR(255)`, `thread_id VARCHAR(255)` |
| *(new)* | — | `raw_source LONGTEXT`, `synced_at DATETIME` |

Indexes: `(account_id, uidvalidity, uid)` UNIQUE; `(account_id, message_id)` UNIQUE;
`content_hash`; `thread_id`; `received_date`.

## 4. Acceptance criteria

| # | Criterion |
|---|---|
| AC1 | A message with 1 From, 2 To, 3 Cc produces **6** rows in `0_ksf_em_addressees` with correct `role` values. |
| AC2 | `raw_headers` contains the full RFC822 header block including `Received:` and `Return-Path:`. |
| AC3 | A base64-encoded `text/plain` part is stored **decoded**. |
| AC4 | A `multipart/mixed` containing `multipart/alternative` (plain + html) plus a PDF attachment yields a populated `body_text`, `body_html`, **and** one attachment row. |
| AC5 | Running sync twice over an unchanged mailbox inserts **0** rows on the second run. |
| AC6 | Changing `uidvalidity` between runs causes a re-walk and **0** duplicate rows. |
| AC7 | A message with no `Message-ID` header is accepted and identified by `content_hash`. |
| AC8 | A 200 KB HTML body round-trips without truncation. |
| AC9 | A message that throws during parse is logged, the run continues, and `last_sync` is not advanced past it. |

## 5. Out of scope

- Threading/conversation grouping as a *user-facing* view (the data is captured
  here; the presentation is a UI concern).
- Outbound sending.
- POP3.
- Deleting or flagging messages on the mail server (see **Q1**).

## 6. Unverified

| Item | Status |
|---|---|
| Correctness of any IMAP code path against a real server | **[UNVERIFIED]** — no IMAP PHP extension on `ksfii_app-fa` (PHP 7.4.33); `sync_email_account()` has never executed here |
| Whether `update_databases()` in `hooks.php:108-115` provisions schema on a **clean** database | **[UNVERIFIED / CONFLICTING]** — `EmailManager_Analysis.md` §5 Q8 asserts a fresh activation creates nothing because `sql/install.sql` is absent (deleted in commit `a9bf721`); but `hooks.php` implements per-file gating via `update_databases()`, which `AGENTS.md` documents as the working pattern. **Must be tested on a clean company before any of this is built.** |
| Whether `Bcc` is obtainable on the actual production mail server | **[UNVERIFIED]** — depends entirely on the MTA; see C1 |

## 7. Related

- [BR-EM-001](./BR-EM-001-inbound-email-capture.md)
- [FR-EM-001-02](./FR-EM-001-02-attachment-persistence.md)
- [FR-EM-001-03](./FR-EM-001-03-addressee-resolution.md)
- [FR-EM-001-04](./FR-EM-001-04-future-actions.md)
- [Inbound_Email_Architecture.md](./Inbound_Email_Architecture.md)