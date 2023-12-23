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
import re

from tbdedup import (
    mbox,
)
from . import (
    keys,
    output,
)
from tbdedup.utils import (
    time,
)

LOG = logging.getLogger(__name__)

class GenerationError(Exception):
    pass

async def generate(output_directory, matched_files, file_mapping):
    file_counter = 1
    for filename in matched_files:
        link_file = f"{file_counter:06}.mbox"
        link_name = os.path.join(
            output_directory,
            link_file,
        )
        source_path = os.path.abspath(filename)
        try:
            # only symlinking files
            os.symlink(
                source_path,
                link_name,
                target_is_directory=False,
                dir_fd=None,
            )
            LOG.info(f'Mapping {source_path} to {link_name}')
        except Exception as ex:
            LOG.exception(f'Failed to symlink file {source_path} as {link_name}')
            raise GenerationError(f'Failed to symlink file {source_path} as {link_name}') from ex

        file_mapping[keys.plan_file_map][link_file] = source_path

        file_counter = file_counter + 1

    mapping_file = os.path.join(
        output_directory,
        "mapping.json",
    )

    file_mapping[keys.plan_counter] = file_counter
    file_mapping[keys.plan_map_file] = mapping_file

    with open(mapping_file, "wt") as file_mapper:
        json.dump(
            file_mapping,
            file_mapper,
            indent=4,
            sort_keys=False,
        )

async def planner(options, mboxfiles):
    try:
        pattern = (
            re.compile(options.limit_pattern)
            if options.limit_pattern is not None
            else None
        )
    except Exception:
        LOG.error(f"Invalid Pattern Specific: {options.limit_pattern}")
        return 1

    allFiles = '\n'.join(mboxfiles)
    matched_files = []
    for filename in mboxfiles:
        if (
            pattern is None
        ) or (
            pattern is not None and pattern.match(filename)
        ):
            matched_files.append(filename)

    output_directory = output.get_directory()
    LOG.info(f"Linking to MBOX files to {output_directory}")

    file_mapping = {
        keys.plan_pattern: options.limit_pattern,
        keys.plan_location: {
            keys.plan_source: options.location,
            keys.plan_output: output_directory,
        },
        keys.plan_file_map: {},
    }

    try:
        mapping_file = await generate(output_directory, matched_files, file_mapping)
    except:
        LOG.exception('Error during file linkage')
        mapping_file = None

    return (output_directory, mapping_file)

# wrap for the command-line
async def asyncPlanner(options):
    locationProcessor = mbox.MailboxFolder(options.location)
    with time.TimeTracker("File Search"):
        mboxfiles = await locationProcessor.getMboxFiles()
    with time.TimeTracker("Planner"):
        await planner(options, mboxfiles)
