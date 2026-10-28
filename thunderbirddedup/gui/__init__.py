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
import sys

import PySide6.QtAsyncio as QtAsyncio
from PySide6.QtWidgets import QApplication

from thunderbirddedup.gui import app


async def asyncGui(options=None):
    the_app = QApplication.instance() or QApplication(sys.argv)
    w = app.MainWindow(initial_options=options)
    the_app._main_window = w
    w.show()
    return w


def run_gui():
    from thunderbirddedup import cmd
    the_app = QApplication.instance() or QApplication(sys.argv)
    the_app.setQuitOnLastWindowClosed(True)
    QtAsyncio.run(cmd.asyncMain(), keep_running=True, handle_sigint=True)
    return 0


def main():
    the_app = QApplication.instance() or QApplication(sys.argv)
    the_app.setQuitOnLastWindowClosed(True)
    w = app.MainWindow()
    the_app._main_window = w
    w.show()
    QtAsyncio.run(keep_running=True, handle_sigint=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
