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
            "CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY AUTOINCREMENT, path, absolute_path)",
            "CREATE TABLE IF NOT EXISTS plan(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS plan_data(id INTEGER PRIMARY KEY AUTOINCREMENT, planid INTEGER NOT NULL, fileid INTEGER NOT NULL, FOREIGN(planid) REFERENCES plan(id), FOREIGNKEY(fileid) REFERENCES files(id))",
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

FILES_ADD_FILE = """
INSERT INTO files (path, absolute_path)
VALUES(:filename, :absolute_filename)
"""

FILES_HAS_FILE = """
SELECT COUNT(*)
FROM files
WHERE path = :filename OR absolute_path = :filename
"""

FILES_GET_FILE_ID = """
SELECT id
FROM files
WHERE path = :filename OR absolute_path = :filename
"""

PLAN_CREATE = """
INSERT INTO plan(name)
VALUES(:name)
RETURNING id
"""

PLAN_GET_BY_NAME = """
SELECT id
FROM plan
WHERE name = :name
"""

PLAN_ADD_FILE = """
INSERT INTO plan_data (planid, fileid)
VALUES(:planid, :fileid)
"""

class UnknownFileException(Exception):
    pass

class PlannerDatabase(object):

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
            if current_schema_version is None:
                current_schema_version = -1
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

    def add_file(self, path, abs_path):
        with self._db as cursor:
            result = cursor.execute(
                FILES_ADD_FILE,
                {
                    "filename": path,
                    "absolute_filename": abs_path,
                },
            )

    def has_file(self, path):
        try:
            with self._db as cursor:
                result = cursor.execute(
                    FILES_HAS_FILE,
                    {
                        "filename": path,
                    },
                )
                value = result.fetchone()
                return value[0] > 0
        except Exception:
            return False

    def get_file_id(self, path):
        try:
            with self._db as cursor:
                result = cursor.execute(
                    FILES_GET_FILE_ID,
                    {
                        "filename": path,
                    },
                )
                value = result.fetchone()
                return value[0]
        except Exception as ex:
            raise UnknownFileException from ex

    def create_plan(self, name):
        with self._db as cursor:
            result = cursor.execute(
                PLAN_CREATE,
                {
                    "name": name,
                },
            )
            value = result.fetchone()
            return value[0]

    def get_plan_by_name(self, name):
        with self._db as cursor:
            result = cursor.execute(
                PLAN_GET_BY_NAME,
                {
                    "name": name,
                },
            )
            value = result.fetchone()
            return value[0]

    def get_or_create_plan(self, name):
        try:
            return self.get_plan_by_name(name)
        except:
            return self.create_plan(name)

    def add_file_to_plan(self, planid, fileid):
        with self._db as cursor:
            result = cursor.execute(
                PLAN_ADD_FILE,
                {
                    "planid": planid,
                    "fileid": fileid,
                },
            )
