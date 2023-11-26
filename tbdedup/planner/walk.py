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

async def asyncPreplanner(options):
    locationProcessor = mbox.MailboxFolder(options.location)
    mboxfiles = await locationProcessor.getMboxFiles()
    preplanner = {
        "location": options.location,
        "planning": {},
    }

    LOG.info(f'Gathered {len(mboxfiles)} MBOX files')
    LOG.info(f'Splitting {len(mboxfiles)} based on {options.pattern}')
    for filename in mboxfiles:
        abs_filename = os.path.abspath(filename)
        root_file = abs_filename
        path_count = abs_filename.count(options.pattern)
        LOG.info(f"Pattern {options.pattern} found {path_count} in {root_file}")
        if path_count > 1:
            root_file_loc = abs_filename.rfind(options.pattern)
            root_file = abs_filename[root_file_loc:]
            LOG.info(f"Converted {abs_filename} to {root_file}")
        
        if root_file not in preplanner["planning"]:
            LOG.info(f'Found root {root_file}')
            preplanner["planning"][root_file] = {
                "location": options.location,
                "files": [
                    abs_filename,
                ],
            }
        else:
            preplanner["planning"][root_file]["files"].append(abs_filename)
    LOG.info(f'Completed pre-planning')
    LOG.info(f'Found {len(preplanner["planning"])} unique sets')

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
