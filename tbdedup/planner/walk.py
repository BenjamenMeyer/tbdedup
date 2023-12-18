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
import json
import logging
import os
import os.path

from tbdedup import (
    mbox,
)

LOG = logging.getLogger(__name__)

location_key = "location"
preplanner_key = "pre_planning"
preplanner_files_key = "files"

def get_output_filename():
    counter = 0
    while True:
        utc_time = datetime.datetime.utcnow()
        output_filename = (
            utc_time.strftime("%Y%m%d_%H%M%S_dedup_preplanner.json")
            if counter == 0
            else utc_time.strftime("%Y%m%d_%H%M%S_dedup_preplanner") + f"_{counter:03}.json"
        )
        if os.path.exists(output_filename):
            counter = counter + 1
            # try again
            continue
        else:
            return output_filename

async def preplan(options, mboxfiles, files_db):

    preplanner = {
        location_key: options.location,
        preplanner_key: {},
    }

    LOG.info(f'Gathered {len(mboxfiles)} MBOX files')
    LOG.info(f'Splitting {len(mboxfiles)} based on {options.folder_pattern}')
    for filename in mboxfiles:
        # get the absolute path of the file
        abs_filename = os.path.abspath(filename)

        # start with assuming that the file is the root file
        # root_file = abs_filename

        # get a count of how many times the folder pattern appears in the absolute path
        path_count = abs_filename.count(options.folder_pattern)
        LOG.info(f"Pattern {options.folder_pattern} found {path_count} in {abs_filename}")

        # if the pattern occurs more than once then it is not the root file
        #if path_count > 1:
        # find the last section that can be used
        root_file_loc = abs_filename.rfind(options.folder_pattern)
        root_file = abs_filename[root_file_loc:]
        LOG.info(f"Converted {abs_filename} to {root_file}")

        #if not files_db.has_file(abs_filename):
        #    files_db.add_file(filename, abs_filename)
        #    # Start Plan for root file

        if root_file not in preplanner[preplanner_key]:
            LOG.info(f'Found root {root_file}')
            preplanner[preplanner_key][root_file] = {
                location_key: options.location,
                preplanner_files_key: [
                    abs_filename,
                ],
            }
        else:
            preplanner[preplanner_key][root_file][preplanner_files_key].append(abs_filename)

    LOG.info(f'Completed pre-planning')
    LOG.info(f'Found {len(preplanner[preplanner_key])} unique sets')
    output_filename = get_output_filename()
    LOG.info(f'Writing preplan to {os.path.abspath(output_filename)}')
    with open(output_filename, "wt") as preplan_output:
        json.dump(
            preplanner,
            preplan_output,
            indent=4,
            sort_keys=False,
        )
    LOG.info('Preplan complete')
    return preplanner

# wrap for the command-line
async def asyncPreplanner(options):
    locationProcessor = mbox.MailboxFolder(options.location)
    mboxfiles = await locationProcessor.getMboxFiles()
    await preplan(options, mboxfiles)
