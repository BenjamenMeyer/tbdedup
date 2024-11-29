from asyncslot import asyncSlot

from PyQt5.QtCore import (
    QObject,
    QThreadPool,
    pyqtSignal,
)

from tbdedup.mbox import (
    MailboxFolder,
)
from tbdedup.gui.runner import (
    Runner,
)

class ErrSearchAlreadyInProgress(Exception):
    pass

class Searcher(QObject):

    progress = pyqtSignal(int) 
    completed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool()
        self.search_active = False
        self.result = None
        self.error_result = None

    async def finished(self):
        self.search_active = False

    async def receive_result(self, obj):
        self.result = obj

    async def receive_error(self, err_tuple):
        self.error_result = err_tuple

    @staticmethod
    async def get_files(*args, **kwargs):
        location = kwargs['location']
        locationProcessor = mbox.MailboxFolder(location)
        with time.TimeTracker("File Search"):
            mboxfiles = await locationProcessor.getMboxFiles()
        print(f'Result type: {type(mboxfiles)}')
        return mboxfiles

    async def mbox_file_search(self, location):
        if self.search_active:
            raise ErrSearchAlreadyInProgress("search already in progress. Please try again later.")
        self.search_active = True

        worker = Runner(self.get_files)
        worker.signals.result.connect(asyncSlot(self.receive_result))
        worker.signals.error.connect(asyncSlot(self.receive_error))
        worker.signals.progress.connect(self.progress)
        worker.signals.finished.connect(asyncSlot(self.finished))
        worker.signals.finished.connect(self.completed)
        self.threadpool.start(worker)
