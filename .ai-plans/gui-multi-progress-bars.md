# GUI Four-Tier Progress Bars, Background Worker & Cancel Plan

**Date:** 2026-10-28
**Status:** Completed & Validated (PR ready)

---

## 1. Goal

Replace the single coarse-grained `QProgressBar` in `thunderbirddedup/gui/app.py` with a **four-tier progress bar panel**, add a **Cancel Operation** button, run `TbDedupRunner` on a dedicated background `asyncio` worker thread, and add periodic `await asyncio.sleep(0)` yields inside the engine so the user receives continuous, non-blocking visual feedback across:

1. **Bar 1 — Overall Logical Folder Groups (`progress_overall`):** Progress across all selected logical folders (`42 / 799`).
2. **Bar 2 — Duplicate Copies of Current Folder (`progress_copies`):** Traversing the $1..K$ duplicate MBOX file copies belonging to the current folder group (`Copy 5 / 18`).
3. **Bar 3 — Current MBOX Copy Read Progress (`progress_file`):** Byte-offset and message-count progress inside the specific MBOX file copy currently being read (`412.5 MB / 1.39 GB — 45,000 msgs`).
4. **Bar 4 — Deduplicated Output Write Progress (`progress_write`):** Merging `X-Mozilla-*` flags across duplicates and writing the unique messages to the folder's deduplicated `.mbox` file (`1,250 / 3,400 unique msgs`).
5. **Live Per-Row `Copies (N/M)` & `Status` Updates in `QTreeView`:** Updating each folder group's row in the tree view in real time (`Queued` $\rightarrow$ `Indexing 5/18 (29%)` $\rightarrow$ `Writing 1,250/3,400 (37%)` $\rightarrow$ `Deduplicated` $\rightarrow$ `Moved`), which scales naturally when multiple folder groups are processed in parallel.
6. **`*.sbd` Subtree Roll-Up Summaries & Savings Column in `QTreeView`:** Adding a `Saved` column (`Saved Bytes (%)`) to `TREE_COLUMNS` and dynamically rolling up `Copies`, `Source Size`, `Total Msgs`, `Unique Msgs`, `Dedup Size`, `Saved`, and `Status` onto every parent `*.sbd` directory row so the user can see where duplication and space savings came from at every level of the folder hierarchy.
7. **Immediate, Clean Operation Cancellation (`btn_cancel`):** Allowing the user to cancel an in-flight Scan, Deduplicate, or Move operation at any time and safely return the UI to a ready state.

---

## 2. Four-Tier Progress Bar Layout (`thunderbirddedup/gui/app.py`)

Replace `self.progress` with four stacked `QProgressBar` widgets (each with `setTextVisible(True)` and descriptive `setFormat(...)` strings):

| Widget Name | Tier | Example Display Text | Tracked Metric |
| :--- | :--- | :--- | :--- |
| `self.progress_overall` | **1. Overall Folder Groups** | `Folder Groups: 42 / 799 (5.3%) — Inbox.sbd/.../change.org` | • **Step 1 (Scan):** Indeterminate (`0, 0`) during `getMboxFiles()`, then `0..N` MBOX files during `preplan()`<br>• **Step 2 (Deduplicate):** `completed_plans / total_selected_plans`<br>• **Step 3 (Move):** `moved_plans / total_selected_plans` |
| `self.progress_copies` | **2. Duplicate Copies in Group** | `Folder Copies [change.org]: Copy 5 / 18 (000005.mbox)` | • Traversing the $1..K$ duplicate MBOX files (`files_indexed / total_files_in_plan`) for the active logical folder group |
| `self.progress_file` | **3. Current Copy Read Activity** | `Reading 000005.mbox: 412.50 MB / 1.39 GB (29.7%) — 45,000 msgs` | • Byte-offset progress (`msg.end_offset / file_size_bytes`) scaled to `0..1000` permille (avoiding 32-bit signed `int` overflow on files $>2\text{ GB}$) |
| `self.progress_write` | **4. Deduplicated Output Write** | `Writing Deduplicated MBOX [change.org]: 1,250 / 3,400 unique msgs (36.8%)` | • Merging `X-Mozilla-*` metadata across duplicates and writing `unique_messages_written / total_unique_messages` to the output `.mbox` file |

