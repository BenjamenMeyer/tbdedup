# GUI Consolidation & Architecture Proposal

## 1. Review of Existing Prototypes (`gui` through `gui5`)

Across your five prototypes, a clear picture emerges of the workflow and UI components you were aiming for:

```text
+-------------------------------------------------------------------------+
| Source Path: [ /home/.../Inbox.sbd          ] [ Select... ] [ Search ]  |
| Work/Storage:[ /home/.../run-01             ] [ Select... ]             |
| Output Tree: [ /home/.../reconstructed      ] [ Select... ]             |
| Folder Split:[ Inbox.sbd/   ]  Hash Source: [ Parsed (Recommended) v ]  |
+-------------------------------------------------------------------------+
| [x] Select All / Deselect All    |  Selected Folder Group Details       |
| +--------------------------------+------------------------------------+ |
| | Logical Folder Groups (Tree)   | Copies Found (ListView):           | |
| | [x] Inbox.sbd (Root)           |  - .../Inbox.sbd/Activities        | |
| |   [x] Activities (18 copies)   |  - .../Kids.sbd/Inbox.sbd/Activ... | |
| |     [x] Scouts (18 copies)     |                                    | |
| |       [x] Kids (19 copies)     | Stats / Status:                    | |
| |   [x] Merchants (18 copies)    |  - Source Files: 18 (42.3 MB)      | |
| |   [ ] Archive (1 copy)         |  - Unique Messages: 1,240 / 22,320 | |
| |                                |  - Deduplicated Size: 2.35 MB      | |
| +--------------------------------+------------------------------------+ |
| Overall Progress: [=====================>               ] 64% (496/775) |
| [ 1. Preplan (Group) ] [ 2. Deduplicate Selected ] [ 3. Move to Output ]|
+-------------------------------------------------------------------------+
| Activity Log:                                                           |
| [INFO] Found 14,173 MBOX files across 775 logical folder groups...      |
+-------------------------------------------------------------------------+
```

### What Worked and What Was Missing in Each Prototype
1. **`gui` (PySide6 + `asyncslot`):**
   - *Strengths:* Clean native desktop look, `QFileDialog`, `QTreeView`, `QTextEdit` log viewer, and `TbDedupRunner` (`runner.py`) calling `MailboxFolder.getMboxFiles()` and `Preplanner`.
   - *Gaps:* Used third-party `asyncslot` (which is broken on Python 3.14 because `asyncio.unix_events.DefaultEventLoopPolicy` was removed), and hadn't yet populated `QTreeView` with the `Preplanner` results or step controls.
2. **`gui2` & `gui3` (PyQt5 + `QThreadPool` / `asyncslot`):**
   - *Strengths:* Added `QProgressBar` and `QStatusBar`, and explored running `MailboxFolder.getMboxFiles()` in a `QRunnable`.
   - *Gaps:* Mixing `QRunnable` (which expects a synchronous `def run(self):`) with `async def run(self):` meant Qt's thread pool created an unawaited coroutine object instead of executing it.
3. **`gui4` (Tkinter + `aiotkinter`):**
   - *Strengths:* Implemented checkbox tree selection (`TtkCheckList` in `tview.py`) so individual folders/files could be checked or unchecked before generating a plan.
   - *Gaps:* Early-1990s X11 appearance; `aiotkinter` is broken on Python 3.14; walked raw directories instead of grouping recursive copies via `Preplanner`.
