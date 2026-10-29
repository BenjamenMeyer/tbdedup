# Architecture Review & Master Completion Plan

## Problem Statement
While organizing email in Thunderbird, a folder was accidentally copied into another folder, triggering a recursive copy loop (`Inbox.sbd/Activities.sbd/Scouts.sbd/Kids.sbd/Inbox.sbd/...`) that ran 19–20 times before Thunderbird was terminated. This inflated ~3 GB of email into ~330 GB across 775 logical mail folders.
- Because email filters and processing continued or changed afterward, unique emails may exist in any of the recursive copies; the top-level folders cannot be assumed to hold all originals.
- Individual folders range from a few emails to tens of thousands (or hundreds of thousands) of emails.
- **Goal:** Index all emails and their locations across the recursive folder tree, compute a disk hash (to verify raw message extraction) and a parsed content hash (to identify duplicates independent of Thunderbird metadata), deduplicate each logical folder down to a single clean copy of every unique email, and reconstruct a clean Thunderbird folder structure—backed by comprehensive unit tests for confidence.

*(See `.ai-plans/thunderbird-mbox-reference.md` for authoritative Thunderbird `comm-central` specifications on `mboxrd`, `.sbd`/`.msf` folder structures, and `X-Mozilla-*` headers.)*

---

## 1. Sufficiency of Current Design (What Works Well)
1. **Low-Memory Offset Indexing (`thunderbirddedup/mbox/mboxfile.py` & `thunderbirddedup/db/__init__.py`):**
   `Mailbox.buildSummary()` streams through each MBOX file once, recording `start_offset` and `end_offset` in SQLite without keeping full message bodies in memory. `Mailbox.getMessageFromFile()` then `seek()`s directly to `start_offset` and reads `length` bytes when writing the deduplicated output.
2. **Dual-Hash Strategy (`Message.getHash()` in `thunderbirddedup/mbox/mboxmessage.py`):**
   - **Parsed hash (`hashid`):** Excludes the MBOX `From - <timestamp>` envelope line and mutable Thunderbird headers (`X-Mozilla-Status`, `X-Mozilla-Status2`, `X-Mozilla-Keys`, `X-Apparently-To`, `Message-ID`), which change when Thunderbird copies or moves messages.
   - **Disk hash (`diskhashid`):** SHA-256 of the exact byte range on disk (`start_offset` to `end_offset`), used by `dedupper()` to verify that the extracted message bytes match what was originally indexed.
3. **Recursive Folder Grouping (`Preplanner` in `thunderbirddedup/planner/walk.py`):**
   Splitting on the *last* occurrence of `Inbox.sbd/` (`rfind(folder_pattern)`) accurately groups all 18–20 recursive copies of each of the 775 logical folders (e.g., `Inbox.sbd/Activities`, `Inbox.sbd/Merchants`) into a single deduplication set.
4. **Non-Destructive Symlink Staging (`planner` in `thunderbirddedup/planner/plan.py`):**
   Numbered symlinks (`000001.mbox` ... `000018.mbox`) and JSON audit files (`mapping.json`, `plan_output.json`, `combinatory_operation.json`) keep the source profile untouched during processing.

---

## 2. Identified Gaps, Risks, and Bugs (Backed by Thunderbird Specs)

### Gap 1 (CRITICAL — Silent Data Loss): Deleted/Expunged Messages & Fragmented Status Flags (`X-Mozilla-Status*` / `X-Mozilla-Keys`)
- Per Thunderbird's `nsMsgMessageFlags`, `X-Mozilla-Status` is a hex bitmask where bit `0x0008` (`Expunged`) marks a message that was deleted or moved out of the folder, awaiting compaction (`nsMsgBrkMBoxStore::AsyncCompact`). Similarly, `X-Mozilla-Status2` bit `0x00200000` marks `IMAPDeleted`.
- Because `getHash(diskHash=False)` strips `X-Mozilla-Status*` and `X-Mozilla-Keys`, and `dedupper()` simply takes the first matching message in SQLite (`000001.mbox`):
  1. If `000001.mbox` has bit `0x0008` (`Expunged`) set, Thunderbird will hide or purge that message when rebuilding the `.msf` index!
  2. If user actions (`Read 0x0001`, `Replied 0x0002`, `Marked/Starred 0x0004`, `Forwarded 0x1000`, or tags in `X-Mozilla-Keys`) occurred across different copies of the message in different recursive folders, taking only `000001.mbox` loses those flags/tags.
