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
import sys

# import asyncqt
# import qasync
import asyncslot

from PyQt5.QtWidgets import QApplication, QWidget

from thunderbirddedup.gui.app import MainWindow


async def asyncGui(options):
    # qt_event_loop = qasync.QEventLoop(app)
    # asyncio.set_event_loop(qt_event_loop)
    pass


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    with asyncslot.AsyncSlotRunner():
        app.exec()


if __name__ == "__main__":
    sys.exit(main())
