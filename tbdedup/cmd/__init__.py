import argparse
import asyncio
import datetime
import hashlib
import logging
import math
import sys

from tbdedup import (
    db,
    mbox
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


async def asyncMain():
    argument_parser = argparse.ArgumentParser(
        description="Thunderbird MBox Deduplicator"
    )
    argument_parser.add_argument(
        '--location', '-l',
        default=None,
        type=str,
        required=True,
        help='Directory to search for Thunderbird MBox Files',
    )
    argument_parser.add_argument(
        '--hash-storage', '-hs',
        default=None,
        type=str,
        required=False,
        help="Specify where to store the database information",
    )
    argument_parser.add_argument(
        '--log-config',
        type=str,
        required=False,
        help='Specify the log configuration data',
        metavar='Log config',
    )

    arguments = argument_parser.parse_args()
    # log config is optional
    if arguments.log_config is not None:
        logging.config.fileConfig(arguments.log_config)
    else:
        lh = logging.StreamHandler(sys.stdout)
        lh.setLevel(logging.DEBUG)

        lf = logging.FileHandler('.tb-dedup.log')
        lf.setLevel(logging.DEBUG)

        log = logging.getLogger()
        log.addHandler(lh)
        log.addHandler(lf)
        log.setLevel(logging.DEBUG)

    log = logging.getLogger()
    locationProcessor = mbox.MailboxFolder(arguments.location)
    mboxfiles = await locationProcessor.getMboxFiles()
    storage = db.MessageDatabase(arguments.hash_storage)

    allFiles = '\n'.join(mboxfiles)
    log.info(f"Found {len(mboxfiles)} files to process:\n{allFiles}")
    file_tasks = []
    for filename in mboxfiles:
        file_task = asyncio.create_task(
            processFile(filename, storage),
        )
        file_tasks.append(file_task)

    file_results = await asyncio.gather(*file_tasks)
    LOG.info(f"Detected {storage.get_unique_message_count()} unique records")

    utc_time = datetime.datetime.utcnow()
    output_filename = utc_time.strftime("%Y%m%d_%H%M%S_deduplicated.mbox")
    LOG.info(f"Writing unique records to {output_filename}")
    with open(output_filename, "wb") as output_data:
        wcounter = 0
        for unique_hashid in storage.get_message_hashes():
            for msg_for_hash in storage.get_messages_by_hash(unique_hashid):
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


# main is a simple wrapper for the setup's console_script
def main():
    asyncio.run(asyncMain())

if __name__ == "__main__":
    sys.exit(main)
