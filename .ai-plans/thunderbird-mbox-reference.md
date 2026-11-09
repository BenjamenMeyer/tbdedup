# Thunderbird MBOX & Folder Storage Reference Plan

## Overview
This document summarizes authoritative Thunderbird (`comm-central`) specifications for local mail storage (`nsMsgBrkMBoxStore`, `MboxMsgInputStream`, `nsParseMailMessageState`, and `NS_HashIfNecessary`) and defines how `thunderbirddedup` should identify MBOX files, parse messages, and handle Thunderbird-specific headers.

---

## 1. How Thunderbird Structures Mail Folders on Disk

In Thunderbird's local mail storage (`Mail/Local Folders/`, POP3 accounts, or offline IMAP stores using Berkeley MBOX via `nsMsgBrkMBoxStore`), each mail folder is represented by up to three filesystem entries:

1. **`<FolderName>` (MBOX File — No Extension):**
   - Contains the raw concatenated messages in **`mboxrd`** format.
   - Note: A folder that only acts as a container for subfolders may have a `0`-byte `<FolderName>` file (or no `<FolderName>` file at all, only `<FolderName>.msf` and `<FolderName>.sbd/`).
2. **`<FolderName>.msf` (Mail Summary File):**
   - Mork database cache storing parsed header summaries, thread trees, flags, and byte offsets into `<FolderName>`.
   - Contains no message bodies. If deleted while Thunderbird is closed, Thunderbird automatically rebuilds `<FolderName>.msf` by scanning `<FolderName>` and reading its `X-Mozilla-*` headers.
3. **`<FolderName>.sbd/` (Subdirectory):**
   - Created only when `<FolderName>` has child folders. Contains the `<ChildFolder>`, `<ChildFolder>.msf`, and `<ChildFolder>.sbd/` entries for those children.

### Folder Name Sanitization & Dots in Folder Names
- When a user creates a folder in Thunderbird, `NS_HashIfNecessary` sanitizes OS-illegal characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) or hashes overly long names into an 8-character hex suffix.
- **Periods (`.`) ARE legal inside folder names** (e.g., `v1.0`, `john.doe@example.com`, `St. Louis`). On disk, a folder named `v1.0` creates:
  - `v1.0` (the MBOX file)
  - `v1.0.msf` (the summary index file)
  - `v1.0.sbd/` (if it has subfolders)
- **Other files Thunderbird stores in mail directories:**
  - `msgFilterRules.dat` (filter definitions)
  - `popstate.dat` (POP3 UIDL state)
  - `virtualFolders.dat`, `folderCache.json`, `.mozmsgs/`, `.wdseml` (search/Spotlight/Windows Search integration files)

### Authoritative Rule for Identifying MBOX Files (`MailboxFolder.getMboxFiles()`)
Because `os.walk()` already separates directories (`dirs`, such as `*.sbd` and `*.mozmsgs`) from regular files (`files`) and never yields `"."` or `".."`:
1. **Never filter by `if "." in filename:`**, because that silently drops any MBOX folder whose name contains a period (like `v1.0` or `user@domain.com`).
2. **Exclude known non-MBOX extensions and hidden dotfiles:**
   - Skip files starting with `"."` (hidden files / logs).
   - Skip files ending with `.msf`, `.dat`, `.json`, `.sqlite`, `.wdseml`, `.html`, `.mboxrecord`.
3. **Optional Positive Companion Check / Header Check:**
   - In Thunderbird, every MBOX folder `<Name>` has a sibling `<Name>.msf` index file, and every non-empty MBOX file starts with an `mbox` envelope line (`From `).

---

## 2. Authoritative Thunderbird MBOX (`mboxrd`) Format & Message Recognition

In Thunderbird's `mailnews/base/src/MboxMsgInputStream.cpp` (`MboxParser`) and `mailnews/local/src/nsParseMailbox.cpp` (`nsParseMailMessageState`):

### A. The Envelope (`From `) Separator Line
- **What Thunderbird Writes:** When Thunderbird itself writes a new message to a local MBOX file, it writes:
  ```text
  From - <DOW> <MON> <DD> <HH>:<MM>:<SS> <YYYY>\r\n
  ```
- **What Thunderbird Reads (`IsEnvelopeLine`):** Because MBOX files may contain messages imported from other mail clients or POP/Unix spools, Thunderbird recognizes a line at the start of a message (or following a blank line) starting with `"From "` (`strncmp(line, "From ", 5) == 0`) followed by an envelope sender (`-` or `user@domain`) and a `ctime`-style timestamp.
- **Tightened Regex for `Mailbox.mboxMessageStart`:**
  Instead of only `^From - `, use:
  ```python
  re.compile(r'^From\s+\S+\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+')
  ```
  (with fallback or support for `^From - ` so synthetic test files continue to work).

### B. `mboxrd` `>From ` Escaping (Critical Misconception in Current `detect_mbox_type`)
- **How `mboxrd` actually works:**
  - The message separator line itself is **always** unescaped `From ...` at column 0.
  - Inside a message's **body**, any line matching `^>*From ` has one extra `>` prepended when written to disk (`From hello` $\rightarrow$ `>From hello`; `>From hello` $\rightarrow$ `>>From hello`).
- **Correction for `Mailbox.detect_mbox_type` / `buildSummary`:**
  - A line starting with `>From - ` is **never** a message separator in `mboxrd`—it is an escaped line inside a message body!
  - Only an unescaped `^From ` line after a blank line (or at file offset 0) marks the start of a new message.

