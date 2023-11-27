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

from tbdedup import (
    db,
    mbox,
)

LOG = logging.getLogger(__name__)

async def processFile(filename, storage):
    box = mbox.Mailbox(None, filename)

    counter = 0
    try:
        LOG.info(f'Processing records...')
        for msg in box.buildSummary():
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

    except mbox.ErrInvalidFileFormat as ex:
        LOG.error(f'Invalid file format detected: {ex}')

    else:
        LOG.info(f"Detected {counter} messages in {filename}")

async def dedupper(options):
    use_disk_data_for_hash = (
        True
        if options.msg_hash_source == 'disk'
        else False # `parsed`
    )

    locationProcessor = mbox.MailboxFolder(options.location)
    mboxfiles = await locationProcessor.getMboxFiles()
    storage = db.MessageDatabase(options.hash_storage)

    allFiles = '\n'.join(mboxfiles)
    LOG.info(f"Found {len(mboxfiles)} files to process:\n{allFiles}")
    file_tasks = []
    for filename in mboxfiles:
        file_task = asyncio.create_task(
            processFile(filename, storage),
        )
        file_tasks.append(file_task)

    file_results = await asyncio.gather(*file_tasks)
    LOG.info(f"[DISK  ] Detected {storage.get_unique_message_count(use_disk=True)} unique records")
    LOG.info(f"[PARSED] Detected {storage.get_unique_message_count(use_disk=False)} unique records")
    if storage.get_unique_message_count(use_disk=True) != storage.get_unique_message_count(use_disk=False):
        LOG.info(f"** WARNING ** Hash Source Choice may result in different output results -- Using {'DISK' if use_disk_data_for_hash else 'PARSED'}")

    utc_time = datetime.datetime.utcnow()
    output_filename = utc_time.strftime("%Y%m%d_%H%M%S_deduplicated.mbox")
    LOG.info(f"Writing unique records to {output_filename}")
    with open(output_filename, "wb") as output_data:
        wcounter = 0
        for unique_hashid in storage.get_message_hashes(use_disk=use_disk_data_for_hash):
            for msg_for_hash in storage.get_messages_by_hash(unique_hashid, use_disk=use_disk_data_for_hash):
                msgData = mbox.Mailbox.getMessageFromFile(msg_for_hash)
                msgDataHasher = hashlib.sha256()
                msgDataHasher.update(msgData)
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
    return output_filename

# wrap for the command-line
async def asyncDedup(options):
    await dedupper(options)
