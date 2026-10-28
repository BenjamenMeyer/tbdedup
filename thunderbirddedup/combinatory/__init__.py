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
import contextlib
import copy
import datetime
import logging
import os
import os.path
import resource
import shutil
import tempfile

from thunderbirddedup import (
    db,
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

DEFAULT_MAX_CONCURRENT_PLANS = 32


def format_bytes(num_bytes):
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024.0 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024.0


def get_reconstructed_mbox_path(output_directory, folder_pattern, plan_source):
    norm_output = output_directory.rstrip(os.sep) or os.sep
    norm_pattern = (folder_pattern or "").rstrip("/")
    if (
        norm_pattern and
        os.path.basename(norm_output) == os.path.basename(norm_pattern) and
        plan_source.startswith(folder_pattern)
    ):
        relative_source = plan_source[len(folder_pattern):]
    else:
        relative_source = plan_source.lstrip("/")
    return os.path.join(output_directory, relative_source)


def collect_plan_stats(
    plan,
    output_file,
    dedup_hash_storage=None,
    use_disk_data_for_hash=False,
):
    source_files = len(plan.files)
    source_bytes = sum(
        os.path.getsize(f)
        for f in plan.files
        if os.path.exists(f)
    )
    dedup_bytes = (
        os.path.getsize(output_file)
        if output_file is not None and os.path.exists(output_file)
        else 0
    )
    total_messages = 0
    unique_messages = 0
    if dedup_hash_storage is not None and os.path.exists(dedup_hash_storage):
        storage = db.MessageDatabase(dedup_hash_storage)
        try:
            total_messages = storage.get_total_message_count()
            unique_messages = storage.get_unique_message_count(
                use_disk=use_disk_data_for_hash
            )
        finally:
            storage.close()

    stats = {
        planner_keys.plan_stats_source_files: source_files,
        planner_keys.plan_stats_source_bytes: source_bytes,
        planner_keys.plan_stats_dedup_bytes: dedup_bytes,
        planner_keys.plan_stats_total_messages: total_messages,
        planner_keys.plan_stats_unique_messages: unique_messages,
    }
    plan.combinatory[planner_keys.plan_stats] = stats
    return stats


async def runDedup(
    output_directory,
    plan,
    dedup_task,
    counter_update=None,
    semaphore=None,
    dedup_hash_storage=None,
    use_disk_data_for_hash=False,
):
    try:
        async with (
            semaphore
            if semaphore is not None
            else contextlib.nullcontext()
        ):
            output_file = await dedup_task
        if counter_update is not None:
            counter_update()

        plan.combinatory[planner_keys.plan_location][planner_keys.plan_mbox] = output_file
        collect_plan_stats(
            plan,
            output_file,
            dedup_hash_storage=dedup_hash_storage,
            use_disk_data_for_hash=use_disk_data_for_hash,
        )

        plan_output_filename = os.path.join(
            output_directory,
            "plan_output.json",
        )
        plan.combinatory[planner_keys.plan_location][planner_keys.plan_output_plan] = plan_output_filename

        json.dump_to_file(plan_output_filename, plan)

        return (
            output_directory,
            plan,
            output_file,
        )
    except Exception:
        LOG.exception(f'Failed while carrying out plan for {output_directory}')
        return (
            output_directory,
            plan,
            None,
        )


def get_plan_output_directory(folder_pattern, temp_directory, root_file):
    path_loc = root_file.rfind(folder_pattern)
    path = root_file[path_loc:] if path_loc != -1 else root_file
    final_path = path.replace("/", "_").replace(".sbd", "")
    return os.path.join(
        temp_directory,
        f"{final_path}_Dedup"
    )


def build_summary_report(
    options,
    temp_directory,
    reconstructed_root,
    worker_results,
):
    total_plans = len(worker_results)
    succeeded_plans = sum(
        1 for _, _, mboxfile in worker_results if mboxfile is not None
    )
    failed_plans = total_plans - succeeded_plans

    total_source_files = 0
    total_source_bytes = 0
    total_dedup_bytes = 0
    total_messages = 0
    unique_messages = 0

    for _, plan, _ in worker_results:
        stats = plan.combinatory.get(planner_keys.plan_stats, {})
        total_source_files += stats.get(planner_keys.plan_stats_source_files, 0)
        total_source_bytes += stats.get(planner_keys.plan_stats_source_bytes, 0)
        total_dedup_bytes += stats.get(planner_keys.plan_stats_dedup_bytes, 0)
        total_messages += stats.get(planner_keys.plan_stats_total_messages, 0)
        unique_messages += stats.get(planner_keys.plan_stats_unique_messages, 0)

    saved_bytes = max(0, total_source_bytes - total_dedup_bytes)
    saved_pct = (
        (saved_bytes / total_source_bytes) * 100.0
        if total_source_bytes > 0
        else 0.0
    )
    removed_messages = max(0, total_messages - unique_messages)

    lines = [
        "=" * 72,
        "Thunderbird Deduplication Summary",
        "=" * 72,
        f"Source Location:        {options.location}",
        f"Working Directory:      {temp_directory}",
        f"Reconstructed Target:   {reconstructed_root}",
        f"Source MBOX Files:      {total_source_files}",
        f"Logical Folders (Plans): {total_plans} ({succeeded_plans} succeeded, {failed_plans} failed)",
        f"Messages Indexed:       {total_messages}",
        f"Unique Messages Kept:   {unique_messages} ({removed_messages} duplicates removed)",
        f"Original MBOX Size:     {format_bytes(total_source_bytes)} ({total_source_bytes} bytes)",
        f"Deduplicated MBOX Size: {format_bytes(total_dedup_bytes)} ({total_dedup_bytes} bytes)",
        f"Disk Space Saved:       {format_bytes(saved_bytes)} ({saved_pct:.2f}%)",
        "=" * 72,
    ]
    return "\n".join(lines)


def confirm_move(
    options,
    temp_directory,
    reconstructed_root,
    worker_results,
):
    summary = build_summary_report(
        options,
        temp_directory,
        reconstructed_root,
        worker_results,
    )
    LOG.info(f"\n{summary}")
    print(summary)

    succeeded_plans = sum(
        1 for _, _, mboxfile in worker_results if mboxfile is not None
    )
    if getattr(options, "yes", False):
        LOG.info(
            f"Auto-confirming move of {succeeded_plans} deduplicated MBOX files to {reconstructed_root}"
        )
        return True

    prompt = (
        f"Proceed with moving {succeeded_plans} deduplicated MBOX files "
        f"to '{reconstructed_root}'? [y/N]: "
    )
    try:
        response = input(prompt)
    except EOFError:
        response = ""
    return response.strip().lower() in ("y", "yes")


async def move_dedup_mbox(
    reconstructed_root,
    folder_pattern,
    plan,
    mboxfile,
):
    if mboxfile is None:
        LOG.info(f'No mboxfile specified for {reconstructed_root}')
        return

    plan_source = plan.combinatory[planner_keys.plan_location][planner_keys.plan_source]
    output_mbox_file = get_reconstructed_mbox_path(
        reconstructed_root,
        folder_pattern,
        plan_source,
    )
    source_mbox_file = plan.combinatory[planner_keys.plan_location][planner_keys.plan_mbox]
    parent_dir = os.path.dirname(output_mbox_file)
    if parent_dir:
        os.makedirs(parent_dir, mode=0o755, exist_ok=True)
    LOG.info(f'Moving {source_mbox_file} to {output_mbox_file}')
    shutil.move(source_mbox_file, output_mbox_file)
    plan.combinatory[planner_keys.plan_location][planner_keys.plan_final_mbox] = output_mbox_file


async def combinatory(options, mboxfiles):
    # 1. Run the preplanner and find all the sets of files to deduplicate
    preplan = planner_walk.Preplanner(options)
    with time.TimeTracker("Preplanner"):
        await preplan.preplan(mboxfiles)

    if preplan.plan_count() == 0:
        LOG.info('No data for deduplication')
        return

    # 2. Create a temporary directory to build processing directories under
    utc_time = datetime.datetime.utcnow()
    temp_directory = tempfile.mkdtemp(
        prefix=utc_time.strftime("%Y%m%d_%H%M%S"),
        suffix='thunderbirddedup',
        dir=options.storage_location,
    )
    LOG.info(f'Using Temporary Directory {temp_directory}')

    # 3. For each file set in the preplanner, add a directory under the
    #    temporary directory and add symlinks for each associated file
    LOG.info('Generating dedup plans...')
    dedup_workers = []
    semaphore = asyncio.Semaphore(DEFAULT_MAX_CONCURRENT_PLANS)

    required_file_count = 0

    counters = {
        "completed": 0.0,
        "total": 0.0,
    }

    def counter_update():
        counters['completed'] = counters['completed'] + 1.0
        if counters['total'] > 0:
            percentage = (counters['completed'] / counters['total']) * 100.0
            LOG.info(f'[Combinatory] Progress Report: {percentage:03.02f}')

    with time.TimeTracker("Planning"):
        for root_file, plan in preplan.plans():
            output_directory = get_plan_output_directory(
                options.folder_pattern,
                temp_directory,
                root_file,
            )
            # ensure the directory tree exists
            os.makedirs(output_directory, mode=0o755, exist_ok=True)

            plan.combinatory = {
                planner_keys.plan_pattern: options.limit_pattern,
                planner_keys.plan_location: {
                    # avoid circular references - we only care about the
                    # value here so a deep-copy is okay, and we need to
                    # be able to output it later
                    planner_keys.plan_source: copy.deepcopy(root_file),
                    planner_keys.plan_output: output_directory,
                },
                planner_keys.plan_file_map: {},
            }

            try:
                mapping_file = await planner_plan.generate(
                    output_directory,
                    plan.files,
                    plan.combinatory,
                )
            except planner_plan.GenerationError:
                LOG.exception(f'Failed to generate data in {output_directory}')
                return

            # plan.combinatory[planner_keys.plan_file_map].keys() == symlinks
            # plan.combinatory[planner_keys.plan_map_file] = mapping.json file
            # increase required files:
            #   - output MBOX file
            #   - input SqliteDB
            #   - reporting
            #   - number of links in the data set
            required_file_count += 3 + plan.combinatory[planner_keys.plan_counter]

            # 4. Split out a async worker for each directory to deduplicate
            #    each directory data set
            dedup_hash_storage = os.path.join(
                output_directory,
                "hash.sqlite",
            )
            use_disk_data_for_hash = dedup.source_option_to_boolean(
                options.msg_hash_source
            )
            dedup_task = asyncio.create_task(
                runDedup(
                    output_directory,
                    plan,
                    dedup.dedupper(
                        # convert the link paths from just filenames to full paths
                        [
                            os.path.join(
                                plan.combinatory[planner_keys.plan_location][planner_keys.plan_output],
                                link_file,
                            )
                            for link_file in plan.combinatory[planner_keys.plan_file_map].keys()
                        ],
                        dedup_hash_storage,
                        use_disk_data_for_hash=use_disk_data_for_hash,
                        output_base_path=plan.combinatory[planner_keys.plan_location][planner_keys.plan_output],
                    ),
                    counter_update=counter_update,
                    semaphore=semaphore,
                    dedup_hash_storage=dedup_hash_storage,
                    use_disk_data_for_hash=use_disk_data_for_hash,
                )
            )
            dedup_workers.append(dedup_task)

    counters['total'] = len(dedup_workers)
    counters['completed'] = -1.0
    counter_update()

    # Ensure there are enough file handles to support the work
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    new_hard_limit = (
        required_file_count + 200
        if hard_limit <= required_file_count
        else hard_limit
    )
    new_soft_limit = (
        required_file_count + 100
        if soft_limit <= required_file_count
        else soft_limit
    )
    LOG.info(f'Attempting to raise Open File Limit from (hard={hard_limit}, soft={soft_limit}) to (hard={new_hard_limit}, soft={new_soft_limit})')
    try:
        resource.setrlimit(
            resource.RLIMIT_NOFILE,
            (min(new_soft_limit, hard_limit), hard_limit),
        )
    except Exception:
        LOG.exception("Failed to set new Open File Limit")
        LOG.error("Unable to adjust open file limit")
        return

    LOG.info(f'Waiting on {len(dedup_workers)} dedup tasks to complete')
    with time.TimeTracker("Deduplicator"):
        worker_results = await asyncio.gather(*dedup_workers)
    LOG.info('Dedup Workers completed')

    # 5. Reconstruct clean Thunderbird folder tree after summary & confirmation
    reconstructed_root = (
        getattr(options, "output_location", None) or
        os.path.join(temp_directory, "reconstructed")
    )
    if confirm_move(options, temp_directory, reconstructed_root, worker_results):
        move_workers = []
        LOG.info(f'Moving deduplicated MBOX files into {reconstructed_root}')

        for wr_output_directory, wr_plan, wr_mboxfile in worker_results:
            move_task = asyncio.create_task(
                move_dedup_mbox(
                    reconstructed_root,
                    options.folder_pattern,
                    wr_plan,
                    wr_mboxfile,
                ),
            )
            move_workers.append(move_task)

        LOG.info(f'Waiting on {len(move_workers)} to move the files')
        with time.TimeTracker("Mover"):
            move_worker_results = await asyncio.gather(*move_workers)
        LOG.info('Move Workers completed')
    else:
        LOG.info(
            f'Move declined; deduplicated MBOX files remain in {temp_directory}'
        )

    # finally write the completed operation under the output directory
    data_output_file = os.path.join(
        temp_directory
        if options.storage_location is None
        else options.storage_location,
        "combinatory_operation.json",
    )
    json.dump_to_file(data_output_file, preplan)


async def asyncCombinatory(options):
    locationProcessor = mbox.MailboxFolder(options.location)
    with time.TimeTracker("File Search"):
        mboxfiles = await locationProcessor.getMboxFiles()
    with time.TimeTracker("Full Operation"):
        await combinatory(options, mboxfiles)