### C. RFC 5322 Message Structure (Headers $\rightarrow$ Blank Line $\rightarrow$ Body)
An email message in an MBOX file strictly consists of:
1. **Line 0:** The `From ...` envelope line.
2. **Headers:** One or more RFC 5322 header lines:
   - Starts with a header field name (`^[\x21-\x39\x3b-\x7e]+:.*`), **or**
   - A folded continuation line starting with whitespace (`^[ \t]+`) immediately following a header line.
3. **Header/Body Separator:** The **first empty line** (`\r\n` or `\n`, where `len(line.strip()) == 0`).
4. **Body:** Every line after that first empty line until the next message's `From ...` envelope line!
   - **Why this simplifies and tightens `buildSummary()`:**
     Once the first blank line after the headers is reached, the parser is unconditionally in the **`body` state** until the next `From ` envelope line (preceded by a blank line).
     - We do **not** need `parseBoundaryMarker()` to figure out where the body starts! MIME boundaries are part of the body (after the first blank line).
     - Lines inside the body that happen to look like `Key: Value` (e.g., forwarded email headers in the body) will never be mistaken for message headers because the parser has already crossed the first blank line into the `body` state.

---

## 3. Authoritative Thunderbird Metadata Headers (`X-Mozilla-*`)

When Thunderbird stores a message in an MBOX file, it injects three internal headers right after the `From -` line so that if the `.msf` file is deleted, Thunderbird can reconstruct all message flags and tags from the MBOX file alone:

1. **`X-Mozilla-Status` (4-digit hex bitmask, e.g. `0001`):**
   - `0x0001` (`Read`): Message has been read.
   - `0x0002` (`Replied`): User replied to this message.
   - `0x0004` (`Marked`): Message is starred/flagged.
   - **`0x0008` (`Expunged`):** **Message was deleted or moved out of this folder**, awaiting folder compaction!
   - `0x0010` (`HasRe`): Subject has `Re:`.
   - `0x1000` (`Forwarded`): Message was forwarded.
2. **`X-Mozilla-Status2` (8-digit hex bitmask, e.g. `00000000`):**
   - Tracks extended flags (Junk/Ham status, attachment flags, MDN report sent).
3. **`X-Mozilla-Keys` (space-separated string, normally padded with spaces to ~80 chars):**
   - Stores user-applied Thunderbird tags (e.g., `$label1`, `important`, `todo`).

### Impact on Deduplication & Hashing
- **Excluding from `parsed` hash (`THUNDERBIRD_HEADERS`):**
  - Excluding `X-Mozilla-Status`, `X-Mozilla-Status2`, `X-Mozilla-Keys`, and `X-Apparently-To` from the content hash is 100% right—when a message is copied between folders or marked read in one folder, its content hash remains identical.
  - **What about `Message-ID`?** `Message-ID` is immutable for a given email (generated by the sending mail server), so keeping or excluding it in `THUNDERBIRD_HEADERS` is fine, though including `Message-ID` in the content hash actually *prevents* two different short emails with identical bodies sent within the same second from colliding!
- **Merging `X-Mozilla-Status`, `X-Mozilla-Status2`, and `X-Mozilla-Keys` Across Duplicates & Clearing `Expunged`:**
  - **Mail Workflow Context:** Emails are moved via a Thunderbird filter rule from a remote IMAP folder to the local disk (`Local Folders`), and then processed from the local disk into the various local subfolders (`Inbox.sbd/...`). IMAP is never directly processed by `thunderbirddedup`.
  - Because interactions (reading, starring, replying, forwarding, tagging) may have occurred on different duplicate copies across the 19–20 recursive folders, and because emails are generally never intentionally deleted, we **merge** the status headers across all duplicate copies of a unique message and **always unset** the deleted/expunged flags:
    1. **`X-Mozilla-Status` (Bitwise `OR` + Unset `Expunged` `0x0008`):**
       ```python
       merged_status = (status_1 | status_2 | ... | status_N) & ~0x0008
       ```
       Preserves `Read` (`0x0001`), `Replied` (`0x0002`), `Marked` (`0x0004`), `Forwarded` (`0x1000`), etc., from any copy, while ensuring `Expunged` (`0x0008`) is cleared so the email is never hidden or purged when Thunderbird rebuilds `.msf` indexes.
    2. **`X-Mozilla-Status2` (Bitwise `OR` + Unset `IMAPDeleted` `0x00200000`):**
       ```python
       merged_status2 = (status2_1 | status2_2 | ... | status2_N) & ~0x00200000
       ```
       Preserves `Attachment` (`0x10000000`) and other extended flags while clearing `IMAPDeleted` (`0x00200000`).
    3. **`X-Mozilla-Keys` (Ordered Union of Tags):**
       Combine all unique space-separated tags (e.g., `$label1`, `important`, `todo`) across all copies of the message.
    4. **Preserve `disk_hash` Integrity Check:**
       During `dedupper()`, first read the raw message bytes from disk (`getMessageFromFile`) and verify `sha256(msgData) == disk_hash`. Once raw byte integrity is verified, replace the `X-Mozilla-Status`, `X-Mozilla-Status2`, and `X-Mozilla-Keys` header lines in the extracted message bytes with the merged values before writing to the deduplicated MBOX file.
