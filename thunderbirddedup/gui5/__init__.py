import asyncio
import logging
import sys

from kivy.app import async_runTouchApp

from thunderbirddedup.gui5.app import TheApp


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

    loop = asyncio.get_event_loop()
    root = TheApp()
    loop.run_until_complete(
        async_runTouchApp(
            root,
            async_lib='asyncio',
        )
    )
    loop.close()


if __name__ == "__main__":
    sys.exit(main())
