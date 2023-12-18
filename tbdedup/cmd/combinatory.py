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
    planner,
)
from tbdedup.planner import walk as planner_walk

LOG = logging.getLogger(__name__)

combinatory_planner_file_mapping_key = "file_mapping"

async def combinatory(options):
    # database for storage
    #files_db = db.PlannerDatabase(options.plan_storage)
    files_db = None

    # generate a single file set of all the MBOX files
    locationProcessor = mbox.MailboxFolder(options.location)
    mboxfiles = await locationProcessor.getMboxFiles()

    # 1. Run the preplanner
    LOG.info("Running preplanner")
    preplanner = await planner_walk.preplan(options, mboxfiles, files_db)

    if len(preplanner[planner_walk.preplanner_key]) == 0:
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
    def get_plan_output_directory(root_file):
        path_loc = root_file.rfind(options.folder_pattern)
        path = root_file[path_loc:]
        final_path = path.replace("/", "_").replace(".sbd", "")
        return os.path.join(
            temp_directory,
            f"{final_path}_Dedup"
        )
    LOG.info('Generating dedup plans...')
    dedup_workers = []

    # object that has only the required types
    # to be able to run the dedup functionality
    class dedup_options(object):
        def __init__(self, hash_storage):
            self.hash_storage = hash_storage
            self.msg_hash_source = options.msg_hash_source

    async def runDedup(output_directory, plan, dedup_task):
        output_file = await dedup_task
        return (
            output_directory,
            plan,
            output_file,
        )

    required_file_count = 0
    for root_file, plan in preplanner[planner_walk.preplanner_key].items():
        output_directory = get_plan_output_directory(root_file)
        # ensure the directory tree exists
        os.makedirs(output_directory, mode=0o755, exist_ok=True)
        plan[combinatory_planner_file_mapping_key] = {
            planner.pattern_key: options.limit_pattern,
            planner.location_key: {
                planner.source_key: root_file,
                planner.output_key: output_directory,
            },
            planner.file_map_key: {},
        }
        try:
            mapping_file = await planner.generate(
                output_directory,
                plan[planner_walk.preplanner_files_key],
                plan[combinatory_planner_file_mapping_key],
            )
        except planner.GenerationError:
            LOG.exception(f'Failed to generate data in {output_directory}')
            return

        # plan["file_mapping"]["file_map"].keys() == symlinks
        # plan["file_mapping"]["mapping"] = mapping.json file
        # increase required files:
        #   - output MBOX file
        #   - input SqliteDB
        #   - reporting
        #   - number of links in the data set
        required_file_count = 3 + plan["file_mapping"]["counter"]

        # 4. Split out a async worker for each directory to deduplicate
        #    each directory data set
        ddup_options = dedup_options(
            os.path.join(
                output_directory,
                "hash.sqlite",
            ),
        )
        dedup_task = asyncio.create_task(
            runDedup(
                output_directory,
                plan,
                dedup.dedupper(
                    ddup_options,
                    plan["file_mapping"].keys(),
                ),
            )
        )
        dedup_workers.append(dedup_task)

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
    worker_results = await asyncio.gather(*dedup_workers)
    LOG.info('Dedup Workers completed')

    # 5. Move result files back into the original data set with the
    #    name `Dedup` appended to differentiate them.
    move_workers = []
    LOG.info(f'Arranging to move results back to Thunderbird')
    async def move_dedup_mbox(output_directory, plan, mboxfile):
        pass

    for wr_output_directory, wr_plan, wr_mboxfile  in worker_results:
        move_task = asyncio.create_task(
            wr_output_directory,
            wr_plan,
            wr_mboxfile,
        )
        move_workers.append(move_task)
    LOG.info(f'Waiting on {len(move_workers)} to move the files')
    move_worker_results = await asyncio.gather(*move_workers)
    LOG.info('Move Workers completed')
