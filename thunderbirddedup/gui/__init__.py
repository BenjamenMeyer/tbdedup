import sys

import asyncslot
from PySide6.QtWidgets import (
    QApplication,
)

from thunderbirddedup.gui import app


def main():
    the_app = QApplication(sys.argv)
    w = app.MainWindow()
    w.show()
    with asyncslot.AsyncSlotRunner():
        return the_app.exec()


if __name__ == "__main__":
    sys.exit(main())