- **Fix:**
  - Parse `X-Mozilla-Status`, `X-Mozilla-Status2`, and `X-Mozilla-Keys` during indexing and store them in `MessageDatabase`.
  - When deduplicating a hash group, **merge** the status values across all copies of that message:
    - `merged_status = (status_1 | ... | status_N) & ~0x0008` (bitwise OR all flags and clear `Expunged` so even if all copies had `0x0008` set, the message is preserved).
    - `merged_status2 = (status2_1 | ... | status2_N) & ~0x00200000` (bitwise OR all extended flags and clear `IMAPDeleted`).
    - `merged_keys` = ordered union of all space-separated tags in `X-Mozilla-Keys`.
  - Verify `disk_hash` on the raw bytes read from disk first, then apply the merged `X-Mozilla-Status`, `X-Mozilla-Status2`, and `X-Mozilla-Keys` headers before writing to the deduplicated MBOX file.

### Gap 2 (CRITICAL — Silent Message Merging): MBOX (`mboxrd`) Parser & RFC 5322 State Machine
1. **Envelope (`From `) Line Recognition (`MboxMsgInputStream` / `nsParseMailMessageState`):**
   - `Mailbox.mboxMessageStart` (`thunderbirddedup/mbox/mboxfile.py` line 43) currently only matches `^From - `. While Thunderbird writes `From - <date>`, imported MBOX files or POP spools may use `From <sender> <date>`. Any envelope line with an email address instead of `-` will not be recognized as a new message and will be merged into the previous message's body.
   - Conversely, in `mboxrd`, lines starting with `>From ` are **escaped body lines**, never message separators.
2. **RFC 5322 Header-to-Body Blank Line Transition (`buildSummary` lines 246–333):**
   - Per RFC 5322 and Thunderbird's `nsParseMailMessageState`, **everything after the first blank line** (`\r\n` or `\n`) until the next `From ` envelope line is the message body (including any MIME boundaries).
   - Currently, when `buildSummary()` encounters the first blank line, it sets `foundBlankLine = True`, but leaves `header_name` set to the last header name and appends the blank line to `currentRecord.headers[header_name]`.
   - If the first line of the body contains `Key: Value` (e.g., forwarded email headers in the body), line 252 (`elif isHeaderLine and header_name != 'body':`) misinterprets body lines as headers and resets `foundBlankLine = False`.
   - If a message has an empty body followed immediately by the next `From ` line, line 305 pops from `currentRecord.lines` (which is empty) while leaving the trailing blank line in `headers`.
   - **Fix:** Transition `header_name = 'body'` immediately upon encountering the first blank line in a message.
3. **`sys.exit(1)` on Malformed Boundary (`parseBoundaryMarker` line 183):**
   A malformed `Content-Type` boundary in a spam email will call `sys.exit(1)` and abort the entire multi-hour run instead of logging a warning and continuing.

### Gap 3 (HIGH — Performance & Concurrency at 330 GB Scale)
1. **Missing SQLite Indexes (`thunderbirddedup/db/__init__.py`):**
   The `messages` table has no index on `hashid` or `diskhashid`. In `dedupper()`, `get_messages_by_hash()` runs a `SELECT ... WHERE hashid = :hashid` query per unique hash, causing $\mathcal{O}(N^2)$ full-table scans on folders with tens or hundreds of thousands of messages.
   - *Also:* `ADD_SCHEMA_VERSION` is defined in `db/__init__.py` but never executed in `init()`.
2. **Per-Message SQLite Transactions (`MessageDatabase.add_message()`):**
   `with self._get_db() as cursor:` commits a transaction on every single message insert, causing one disk `fsync()` per email when using a file-backed SQLite database. Batching commits per file (or every $N$ messages) will dramatically speed up indexing.
3. **Unbounded Async Task Creation in `combinatory`:**
   Spawning all 775 folder deduplication plans and thousands of file tasks simultaneously opens thousands of files and SQLite connections at once. Bounding concurrency via `asyncio.Semaphore` will keep resource usage predictable.
   - *Also:* Line 159 overwrites `required_file_count` instead of accumulating (`+=`) across plans.

### Gap 4 (HIGH — Folder Discovery & Clean Tree Reconstruction)
1. **Identifying Thunderbird MBOX Files (`MailboxFolder.getMboxFiles()`):**
   - `os.walk()` already excludes `"."` and `".."` and separates `.sbd` directories (`dirs`) from files (`files`).
   - `thunderbirddedup/mbox/mboxfolder.py` line 36 currently skips any file where `"." in filename`. In Thunderbird (`NS_HashIfNecessary`), periods are legal in folder names (e.g., `v1.0` creates MBOX file `v1.0` and index `v1.0.msf`).
   - Instead of `if "." in filename:`, `getMboxFiles()` should skip dotfiles (`filename.startswith(".")`) and known non-MBOX extensions (`.msf`, `.dat`, `.json`, `.sqlite`, `.wdseml`, `.html`, `.mboxrecord`).
