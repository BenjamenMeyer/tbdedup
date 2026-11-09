"""
Copyright 2023-2026 Benjamen R. Meyer

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import asyncio
import copy
import datetime
import logging
import os
import os.path
import tempfile
import traceback

from PySide6.QtCore import (
    QObject,
    Signal,
)

from thunderbirddedup import (
    combinatory,
    dedup,
    mbox,
)
from thunderbirddedup.planner import (
    keys as planner_keys,
    plan as planner_plan,
    walk as planner_walk,
)
from thunderbirddedup.utils import (
    file_tracker,
    json,
    time,
)

LOG = logging.getLogger(__name__)


class TbDedupOptions(object):

    def __init__(
        self,
        location,
        storage_location=None,
        output_location=None,
        folder_pattern="Inbox.sbd/",
        limit_pattern=None,
        msg_hash_source="parsed",
        hash_storage=None,
        yes=False,
        max_open_files=None,
    ):
        self.location = location
        self.storage_location = storage_location
        self.output_location = output_location
        self.folder_pattern = folder_pattern
        self.limit_pattern = limit_pattern
        self.msg_hash_source = msg_hash_source
        self.hash_storage = hash_storage
        self.yes = yes
        self.max_open_files = max_open_files


class TbDedupRunner(QObject):

    record_log = Signal(str)
    progress_updated = Signal(int, int)
    overall_progress_updated = Signal(int, int, str)
    copy_progress_updated = Signal(int, int, str)
    file_progress_updated = Signal(int, int, str)
    write_progress_updated = Signal(int, int, str)
    plan_live_status_updated = Signal(str, str, str)
    preplan_complete = Signal(object)
    plan_dedup_updated = Signal(str, object, str)
    dedup_complete = Signal(object, str, str)
    move_complete = Signal(str)
    operation_cancelled = Signal(str)

    def __init__(self):
        super().__init__()
        self.preplanner = None
        self.mboxfiles = []
        self.temp_directory = None
        self.reconstructed_root = None
        self.worker_results = []

    async def scan_and_preplan(self, options):
        try:
            combinatory.ensure_max_open_files()
            self.record_log.emit(f"Scanning for MBOX files under {options.location}...")
            self.overall_progress_updated.emit(
                0, 0, f"Scanning directory tree under {options.location}..."
            )
            await asyncio.sleep(0)
            location_processor = mbox.MailboxFolder(options.location)
            with time.TimeTracker("File Search"):
                self.mboxfiles = await location_processor.getMboxFiles()

            total_files = len(self.mboxfiles)
            self.record_log.emit(
                f"Found {total_files} MBOX files. Grouping by '{options.folder_pattern}'..."
            )
            self.preplanner = planner_walk.Preplanner(options)

            def on_preplan_progress(done, total):
                self.overall_progress_updated.emit(
                    done,
                    max(total, 1),
                    f"Grouping MBOX files: {done:,} / {total:,}",
                )

            with time.TimeTracker("Preplanner"):
                await self.preplanner.preplan(
                    self.mboxfiles,
                    progress_callback=on_preplan_progress,
                )

            plan_count = self.preplanner.plan_count()
            self.overall_progress_updated.emit(
                max(total_files, 1),
                max(total_files, 1),
                f"Scan complete: {plan_count} logical folder groups ({total_files:,} MBOX files)",
            )
            self.record_log.emit(
                f"Preplanning complete: {plan_count} logical folder groups found."
            )
            self.preplan_complete.emit(self.preplanner)
            return self.preplanner
        except asyncio.CancelledError:
            self.record_log.emit("Scan cancelled by user.")
            self.operation_cancelled.emit("Scan cancelled by user.")
            raise

    async def deduplicate_selected(self, options, selected_root_files):
        combinatory.ensure_max_open_files()
        if self.preplanner is None or not selected_root_files:
            self.record_log.emit("No logical folder groups selected for deduplication.")
            return []

        selected_set = set(selected_root_files)
        selected_plans = [
            (root_file, plan)
            for root_file, plan in self.preplanner.plans()
            if root_file in selected_set
        ]
        total_plans = len(selected_plans)
        if total_plans == 0:
            self.record_log.emit("No matching folder plans found.")
            return []

        utc_time = datetime.datetime.utcnow()
        self.temp_directory = tempfile.mkdtemp(
            prefix=utc_time.strftime("%Y%m%d_%H%M%S"),
            suffix="thunderbirddedup",
            dir=options.storage_location,
        )
        self.reconstructed_root = (
            options.output_location or
            os.path.join(self.temp_directory, "reconstructed")
        )
        self.record_log.emit(f"Working directory: {self.temp_directory}")
        self.progress_updated.emit(0, total_plans)
        self.overall_progress_updated.emit(
            0, total_plans, f"Folder Groups: 0 / {total_plans} (0.0%)"
        )
        self.copy_progress_updated.emit(0, 1, "Folder Copies: Waiting...")
        self.file_progress_updated.emit(0, 1000, "Current Copy Read: Waiting...")
        self.write_progress_updated.emit(0, 1, "Deduplicated Output Write: Waiting...")

        if getattr(options, "max_open_files", None) is not None:
            file_tracker.set_max_open_files(options.max_open_files)

        semaphore = asyncio.Semaphore(1)
        completed_count = 0
        dedup_workers = []

        def make_plan_completed(rf):
            def _on_plan_completed():
                nonlocal completed_count
                completed_count += 1
                pct = (completed_count / total_plans) * 100.0
                self.progress_updated.emit(completed_count, total_plans)
                self.overall_progress_updated.emit(
                    completed_count,
                    total_plans,
                    f"Folder Groups: {completed_count} / {total_plans} ({pct:.1f}%) — {rf}",
                )
            return _on_plan_completed

        try:
            for root_file, plan in selected_plans:
                total_copies = len(plan.files)
                self.plan_live_status_updated.emit(
                    root_file,
                    f"0 / {total_copies}",
                    "Queued",
                )
                output_directory = combinatory.get_plan_output_directory(
                    options.folder_pattern,
                    self.temp_directory,
                    root_file,
                )
                os.makedirs(output_directory, mode=0o755, exist_ok=True)
                plan.combinatory = {
                    planner_keys.plan_pattern: options.limit_pattern,
                    planner_keys.plan_location: {
                        planner_keys.plan_source: copy.deepcopy(root_file),
                        planner_keys.plan_output: output_directory,
                    },
                    planner_keys.plan_file_map: {},
                }

                dedup_hash_storage = os.path.join(output_directory, "hash.sqlite")
                use_disk = dedup.source_option_to_boolean(options.msg_hash_source)

                async def _run_single_plan(rf, pl, out_dir, hash_db):
                    short_rf = os.path.basename(rf) or rf
                    num_copies = len(pl.files)

                    # Check if already completed on disk in existing run directory
                    existing_plan, existing_mbox = combinatory.check_plan_completed_on_disk(out_dir)
                    if existing_plan is not None and existing_mbox is not None:
                        pl.combinatory = existing_plan.get("combinatory", pl.combinatory)
                        make_plan_completed(rf)()
                        self.plan_dedup_updated.emit(rf, pl, "Deduplicated")
                        self.record_log.emit(f"Reusing existing deduplicated MBOX for {short_rf}")
                        return (out_dir, pl, existing_mbox)

                    try:
                        async with semaphore:
                            await planner_plan.generate(
                                out_dir,
                                pl.files,
                                pl.combinatory,
                            )

                            def on_copy_progress(done, total, fname):
                                bname = os.path.basename(fname) if fname else ""
                                suffix = f" ({bname})" if bname else ""
                                self.copy_progress_updated.emit(
                                    done,
                                    max(total, 1),
                                    f"Folder Copies [{short_rf}]: {done} / {total}{suffix}",
                                )
                                self.plan_live_status_updated.emit(
                                    rf,
                                    f"{done} / {total}",
                                    f"Indexing {done}/{total}",
                                )

                            def on_file_progress(fname, cur_bytes, tot_bytes, msg_count):
                                permille = (
                                    int((cur_bytes / tot_bytes) * 1000)
                                    if tot_bytes > 0
                                    else 1000
                                )
                                pct = (
                                    (cur_bytes / tot_bytes) * 100.0
                                    if tot_bytes > 0
                                    else 100.0
                                )
                                bname = os.path.basename(fname)
                                self.file_progress_updated.emit(
                                    permille,
                                    1000,
                                    f"Reading {bname}: {combinatory.format_bytes(cur_bytes)} / "
                                    f"{combinatory.format_bytes(tot_bytes)} ({pct:.1f}%) — {msg_count:,} msgs",
                                )

                            def on_write_progress(written, total_unique):
                                self.write_progress_updated.emit(
                                    written,
                                    max(total_unique, 1),
                                    f"Writing Deduplicated MBOX [{short_rf}]: {written:,} / {total_unique:,} unique msgs",
                                )
                                if total_unique > 0:
                                    self.plan_live_status_updated.emit(
                                        rf,
                                        f"{num_copies} / {num_copies}",
                                        f"Writing {written:,}/{total_unique:,}",
                                    )

                            dedup_coro = dedup.dedupper(
                                [
                                    os.path.join(
                                        pl.combinatory[planner_keys.plan_location][planner_keys.plan_output],
                                        link_file,
                                    )
                                    for link_file in pl.combinatory[planner_keys.plan_file_map].keys()
                                ],
                                hash_db,
                                use_disk_data_for_hash=use_disk,
                                output_base_path=pl.combinatory[planner_keys.plan_location][planner_keys.plan_output],
                                copy_progress_callback=on_copy_progress,
                                file_progress_callback=on_file_progress,
                                write_progress_callback=on_write_progress,
                            )
                            try:
                                res_dir, res_plan, res_file = await combinatory.runDedup(
                                    out_dir,
                                    pl,
                                    dedup_coro,
                                    counter_update=make_plan_completed(rf),
                                    semaphore=None,
                                    dedup_hash_storage=hash_db,
                                    use_disk_data_for_hash=use_disk,
                                )
                            except Exception:
                                dedup_coro.close()
                                raise
                            if res_file is not None:
                                status = "Deduplicated"
                            else:
                                err = (res_plan.combinatory or {}).get(planner_keys.plan_stats, {}).get("error", "Processing failed")
                                status = f"Failed ({err})"
                                self.record_log.emit(f"ERROR: Plan failed for {short_rf}: {err}")
                            self.plan_dedup_updated.emit(rf, res_plan, status)
                            return (res_dir, res_plan, res_file)
                    except asyncio.CancelledError:
                        raise
                    except Exception as ex:
                        err_str = f"{type(ex).__name__}: {ex}"
                        LOG.exception(f"Unhandled error while deduplicating {rf}: {ex}")
                        self.record_log.emit(f"ERROR [{short_rf}]: {err_str}")
                        if pl.combinatory is not None:
                            stats = pl.combinatory.get(planner_keys.plan_stats, {})
                            stats["error"] = err_str
                            stats["traceback"] = traceback.format_exc()
                            pl.combinatory[planner_keys.plan_stats] = stats
                        self.plan_dedup_updated.emit(rf, pl, f"Failed ({err_str})")
                        make_plan_completed(rf)()
                        return (out_dir, pl, None)

                dedup_workers.append(
                    asyncio.create_task(
                        _run_single_plan(
                            root_file,
                            plan,
                            output_directory,
                            dedup_hash_storage,
                        )
                    )
                )

            self.worker_results = list(await asyncio.gather(*dedup_workers))
            self.record_log.emit(
                f"Completed deduplicating {len(self.worker_results)} folder groups."
            )
            self.dedup_complete.emit(
                self.worker_results,
                self.temp_directory,
                self.reconstructed_root,
            )
            return self.worker_results
        except asyncio.CancelledError:
            for w_task in dedup_workers:
                if not w_task.done():
                    w_task.cancel()
            if dedup_workers:
                await asyncio.gather(*dedup_workers, return_exceptions=True)
            self.record_log.emit("Deduplication cancelled by user.")
            self.operation_cancelled.emit("Deduplication cancelled by user.")
            raise
        except Exception as ex:
            LOG.exception(f"Fatal error during deduplication: {ex}")
            self.record_log.emit(f"FATAL ERROR during deduplication: {ex}")
            completed = []
            for w_task in dedup_workers:
                if w_task.done() and not w_task.cancelled() and w_task.exception() is None:
                    completed.append(w_task.result())
            self.worker_results = completed
            self.dedup_complete.emit(
                self.worker_results,
                self.temp_directory,
                self.reconstructed_root,
            )
            raise
        finally:
            all_closed, leaks = file_tracker.verify_all_closed(log_leaks=True)
            if not all_closed:
                leak_sample = ", ".join(
                    f"{os.path.basename(f['path'])} ({f['caller']})"
                    for f in leaks[:5]
                )
                if len(leaks) > 5:
                    leak_sample += f" (+{len(leaks) - 5} more)"
                LOG.warning(
                    f"Unclosed files detected after deduplication run: {leak_sample}"
                )
                self.record_log.emit(
                    f"WARNING: {len(leaks)} unclosed file(s) detected: {leak_sample}"
                )
            else:
                LOG.info("All files verified closed.")
                self.record_log.emit("All files verified closed.")

    async def move_results(
        self,
        options,
        worker_results=None,
        reconstructed_root=None,
    ):
        results = (
            worker_results
            if worker_results is not None
            else self.worker_results
        )
        target_root = (
            reconstructed_root or
            options.output_location or
            self.reconstructed_root
        )
        self.record_log.emit(
            f"Moving deduplicated MBOX files into {target_root}..."
        )
        total = len(results)
        self.progress_updated.emit(0, total)
        self.overall_progress_updated.emit(
            0, max(total, 1), f"Moving Folder Groups: 0 / {total}"
        )

        try:
            for idx, (_, wr_plan, wr_mboxfile) in enumerate(results, start=1):
                await combinatory.move_dedup_mbox(
                    target_root,
                    options.folder_pattern,
                    wr_plan,
                    wr_mboxfile,
                )
                root_file = wr_plan.combinatory[planner_keys.plan_location][planner_keys.plan_source]
                status = "Moved" if wr_mboxfile is not None else "Failed"
                self.plan_dedup_updated.emit(root_file, wr_plan, status)
                self.progress_updated.emit(idx, total)
                self.overall_progress_updated.emit(
                    idx,
                    max(total, 1),
                    f"Moving Folder Groups: {idx} / {total} — {root_file}",
                )
                await asyncio.sleep(0)

            output_base = (
                self.temp_directory
                if options.storage_location is None
                else options.storage_location
            )
            data_output_file = os.path.join(
                output_base,
                "combinatory_operation.json",
            )
            json.dump_to_file(data_output_file, self.preplanner)
            self.record_log.emit(
                f"Move completed. Operation record written to {data_output_file}"
            )
            self.move_complete.emit(data_output_file)
            return data_output_file
        except asyncio.CancelledError:
            self.record_log.emit("Move operation cancelled by user.")
            self.operation_cancelled.emit("Move operation cancelled by user.")
            raise

    def discover_disk_results(self, storage_location):
        return combinatory.discover_disk_results(storage_location)

    def inspect_storage_directory(self, storage_location):
        return combinatory.inspect_storage_directory(storage_location)

    def cleanup_storage_directory(self, storage_location, remove_working_files=False):
        return combinatory.cleanup_storage_directory(
            storage_location, remove_working_files=remove_working_files
        )

    def sync_with_disk_data(self, storage_location, folder_pattern="Inbox.sbd/"):
        if not storage_location or not os.path.isdir(storage_location) or not self.preplanner:
            return 0
        plans_by_root = dict(self.preplanner.plans())
        recovered_count = 0
        recovered_results = []
        for root_file, plan in plans_by_root.items():
            out_dir = combinatory.get_plan_output_directory(
                folder_pattern,
                storage_location,
                root_file,
            )
            plan_data, mbox_path = combinatory.check_plan_completed_on_disk(out_dir)
            if plan_data is not None and mbox_path is not None:
                plan.combinatory = plan_data.get("combinatory", plan.combinatory)
                recovered_results.append((out_dir, plan, mbox_path))
                self.plan_dedup_updated.emit(root_file, plan, "Deduplicated")
                recovered_count += 1
        if recovered_results:
            self.worker_results = recovered_results
            self.temp_directory = storage_location
            self.record_log.emit(
                f"Discovered {recovered_count} completed folder groups on disk in {storage_location}"
            )
        return recovered_count
