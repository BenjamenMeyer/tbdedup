"""
Copyright 2023-2026 Benjamen R. Meyer

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import os.path

from thunderbirddedup import db

from tests import base


class TestMessageDatabase(base.TestCase):

    def test_init_and_schema_version(self):
        storage = db.MessageDatabase(None)
        self.assertEqual(storage.get_schema_version(), 0)

        # Verify indexes were created on messages table
        with storage._get_db() as cursor:
            rows = cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
            index_names = {row[0] for row in rows}
            self.assertIn("idx_messages_hashid", index_names)
            self.assertIn("idx_messages_diskhashid", index_names)

        # Calling close twice is safe
        storage.close()
        self.assertIsNone(storage._db)
        storage.close()

    def test_file_backed_reinit_and_empty_schema_table(self):
        with base.KeepLocalDirClean() as cwd:
            db_path = os.path.join(cwd.temp_dir.name, "test_messages.sqlite")
            storage = db.MessageDatabase(db_path)
            self.assertEqual(storage.get_schema_version(), 0)
            storage.close()

            # Re-opening an already initialized database should skip re-running schema 0
            storage2 = db.MessageDatabase(db_path)
            self.assertEqual(storage2.get_schema_version(), 0)

            # If schema_version table is emptied, get_schema_version returns -1
            with storage2._get_db() as cursor:
                cursor.execute("DELETE FROM schema_version")
            self.assertEqual(storage2.get_schema_version(), -1)
            storage2.close()

            # Accessing _get_db after close automatically re-initializes
            self.assertEqual(storage2.get_schema_version(), 0)
            storage2.close()

    def test_add_and_query_messages(self):
        storage = db.MessageDatabase(None)
        storage.add_message(
            "parsed_hash_1",
            "msg_1",
            "/path/to/000001.mbox",
            "<id1@example.com>",
            "id1_hash",
            0,
            100,
            "disk_hash_1",
            0x0001,
            0x00000000,
            "$label1",
        )
        # Second copy with same parsed hash but different disk hash
        storage.add_message(
            "parsed_hash_1",
            "msg_1_copy",
            "/path/to/000002.mbox",
            "<id1@example.com>",
            "id1_hash",
            200,
            310,
            "disk_hash_2",
            0x0004,
            0x10000000,
            "$label2",
        )

        self.assertEqual(storage.get_total_message_count(), 2)
        self.assertEqual(storage.get_unique_message_count(use_disk=False), 1)
        self.assertEqual(storage.get_unique_message_count(use_disk=True), 2)

        parsed_hashes = list(storage.get_message_hashes(use_disk=False))
        self.assertEqual(parsed_hashes, ["parsed_hash_1"])

        disk_hashes = set(storage.get_message_hashes(use_disk=True))
        self.assertEqual(disk_hashes, {"disk_hash_1", "disk_hash_2"})

        msgs_by_parsed = list(
            storage.get_messages_by_hash("parsed_hash_1", use_disk=False)
        )
        self.assertEqual(len(msgs_by_parsed), 2)
        self.assertEqual(msgs_by_parsed[0]["length"], 100)
        self.assertEqual(msgs_by_parsed[0]["mozilla_status"], 0x0001)
        self.assertEqual(msgs_by_parsed[1]["length"], 110)
        self.assertEqual(msgs_by_parsed[1]["mozilla_keys"], "$label2")

        msgs_by_disk = list(
            storage.get_messages_by_hash("disk_hash_2", use_disk=True)
        )
        self.assertEqual(len(msgs_by_disk), 1)
        self.assertEqual(msgs_by_disk[0]["location"], "/path/to/000002.mbox")
        storage.close()

    def test_transaction_batching_and_rollback(self):
        storage = db.MessageDatabase(None)
        with storage.transaction():
            # Nested transaction context should also work seamlessly
            with storage.transaction():
                storage.add_message(
                    "hash_a",
                    "id_a",
                    "/mbox/a",
                    "<a@example.com>",
                    "id_a_hash",
                    0,
                    50,
                    "disk_a",
                )
                storage.add_message(
                    "hash_b",
                    "id_b",
                    "/mbox/b",
                    "<b@example.com>",
                    "id_b_hash",
                    50,
                    120,
                    "disk_b",
                )

        self.assertEqual(storage.get_unique_message_count(use_disk=False), 2)

        # Verify rollback when an exception occurs inside transaction()
        with self.assertRaises(RuntimeError):
            with storage.transaction():
                storage.add_message(
                    "hash_c",
                    "id_c",
                    "/mbox/c",
                    "<c@example.com>",
                    "id_c_hash",
                    0,
                    80,
                    "disk_c",
                )
                raise RuntimeError("Simulated failure during batch")

        self.assertEqual(storage.get_unique_message_count(use_disk=False), 2)
        storage.close()
