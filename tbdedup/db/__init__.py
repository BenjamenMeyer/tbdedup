"""
Database

Table 1:
- Hash, Message ID, Folder
- Key: (Hash, Message ID)
"""
import sqlite3

SCHEMAS = [
    {
        "version": 0,
        "changes": [
            "CREATE TABLE IF NOT EXISTS schema_version(version INT)",
            "CREATE TABLE IF NOT EXISTS messages(hashid TEXT, messageid TEXT, messageid2 TEXT, hashid2 TEXT, location TEXT)",
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
INSERT INTO messages(hashid, messageid, messageid2, hashid2, location)  VALUES(:hashid, :messageid, :messageid2, :hashid2, :location)
"""

GET_UNIQUE_MESSAGE_COUNT = """
SELECT COUNT(*) FROM (SELECT DISTINCT hashid FROM messages)
"""

GET_MESSAGE_HASHES = """
SELECT DISTINCT hashid FROM messages
"""

GET_MESSAGES_BY_HASH = """
SELECT messageid, location FROM messages WHERE hashid = :hashid
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

    def add_message(self, msg_hash, msg_id, msg_location, msg_id2, msg_hash2):
        with self._db as cursor:
            result = cursor.execute(
                ADD_MESSAGE,
                {
                    "hashid": msg_hash,
                    "messageid": msg_id,
                    "messageid2": msg_id2,
                    "hashid2": msg_hash2,
                    "location": msg_location,
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
                yield msg_hash

    def get_messages_by_hash(self, hashid):
        with self._db as cursor:
            for msg_id, msg_location in cursor.execute(
                GET_MESSAGES_BY_HASH,
                {
                    "hashid": hashid
                },
            ):
                yield (msg_id, msg_location)
