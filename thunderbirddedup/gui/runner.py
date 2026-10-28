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
    ):
        self.location = location
        self.storage_location = storage_location
        self.output_location = output_location
        self.folder_pattern = folder_pattern
        self.limit_pattern = limit_pattern
        self.msg_hash_source = msg_hash_source
        self.hash_storage = hash_storage
        self.yes = yes


class TbDedupRunner(QObject):

    record_log = Signal(str)
    progress_updated = Signal(int, int)
    preplan_complete = Signal(object)
    plan_dedup_updated = Signal(str, object, str)
    dedup_complete = Signal(object, str, str)
    move_complete = Signal(str)

    def __init__(self):
        super().__init__()
        self.preplanner = None
        self.mboxfiles = []
        self.temp_directory = None
        self.reconstructed_root = None
        self.worker_results = []

    async def scan_and_preplan(self, options):
        self.record_log.emit(f"Scanning for MBOX files under {options.location}...")
        location_processor = mbox.MailboxFolder(options.location)
        with time.TimeTracker("File Search"):
            self.mboxfiles = await location_processor.getMboxFiles()

        self.record_log.emit(
            f"Found {len(self.mboxfiles)} MBOX files. Grouping by '{options.folder_pattern}'..."
        )
        self.preplanner = planner_walk.Preplanner(options)
        with time.TimeTracker("Preplanner"):
            await self.preplanner.preplan(self.mboxfiles)

        self.record_log.emit(
            f"Preplanning complete: {self.preplanner.plan_count()} logical folder groups found."
        )
        self.preplan_complete.emit(self.preplanner)
        return self.preplanner

    async def deduplicate_selected(self, options, selected_root_files):
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

        semaphore = asyncio.Semaphore(combinatory.DEFAULT_MAX_CONCURRENT_PLANS)
        completed_count = 0
        dedup_workers = []

        def on_plan_completed():
            nonlocal completed_count
            completed_count += 1
            self.progress_updated.emit(completed_count, total_plans)

        for root_file, plan in selected_plans:
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
            await planner_plan.generate(
                output_directory,
                plan.files,
                plan.combinatory,
            )

            dedup_hash_storage = os.path.join(output_directory, "hash.sqlite")
            use_disk = dedup.source_option_to_boolean(options.msg_hash_source)

            async def _run_single_plan(rf, pl, out_dir, hash_db):
                res_dir, res_plan, res_file = await combinatory.runDedup(
                    out_dir,
                    pl,
                    dedup.dedupper(
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
                    ),
                    counter_update=on_plan_completed,
                    semaphore=semaphore,
                    dedup_hash_storage=hash_db,
                    use_disk_data_for_hash=use_disk,
                )
                status = "Deduplicated" if res_file is not None else "Failed"
                self.plan_dedup_updated.emit(rf, res_plan, status)
                return (res_dir, res_plan, res_file)

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
