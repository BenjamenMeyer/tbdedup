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
import hashlib
import json
import logging
import os
import os.path
import re

from tbdedup import (
    mbox,
)

LOG = logging.getLogger(__name__)

counter_key = "counter"
map_file_key = "mapping"
file_map_key = "file_map"
location_key = "location"
output_key = "output"
pattern_key = "pattern"
source_key = "source"

class GenerationError(Exception):
    pass

def get_output_directory():
    counter = 0
    while True:
        utc_time = datetime.datetime.utcnow()
        output_directory = (
            utc_time.strftime("%Y%m%d_%H%M%S_dedup_planner")
            if counter == 0
            else utc_time.strftime("%Y%m%d_%H%M%S_dedup_planner") + f"_{counter:03}"
        )
        try:
            os.mkdir(output_directory)
        except (FileExistsError, FileNotFoundError):
            counter = counter + 1
            # try again
            continue
        else:
            return output_directory

async def generate(output_directory, matched_files, file_mapping):
    file_counter = 1
    LOG.info(f'Attempting to map out {len(matched_files)} into {output_directory}')
    LOG.info(f'Files: {matched_files}')
    for filename in matched_files:
        link_file = f"{file_counter:06}.mbox"
        link_name = os.path.join(
            output_directory,
            link_file,
        )
        source_path = os.path.abspath(filename)
        LOG.info(f'Mapping {source_path} to {link_name}')
        try:
            # only symlinking files
            os.symlink(
                source_path,
                link_name,
                target_is_directory=False,
                dir_fd=None,
            )
        except Exception as ex:
            LOG.exception(f'Failed to symlink file {source_path} as {link_name}')
            raise GenerationError(f'Failed to symlink file {source_path} as {link_name}') from ex
        file_counter = file_counter + 1
        file_mapping[file_map_key][link_file] = source_path


    mapping_file = os.path.join(
        output_directory,
        "mapping.json",
    )
    file_mapping[counter_key] = file_counter
    file_mapping[map_file_key] = mapping_file
    with open(mapping_file, "wt") as file_mapper:
        json.dump(
            file_mapping,
            file_mapper,
            indent=4,
            sort_keys=False,
        )
    return mapping_file

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

    output_directory = get_output_directory()
    LOG.info(f"Linking to MBOX files to {output_directory}")

    file_mapping = {
        pattern_key: options.limit_pattern,
        location_key: {
            source_key: options.location,
            output_key: output_directory,
        },
        file_map_key: {},
    }
    try:
        mapping_file = await generate(output_directory, matched_files, file_mapping)
    except:
        pass

    return (output_directory, mapping_file)

# wrap for the command-line
async def asyncPlanner(options):
    locationProcessor = mbox.MailboxFolder(options.location)
    mboxfiles = await locationProcessor.getMboxFiles()
    await planner(options, mboxfiles)
