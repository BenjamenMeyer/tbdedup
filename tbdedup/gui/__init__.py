import asyncio
import sys

#import asyncqt
#import qasync
import asyncslot

from PyQt5.QtWidgets import QApplication, QWidget

from tbdedup.gui.app import MainWindow

async def asyncGui(options):
    #qt_event_loop = qasync.QEventLoop(app)
    #asyncio.set_event_loop(qt_event_loop)
    pass

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    with asyncslot.AsyncSlotRunner():
        app.exec()

if __name__ == "__main__":
    sys.exit(main())
