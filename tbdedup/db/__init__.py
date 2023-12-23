"""
Copyright 2023 Benjamen R. Meyer

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Database

Table 1:
- Hash ID, Disk Hash ID, Message ID, Message ID 2, Hash ID 2, Location, Disk Start Offset, Disk End Offset
- There are no primary keys
- Data should be looked up based on either the Hash ID or the Disk Hash ID
- Message ID is not guaranteed to be unique; and Hash ID 2 is the hash of the Message ID (again, not guaranteed to be unique).
- The Disk Hash ID is the hash of the entire message as read from the disk while the Hash ID is the hash of the parsed
  message data excluding the MBOX `FROM` format line that distinguishes between the individual messages in the MBOX File Format.
  Ideally these two values would generate the same unique record counts; however that cannot be guaranteed to be the case;
  therefore the option is given for the caller to select between the two hashes.

  In testing it was noticed that the disk hash count was twice the size of the non-disk hash count; upon examination of a small
  set no actual difference between the two could be observed in the output data. Therefore it is recommended at this time
  that the non-disk hash is used as it results in the smaller data set.
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
INSERT INTO schema_version (version)
VALUES(:version)
"""

GET_SCHEMA_VERSION = """
SELECT MAX(version)
FROM schema_version
"""


ADD_MESSAGE = """
INSERT INTO messages(hashid, diskhashid, messageid, messageid2, hashid2, location, startOffset, endOffset)
VALUES(:hashid, :diskhashid, :messageid, :messageid2, :hashid2, :location, :startOffset, :endOffset)
"""

DISK_GET_UNIQUE_MESSAGE_COUNT = """
SELECT COUNT(*)
FROM (
    SELECT DISTINCT diskhashid
    FROM messages
)
"""

DISK_GET_MESSAGE_HASHES = """
SELECT DISTINCT diskhashid
FROM messages
"""

DISK_GET_MESSAGES_BY_HASH = """
SELECT messageid, location, startOffset, endOffset, diskhashid
FROM messages
WHERE diskhashid = :diskhashid
"""

GET_UNIQUE_MESSAGE_COUNT = """
SELECT COUNT(*)
FROM (
    SELECT DISTINCT hashid
    FROM messages
)
"""

GET_MESSAGE_HASHES = """
SELECT DISTINCT hashid
FROM messages
"""

GET_MESSAGES_BY_HASH = """
SELECT messageid, location, startOffset, endOffset, diskhashid
FROM messages
WHERE hashid = :hashid
"""


class MessageDatabase(object):

    def __init__(self, storageLocation):
        self._db = None
        self._location = storageLocation
        self.init()

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None

    def init(self):
        self._db = sqlite3.connect(
            ":memory:"
            if self._location is None
            else self._location
        )
        for version_schema in SCHEMAS:
            current_schema_version = self.get_schema_version()
            if current_schema_version < version_schema["version"]:
                # directly access the db here since it was just
                # initialized
                with self._db as cursor:
                    for change in version_schema["changes"]:
                        cursor.execute(change)
                    cursor.commit()

    def _get_db(self):
        if self._db is None:
            self.init()
        return self._db

    def get_schema_version(self):
        try:
            with self._get_db() as cursor:
                result = cursor.execute(GET_SCHEMA_VERSION)
                values = result.fetchone()
                return values[0]
        except Exception:
            return -1

    def add_message(self, msg_hash, msg_id, msg_location, msg_id2, msg_hash2, start_offset, end_offset, disk_hash):
        with self._get_db() as cursor:
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

    def get_unique_message_count(self, use_disk=False):
        with self._get_db() as cursor:
            result = cursor.execute(
                DISK_GET_UNIQUE_MESSAGE_COUNT
                if use_disk
                else GET_UNIQUE_MESSAGE_COUNT
            )
            value = result.fetchone()
            return value[0]

    def get_message_hashes(self, use_disk=False):
        with self._get_db() as cursor:
            for msg_hash in cursor.execute(
                DISK_GET_MESSAGE_HASHES
                if use_disk
                else GET_MESSAGE_HASHES
            ):
                yield msg_hash[0]

    def get_messages_by_hash(self, hashid, use_disk=False):
        with self._get_db() as cursor:
            sqlquery = (
                DISK_GET_MESSAGES_BY_HASH
                if use_disk
                else GET_MESSAGES_BY_HASH
            )
            sqlargs_key = (
                "diskhashid"
                if use_disk
                else
                "hashid"
            )
            for msg_id, msg_location, start_offset, end_offset, disk_hashid in cursor.execute(
                sqlquery,
                {
                    sqlargs_key: hashid
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
