from asyncslot import asyncSlot
from PySide6.QtCore import (
    QObject,
    Signal,
    Slot,
)

from thunderbirddedup import (
    db,
    dedup,
    mbox,
)
from thunderbirddedup.planner import (
    keys as planner_keys,
    plan as planner_plan,
    walk as planner_walk,
)
from thunderbirddedup.utils import (
    json,
    time,
)


class TbDedupOptions(object):

    def __init__(self, location):
        self.location = location
        self.hash_storage = None
        self.msg_hash_source = 'parsed'
        self.limit_pattern = None
        self.folder_pattern = "Inbox.sbd/"
        self.storage_location = None
        self.record_log_emit = self.record_log_default
        self.preplan_completed_emit = self.preplan_completed

    def record_log_default(self, message):
        print(message)

    def preplan_completed(self):
        print("Preplan completed")


async def do_preplan(options):
    options.record_log_emit(f"Locating MBOX files under {location}")
    locationProcessor = mbox.MailboxFolder(options.location)
    with time.TimeTracker("File Search"):
        self.mboxfiles = await locationProcessor.getMboxFiles()

    options.record_log_emit(f"Found {len(self.mboxfiles)} MBOX files")
    options.record_log_emit("Preplanning...")
    self.preplan = planner_walk.Preplanner(options)
    with time.TimeTracker("Preplanner"):
        await preplan.preplan(self.mboxfiles)
    options.record_log_emit("Preplan completed")
    options.preplan_completed_emit()


class TbDedupRunner(QObject):

    record_log = Signal(str)
    preplan_do = Signal(TbDedupOptions)
    preplan_complete = Signal()

    def __init__(self):
        super().__init__()
        self.preplan = None
        self.mboxfiles = None
        self.preplan_do.connect(asyncSlot(do_preplan))

    @Slot(str)
    def preplan(self, location):
        self.record_log.emit(f"Setting up preplanning for {location}")
        options = TbDedupOptions(location)
        self.record_log_emit = self.record_log.emit
        self.preplan_completed_emit = preplan_complete.emit
        self.preplan.emit(options)