2. **Incomplete & Duplicated Path in `combinatory` Step 5 (`move_dedup_mbox`):**
   - See `.ai-plans/combinatory-file-move.md` for details.
   - Reconstructing a clean folder hierarchy (with `.sbd` subdirectories and extensionless MBOX files, omitting `.msf` files so Thunderbird rebuilds fresh indexes automatically) allows a clean replacement of the bloated 330 GB `Inbox.sbd`.

---

## 3. Phased Implementation Plan

### Phase 1: Parser, Folder Discovery & Hashing Hardening (Data Integrity) — COMPLETED
- [x] Update `MailboxFolder.getMboxFiles()` to skip dotfiles and known non-MBOX extensions (`.msf`, `.dat`, etc.) rather than all filenames containing `"."`.
- [x] Harden `Mailbox.buildSummary()` per `mboxrd` / RFC 5322 specs:
  - Transition `header_name = 'body'` immediately on the first blank line after headers so body lines with colons and empty-body messages are handled accurately.
  - Support standard MBOX `From <sender> <date>` envelope lines in addition to `From - <date>`.
  - Replace `sys.exit(1)` in `parseBoundaryMarker()` with a logged warning and graceful fallback.
- [x] Merge `X-Mozilla-Status`, `X-Mozilla-Status2`, and `X-Mozilla-Keys` across duplicates and always unset `Expunged` (`0x0008`) / `IMAPDeleted` (`0x00200000`):
  - Parse `X-Mozilla-Status`, `X-Mozilla-Status2`, and `X-Mozilla-Keys` on each message record and store them in SQLite.
  - Across all duplicate copies of a unique message, bitwise-OR `X-Mozilla-Status` (always clearing `0x0008`), bitwise-OR `X-Mozilla-Status2` (always clearing `0x00200000`), and union `X-Mozilla-Keys` tags.
  - After verifying `disk_hash` on the raw message bytes from disk, update the `X-Mozilla-*` headers in the output message with the merged values.
- [x] Add unit tests in `tests/mbox/` and `tests/dedup/` covering dot-named folders, empty-body messages, body lines with colons, `>From ` body escaping, malformed boundaries, and merging/unsetting `X-Mozilla-Status*` & `X-Mozilla-Keys` across duplicates.

### Phase 2: SQLite Performance & Reliability — COMPLETED
- [x] Add SQLite indexes on `hashid` and `diskhashid` in `MessageDatabase` (`thunderbirddedup/db/__init__.py`).
- [x] Fix `schema_version` insertion (`ADD_SCHEMA_VERSION`) in `MessageDatabase.init()`.
- [x] Add transaction batching support so `processFile()` commits once per file (or per batch) instead of per message.
- [x] Add unit tests in `tests/db/test_db.py` to bring `thunderbirddedup/db/` to $\ge 95\%$ coverage (achieved 100%).

### Phase 3: Clean Folder Structure Reconstruction (`combinatory`) — COMPLETED
- [x] Implement canonical path resolution in `combinatory` Step 5 (`move_dedup_mbox`) so `Inbox.sbd/` is not duplicated and required parent `.sbd` directories are created automatically (omitting `.msf` files so Thunderbird regenerates them).
- [x] Add post-deduplication summary report and interactive confirmation prompt (with `--yes` / `-y` auto-confirm flag and `--output-location` / `-ol` flag on `tb-dedup do`), moving deduplicated MBOX files into a clean reconstructed directory tree and recording `final_mbox` and per-folder `stats` in `combinatory_operation.json`.
- [x] Fix `required_file_count` accumulation, safe `RLIMIT_NOFILE` handling on Linux, and bound concurrent workers with `asyncio.Semaphore`.
- [x] Add end-to-end unit tests in `tests/combinatory/test_combinatory.py` simulating a multi-level recursive `Inbox.sbd` tree with unique emails scattered across recursion levels (achieved 98.10% coverage on `combinatory`).

### Phase 4: CLI & GUI Cleanup + Test Coverage Target ($\ge 92\%$) — COMPLETED
- [x] Add unit tests for `thunderbirddedup/cmd/__init__.py` (`tests/cmd/test_cmd.py`), `thunderbirddedup/utils/json.py` (`tests/utils/json_test.py`), and `thunderbirddedup/utils/disk.py` (`tests/utils/disk_test.py`).
- [x] Execute `.ai-plans/gui-consolidation.md` (consolidating onto PySide6 + `PySide6.QtAsyncio` in `thunderbirddedup/gui/` and adding headless unit tests in `tests/gui/test_gui.py`) so `tox` passes both `py3.14` (achieved **98.10%** overall coverage across 146 tests) and `pep8`.