### Backward Compatibility
Keep `self.progress` as an alias for `self.progress_overall` (and keep `on_progress_updated(completed, total)` working) so any existing callers or unit tests referencing `win.progress` or `win.on_progress_updated` continue to work without breaking.

---

## 3. Backend Progress Callbacks & Asyncio Yielding (`thunderbirddedup/dedup/__init__.py`)

### 3.1 Why the Current GUI Locks Up During Runs (and How We Fix Both Causes)
There are two reasons the current GUI locks up during active runs:

1. **`time.sleep(0)` Instead of `await asyncio.sleep(0)`:**
   Currently, `thunderbirddedup/utils/time.py` defines:
   ```python
   def do_yield():
       time.sleep(0)
   ```
   `time.sleep(0)` yields the OS thread, **not** the Python `asyncio` event loop. Because `Mailbox.buildSummary()`, `os.walk()`, SQLite inserts, and SHA-256 hashing are synchronous, coroutines run from start to finish without an `await` point.
2. **CPU-Intensive SHA-256 Hashing & Disk I/O Sharing the Main Qt Thread:**
   When `asyncio` runs on the same thread as `QApplication` (`QtAsyncio`), every millisecond spent reading gigabytes of MBOX data, computing SHA-256 hashes, or writing to SQLite blocks the Qt GUI thread from painting or handling mouse/window events (causing Linux desktop environments to report the window as "Not Responding").

#### Dual Fix:
1. **Dedicated Background `asyncio` Worker Thread for `TbDedupRunner`:**
   - Keep Qt's `QApplication` event loop on the main thread exclusively for UI rendering and user interaction.
   - Run `TbDedupRunner` coroutines (`scan_and_preplan`, `deduplicate_selected`, `move_results`) on a dedicated background `asyncio` event-loop thread (`threading.Thread(daemon=True)` running an `asyncio` loop via `asyncio.run_coroutine_threadsafe(coro, bg_loop)`).
   - Because PySide6 `Signal.emit(...)` is **thread-safe** (Qt automatically uses `Qt.QueuedConnection` across threads), all progress signals, log messages, and completion events marshal safely onto the main GUI thread without ever blocking UI responsiveness.
   - Clicking **Cancel Operation** calls `bg_loop.call_soon_threadsafe(future_or_task.cancel)` immediately from the responsive GUI thread.
2. **Periodic `await asyncio.sleep(0)` Yields Inside Backend Loops:**
   - Adding `await asyncio.sleep(0)` every ~250 messages (or ~50 ms) inside `processFile()`, `dedupper()`, `getMboxFiles()`, and `preplan()` ensures `asyncio.CancelledError` is injected within milliseconds when the user clicks **Cancel**, and allows concurrent `asyncio` tasks to interleave smoothly.

### 3.2 `processFile()` Enhancements
Update signature (preserving backward compatibility):
```python
async def processFile(
    filename,
    storage,
    counter_update=None,
    file_progress_callback=None,
):
```
- Before entering `for msg in box.buildSummary():`:
  - Query `total_bytes = os.path.getsize(filename) if os.path.exists(filename) else 0`.
  - If `file_progress_callback is not None`: call `file_progress_callback(filename, 0, total_bytes, 0)`.
- Inside `for msg in box.buildSummary():`:
  - Every `250` messages (or when `time.monotonic() - last_yield >= 0.05`):
    - If `file_progress_callback is not None`:
      `file_progress_callback(filename, msg.end_offset, total_bytes, counter)`
    - `await asyncio.sleep(0)`
