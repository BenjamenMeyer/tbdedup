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
import traceback

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


def ensure_max_open_files(target_limit=524288):
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        new_soft = min(hard, max(soft, target_limit))
        if new_soft > soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (new_soft, hard))
            LOG.info(
                f"Raised open file limit from soft={soft} to soft={new_soft} (hard={hard})"
            )
            return new_soft
        return soft
    except Exception as ex:
        LOG.warning(f"Unable to adjust open file limit: {ex}")
        return None


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
    except asyncio.CancelledError:
        raise
    except Exception as ex:
        err_msg = f"{type(ex).__name__}: {ex}"
        tb = traceback.format_exc()
        LOG.exception(f'Failed while carrying out plan for {output_directory}: {err_msg}')
        if plan.combinatory is not None:
            stats = plan.combinatory.get(planner_keys.plan_stats, {})
            stats["error"] = err_msg
            stats["traceback"] = tb
            plan.combinatory[planner_keys.plan_stats] = stats
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


def check_plan_completed_on_disk(output_directory):
    if not output_directory or not os.path.isdir(output_directory):
        return None, None
    plan_json = os.path.join(output_directory, "plan_output.json")
    if not os.path.exists(plan_json):
        return None, None
    try:
        plan_data = json.load_from_file(plan_json)
        mbox_path = (
            plan_data.get("combinatory", {})
            .get(planner_keys.plan_location, {})
            .get(planner_keys.plan_mbox)
        )
        if mbox_path and os.path.exists(mbox_path):
            return plan_data, mbox_path
    except Exception as ex:
        LOG.warning(f"Error checking disk plan at {plan_json}: {ex}")
    return None, None


def discover_disk_results(storage_location):
    if not storage_location or not os.path.isdir(storage_location):
        return []
    results = []
    for entry in sorted(os.listdir(storage_location)):
        entry_dir = os.path.join(storage_location, entry)
        if os.path.isdir(entry_dir) and entry.endswith("_Dedup"):
            plan_data, mbox_path = check_plan_completed_on_disk(entry_dir)
            if plan_data is not None and mbox_path is not None:
                results.append((entry_dir, plan_data, mbox_path))
    return results


def inspect_storage_directory(storage_directory):
    if not storage_directory or not os.path.isdir(storage_directory):
        return {
            "symlinks": [],
            "working_files": [],
            "directories": [],
        }

    symlinks = []
    working_files = []
    directories = []

    for root, dirs, files in os.walk(storage_directory, followlinks=False):
        for d in dirs:
            dir_path = os.path.join(root, d)
            if os.path.islink(dir_path):
                symlinks.append(dir_path)
            else:
                directories.append(dir_path)

        for f in files:
            file_path = os.path.join(root, f)
            if os.path.islink(file_path):
                symlinks.append(file_path)
            else:
                working_files.append(file_path)

    return {
        "symlinks": symlinks,
        "working_files": working_files,
        "directories": directories,
    }


def cleanup_storage_directory(storage_directory, remove_working_files=False):
    if not storage_directory or not os.path.isdir(storage_directory):
        return {
            "symlinks_removed": 0,
            "files_removed": 0,
            "dirs_removed": 0,
            "storage_dir": storage_directory,
        }

    symlinks_removed = 0
    files_removed = 0
    dirs_removed = 0

    # 1. Remove all symlinks first
    for root, dirs, files in os.walk(storage_directory, followlinks=False):
        for name in files + dirs:
            path = os.path.join(root, name)
            if os.path.islink(path):
                try:
                    os.unlink(path)
                    symlinks_removed += 1
                    LOG.info(f"Removed symlink: {path}")
                except Exception as ex:
                    LOG.warning(f"Failed to remove symlink {path}: {ex}")

    # 2. If requested, remove working files and subdirectories
    if remove_working_files:
        for root, dirs, files in os.walk(
            storage_directory, topdown=False, followlinks=False
        ):
            for f in files:
                fpath = os.path.join(root, f)
                if not os.path.islink(fpath):
                    try:
                        os.remove(fpath)
                        files_removed += 1
                        LOG.debug(f"Removed working file: {fpath}")
                    except Exception as ex:
                        LOG.warning(f"Failed to remove file {fpath}: {ex}")

            for d in dirs:
                dpath = os.path.join(root, d)
                if not os.path.islink(dpath):
                    try:
                        os.rmdir(dpath)
                        dirs_removed += 1
                        LOG.debug(f"Removed directory: {dpath}")
                    except Exception as ex:
                        LOG.warning(f"Failed to remove directory {dpath}: {ex}")

    return {
        "symlinks_removed": symlinks_removed,
        "files_removed": files_removed,
        "dirs_removed": dirs_removed,
        "storage_dir": storage_directory,
    }


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
