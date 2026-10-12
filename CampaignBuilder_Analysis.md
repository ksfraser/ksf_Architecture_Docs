# CampaignBuilder — Three-Repo Analysis

**Date:** 2026-10-11
**Scope:** `ksfraser/ksf_CampaignBuilder`, `ksfraser/ksf_CampaignBuilder_UI`, `ksfraser/ksf_FA_CampaignBuilder`
**Method:** Read-only inspection of local clones in `/home/kevin/Documents/`. No source code modified. One executable probe was run against the library to verify a suspected runtime bug (script written to `/tmp/opencode`, not into any repo).

---

## 0. Headline Finding

**The premise in the brief is wrong, and this is the single most important result.**

CampaignBuilder is **not** an outbound message composer in the SuiteCRM Campaign Builder sense. It is a **multi-channel marketing-automation workflow / journey engine** — a directed graph of trigger → action/condition/delay nodes, with a traversal engine, cycle detection, and validation.

There is **no email/message template, no subject, no body, no MIME, no merge tags, and no composer of any kind anywhere in the three repos.** Email is treated as an opaque `email_id` string that is handed to a repository method named `queueEmail()`.

> **It also does *not* do subscriber/list management.** That gap is clean: zero code, zero tables, zero repository methods for subscribers, mailing lists, consent, or unsubscribe.

