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
import logging
import math
import os.path

from tbdedup import (
    db,
    mbox,
)

from tbdedup.utils import (
    encoder,
    time,
)

LOG = logging.getLogger(__name__)

def source_option_to_boolean(msg_hash_source):
    # NOTE: in testing found that `msg_hash_source == 'disk'` results
    #   in twice as many files as `msg_hash_source == 'parsed'` with
    #   the difference between deplicates. Thus the parameter value defaults
    #   to False as it yields better results
    return (
        True
        if msg_hash_source == 'disk'
        else False # `parsed`
    )

async def processFile(filename, storage, counter_update=None):
    box = mbox.Mailbox(None, filename)

    counter = 0
    try:
        LOG.info(f'Processing records...')
        for msg in box.buildSummary():
            try:
                storage.add_message(
                    msg.getHash(diskHash=False),  # hash for comparisons
                    msg.getMsgId(), # id
                    filename, # location
                    msg.getMessageIDHeader(), # 2nd id from the headers
                    msg.getMessageIDHeaderHash(), # 2nd hash
                    msg.start_offset,
                    msg.end_offset,
                    msg.getHash(diskHash=True), # hash to ensure we read the right thing
                )
                counter = counter + 1
                if math.fmod(counter, 10000) == 0:
                    LOG.info(f"Record Counter: {counter}")
            except Exception:
                LOG.exception(f'File: {filename} - Message ID: {msg.getMsgId()} - Start: {msg.start_offset} - End: {msg.end_offset}')
                raise

    except mbox.ErrInvalidFileFormat as ex:
        LOG.error(f'Invalid file format detected: {ex}')

    else:
        LOG.info(f"Detected {counter} messages in {filename}")

    if counter_update is not None:
        counter_update()

async def dedupper(mboxfiles, msg_hash_storage_location, use_disk_data_for_hash=False, output_base_path=None):
    # NOTE: in testing found that `use_disk_data_for_hash == True` results
    #   in twice as many files as `use_disk_data_for_hash == False` with
    #   the difference between deplicates. Thus the parameter value defaults
    #   to False as it yields better results

    storage = db.MessageDatabase(msg_hash_storage_location)

    counters = {
        "completed": 0.0,
        "total": 0.0,
    }
    def counter_update():
        counters['completed'] = counters['completed'] + 1.0
        if counters['total'] > 0:
            percentage = counters['completed'] /counters['total'] * 100.0
            msg = (
                f'[{output_base_path}] ' if output_base_path is not None else ''
            )
            msg = msg + f'Progress Report: {percentage:03.02f}'
            LOG.info(msg)

    allFiles = '\n'.join(mboxfiles)
    LOG.info(f"Found {len(mboxfiles)} files to process:\n{allFiles}")
    file_tasks = []
    for filename in mboxfiles:
        file_task = asyncio.create_task(
            processFile(filename, storage, counter_update=counter_update),
        )
        file_tasks.append(file_task)
    counters['total'] = len(file_tasks)

    file_results = await asyncio.gather(*file_tasks)
    LOG.info(f"[DISK  ] Detected {storage.get_unique_message_count(use_disk=True)} unique records")
    LOG.info(f"[PARSED] Detected {storage.get_unique_message_count(use_disk=False)} unique records")
    if storage.get_unique_message_count(use_disk=True) != storage.get_unique_message_count(use_disk=False):
        LOG.info(f"** WARNING ** Hash Source Choice may result in different output results -- Using {'DISK' if use_disk_data_for_hash else 'PARSED'}")

    utc_time = datetime.datetime.utcnow()
    output_filename_timestamp = utc_time.strftime("%Y%m%d_%H%M%S_deduplicated.mbox")

    output_filename = (
        output_filename_timestamp
        if output_base_path is not None
        else os.path.join(
            output_base_path,
            output_filename_timestamp,
        )
    )
    LOG.info(f"Writing unique records to {output_filename}")
    with open(output_filename, "wb") as output_data:
        wcounter = 0
        for unique_hashid in storage.get_message_hashes(use_disk=use_disk_data_for_hash):
            for msg_for_hash in storage.get_messages_by_hash(unique_hashid, use_disk=use_disk_data_for_hash):
                msgData = mbox.Mailbox.getMessageFromFile(msg_for_hash)
                msgDataHasher = hashlib.sha256()
                msgDataHasher.update(encoder.to_encoding(msgData))
                msgDataHash = msgDataHasher.hexdigest()
                if msgDataHash != msg_for_hash['disk_hash']:
                    LOG.info(f'Unable to rebuild message with hash {unique_hashid} - got {msgDataHash} - {msgData}')
                    with open(f"{msgDataHash}.orig-{unique_hashid}.mboxrecord", "wb") as msg_recorder:
                        msg_recorder.write(msgData)
                        msg_recorder.flush()
                    continue

                output_data.write(msgData)
                output_data.flush()

                # just take the first entry
                break

            wcounter = wcounter + 1
    LOG.info(f'Wrote {wcounter} records')
    # close the database and free up some memory
    # it's not sent any where else so it can be safely closed now
    storage.close()
    return output_filename

# wrap for the command-line
async def asyncDedup(options):
    locationProcessor = mbox.MailboxFolder(options.location)
    with time.TimeTracker("File Search"):
        mboxfiles = await locationProcessor.getMboxFiles()
    use_disk_data_for_hash = source_option_to_boolean(
        options.msg_hash_source
    )

    with time.TimeTracker("Deduplicator"):
        await dedupper(mboxfiles, options.hash_storage, use_disk_data_for_hash)