- After the loop finishes (before `counter_update()`):
  - If `file_progress_callback is not None`:
    `file_progress_callback(filename, total_bytes, total_bytes, counter)`
  - `await asyncio.sleep(0)`

### 3.3 `dedupper()` Enhancements
Update signature (preserving backward compatibility):
```python
async def dedupper(
    mboxfiles,
    msg_hash_storage_location,
    use_disk_data_for_hash=False,
    output_base_path=None,
    copy_progress_callback=None,
    file_progress_callback=None,
    write_progress_callback=None,
):
```
- **Phase A (Traversing duplicate MBOX copies in plan — Bar 2 & Bar 3):**
  - Emit initial `copy_progress_callback(0, len(mboxfiles), "")` and `write_progress_callback(0, 0)` if provided.
  - Inside `counter_update()`, emit `copy_progress_callback(int(counters["completed"]), int(counters["total"]), filename)`.
  - Pass `file_progress_callback=file_progress_callback` into `processFile(...)`.
- **Phase B (Writing unique messages to deduplicated MBOX — Bar 4):**
  - Query `total_unique = storage.get_unique_message_count(use_disk=use_disk_data_for_hash)`.
  - Emit `write_progress_callback(0, total_unique)` if provided.
  - Every `250` written messages (and on completion):
    - Emit `write_progress_callback(wcounter, total_unique)` if provided.
    - `await asyncio.sleep(0)`

---

## 4. Runner Signals & Wiring (`thunderbirddedup/gui/runner.py`)

### 4.1 Signals on `TbDedupRunner`
Add granular signals for all 4 progress bars while keeping `progress_updated = Signal(int, int)` for backward compatibility:
```python
progress_updated = Signal(int, int)
overall_progress_updated = Signal(int, int, str)  # Bar 1: (completed_plans, total_plans, label)
copy_progress_updated = Signal(int, int, str)     # Bar 2: (copy_index, total_copies, label)
file_progress_updated = Signal(int, int, str)     # Bar 3: (permille_0_1000, 1000, label)
write_progress_updated = Signal(int, int, str)    # Bar 4: (written_msgs, total_unique_msgs, label)
plan_live_status_updated = Signal(str, str, str)  # Tree Row: (root_file, copies_text, status_text)
```

### 4.2 Emitting Progress Across All 3 GUI Steps
1. **Step 1 (`scan_and_preplan`):**
   - Emit `overall_progress_updated(0, 0, "Scanning directory tree for MBOX files...")` before `getMboxFiles()` (putting `progress_overall` into indeterminate/busy mode) and `await asyncio.sleep(0)`.
   - Once `self.mboxfiles` are found (`total_files = len(self.mboxfiles)`), emit `overall_progress_updated(total_files, total_files, f"Grouped {total_files} MBOX files into {self.preplanner.plan_count()} logical folders")`.
2. **Step 2 (`deduplicate_selected`):**
   - Emit `overall_progress_updated(0, total_plans, f"Folder Groups: 0 / {total_plans} (0.0%)")`.
   - Pass `copy_progress_callback`, `file_progress_callback`, and `write_progress_callback` closures from `_run_single_plan()` into `dedup.dedupper(...)`:
     - `copy_progress_callback(done, total, fname)` emits:
       `self.copy_progress_updated.emit(done, total, f"Folder Copies [{rf}]: Copy {done} / {total} ({os.path.basename(fname)})")`
     - `file_progress_callback(fname, current_bytes, total_bytes, msg_count)` computes permille (`int((current_bytes / total_bytes) * 1000)` when `total_bytes > 0` else `1000`) and human-readable byte sizes via `combinatory.format_bytes()`, emitting:
       `self.file_progress_updated.emit(permille, 1000, f"Reading {os.path.basename(fname)}: {combinatory.format_bytes(current_bytes)} / {combinatory.format_bytes(total_bytes)} ({msg_count:,} msgs)")`
     - `write_progress_callback(written, total_unique)` emits:
       `self.write_progress_updated.emit(written, total_unique, f"Writing Deduplicated MBOX [{rf}]: {written:,} / {total_unique:,} unique msgs")`
       and updates the tree row via:
       `self.plan_live_status_updated.emit(rf, f"{total_copies}/{total_copies}", f"Writing {written:,}/{total_unique:,}")`
   - Also emit `self.plan_live_status_updated.emit(rf, f"{done}/{total}", f"Indexing {done}/{total} ({pct:.0f}%)")` from `copy_progress_callback` / `file_progress_callback` so each folder row in `QTreeView` (`self._row_items_by_root[rf]`) displays live `Copies` (`N/M`) and `Status` even when multiple folder groups are processed concurrently.
   - As each plan completes, `on_plan_completed(rf)` increments `completed_count` and emits both `progress_updated(completed_count, total_plans)` and `overall_progress_updated(completed_count, total_plans, f"Folder Groups: {completed_count} / {total_plans} — Completed {rf}")`.