4. **`gui5` (Kivy):**
   - *Strengths:* Custom directory chooser popup (`SelectDirectory` in `filedialog.py`).
   - *Gaps:* Non-native desktop look/feel, requires external SDL2/PIL/pygame text providers (which caused `sys.exit(1)` on import in headless/test environments), and filtered for `.mbox` extensions (missing Thunderbird's extensionless MBOX files).

---

## 2. Recommended Framework: **PySide6 + Built-in `PySide6.QtAsyncio`**

**Why PySide6 (`6.12.0`, already installed in `.tox/py3.14`) is the best fit:**
1. **First-Party `asyncio` Support (`PySide6.QtAsyncio`):**
   - Starting in PySide6 6.6+, Qt provides official `PySide6.QtAsyncio` out of the box (`import PySide6.QtAsyncio as QtAsyncio` and `QtAsyncio.run(...)`).
   - We verified that `PySide6.QtAsyncio` works natively on **Python 3.14** in your environment—eliminating `asyncslot`, `aiotkinter`, `kivy`, and `PyQt5` completely!
   - Any `async def` method on `MainWindow` or controller can be scheduled directly via `asyncio.ensure_future(...)` or `QtAsyncio.run(...)` without freezing the UI or fighting thread pools.
2. **Rich Native Desktop Widgets:**
   - **`QTreeView` + `QStandardItemModel` with `Qt.ItemIsUserCheckable` (`Qt.ItemIsAutoTristate`):** Gives you native tri-state checkboxes on every folder node in the tree (checking/unchecking a parent `.sbd` folder automatically checks/unchecks its children, or you can select individual folders) plus multi-column stats (`Copies`, `Source Size`, `Unique Msgs`, `Dedup Size`, `Status`).
   - **`QListView` / `QTableWidget` (Detail Pane):** Clicking any logical folder in the `QTreeView` shows all 18–20 recursive source file paths mapped to that folder in the right-hand `QListView` (with checkboxes if you even want to exclude a specific recursive copy!).
   - **`QComboBox` (Drop-Downs):** Select Hash Source (`parsed` vs. `disk`) and Folder Split Pattern (`Inbox.sbd/`).
   - **`QProgressBar`, `QSplitter`, `QTextEdit` Log Pane, and `QStatusBar`.**
3. **Headless Unit Testing (`QT_QPA_PLATFORM=offscreen`):**
   - PySide6 supports `QT_QPA_PLATFORM=offscreen` out of the box on Linux, allowing `pytest` under `tox` to instantiate and unit-test the entire GUI and controller headlessly without needing an X11/Wayland display or failing coverage!

---

## 3. Proposed Step-by-Step GUI Workflow

1. **Configure Paths & Options (Top Bar):**
   - **Source Location:** Path to Thunderbird mail folder (e.g., `.../Mail/Local Folders/Inbox.sbd`) via text box or `Select...` (`QFileDialog`).
   - **Working / Storage Directory:** Optional path for temporary symlink staging & `hash.sqlite` files.
   - **Reconstructed Output Directory:** Target directory for the clean reconstructed folder tree.
   - **Drop-Downs / Inputs:** Hash Source (`QComboBox`: `parsed` [default] or `disk`) and Folder Pattern (`QLineEdit`: `Inbox.sbd/`).
2. **Step 1 — Search & Preplan (`[ 1. Scan & Group Folders ]`):**
   - Runs `MailboxFolder.getMboxFiles()` and `Preplanner.preplan()` asynchronously.
   - Populates the **`QTreeView`** with the clean hierarchical folder structure (`Inbox.sbd` $\rightarrow$ `Activities` $\rightarrow$ `Scouts` $\rightarrow$ `Kids`), showing the number of duplicate MBOX files and total size for each logical folder.
   - Every node in the `QTreeView` has a **checkbox** (checked by default, with `Select All` / `Deselect All` buttons) so you can choose to process all 775 folders or focus on a specific subset of folders.
   - Selecting any folder in the `QTreeView` populates the right-hand **`QListView`** with the exact disk paths of the recursive copies for that folder.
3. **Step 2 — Deduplicate Selected (`[ 2. Deduplicate Checked Folders ]`):**
   - For only the **checked** logical folders in the `QTreeView`, creates the staging symlinks (`planner_plan.generate`) and runs `dedup.dedupper` (with bounded concurrency via `asyncio.Semaphore`).
   - Live-updates each folder row in the `QTreeView` as it finishes (`Total Msgs`, `Unique Msgs`, `Dedup Size`, `Status = Done`) and updates the overall `QProgressBar`.
   - Displays the summary metrics (messages indexed vs. unique kept, original size vs. deduplicated size, space saved).
4. **Step 3 — Confirm & Reconstruct (`[ 3. Move to Reconstructed Tree ]`):**
   - Presents a confirmation dialog (`QMessageBox.question`) showing the summary of deduplicated folders, message counts, and disk savings.
   - Upon confirmation, runs `move_dedup_mbox` for the completed plans into the clean reconstructed folder tree, updates each row's status to `Moved`, and writes `combinatory_operation.json`.

---

## 4. Cleanup & Consolidation Plan
1. Remove `thunderbirddedup/gui2`, `thunderbirddedup/gui3`, `thunderbirddedup/gui4`, `thunderbirddedup/gui5`, and untracked `tools/test_kivy_filechooser.py`.
2. Update `setup.py`:
   - Keep only `PySide6` in `REQUIRES` (removing `aiotkinter`, `kivy`, `asyncslot`).
   - Consolidate `console_scripts` to `tb-dedup = thunderbirddedup.cmd:main` and `tb-dedup-gui = thunderbirddedup.gui:main`.
3. Implement the consolidated **PySide6 + `PySide6.QtAsyncio`** application in `thunderbirddedup/gui/` (`__init__.py`, `app.py`, `runner.py`).
4. Add headless unit tests (`tests/gui/test_gui.py` using `QT_QPA_PLATFORM=offscreen`) so `tox` passes both `py3.14` ($\ge 92\%$ coverage across the entire repository, including `gui`!) and `pep8`.
