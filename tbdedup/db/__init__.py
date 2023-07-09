"""
Database

Table 1:
- Hash, Message ID, Folder
- Key: (Hash, Message ID)
"""
import sqlite3

ADD_MESSAGE = """
INSERT INTO messages VALUES(hashid, messageid, location) (?, ?, ?)
"""

GET_MESSAGE_HASHES = """
SELECT DISTINCT hashid FROM messages
"""

GET_MESSAGES_BY_HASH = """
SELECT messageid, location FROM messages WHERE hashid = ?
"""

class MessageDatabase(object):

    def __init__(self, cfg):
        self._db = None
        self._cfg = cfg

    def add_message(self, msg_hash, msg_id, msg_location):
        with self._db as cursor:
            result = cursor.execute(ADD_MESSAGE, msg_hash, msg_id, msg_location)

    def get_message_hashes(self):
        with self._db as cursor: 
            for msg_hash in cursor.query(GET_MESSAGE_HASHES):
                yield msg_hash

    def get_messages_by_hash(self, hashid):
        with self._db as cursor:
            for msg_id, msg_location in cursor.query(GET_MESSAGES_BY_HASH, hashid):
                yield (msg_id, msg_location)
