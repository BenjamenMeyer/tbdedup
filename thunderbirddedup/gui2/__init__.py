import sys

import asyncslot

from PyQt5.QtWidgets import (
    QApplication
)

from thunderbirddedup.gui2 import (
    app,
)


def main():
    the_app = QApplication(sys.argv)
    main_app = app.MainWindow()
    main_app.show()
    with asyncslot.AsyncSlotRunner():
        the_app.exec()


if __name__ == "__main__":
    sys.exit(main())