3. **Step 3 (`move_results`):**
   - For each plan moved (`idx / total`), emit `overall_progress_updated(idx, total, f"Moving: {idx} / {total} — {root_file}")` and `await asyncio.sleep(0)` so the move step also updates smoothly.

---

## 5. `*.sbd` Subtree Roll-Up Summaries & Savings Column (`thunderbirddedup/gui/app.py`)

### 5.1 Expanded `TREE_COLUMNS`
Add a dedicated `"Saved"` column so both leaf MBOX rows and parent `*.sbd` directory rows display exact disk space and message savings:
```python
TREE_COLUMNS = [
    "Logical Folder",
    "Copies",
    "Source Size",
    "Total Msgs",
    "Unique Msgs",
    "Dedup Size",
    "Saved",
    "Status",
]
```

### 5.2 Subtree Aggregation on `*.sbd` Directory Rows
Currently, `on_preplan_completed()` creates `*.sbd` parent rows with empty strings `""` for columns `1..N`. Instead:
- Store `self._dir_rows_by_key[dir_key] = row_items` for every `*.sbd` directory node in the tree, along with per-leaf numeric stats in `self._leaf_stats[root_file]`:
  ```python
  {
      "copies_done": 0,
      "copies_total": len(plan.files),
      "source_bytes": source_bytes,
      "total_msgs": None,
      "unique_msgs": None,
      "dedup_bytes": None,
      "status": "Pending",
  }
  ```
- Provide a helper `self._update_ancestor_sbd_summaries(root_file)` (and a bulk `self._update_all_sbd_summaries()` called at the end of `on_preplan_completed()`):
  - For each `*.sbd` directory `dir_key`, aggregate all descendant `root_file` leaves whose path starts with `dir_key + "/"`:
    - **Copies:** `f"{sum_copies_done} / {sum_copies_total}"` (or `f"{sum_copies_total}"` before deduplication starts)
    - **Source Size:** `combinatory.format_bytes(sum_source_bytes)`
    - **Total Msgs:** `f"{sum_total_msgs:,}"` (if at least one descendant has completed deduplication, else `"-"`)
    - **Unique Msgs:** `f"{sum_unique_msgs:,} (-{sum_total_msgs - sum_unique_msgs:,})"` (if at least one descendant has completed deduplication, else `"-"`)
    - **Dedup Size:** `combinatory.format_bytes(sum_dedup_bytes)` (if at least one descendant has completed deduplication, else `"-"`)
    - **Saved:** Computed across completed descendants (`completed_source_bytes - sum_dedup_bytes`):
      `f"{combinatory.format_bytes(saved_bytes)} ({saved_pct:.1f}%)"`
    - **Status:** Roll-up summary of descendant states, e.g.:
      - `"Pending (N folders)"` before run
      - `"Active (done/N folders)"` while descendants are indexing/writing
      - `"Deduplicated (N/N)"` when all checked descendants in the subtree finish deduplication
      - `"Moved (N/N)"` when all checked descendants in the subtree are moved
