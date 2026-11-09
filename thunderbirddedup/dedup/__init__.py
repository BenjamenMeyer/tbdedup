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
import datetime
import hashlib
import logging
import os.path

from thunderbirddedup import (
    db,
    mbox,
)

from thunderbirddedup.utils import (
    encoder,
    file_tracker,
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
        else False  # `parsed`
    )


async def processFile(
    filename,
    storage,
    counter_update=None,
    file_progress_callback=None,
):
    box = mbox.Mailbox(None, filename)
    total_bytes = (
        os.path.getsize(filename) if os.path.exists(filename) else 0
    )
    if file_progress_callback is not None:
        file_progress_callback(filename, 0, total_bytes, 0)

    counter = 0
    try:
        LOG.info(f'Processing records...')
        summary_gen = box.buildSummary()
        try:
            with storage.transaction():
                for msg in summary_gen:
                    try:
                        storage.add_message(
                            msg.getHash(diskHash=False),  # hash for comparisons
                            msg.getMsgId(),  # id
                            filename,  # location
                            msg.getMessageIDHeader(),  # 2nd id from the headers
                            msg.getMessageIDHeaderHash(),  # 2nd hash
                            msg.start_offset,
                            msg.end_offset,
                            msg.getHash(diskHash=True),  # hash to ensure we read the right thing
                            msg.getMozillaStatus(),
                            msg.getMozillaStatus2(),
                            msg.getMozillaKeys(),
                        )
                        counter = counter + 1
                        if counter % 250 == 0:
                            if file_progress_callback is not None:
                                file_progress_callback(
                                    filename,
                                    msg.end_offset,
                                    total_bytes,
                                    counter,
                                )
                            await asyncio.sleep(0)
                        if time.check_yield(counter, 10000) == 0:
                            LOG.info(f"Record Counter: {counter}")

                    except Exception:
                        LOG.exception(f'File: {filename} - Message ID: {msg.getMsgId()} - Start: {msg.start_offset} - End: {msg.end_offset}')
                        raise
        finally:
            if hasattr(summary_gen, "close"):
                summary_gen.close()

    except mbox.ErrInvalidFileFormat as ex:
        LOG.error(f'Invalid file format detected: {ex}')

    except mbox.ErrEmptyFile as ex:
        LOG.info(f"Detected empty file - {filename}")

    else:
        LOG.info(f"Detected {counter} messages in {filename}")

    if file_progress_callback is not None:
        file_progress_callback(filename, total_bytes, total_bytes, counter)
    await asyncio.sleep(0)

    if counter_update is not None:
        try:
            counter_update(filename)
        except TypeError:
            counter_update()


async def dedupper(
    mboxfiles,
    msg_hash_storage_location,
    use_disk_data_for_hash=False,
    output_base_path=None,
    copy_progress_callback=None,
    file_progress_callback=None,
    write_progress_callback=None,
):
    # NOTE: in testing found that `use_disk_data_for_hash == True` results
    #   in twice as many files as `use_disk_data_for_hash == False` with
    #   the difference between deplicates. Thus the parameter value defaults
    #   to False as it yields better results

    storage = db.MessageDatabase(msg_hash_storage_location)

    try:
        counters = {
            "completed": 0.0,
            "total": 0.0,
        }

        def counter_update(completed_filename=""):
            counters['completed'] = counters['completed'] + 1.0
            if counters['total'] > 0:
                percentage = (counters['completed'] / counters['total']) * 100.0
                msg = (
                    f'[{output_base_path}] ' if output_base_path is not None else ''
                )
                msg = msg + f'Progress Report: {percentage:03.02f}'
                LOG.info(msg)
            if copy_progress_callback is not None:
                copy_progress_callback(
                    int(counters['completed']),
                    int(counters['total']),
                    completed_filename,
                )

        allFiles = '\n'.join(mboxfiles)
        LOG.info(f"Found {len(mboxfiles)} files to process:\n{allFiles}")
        counters['total'] = len(mboxfiles)
        if copy_progress_callback is not None:
            copy_progress_callback(0, len(mboxfiles), "")

        for filename in mboxfiles:
            await processFile(
                filename,
                storage,
                counter_update=counter_update,
                file_progress_callback=file_progress_callback,
            )
        unique_disk = storage.get_unique_message_count(use_disk=True)
        unique_parsed = storage.get_unique_message_count(use_disk=False)
        LOG.info(f"[DISK  ] Detected {unique_disk} unique records")
        LOG.info(f"[PARSED] Detected {unique_parsed} unique records")
        if unique_disk != unique_parsed:
            LOG.info(f"** WARNING ** Hash Source Choice may result in different output results -- Using {'DISK' if use_disk_data_for_hash else 'PARSED'}")

        total_unique = unique_disk if use_disk_data_for_hash else unique_parsed
        if write_progress_callback is not None:
            write_progress_callback(0, total_unique)

        utc_time = datetime.datetime.utcnow()
        output_filename_timestamp = utc_time.strftime("%Y%m%d_%H%M%S%f_deduplicated.mbox")

        output_filename = (
            output_filename_timestamp
            if output_base_path is None
            else os.path.join(
                output_base_path,
                output_filename_timestamp,
            )
        )

        LOG.info(f"Writing unique records to {output_filename}")
        with file_tracker.open_file(output_filename, "wb") as output_data:
            wcounter = 0
            for unique_hashid in storage.get_message_hashes(use_disk=use_disk_data_for_hash):
                msgs_for_hash = list(
                    storage.get_messages_by_hash(unique_hashid, use_disk=use_disk_data_for_hash)
                )
                merged_status, merged_status2, merged_keys = mbox.Message.mergeMozillaMetadata(
                    msgs_for_hash
                )
                for msg_for_hash in msgs_for_hash:
                    msgData = mbox.Mailbox.getMessageFromFile(msg_for_hash)
                    msgDataHasher = hashlib.sha256()
                    msgDataHasher.update(encoder.to_encoding(msgData))
                    msgDataHash = msgDataHasher.hexdigest()
                    if msgDataHash != msg_for_hash['disk_hash']:
                        LOG.info(f'Unable to rebuild message with hash {unique_hashid} - got {msgDataHash} - {msgData}')
                        with file_tracker.open_file(f"{msgDataHash}.orig-{unique_hashid}.mboxrecord", "wb") as msg_recorder:
                            msg_recorder.write(msgData)
                            msg_recorder.flush()
                        continue

                    msgData = mbox.Message.updateMozillaHeaders(
                        msgData,
                        merged_status,
                        merged_status2,
                        merged_keys,
                    )
                    output_data.write(msgData)
                    output_data.flush()

                    # just take the first entry
                    break

                wcounter = wcounter + 1
                if wcounter % 250 == 0:
                    if write_progress_callback is not None:
                        write_progress_callback(wcounter, total_unique)
                    await asyncio.sleep(0)
                time.check_yield(wcounter, 1000)

        if write_progress_callback is not None:
            write_progress_callback(wcounter, total_unique)
        await asyncio.sleep(0)
        LOG.info(f'Wrote {wcounter} records')
        return output_filename
    finally:
        storage.close()


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
