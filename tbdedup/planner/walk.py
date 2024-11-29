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

from tbdedup import (
    mbox,
)
from . import (
    keys,
    output,
)
from tbdedup.utils import (
    json,
    time,
)

LOG = logging.getLogger(__name__)


class PreplannerFileManager(object):

    def __init__(self, location):
        self.location = location
        self.files = []
        self.combinatory = None

    def add_file(self, filename):
        self.files.append(filename)

    def __json__(self):
        return {
            "location": self.location,
            "files": self.files,
            "combinatory": self.combinatory,
        }


class Preplanner(object):

    def __init__(self, options):
        self.options = options

        self.folder_pattern = options.folder_pattern
        self.location = options.location
        self.output_filename = None

        self.preplanner = {
            keys.preplan_location: options.location,
            keys.preplan_planning: {},
        }

    def __json__(self):
        return {
            # it is not feasible to include `options` in the JSON output
            # as it will not serialize properly; it's also not valuable
            # to do this either
            # "options": self.options,
            "folder_pattern": self.folder_pattern,
            "location": self.location,
            "output_filename": self.output_filename,
            "preplanner": {
                keys.preplan_location: self.preplanner[keys.preplan_location],
                keys.preplan_planning: self.preplanner[keys.preplan_planning],
            }
        }

    def has_file(self, root_file):
        return root_file in self.preplanner[keys.preplan_planning]

    def init_file(self, root_file, location, abs_filename):
        manager = PreplannerFileManager(
            location
        )
        manager.add_file(abs_filename)
        self.preplanner[keys.preplan_planning][root_file] = manager

    def append_file(self, root_file, abs_filename):
        self.preplanner[keys.preplan_planning][root_file].add_file(
            abs_filename
        )

    async def preplan(self, mboxfiles):
        LOG.info(f'Gathered {len(mboxfiles)} MBOX files')
        LOG.info(f'Splitting {len(mboxfiles)} based on {self.folder_pattern}')

        for filename in mboxfiles:
            abs_filename = os.path.abspath(filename)
            path_count = abs_filename.count(self.folder_pattern)
            LOG.info(f"Pattern {self.folder_pattern} found {path_count} in {abs_filename}")
            root_file_loc = abs_filename.rfind(self.folder_pattern)
            root_file = abs_filename[root_file_loc:]
            LOG.info(f"Converted {abs_filename} to {root_file}")

            if not self.has_file(root_file):
                LOG.info(f'Found root {root_file}')
                self.init_file(root_file, self.location, abs_filename)
            else:
                self.append_file(root_file, abs_filename)

        LOG.info(f'Completed pre-planning')

        LOG.info(f'Found {len(self.preplanner[keys.preplan_planning])} unique sets')
        self.output_filename = output.get_filename()
        LOG.info(f'Writing preplan to {os.path.abspath(self.output_filename)}')
        json.dump_to_file(self.output_filename, self.preplanner)
        LOG.info('Preplan complete')
        return self.preplanner

    def plan_count(self):
        return len(self.preplanner[keys.preplan_planning])

    def plans(self):
        for root_file, plan in self.preplanner[keys.preplan_planning].items():
            yield (root_file, plan)


# wrap for the command-line
async def asyncPreplanner(options):
    locationProcessor = mbox.MailboxFolder(options.location)
    with time.TimeTracker("File Search"):
        mboxfiles = await locationProcessor.getMboxFiles()
    preplan = Preplanner(options)
    with time.TimeTracker("Preplanner"):
        await preplan.preplan(mboxfiles)
