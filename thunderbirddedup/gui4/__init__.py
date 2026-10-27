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
