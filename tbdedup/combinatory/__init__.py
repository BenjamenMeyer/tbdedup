"""
Copyright 2023 Benjamen R. Meyer

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
import resource
import tempfile

from tbdedup import (
    db,
    dedup,
    mbox,
)
from tbdedup.planner import (
    keys as planner_keys,
    plan as planner_plan,
    walk as planner_walk,
)
from tbdedup.utils import (
    json,
    time,
)

LOG = logging.getLogger(__name__)


async def runDedup(output_directory, plan, dedup_task, counter_update=None):
    try:
        output_file = await dedup_task
        if counter_update is not None:
            counter_update()

        plan.combinatory[planner_keys.plan_location][planner_keys.plan_mbox] = output_file

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
    path = root_file[path_loc:]
    final_path = path.replace("/", "_").replace(".sbd", "")
    return os.path.join(
        temp_directory,
        f"{final_path}_Dedup"
    )


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
        suffix='tbdedup',
        dir=options.storage_location,
    )
    LOG.info(f'Using Temporary Directory {temp_directory}')

    # 3. For each file set in the preplanner, add a directory under the
    #    temporary directory and add symlinks for each associated file
    LOG.info('Generating dedup plans...')
    dedup_workers = []

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
            required_file_count = 3 + plan.combinatory[planner_keys.plan_counter]

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
                )
            )
            dedup_workers.append(dedup_task)

    counters['total'] = len(dedup_workers)
    counters['completed'] = -1.0
    counter_update()

    # Ensure there are enough file handles to support the work
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    new_soft_limit = (
        required_file_count + 100
        if soft_limit <= required_file_count
        else soft_limit
    )
    new_hard_limit = (
        required_file_count + 200
        if hard_limit <= required_file_count
        else hard_limit
    )
    LOG.info(f'Attempting to raise Open File Limit from (hard={hard_limit}, soft={soft_limit}) to (hard={new_hard_limit}, soft={new_soft_limit})')
    try:
        resource.setrlimit(
            resource.RLIMIT_NOFILE,
            (new_soft_limit, new_hard_limit),
        )
    except Exception:
        LOG.exception("Failed to set new Open File Limit")
        LOG.error("Unable to adjust open file limit")
        return

    LOG.info(f'Waiting on {len(dedup_workers)} dedup tasks to complete')
    with time.TimeTracker("Deduplicator"):
        worker_results = await asyncio.gather(*dedup_workers)
    LOG.info('Dedup Workers completed')

    # 5. Move result files back into the original data set with the
    #    name `Dedup` appended to differentiate them.
    move_workers = []
    LOG.info(f'Arranging to move results back to Thunderbird')

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

    for wr_output_directory, wr_plan, wr_mboxfile in worker_results:
        move_task = asyncio.create_task(
            move_dedup_mbox(
                #wr_output_directory,
                options.location,
                wr_plan,
                wr_mboxfile,
            ),
        )
        move_workers.append(move_task)

    LOG.info(f'Waiting on {len(move_workers)} to move the files')
    with time.TimeTracker("Mover"):
        move_worker_results = await asyncio.gather(*move_workers)
    LOG.info('Move Workers completed')

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
