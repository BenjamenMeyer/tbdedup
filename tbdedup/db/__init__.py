"""
Database

Table 1:
- Hash, Message ID, Folder
- Key: (Hash, Message ID)
"""
import logging
import sqlite3

LOG = logging.getLogger(__name__)

SCHEMAS = [
    {
        "version": 0,
        "changes": [
            "CREATE TABLE IF NOT EXISTS schema_version(version INT)",
            "CREATE TABLE IF NOT EXISTS messages(hashid TEXT, diskhashid TEXT, messageid TEXT, messageid2 TEXT, hashid2 TEXT, location TEXT, startOffset INT, endOffset INT)",
        ],
    },
]

ADD_SCHEMA_VERSION = """
INSERT INTO schema_version (version) VALUES(:version)
"""

GET_SCHEMA_VERSION = """
SELECT MAX(version) FROM schema_version
"""


ADD_MESSAGE = """
INSERT INTO messages(hashid, diskhashid, messageid, messageid2, hashid2, location, startOffset, endOffset)  VALUES(:hashid, :diskhashid, :messageid, :messageid2, :hashid2, :location, :startOffset, :endOffset)
"""

GET_UNIQUE_MESSAGE_COUNT = """
SELECT COUNT(*) FROM (SELECT DISTINCT hashid FROM messages)
"""

GET_MESSAGE_HASHES = """
SELECT DISTINCT hashid FROM messages
"""

GET_MESSAGES_BY_HASH = """
SELECT messageid, location, startOffset, endOffset, diskhashid FROM messages WHERE hashid = :hashid
"""

class MessageDatabase(object):

    def __init__(self, storageLocation):
        self._db = None
        self._location = storageLocation
        self.init()

    def init(self):
        self._db = sqlite3.connect(
            ":memory:"
            if self._location == None
            else self._location
        )
        for version_schema in SCHEMAS:
            current_schema_version = self.get_schema_version()
            if current_schema_version < version_schema["version"]:
                with self._db as cursor:
                    for change in version_schema["changes"]:
                        cursor.execute(change)
                    cursor.commit()


    def get_schema_version(self):
        try:
            with self._db as cursor:
                result = cursor.execute(GET_SCHEMA_VERSION)
                values = result.fetchone()
                return values[0]
        except Exception:
            return -1

    def add_message(self, msg_hash, msg_id, msg_location, msg_id2, msg_hash2, start_offset, end_offset, disk_hash):
        with self._db as cursor:
            result = cursor.execute(
                ADD_MESSAGE,
                {
                    "hashid": msg_hash,
                    "diskhashid": disk_hash,
                    "messageid": msg_id,
                    "messageid2": msg_id2,
                    "hashid2": msg_hash2,
                    "location": msg_location,
                    "startOffset": start_offset,
                    "endOffset": end_offset,
                },
            )

    def get_unique_message_count(self):
        with self._db as cursor:
            result = cursor.execute(GET_UNIQUE_MESSAGE_COUNT)
            value = result.fetchone()
            return value[0]

    def get_message_hashes(self):
        with self._db as cursor: 
            for msg_hash in cursor.execute(GET_MESSAGE_HASHES):
                yield msg_hash[0]

    def get_messages_by_hash(self, hashid):
        with self._db as cursor:
            for msg_id, msg_location, start_offset, end_offset, disk_hashid in cursor.execute(
                GET_MESSAGES_BY_HASH,
                {
                    "hashid": hashid
                },
            ):
                yield {
                    "hash": hashid,
                    "messageid": msg_id,
                    "location": msg_location,
                    "start_offset": start_offset,
                    "end_offset": end_offset,
                    "length": end_offset - start_offset,
                    "disk_hash": disk_hashid,
                }