So the answer to the framing question is neither "composer only" nor "overlaps subscriber management" — it is **neither**. It is an orchestration layer that sits *above* both and delegates to both. See [§5](#5-the-four-specific-questions).

---

## 1. Summary Table

| | **ksf_CampaignBuilder** | **ksf_CampaignBuilder_UI** | **ksf_FA_CampaignBuilder** |
|---|---|---|---|
| Role | Business-logic library | "Presentation package" | FrontAccounting module |
| Composer package name | `ksfraser/ksf-f-campaign-builder` | **none — no composer.json exists** | `ksfraser/ksf-f-campaign-builder` (**collides with the library**) |
| `type` | `library` | — | `library` (not a FA-extension type) |
| PHP constraint | `^8.1` | — | `>=7.4` (**contradicts org's 7.3 floor**) |
| PSR-4 | `ksfraser\` → `src/ksfraser/` | — | `Ksfraser\` → `src/Ksfraser/` (**dir does not exist**) |
| Runtime deps | `psr/log ^1|^2|^3` | — | `psr/log ^1\|^2\|^3` (nothing else) |
| Commits | 12 | 9 | 19 |
| Last commit | **2026-10-08** (active) | 2026-09-28 (docs only) | 2026-09-28 (docs only) |
| Real code | ~1,150 LOC, 6 classes | **1 file, 12 lines** | hooks.php + 1 include, 4 functions |
| Tests | **17 pass** (entity unit tests only) | none | 2 placeholder `assertTrue(true)` |
| Tables | none (interface only) | none | 2 (`fa_campaigns`, `fa_campaign_nodes`) — see §3.3 caveats |
| Maturity | Working prototype, real latent bug | **Skeleton / near-empty** | **Skeleton / non-functional** |
| Subscribers/lists? | No | No | No |
| Open/click/read tracking? | Constants only, never emitted | No | No |
| Mail transport? | None | None | None |

**Honesty note on "maturity":** all three are early-stage. Only the library has meaningful code. The other two are scaffolding. Every `ProjectDcs/` doc in all three repos says `Status: Implemented` — that claim is **not supported by the code** and is called out in §6.3.

---

## 2. ksf_CampaignBuilder — the business-logic library

### 2.1 Purpose

`composer.json` description: *"Visual drag-drop campaign builder for marketing automation."* There is **no README.md** in this repo (confirmed: never has existed). Purpose is established from code and `ProjectDcs/`.

`ProjectDcs/01_Business_Requirements.md:16` — "provides a visual campaign creation and management interface for marketing automation... design multi-channel campaigns... track campaign performance through built-in analytics."

The code delivers a **journey/workflow graph model plus an execution engine**. The "visual drag-drop" part is not in this repo — it is delegated to the UI repo, which does not implement it (§2.3).

### 2.2 composer.json

Evidence: `ksf_CampaignBuilder/composer.json`

```json
"name": "ksfraser/ksf-f-campaign-builder",
"type": "library",
"autoload": { "psr-4": { "ksfraser\\": "src/ksfraser/" } },
"autoload-dev": { "psr-4": { "ksfraser\\Tests\\": "tests/" } },
"require": { "php": "^8.1", "psr/log": "^1.0|^2.0|^3.0" },
"require-dev": { "phpunit/phpunit": "^10.0" }
```

- **Dependencies:** only `psr/log`. No DB driver, no mail library, no HTTP client, no framework. Notably **no dependency on any other KSF package** — this repo is standalone.
- **PHP `^8.1`** is a **real blocker for FrontAccounting**. The sibling FA module targets `>=7.4` and `_init/config` declares `PHP-Version: 7.3` (§4.1). A `^8.1` library cannot be loaded by the FA module as configured.
- **Namespace casing note (uncommitted).** `HEAD` still declares `Ksfraser\` → `src/Ksfraser/`. The working tree has uncommitted changes lowercasing this to `ksfraser\` → `src/ksfraser/` and moving the directory accordingly. Commit `67e9932` ("fix(namespace): vendor segment Ksfraser -> ksfraser") is about the *class* namespace, not the vendor segment. **The working tree is ahead of `HEAD` and is uncommitted** — see §6.4.

### 2.3 What the code actually does

Six classes, all under `ksf_CampaignBuilder/src/ksfraser/CampaignBuilder/`. Read in full; responsibilities below are from the implementations, not the names.

| Class | File | Actual responsibility |
|---|---|---|
| `Campaign` | `Entity/Campaign.php` | Aggregate root. Holds `id`, `name`, `description`, `status`, timestamps, `startsAt`/`endsAt`, a map of `CampaignNode`, a map of `CampaignTrigger`. Implements `JsonSerializable` + `fromArray()`. Contains `validate()` (name required, ≥1 node, ≥1 trigger, delegates to node validation, rejects cycles) and `hasCycle()` — a real DFS cycle detection using a `$recursionStack`. Lifecycle: `activate()`/`deactivate()` set `isActive` + status `active`/`paused`; `isActive()` requires **both** flags. |
| `CampaignNode` | `Entity/CampaignNode.php` | A node in the graph. `type` ∈ `trigger\|action\|condition\|delay\|notification`; `subType` ∈ `email\|score\|segment\|webhook\|form_submit\|page_view\|link_click\|manual`. Carries a free-form `config` array, a map of `CampaignOutcome` (edges), and **canvas `positionX`/`positionY` — the only trace of the "drag-drop canvas" claim**. `validate()` requires: name, valid type, sub-type on actions, a delay value on delays, and outgoing edges for non-terminal nodes. |
| `CampaignOutcome` | `Entity/CampaignOutcome.php` | An **edge** between nodes: `id`, `label`, `targetNodeId`, optional `condition`, `isDefault`. `shouldFollow(array $contactData)` decides branch traversal. |
| `CampaignTrigger` | `Entity/CampaignTrigger.php` | Defines what starts a journey. `eventType` ∈ `form_submit\|page_view\|link_click\|email_open\|email_click\|manual\|date\|score\|segment`. Holds an ordered `filters` list; `matchesFilters()` is a real evaluator supporting `equals, not_equals, contains, starts_with, ends_with, greater_than, less_than, is_empty, is_not_empty` (unknown operator ⇒ `true`). |
| `CampaignRepositoryInterface` | `Repository/CampaignRepositoryInterface.php` | **Interface only — no implementation exists in any of the three repos.** 12 methods: CRUD on campaigns, `findActiveCampaigns`, `findByStatus`, `enrollContact`, `getCampaignContacts`, `updateContactScore`, `addToSegment`, `queueEmail`, `scheduleExecution`. |
| `CampaignService` | `Service/CampaignService.php` | **The execution engine.** Constructor-injects the repository + optional PSR-3 logger. `processEvent($type,$data)` iterates active campaigns and enrolls a contact on the first matching trigger. `executeCampaign($id,$contactId,$data)` walks the graph from trigger nodes through `executeNode()`, guarded by an `$executedNodes` memo (loop protection). Per node type: `delay` → `scheduleExecution`; `action` → `executeAction`; `notification` → fires registered listeners. `executeAction` dispatches registered custom handlers first, else a switch on sub-type: `score` → `updateContactScore`, `segment` → `addToSegment`, `email` → `sendEmail` → `queueEmail`, `webhook` → raw `curl_init/curl_setopt/curl_exec`. Also `activateCampaign` (validates first, throws on errors), `pauseCampaign`, `registerActionHandler`, `on()`. |

**Design quality:** this is genuinely the most substantial of the three. DI via constructor, PSR-3 logging, an extension point (`registerActionHandler`), cycle detection, and graph memoization. It is coherent code, not a stub — but it is *unfinished*, per §2.5.

### 2.4 Data model

- **SQL:** none. The library is persistence-agnostic; it defines only the repository contract.
- **DTOs/entities:** the four classes above, all `JsonSerializable` with `fromArray()` static constructors — a deliberate serialisation boundary suited to storing a journey graph as a JSON blob.
- **No value objects.** No `EmailId`, no `Address`, no money/quantity types. Node `config` is an untyped `array`.

**Known serialisation defects** (relevant if you plan to persist graphs as JSON):
- `Campaign::fromArray()` (`Entity/Campaign.php`) restores id/name/description/status/timestamps but **never restores `nodes` or `triggers`** — a round-trip through `jsonSerialize()`→`fromArray()` silently loses the entire graph.
- `CampaignNode::fromArray()` likewise **never restores `outcomes`**, losing all edges.
- `Campaign::getEntryPoints()` is documented as "nodes with no incoming connections" but implemented as "nodes whose type is `trigger`". Harmless here, but the docblock is wrong.

### 2.5 What it explicitly does NOT do

Verified by reading the code, not inferred:
- **No message composition.** No subject, body, template, MIME, HTML, merge/tag substitution, or personalization. The string `email_id` (`CampaignNode::SUBTYPE_EMAIL`, `CampaignService.php:236-239`) is the entire email model.
- **No actual sending.** `sendEmail()` (`CampaignService.php:273-277`) does exactly one thing: `$this->repository->queueEmail($emailId, $contactId)` then logs. It never touches a transport.
- **No repository implementation.** `CampaignRepositoryInterface` has zero implementations in the org, so `queueEmail`, `scheduleExecution` and `enrollContact` cannot actually execute. The library is unusable as shipped.
- **No transport.** Only outbound HTTP via raw `curl_*` for the `webhook` action — and that is for calling third-party endpoints, not mail.
- **No tracking.** Never emits, records or consumes an open/click event (see §5.3).
- **No list/segment/audience definitions.** It references opaque `segmentId` strings; it never defines a segment.
- **No scheduling loop.** `scheduleExecution` is a repository call; nothing drains a schedule at a later time. Delays therefore never fire.
- **No UI, no persistence, no FA awareness.**

### 2.6 Status: working prototype, with a confirmed fatal bug

`git log`: 12 commits; the last three are docs, the substantive last change is `67e9932` (2026-10-08, namespace fix). Substantive code work stopped around **2026-05-14** (`0607999`). So: **actively touched, but the feature work is ~5 months stale.**

Tests **do pass**: `vendor/bin/phpunit` → `OK (17 tests, 33 assertions)` on PHP 8.1.18. But read `tests/Unit/CampaignEntityTest.php` honestly — it is a single file testing **entity** construction/validation only. **`CampaignService`, the actual engine, has zero test coverage.** The green suite gives false confidence.

**Verified defect — delay nodes are fatal.** `CampaignService.php:176` writes `new DateTime()` unqualified inside `namespace ksfraser\CampaignBuilder\Service`, so PHP resolves it to `ksfraser\CampaignBuilder\Service\DateTime`, which does not exist. I confirmed this by executing the engine against a hand-written stub repository (script in `/tmp/opencode`, nothing written into the repo):

```
THROWN: Error: Class "ksfraser\CampaignBuilder\Service\DateTime" not found
  at .../CampaignService.php:176
```

Any campaign containing a `delay` node fatals before it can schedule. The same method also has a **second bug** on the adjacent line: `new \DateInterval('PT' . $delay->format('i') . 'M')` uses `format('i')` (minutes-within-hour) to build a duration, so even once the class bug is fixed the interval is meaningless. `DateTime`, `DateInterval` and `RuntimeException` are all unqualified or inconsistently qualified in this file (`CampaignService.php:176-179`).

**Security note:** `CampaignOutcome::shouldFollow()` (`Entity/CampaignOutcome.php:120-135`) evaluates branch conditions with **`eval()`**, interpolating `$contactData` values through `var_export()` into a generated PHP string. Since `condition` is campaign-authored and `contactData` originates from inbound event data, this is a **code-injection surface**. It should be a safe expression evaluator, not `eval`.

---

## 3. ksf_CampaignBuilder_UI — the "presentation package"

### 3.1 Purpose and status: essentially empty

`ksf_CampaignBuilder_UI/README.md` describes "UI pages for CampaignBuilder in FrontAccounting". That is the entirety of the intent.

**The repo contains exactly one line of application code.** Full tracked file list (from `git log --all --diff-filter=A`): `README.md`, `.gitignore`, `pages/campaigns.php`, `AGENTS.md`, `AGENTS_ARCH.md`, and 7 `ProjectDcs/*.md`. Nothing else, ever.

### 3.2 composer.json — **does not exist**

`ls` confirms no `composer.json`. `git log --all --diff-filter=A --name-only | grep -i composer` returns **nothing** — the file has *never existed* in this repository's history.

This is a hard contradiction with its own README:

> `composer require ksfraser/ksf-campaign-builder-ui --dev`

That package name is not installable from this repo, and **no package by that name exists on Packagist** as far as I can verify locally (see §7 for the limit of this claim). The repo's `.gitignore` does list `vendor/`, implying a Composer-managed package was intended but never set up.

### 3.3 What the code actually does

One file: `ksf_CampaignBuilder_UI/pages/campaigns.php` (12 lines, single-line minified style). It is a **read-only campaign list page**:

- sets `$page_security = 'SA_CAMPAIGN'` and `$path_to_root = "../../.."`
- includes `session.inc`, `ui.inc`, and `modules/FA_CampaignBuilder/includes/campaign_db.inc`
- calls `get_campaigns()`, renders a table of `Name` / `Status` / `Action`
- emits an `?edit=` link per row — **and there is no page that handles `?edit=`**
- ends with `end_table(1); end_page(true);`

**There is no drag-drop canvas, no editor, no node palette, no graph rendering, no JavaScript, and no create/save/delete UI** — none of the features its own `ProjectDcs/` claims.

**Two correctness problems:**
1. `$path_to_root = "../../.."` — the page lives at `pages/campaigns.php` inside this package, but FA pages expect to live under `modules/<module>/pages/`. Three levels up only lands in FA root if the package is deployed to `modules/ksf_CampaignBuilder_UI/pages/`. Combined with the next point, this file is not deployable as-is.
2. It includes `modules/**FA_CampaignBuilder**/includes/campaign_db.inc` — the directory is `ksf_FA_CampaignBuilder`, not `FA_CampaignBuilder`. **The include path does not match the repo that exists.** The page would fatal on include.
3. `SA_CAMPAIGN` is used but **never defined** by `ksf_FA_CampaignBuilder`'s `install_access()`, which defines `SA_ksf_FA_CampaignBuilderVIEW` / `...MANAGE` instead (`ksf_FA_CampaignBuilder/hooks.php:60-68`).

### 3.4 Data model, FA integration, tracking

- **Tables:** none.
- **DTOs/classes:** none — no classes, no autoloading, no Composer.
- **FA integration:** by convention only (include paths), and as shown above those paths are wrong. It has **no `hooks.php`**, so it cannot register a menu, tab, or security area itself.
- **Open/click/read tracking:** no.

### 3.5 Status: **stub / abandoned**

9 commits. The first two (`9513afa` "Initial commit: ... **placeholder**", `dc7e253` "Add CampaignBuilder UI") are April 2026. **Every commit since 2026-05-15 is documentation only** — and 7 of the 9 are just the shared `AGENTS.md`/`AGENTS_ARCH.md` blobs being synced. The last code commit is `dc7e253`, **2026-04-28**. No code change in ~5.5 months. The initial commit message literally calls it a placeholder.

---

## 4. ksf_FA_CampaignBuilder — the FrontAccounting module

### 4.1 composer.json

Evidence: `ksf_FA_CampaignBuilder/composer.json`

```json
"name": "ksfraser/ksf-f-campaign-builder",
"type": "library",
"autoload": { "psr-4": { "Ksfraser\\": "src/Ksfraser/" } },
"require": { "php": ">=7.4", "psr/log": "^1.0|^2.0|^3.0" }
```

Three serious problems:

1. **Package-name collision.** Both `ksf_CampaignBuilder` and `ksf_FA_CampaignBuilder` declare the name `ksfraser/ksf-f-campaign-builder`. **Two Composer packages cannot share a name.** Whichever is required second will fail resolution. Given the library is the more developed of the two, this is very likely the intended cause of nothing working. (Compare: the UI README uses a distinct `ksf-campaign-builder-ui`, so the collision is specific to these two.)
2. **PSR-4 points at a non-existent directory.** `src/Ksfraser/` — the actual `src/` contains only an **empty** `Ksfraser/FrontAccounting/` directory. I verified this directly with `ls -la`: **zero files**. Composer will emit a warning and autoload nothing. The PSR-4 also still uses the old uppercase `Ksfraser\` casing that the library just abandoned.
3. **PHP `>=7.4` contradicts the library's `^8.1`.** Commit `7879c70` ("Change PHP requirement to >=7.4 for FA 2.4.x compatibility") deliberately lowered this. The consequence is that the two packages **cannot be installed together**: Composer will refuse, because no PHP version satisfies both `>=7.4` and `^8.1`. **This is a hard, structural incompatibility, not a tuning issue.**

### 4.2 What the code actually does

Four real artifacts:

- **`hooks.php`** — `class hooks_ksf_FA_CampaignBuilder extends hooks`, `$version = '1.0.0'`.
  - `install_tabs($app)` — **empty body, commented out.** No tab.
  - `install_options($app)` — **empty body, commented out.** No menu item. **So the module adds nothing to the FA UI at all.**
  - `install_access()` — defines `SS_ksf_FA_CampaignBuilder = 126 << 8` plus areas `SA_ksf_FA_CampaignBuilderVIEW` (`|1`) and `SA_ksf_FA_CampaignBuilderMANAGE` (`|2`). Area labels are literally `_("View ")` and `_("Manage ")` — trailing space, no module name.
  - `activate_extension($company, $check_only)` — calls `ensure_composer_dependencies()`, then `update_databases()` with `sql/install.sql`. Correct FA pattern.
  - `ensure_composer_dependencies()` — private helper that `exec('composer install ...')` on activation if `vendor/autoload.php` is absent. **This runs a shell `composer install` during extension activation** — a questionable pattern for a production installer (slow, network-dependent, fails silently to `error_log` only).
- **`_init/config`** — gzipped FA control file. Decompressed it declares `Version: 2.4.3-0`, `FA-Version: 2.4`, `PHP-Version: 7.3`, `InstallPath: modules/ksf_FA_CampaignBuilder`. Commit `82fc6a0` confirms this was fixed specifically to carry a numeric FA version. But it declares **PHP 7.3** while `composer.json` says `>=7.4` — internally inconsistent.
- **`includes/campaign_db.inc`** — 4 functions: `get_campaigns()`, `get_campaign(int $id)`, `create_campaign(string $name, string $trigger = '')`, `get_campaign_nodes(int $cid)`. Written in a **minified, whitespace-stripped one-line style** unlike anything else in the org.
- **`sql/install.sql`** — 2 tables + 1 insert.

**There is no `src/` code** (empty dir, §4.1) and **`pages/` is empty** (verified: `total 4`, no files). The module has never had a page of its own.

**Critical: `campaign_db.inc` is broken and will fatal in FA.** It is written against a `$db` object with a mysqli-like API:

```php
function get_campaigns():?object{global$db;return$db->query("SELECT*FROM ".TB_PREF."campaigns ORDER BY created_at DESC");}
```

**FA has no global `$db` object.** FA's DB layer is procedural: `db_query()`, `db_fetch_assoc()`, `db_escape()`, `db_insert_id()`, `db_num_rows()`. There is no `$db->query()` and no `$db->fetch()` in the FA API. Every function here would fatal on call. `create_campaign()` additionally concatenates `user_id()` unquoted. **This file has never worked against a real FA runtime.**

### 4.3 Data model — `sql/install.sql`

Two tables:
- `fa_campaigns` — `id`, `name`, `description`, `status ENUM('Draft','Active','Paused','Completed')`, `trigger_type`, `created_by`, `created_at`
- `fa_campaign_nodes` — `id`, `campaign_id`, `node_type`, `config JSON`, `position_x`, `position_y`

**Four problems, any one of which blocks installation:**
1. **No `0_` table prefix.** FA's installer (`db_import()` in `admin/db/maintenance_db.inc`) replaces only the literal `0_` with `TB_PREF`. `hooks.php` comments even claim *"This handles @TB_PREF@ replacement automatically"* — **false**. These tables will be created unprefixed, in a fixed global namespace, colliding with any other module's `campaigns` table.
2. **`INSERT INTO fa_modules`** — a table this file never creates, and which is not a standard FA table. This insert will fail.
3. **Schema is too thin for the domain.** There is no join table from `campaign_nodes` to outcomes/edges, no triggers table, no enrollment table, no schedule table, no queue table. The library's `Campaign`, `CampaignTrigger` and `CampaignOutcome` entities have **no storage at all**.
4. **Status enum disagrees with the code.** SQL uses `'Draft','Active','Paused','Completed'` (capitalised); `Campaign::activate()`/`deactivate()` write `'active'`/`'paused'` and the constructor defaults to `'draft'` (`Campaign.php`). Under a strict MySQL enum these inserts fail or coerce to the empty string. (Would silently "work" only if the column were a VARCHAR, which it is not.)

The `position_x`/`position_y` columns and the `config JSON` column are the only genuinely thought-through touches — they map cleanly onto `CampaignNode::setPosition()` and `getConfig()`.

### 4.4 Data model — claimed vs actual

`AGENTS.local.md` describes a repository structure that **does not exist**:

| Claimed in `AGENTS.local.md` | Actual |
|---|---|
| `sql/fa_campaigns.sql`, `fa_campaign_leads.sql`, `fa_campaign_metrics.sql` | only `sql/install.sql` |
| `includes/campaigns_db.inc`, `leads_db.inc`, `metrics_db.inc` | only `includes/campaign_db.inc` (4 fns, all broken) |
| `ProjectDocs/` | actual dir is `ProjectDcs/` |
| Depends on `ksf_FA_CampaignBuilder_Core` | no such package; not in composer.json |
| "FA Module for Marketing Campaign Management... with CRM integration" | no CRM code |

### 4.5 What it explicitly does NOT do

- No campaign CRUD UI, no pages, no tab, no menu.
- No repository adapter implementing `CampaignRepositoryInterface` — so nothing bridges the library to these tables.
- No trigger, outcome, enrollment, segment, schedule or queue tables.
- No composer name collision aside, it **does not actually depend on the library**: `composer.json` has no `require` for `ksfraser/ksf-f-campaign-builder`. The dependency the README asserts is absent from the manifest.

### 4.6 Status: **skeleton, non-functional**

19 commits — the most of the three — but the substantive work all landed 2026-04-27 → 2026-05-17. Since 2026-09-01 it is **100% documentation**. Its own history is revealing:

- `e3d338a` (2026-04-27) "Initial commit ... with TDD"
- `86bbb3f` (2026-04-27) **"Remove extracted library code - now depends on ksf_CampaignBuilder"**
- `7a09200` (2026-05-16) "Simplify hooks, move code to common utilities"

`86bbb3f` is the key event: the FA module's copy of the library was deleted in favour of depending on the package — **but that dependency was never added to `composer.json`.** The module has been a hollow shell since late April 2026.

Its `src/Ksfraser/CampaignBuilder/**` files *did* exist historically (confirmed via `git log --diff-filter=A`) and were removed by `86bbb3f`. Good decision in principle; it was just never completed.

**Tests are placeholders.** `tests/Unit/CampaignBuilderAdapterTest.php` contains two methods, both of which assert `true`:

```php
public function testAdapterCanBeInstantiated(): void { $this->assertTrue(true); }
public function testAdapterExistence(): void { $this->assertTrue(true, 'FA CampaignBuilder adapter placeholder - implementation pending'); }
```

They are not even in the declared namespace's directory (`class` is `Ksfraser\FA\Tests`; file is `tests/Unit/`). `tests/bootstrap.php` defines `TB_PREF` and `INPUT_COOKIE` fakes to satisfy FA-shaped code. The second assertion's own message says *"implementation pending"* — the repo is candid about this.

### 4.7 FA integration summary

| Concern | State |
|---|---|
| `hooks.php` class | ✅ correct FA 2.4 class-based pattern, `$version` set |
| Security section | ✅ `SS_ksf_FA_CampaignBuilder = 126 << 8` |
| Security areas | ⚠️ defined but **never used** — no page references them, and the UI repo references an undefined `SA_CAMPAIGN` |
| `_init/config` | ✅ gzipped, numeric `2.4.3-0` (FA-version gate satisfied) |
| Activation → schema | ⚠️ `update_databases()` correct, but the SQL itself is broken (§4.3) |
| Menu / tab | ❌ both hooks empty |
| Pages | ❌ `pages/` empty |
| DB layer | ❌ uses non-existent FA `$db` object API |
| Composer dep on library | ❌ absent from manifest |

**Net: the module is installable (the control file and hook skeleton are valid) but functionally inert.** Activating it creates two mis-prefixed tables and adds no UI.

---

## 5. The Four Specific Questions

### 5.1 Does it cover campaign SENDING/QUEUING, or only message composition?

**Neither — and this is where the brief's framing breaks down.**

- It does **not** compose. There is no message object. `CampaignNode::SUBTYPE_EMAIL = 'email'` carries a bare `email_id` string (`CampaignNode.php:42`); `CampaignService::executeAction` reads `$config['email_id']` and passes it to `sendEmail()` (`CampaignService.php:235-239`). Subject, body, template, merge fields, attachments, MIME, HTML — **none exist in any file of any repo.**
- It does **not** send. `sendEmail()` (`CampaignService.php:273-277`) delegates to `$this->repository->queueEmail($emailId, $contactId)` and logs. **No `CampaignRepositoryInterface` implementation exists anywhere**, so this call cannot reach a queue. `queueEmail` is an unimplemented contract method, not a feature.
- **Queuing** is a *declared intent*, at the interface level only (`CampaignRepositoryInterface.php:74-77`). No queue table (`sql/install.sql` has none), no queue writer, no queue drainer.
- **Scheduling** is likewise interface-only (`scheduleExecution`), and its only call site (`CampaignService.php:176-181`) is the site that **fatals** (§2.6).

**Verdict: it reaches the *boundary* of sending/queuing and stops there.** Against SuiteCRM's Campaign Builder, which composes a target URL/query/email body and hands it to Sugar's scheduler, CampaignBuilder composes **a workflow graph** and hands it to a repository that doesn't exist. It is one layer above message composition, not at it.

### 5.2 Does it manage subscribers/lists at all?

**No. Not at all — this is the cleanest gap in the whole codebase.**

I searched all source for `subscri|mailing_?list|list|unsubscribe|opt_?in|opt_?out|consent|segment|contact|recipient`. Every hit is one of:

- **`contact` as an opaque `string $contactId` parameter** threaded through the engine (`CampaignService.php:121,151,209,257`; `CampaignRepositoryInterface.php:56,61,66,71,81`). The library never looks up, creates, stores or validates a contact. It passes IDs around.
- **`segment` as two string constants** — `CampaignNode::SUBTYPE_SEGMENT` and `CampaignTrigger::EVENT_SEGMENT` — plus one repository method `addToSegment(string $contactId, string $segmentId)`. A segment is an opaque identifier; **nothing defines, queries, or populates one.**
- **`enrollContact()` / `getCampaignContacts()`** — campaign↔contact association only, declared on the unimplemented interface.

**No subscriber entity, no list entity, no membership table, no consent/opt-in/opt-out, no unsubscribe, no suppression/bounce handling, no double-opt-in, no segment builder.** Grep returned **zero** matches for `subscri`, `unsubscribe`, `opt_in`, `opt_out`, or `consent` across all source in all three repos.

This is arguably a deliberate boundary — the library treats audience as a dependency (`ksf_Marketing` lead segments are named in `01_Business_Requirements.md:41` as an integration point). **But no such integration exists in code.** The boundary is real; the thing on the other side of it is unwritten.

### 5.3 Does it do open/click/READ tracking?

**No — zero implementation. There are constant names and nothing else.**

I grepped all source for `pixel|tracking|track_|\bopen(ed)?_?(rate|ed)|click(ed)?_?(url|track)|utm_` across every `.php`, `.sql`, `.json` and `.inc` file in all three repos: **zero matches in any source file.** No tracking pixel, no redirect endpoint, no UTM rewriting, no open-rate or click-rate aggregation, no `open_time`/`click_time` columns.

The only trace is **four constants that name behaviours nothing implements**:

| Constant | Location | Reality |
|---|---|---|
| `CampaignTrigger::EVENT_EMAIL_OPEN` | `CampaignTrigger.php:36` | Declared. **Never read.** `CampaignService::processEvent()` accepts *any* `$eventType` string, but **no code in any repo ever calls `processEvent('email_open', ...)`.** There is no emitter, no pixel, no webhook endpoint to receive the event. |
| `CampaignTrigger::EVENT_EMAIL_CLICK` | `CampaignTrigger.php:37` | Same — declared, never emitted. |
| `CampaignNode::SUBTYPE_LINK_CLICK` | `CampaignNode.php:48` | Declared; never used by `executeAction()`, whose switch handles only `score`, `segment`, `email`, `webhook`. |
| README claim | `ksf_FA_CampaignBuilder/README.md:9` | *"Triggers: form submit, page view, link click, email open/click"* — **aspirational.** |

Also relevant: the FA module's `EVENTS.md` (the org's cross-module event registry, 483 lines) — I grepped it for `campaign` and found **nothing**. CampaignBuilder emits no registered events, despite `ksf_CampaignBuilder/ProjectDcs/RTM.md` claiming it provides `campaign.*` events to three consumers and a `campaign.sent` event to `ksf_EmailManager`. **Those events do not exist in code.**

**Verdict: tracking is a naming-only placeholder.** The architecture *anticipates* inbound open/click events to drive re-entry into a journey (which is the standard shape of such a system), but the entire producing half — pixel, redirect, open/click recording — is absent.

### 5.4 What mail transport does it use, if any?

**None. No mail transport is present in any of the three repos.**

Grep for `mailgun|sendgrid|ses|smtp|mail\(|PHPMailer|swiftmailer|symfony/mail|wp_mail|\bsend(` across all source and all three `composer.json` files: **zero matches.**

- Neither `composer.json` requires any mail library. Dependencies are `psr/log` only.
- There is **no direct use of FrontAccounting's mail capability.** FA ships a mailer (`includes/mail/*.inc`, and `email_send()` in class `email`); this module never calls it. `ksf_FA_CampaignBuilder/README.md:52` defers entirely to `ksf_FA_EmailManager` for email actions, and `ProjectDcs/01_Business_Requirements.md:43` names `ksf_EmailManager` as the "Email channel delivery" integration — **neither is referenced in code.**
- The **only** outbound network call anywhere is the `webhook` action: raw `curl_init` / `curl_setopt(CURLOPT_POST)` / `curl_exec` (`CampaignService.php:284-294`). That posts JSON to a third-party URL. It is not mail, and it has **no timeout, no status check, no retry, no error handling** — the `curl` handle's response is discarded and `curl_close`d unconditionally.
- The `notification` node type (`executeNotification`, `CampaignService.php:257-266`) sends **nothing** — it calls listeners registered via `on('notification', ...)`. **No listener is registered anywhere in the org**, so it is a no-op.

**Verdict: transport is entirely deferred and unimplemented.** The design intends `ksf_FA_EmailManager` (or a queue drained by a scheduler) to own delivery. That component does not exist in this codebase's visible scope, and nothing in these three repos calls it.

---

## 6. Cross-Cutting Observations

### 6.1 Two Package-Name Collisions and One Version Deadlock

This is the most consequential finding and it is not a documentation issue:

| Problem | Detail |
|---|---|
| **Duplicate package name** | `ksfraser/ksf-f-campaign-builder` is declared by **both** `ksf_CampaignBuilder/composer.json` and `ksf_FA_CampaignBuilder/composer.json`. Composer cannot install two packages under one name. |
| **Unsatisfiable PHP constraints** | Library: `^8.1`. FA module: `>=7.4` (deliberately lowered in `7879c70` for FA compatibility). **No PHP version satisfies both.** They cannot coexist in one `vendor/`. |
| **Missing dependency** | The FA module never `require`s the library at all, so it does not currently *hit* the collision — it simply silently has no library. The documented dependency (`86bbb3f`) was never declared. |
| **Dead PSR-4** | FA module maps `Ksfraser\` → `src/Ksfraser/`; that directory is **empty**. |
| **Namespace case drift** | Library is moving `Ksfraser\`→`ksfraser\` **uncommitted**, while the FA module still uses the old uppercase casing in its PSR-4 and in `Architecture.md:14` (`Ksfraser\FA\Campaignbuilder`, which matches no real class). |

Together these mean **the three repos cannot currently be assembled into a working integration**, regardless of any missing functionality.

### 6.2 Module path inconsistency

`ksf_FA_CampaignBuilder/_init/config` declares `InstallPath: modules/ksf_FA_CampaignBuilder`, but `ksf_CampaignBuilder_UI/pages/campaigns.php` includes `modules/FA_CampaignBuilder/includes/campaign_db.inc` — missing the `ksf_` prefix. If the module were installed at its declared path, the include fails.

### 6.3 The ProjectDcs systematically overclaim — treat as aspirational

All three repos carry 6-8 BABOK-style documents (`Business Requirements`, `Architecture`, `Functional Requirements`, `Use Case`, `Test Plan`, `UAT Plan`, `RTM`, and in the FA repo an `EVENTS.md`). They are **not BABOK-compliant individual files** — they are bundled markdown sections, not the per-requirement file structure (`BR-<MOD>-<SEQ>-...md`, `FR-...md`, `UT-...md`, `UAT-...md`) the org standard calls for. `ksf_CampaignBuilder` has both a numbered `ProjectDcs/` set (6 files) and a `doc/ProjectDcs/` set with the same 6 titles — **duplicated documentation under two paths.**

Every one of these documents is stamped **`Status: Implemented`**. Cross-checked against the code, the gaps are large:

| Claim | Source | Reality |
|---|---|---|
| "Audience segmentation ✓" | lib `RTM.md:20` | No segment entity, table or builder. Only an opaque `segmentId` string. |
| "Performance analytics ✓" | lib `RTM.md:21`; BR §2.1 | **No analytics code whatsoever.** |
| "Multi-channel support ✓" (SMS, push, A/B testing) | lib `RTM.md:22`; BR §2.1 | No SMS, no push, no A/B. One email sub-type. |
| "Campaign editor / Audience selector / Automation builder / Analytics dashboard ✓" | UI `RTM.md:19-22` | **One list page.** No editor, no selector, no dashboard. |
| "FA-CAMPAIGNBUILDER-002 DB adapters ✓", "3 unit tests, ~90% coverage" | FA `RTM.md:14-27` | **2 placeholder tests** asserting `true`. Zero adapters. |
| Provides `campaign.*` + `campaign.sent` events | lib `RTM.md:35-41` | **No `hook_invoke*` call in any repo.** Absent from the org's own `EVENTS.md` registry. |
| `src/Ksfraser/…` "Adapters" + `Integration/` | FA `Architecture.md:19-26` | `src/` empty; no `Integration/` dir. |
| `FA Module … with CRM integration`; depends on `ksf_FA_CRM` | FA `AGENTS.local.md` | No CRM code; not in composer.json. |

**Conclusion: the docs describe an intended system, not the delivered one.** Anyone reading `ProjectDcs/` alone would conclude this is a finished, analytics-capable, multi-channel campaign platform. It is not. Read the code.

### 6.4 Working trees are dirty

All three repos have **uncommitted** modifications (`git status --porcelain`). For `ksf_CampaignBuilder` this is substantive — it is an **uncommitted namespace migration** (`Ksfraser\` → `ksfraser\`, 10 files, 31 insertions/31 deletions) touching `composer.json`, all four entities, the repository interface, the service and the tests. This analysis describes the **working tree**, which is one rename ahead of `HEAD` (`67e9932`). The FA module's uncommitted changes are docs-only.

### 6.5 Code-quality observations

- `CampaignOutcome::shouldFollow()` uses **`eval()`** on campaign-authored conditions interpolated with inbound `contactData` (`Entity/CampaignOutcome.php:120-135`). **Remote-code-execution risk** if any external input reaches `condition`. Replace with a whitelist expression evaluator.
- `CampaignService::callWebhook()` has **no timeout, no HTTP status check, no retry, and no error handling** (`Service/CampaignService.php:284-294`); the response body is discarded.
- `includes/campaign_db.inc` is minified/whitespace-stripped, diverging from the org's readable style, and additionally has an **unquoted `user_id()`** interpolation (`WHERE id=".$id` and the `created_by` insert).
- Unqualified global class references in `CampaignService.php` are inconsistent: `\DateTime` and `\RuntimeException` are backslash-qualified, while the `DateTime`/`DateInterval` on lines 176-179 are not — the root cause of the fatal in §2.6. (Entity classes import their globals correctly.)
- **No test covers `CampaignService`** in any repo. The 17 green tests in the library cover entities only. The 5-minute-old delay-node fatal (§2.6) was never caught because of this.

---

## 7. Explicit Uncertainty

I want to be plain about what I could *not* establish:

1. **I did not contact GitHub.** The repos were found already cloned locally, so I never used the network. I therefore **cannot confirm whether these three repos exist under those names on `ksfraser`, or whether anything has been pushed since the local clones.** All git facts (commit counts, dates, diffs) are **local** and could be behind origin. The local remotes are configured as `git@github.com:ksfraser/<repo>.git` (`ksf_CampaignBuilder`, `ksf_CampaignBuilder_UI`, `ksf_FA_CampaignBuilder`).
2. **I cannot verify Packagist.** Whether `ksfraser/ksf-f-campaign-builder` or `ksfraser/ksf-campaign-builder-ui` are actually published (and under which name, given the collision) is **unverified**. The UI README's install instruction assumes the latter exists; nothing local confirms it.
3. **Other repos in the org are out of scope.** `ksf_FA_EmailManager`, `ksf_Marketing`, `ksf_FA_Forms` and `ksf_FA_Tracking` are named as integration points in the docs but I did not inspect them. The actual transport and any real subscriber/segment management may live there — **that is the most likely place to look next**, and it would directly answer the "who actually sends the email" question that these three repos leave open.
4. **I did not run the FA module.** No FA instance was booted, so §4.2's claim that `campaign_db.inc` will fatal is based on reading FA's documented DB API versus the code, not on an observed stack trace. I am confident, but it is inference.
5. **"Complete vs stubbed" is a judgement.** The library is coherent and tested but has an unfilled fatal path and no persistence layer; the UI and FA repos are, in my assessment, stubs. If the intent was always *"design spike, real build later"*, then this is on-plan rather than abandoned — **nothing in the repos says so.**

---

## 8. Bottom Line

**CampaignBuilder is neither a message composer nor a subscriber manager. It is a marketing-automation journey/workflow engine** — trigger/condition/action/delay graph, traversal, validation, cycle detection — with a clean, unimplemented boundary around persistence.

Against the SuiteCRM Campaign Builder analogy: SuiteCRM composes the outbound *message*. CampaignBuilder composes the outbound *journey*, and treats the message as an external service it never inspects.

The three-repo split is **aspirationally correct and practically broken**:
- the library has real code and real tests, but **no repository implementation, a fatal delay-path bug, and an `eval()` injection surface**;
- the UI repo is **one list page**, with no `composer.json` ever, and include paths that don't match reality;
- the FA repo is an **installable but inert shell** — empty menu hooks, empty `pages/`, empty `src/`, a `composer.json` whose package name **collides with the library** and whose PHP constraint is **unsatisfiable alongside it**, SQL with the wrong table prefix, and a DB layer written against an FA API that doesn't exist.

**Subscriber/list management is untouched by all three.** Open/click tracking is four constant names with no emitter. Mail transport is deferred to `ksf_FA_EmailManager`, which is never called.

**Before any of this can be built on, the minimum fixes are:** rename one package; reconcile the PHP constraints; actually `require` the library from the FA module; prefix the SQL with `0_`; replace `campaign_db.inc` with FA's `db_*` functions; fix `CampaignService.php:176`; and replace `eval()` in `CampaignOutcome::shouldFollow()`.

**Most useful next step:** inspect `ksf_FA_EmailManager` and `ksf_Marketing`. Those two own the transport and the audience — the two functions this codebase delegates away and never implements.