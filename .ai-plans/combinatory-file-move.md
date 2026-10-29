# Combinatory File Move & Folder Reconstruction Plan (`tb-dedup do`)

## Overview
Complete Step 5 (`move_dedup_mbox`) in `thunderbirddedup/combinatory/__init__.py` so that deduplicated MBOX files generated during a `tb-dedup do` (`combinatory`) run are properly placed into a clean, Thunderbird-compatible folder hierarchy (following `comm-central` `nsMsgBrkMBoxStore` conventions) and recorded in `combinatory_operation.json`.

*(See `.ai-plans/thunderbird-mbox-reference.md` for authoritative Thunderbird storage specifications.)*

---

## Current Pipeline (Steps 1–4)
When running:
```bash
tb-dedup do --location "/path/to/Thunderbird/.../Inbox.sbd" --storage-location "run-0110"
```
1. **Step 1 (Preplan):** `Preplanner` (`thunderbirddedup/planner/walk.py`) finds all MBOX files under `options.location` and groups them by their suffix starting at the *last* occurrence of `options.folder_pattern` (default `"Inbox.sbd/"`).
   - Example key (`root_file` / `plan_source`): `"Inbox.sbd/Activities"` or `"Inbox.sbd/Activities.sbd/Scouts"`.
2. **Step 2 (Temp Directory):** Creates a temporary directory inside `options.storage_location` (e.g., `run-0110/20241122_230001...thunderbirddedup`).
3. **Step 3 (Plan Generation):** For each group (`root_file`), creates a subdirectory (e.g., `Inbox_Activities_Dedup`), symlinks all duplicate MBOX files (`000001.mbox` ... `000018.mbox`), and writes `mapping.json`.
4. **Step 4 (Deduplication):** Runs `dedup.dedupper` (`thunderbirddedup/dedup/__init__.py`) on each group's symlinks, producing:
   - `plan.combinatory["location"]["mbox"]` = `"run-0110/.../Inbox_Activities_Dedup/20241122_..._deduplicated.mbox"`
   - `plan_output.json` inside that folder.

---

## Current State of Step 5 (`move_dedup_mbox`)
In `thunderbirddedup/combinatory/__init__.py` (lines 224–256):
```python
    async def move_dedup_mbox(output_directory, plan, mboxfile):
        if mboxfile is None:
            LOG.info(f'No mboxfile specified for {output_directory}')
            return

        target_directory = os.path.join(
            output_directory,
            plan.combinatory[planner_keys.plan_location][planner_keys.plan_source]
        )
        output_mbox_file = f"{target_directory}_Dedup"
        source_mbox_file = plan.combinatory[planner_keys.plan_location][planner_keys.plan_mbox]
        LOG.info(f'Copying {source_mbox_file} to {output_mbox_file}')
```

---

## Issues to Resolve (Updated with Thunderbird Storage Specifications)

### 1. Clean `.sbd` Hierarchy Reconstruction (No `Inbox.sbd/Inbox.sbd` Duplication or `_Dedup` Suffix)
- In Thunderbird's local MBOX store (`nsMsgBrkMBoxStore`), a folder with subfolders has three entries:
  - `<FolderName>` (the extensionless MBOX file)
  - `<FolderName>.msf` (Mork index cache—regenerated automatically by Thunderbird when omitted)
  - `<FolderName>.sbd/` (subdirectory containing child MBOX files)
- When `options.location` is `/home/.../Mail/Local Folders/Inbox.sbd` and `plan_source` is `"Inbox.sbd/Activities.sbd/Scouts"`, `os.path.join(options.location, plan_source)` previously produced:
  `/home/.../Mail/Local Folders/Inbox.sbd/Inbox.sbd/Activities.sbd/Scouts_Dedup`
- **Clean Reconstruction Strategy:**
  - Provide an optional `--output-location` (`-ol`) CLI argument on `tb-dedup do` (defaulting to `<temp_directory>/reconstructed`).
  - Reconstruct the canonical folder hierarchy (`Inbox.sbd/Activities`, `Inbox.sbd/Activities.sbd/Scouts`, etc.) inside the reconstructed root directory **without** `_Dedup` suffixes on the final MBOX filenames, **without** any of the 19 recursive `Kids.sbd/Inbox.sbd/...` loops, and **without** copying stale `.msf` files.
  - If the target `output_directory` already ends with `folder_pattern.rstrip('/')` (e.g., `Inbox.sbd`), strip the leading `folder_pattern` from `plan_source` so `Inbox.sbd/` is never doubled.
  - Ensure all parent `.sbd` directories exist before moving each MBOX file: `os.makedirs(os.path.dirname(output_mbox_file), exist_ok=True)`.

### 2. Summary Report & Confirmation Prompt Before Moving (`shutil.move`)
- After Step 4 (`dedupper` workers) completes and before Step 5 (`move_dedup_mbox`) moves the files:
  - Compute and display a summary of what was found and deduplicated:
    - Source location, working directory, and target reconstructed directory
    - Total source MBOX files scanned and logical folder plans processed (succeeded vs. failed)
    - Total messages indexed vs. unique messages retained across all folders
    - Total original MBOX size vs. deduplicated MBOX size (and disk space reduction)
  - Prompt the user for confirmation (`Proceed with moving deduplicated MBOX files to <target_dir>? [y/N]: `), with an optional `--yes` (`-y`) CLI flag to auto-confirm for non-interactive runs.
  - If confirmed, move (`shutil.move`) each deduplicated `<timestamp>_deduplicated.mbox` file into its canonical path in the reconstructed folder tree. If declined, leave the deduplicated MBOX files in their per-plan work directories and still write `combinatory_operation.json`.

### 3. Record Final Destination & Verification Metrics in `combinatory_operation.json`
- Add `plan_final_mbox = "final_mbox"` in `thunderbirddedup/planner/keys.py` and store `output_mbox_file` in `plan.combinatory[planner_keys.plan_location]` when moved so `combinatory_operation.json` has a complete audit trail from all source files $\rightarrow$ symlinks $\rightarrow$ deduplicated MBOX $\rightarrow$ final reconstructed folder path.

### 4. File Handle Limit Accumulation & Bounded Concurrency (Line 159)
- Fix `required_file_count` accumulation (`+=` instead of `=`) in `thunderbirddedup/combinatory/__init__.py` and bound concurrent `runDedup` tasks with an `asyncio.Semaphore` so file descriptor usage stays well within OS limits.