- Clicking on a `*.sbd` row in `QTreeView` (`on_folder_selected`) will also display a detailed subtree breakdown in the right-hand details panel (total descendant folders, total copies, source size, deduplicated size, messages removed, and space saved).

---

## 6. Cancel Button & Clean Async Cancellation

### 5.1 UI Controls (`thunderbirddedup/gui/app.py`)
- Add `self.btn_cancel = QPushButton("Cancel Operation")` to `actions_layout` next to the 3 step buttons:
  - Initially disabled (`self.btn_cancel.setEnabled(False)`).
  - Enabled whenever an async operation (`do_search`, `do_deduplicate`, or `do_move`) starts, and disabled again when the operation finishes or is cancelled.
- Track the currently running top-level `asyncio.Task` on `MainWindow` (`self._active_task = None`).
- Clicking **Cancel Operation** calls `self.do_cancel()`:
  - Calls `self.runner.request_cancel()` and cancels `self._active_task` (`self._active_task.cancel()`).
  - Logs `"Cancelling current operation..."` and disables `btn_cancel` while cancellation unwinds.
- Also cancel `self._active_task` inside `MainWindow.closeEvent()` if the user closes the window while an operation is running.

### 5.2 Runner & Worker Cancellation Handling (`thunderbirddedup/gui/runner.py`, `combinatory/__init__.py`, `dedup/__init__.py`)
- Because `processFile()`, `dedupper()`, `getMboxFiles()`, `preplan()`, and `move_results()` will yield periodically via `await asyncio.sleep(0)`, calling `.cancel()` on the active task raises `asyncio.CancelledError` within milliseconds—even in the middle of a 33 GB MBOX file.
- **Resource Cleanup on `asyncio.CancelledError`:**
  - In `dedupper()`: Wrap the `file_tasks` gather and output loop in a `try ... finally:` block that cancels any unfinished child `file_tasks` and always calls `storage.close()` so no SQLite file locks are leaked.
  - In `processFile()` / `MessageDatabase.transaction()`: Let `BaseException` (which includes `asyncio.CancelledError` in Python 3.8+) roll back any uncommitted transaction cleanly before re-raising.
  - In `combinatory.runDedup()`: Explicitly re-raise `asyncio.CancelledError` (`except asyncio.CancelledError: raise`) before the generic `except Exception:` block so cancellation is not swallowed as a failed plan.
  - In `TbDedupRunner`:
    - Add `operation_cancelled = Signal(str)` signal.
    - In `deduplicate_selected()`, cancel all child `dedup_workers` inside `except asyncio.CancelledError:` before emitting `operation_cancelled.emit("Deduplication cancelled by user.")`.
    - In `MainWindow.on_operation_cancelled(msg)`: Restore button states (`btn_search` enabled, `btn_dedup` enabled if checked folders exist, `btn_move` enabled if prior results exist, `btn_cancel` disabled) and update the progress bar labels to indicate `"Cancelled"`.

---

## 6. Verification Plan

1. **Unit Tests (`tests/gui/test_gui.py` & `tests/dedup/test_dedup.py`):**
   - Verify `processFile()` and `dedupper()` invoke `plan_progress_callback` and `file_progress_callback` with expected values.
   - Verify `MainWindow` updates `progress_overall`, `progress_plan`, and `progress_file` (including indeterminate `total == 0` and $>2\text{ GB}$ byte-progress scaling) across Scan, Deduplicate, and Move workflows.
   - Verify clicking `btn_cancel` (`do_cancel()`) during an active operation cancels in-flight tasks, closes SQLite storage cleanly, emits `operation_cancelled`, and restores GUI button states.
2. **Quality Gates:**
   - Run `tox` (`py3.14` unit tests with $\ge 92\%$ coverage requirement and `pep8` linter).
