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
import logging
import sys

import tkinter

import aiotkinter

from thunderbirddedup.gui4.app import App


async def asyncGui(options):
    pass


def main():
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

    asyncio.set_event_loop_policy(aiotkinter.TkinterEventLoopPolicy())
    loop = asyncio.get_event_loop()
    root = App()
    loop.run_forever()
    loop.close()


if __name__ == "__main__":
    sys.exit(main())
