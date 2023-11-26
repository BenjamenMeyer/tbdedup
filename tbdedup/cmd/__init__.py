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

from tbdedup import (
    dedup,
    planner,
)

LOG = logging.getLogger(__name__)

async def asyncMain():
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
        choices=['disk','parsed'],
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
        '--pattern', '-p',
        default=None,
        type=str,
        required=False,
        help="Pattern to limit the files to if provided",
    )
    planner_parser.set_defaults(func=planner.asyncPlanner)

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

    result = await arguments.func(arguments)
    if result is not None:
        return result
    else:
        return 0

# main is a simple wrapper for the setup's console_script
def main():
    asyncio.run(asyncMain())

if __name__ == "__main__":
    sys.exit(main)
