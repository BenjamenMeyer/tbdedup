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
import argparse
import asyncio
import logging
import sys

#import asyncqt
#import qasync

from tbdedup import (
    combinatory,
    dedup,
    gui,
)
from tbdedup.planner import (
    plan as planner_plan,
    walk as planner_walk,
)

LOG = logging.getLogger(__name__)


async def asyncMain():
    message_hash_source_choices = ['disk', 'parsed']

    argument_parser = argparse.ArgumentParser(
        description="Thunderbird MBox Deduplicator"
    )
    argument_parser.add_argument(
        '--log-config',
        type=str,
        required=False,
        help='Specify the log configuration data',
        metavar='Log config',
    )
    subparsers = argument_parser.add_subparsers(required=True)

    gui_parser = subparsers.add_parser('gui')
    gui_parser.set_defaults(func=gui.asyncGui)

    dedup_parser = subparsers.add_parser('dedup')

    dedup_parser.add_argument(
        '--location', '-l',
        default=None,
        type=str,
        required=True,
        help='Directory to search for Thunderbird MBox Files',
    )
    dedup_parser.add_argument(
        '--hash-storage', '-hs',
        default=None,
        type=str,
        required=False,
        help="Specify where to store the database information",
    )
    dedup_parser.add_argument(
        '--msg-hash-source',
        choices=message_hash_source_choices,
        help='Specify which source to use for the hash. `disk` means using the raw message off the disk. `parsed` means using everything but the MBOX FROM line that identifies the message',
        default='parsed',
    )
    dedup_parser.set_defaults(func=dedup.asyncDedup)

    planner_parser = subparsers.add_parser('planner')

    planner_parser.add_argument(
        '--location', '-l',
        default=None,
        type=str,
        required=True,
        help='Directory to search for Thunderbird MBox Files',
    )
    planner_parser.add_argument(
        '--limit-pattern', '-lp',
        default=None,
        type=str,
        required=False,
        help="Pattern to limit the files to if provided",
    )
    planner_parser.set_defaults(func=planner_plan.asyncPlanner)

    preplanner_parser = subparsers.add_parser('preplanner')
    preplanner_parser.add_argument(
        '--location', '-l',
        default=None,
        type=str,
        required=True,
        help='Directory to search for Thunderbird MBox Files',
    )
    preplanner_parser.add_argument(
        '--folder-pattern', '-fp',
        default="Inbox.sbd/",
        type=str,
        required=False,
        help="Pattern split file paths in order to match common paths",
    )
    preplanner_parser.set_defaults(func=planner_walk.asyncPreplanner)

    combinatory_parser = subparsers.add_parser('do')

    combinatory_parser.add_argument(
        '--location', '-l',
        default=None,
        type=str,
        required=True,
        help='Directory to search for Thunderbird MBox Files',
    )
    combinatory_parser.add_argument(
        '--storage-location', '-sl',
        default=None,
        type=str,
        required=False,
        help='Directory location to use for storage while processing',
    )
    combinatory_parser.add_argument(
        '--hash-storage', '-hs',
        default=None,
        type=str,
        required=False,
        help="Specify where to store the database information",
    )
    combinatory_parser.add_argument(
        '--msg-hash-source',
        choices=message_hash_source_choices,
        help='Specify which source to use for the hash. `disk` means using the raw message off the disk. `parsed` means using everything but the MBOX FROM line that identifies the message',
        default='parsed',
    )
    combinatory_parser.add_argument(
        '--folder-pattern', '-fp',
        default="Inbox.sbd/",
        type=str,
        required=False,
        help="Pattern split file paths in order to match common paths",
    )
    combinatory_parser.add_argument(
        '--limit-pattern', '-lp',
        default=None,
        type=str,
        required=False,
        help="Pattern to limit the files to if provided",
    )
    combinatory_parser.set_defaults(func=combinatory.asyncCombinatory)

    arguments = argument_parser.parse_args()
    # log config is optional
    if arguments.log_config is not None:
        logging.config.fileConfig(arguments.log_config)
    else:
        lh = logging.StreamHandler(sys.stdout)
        lh.setLevel(logging.DEBUG)

        lfmt = logging.Formatter(
                fmt='[%(asctime)s][%(levelname)s][%(name)s/%(lineno)d][%(threadName)s][]: %(message)s',
        )

        lf = logging.FileHandler('.tb-dedup.log')
        lf.setLevel(logging.DEBUG)

        log = logging.getLogger()
        log.addHandler(lh)
        log.addHandler(lf)
        log.setLevel(logging.DEBUG)

    try:
        result = await arguments.func(arguments)
    except Exception:
        LOG.exception('Error during processing')
        result = -1

    if result is not None:
        return result
    else:
        return 0


# main is a simple wrapper for the setup's console_script
def main():
    print(f"Args: {sys.argv}")
    if 'gui' in sys.argv:
        print("Detected GUI Application. Setting Qt Event Loop")
    else:
        print("Detected TUI Application. Using standard Python3 Asyncio Event Loop")

    asyncio.run(asyncMain())


if __name__ == "__main__":
    sys.exit(main())
