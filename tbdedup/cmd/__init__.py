import argparse
import asyncio
import logging
import sys

from tbdedup import mbox

LOG = logging.getLogger(__name__)

async def processFile(filename):
    LOG.info(f"Detecting MBox File Type of {filename}")
    mbox_filetype = mbox.Mailbox.detect_mbox_type(filename)
    LOG.info(f"Detected Mbox File Type of {mbox_filetype} for file {filename}")

async def asyncMain():
    argument_parser = argparse.ArgumentParser(
        description="Thunderbird MBox Deduplicator"
    )
    argument_parser.add_argument(
        '--location', '-l',
        default=None,
        type=str,
        required=True,
        help=(
            'Directory to search for Thunderbird MBox Files',
        ),
    )
    argument_parser.add_argument(
        '--hash-storage', '-hs',
        default=None,
        type=str,
        required=False,
        help=(
            "",
        ),
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

    allFiles = '\n'.join(mboxfiles)
    log.info(f"Found {len(mboxfiles)} files to process:\n{allFiles}")
    file_tasks = []
    for filename in mboxfiles:
        file_task = asyncio.create_task(
            processFile(filename),
        )
        file_tasks.append(file_task)

    file_results = await asyncio.gather(*file_tasks)


# main is a simple wrapper for the setup's console_script
def main():
    asyncio.run(asyncMain())

if __name__ == "__main__":
    sys.exit(main)
