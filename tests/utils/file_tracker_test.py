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
import os
import threading
import time

from thunderbirddedup import db
from thunderbirddedup.utils import file_tracker

from tests import base


class TestFileTracker(base.AsyncioTestCase):

    def setUp(self):
        super().setUp()
        self.tracker = file_tracker.FileTracker(max_open_files=5)

    def tearDown(self):
        self.tracker.close_all()
        file_tracker.close_all()
        super().tearDown()

    def test_open_read_write_context_manager(self):
        with base.KeepLocalDirClean() as cwd:
            fpath = os.path.join(cwd.temp_dir.name, "test_file.txt")

            # Write data
            with self.tracker.open_file(fpath, "wt") as f:
                self.assertEqual(self.tracker.get_open_file_count(), 1)
                self.assertFalse(f.closed)
                self.assertTrue(f.writable())
                self.assertTrue(f.seekable())
                f.write("Line 1\nLine 2\n")
                f.writelines(["Line 3\n"])
                f.flush()
                self.assertGreater(f.fileno(), 0)

            # Once exited context, file is closed
            self.assertEqual(self.tracker.get_open_file_count(), 0)
            self.assertTrue(f.closed)
            self.tracker.assert_all_closed()

            # Read data
            with self.tracker.open_file(fpath, "rt") as f:
                self.assertEqual(self.tracker.get_open_file_count(), 1)
                self.assertTrue(f.readable())
                line1 = f.readline()
                self.assertEqual(line1, "Line 1\n")
                self.assertEqual(f.tell(), len(line1))
                f.seek(0)
                self.assertEqual(f.tell(), 0)
                lines = f.readlines()
                self.assertEqual(len(lines), 3)

            self.assertEqual(self.tracker.get_open_file_count(), 0)

    async def test_async_context_manager(self):
        with base.KeepLocalDirClean() as cwd:
            fpath = os.path.join(cwd.temp_dir.name, "test_async.txt")
            async with self.tracker.open_file(fpath, "wt") as f:
                self.assertEqual(self.tracker.get_open_file_count(), 1)
                f.write("Async Hello")
            self.assertEqual(self.tracker.get_open_file_count(), 0)

            async with self.tracker.open_file(fpath, "rt") as f:
                content = f.read()
                self.assertEqual(content, "Async Hello")
            self.assertEqual(self.tracker.get_open_file_count(), 0)

    def test_explicit_open_and_close(self):
        with base.KeepLocalDirClean() as cwd:
            fpath = os.path.join(cwd.temp_dir.name, "explicit.txt")
            f = self.tracker.open_file(fpath, "wt")
            self.assertEqual(self.tracker.get_open_file_count(), 1)
            f.write("Explicit")
            f.close()
            self.assertEqual(self.tracker.get_open_file_count(), 0)
            self.assertTrue(f.closed)

            # Calling close twice is safe
            f.close()
            self.assertEqual(self.tracker.get_open_file_count(), 0)

    def test_iteration_and_next(self):
        with base.KeepLocalDirClean() as cwd:
            fpath = os.path.join(cwd.temp_dir.name, "iter.txt")
            with self.tracker.open_file(fpath, "wt") as f:
                f.write("A\nB\nC\n")

            with self.tracker.open_file(fpath, "rt") as f:
                collected = [line.strip() for line in f]
                self.assertEqual(collected, ["A", "B", "C"])

    def test_max_open_files_limiting(self):
        with base.KeepLocalDirClean() as cwd:
            self.tracker.set_max_open_files(2)
            self.assertEqual(self.tracker.get_max_open_files(), 2)

            f1_path = os.path.join(cwd.temp_dir.name, "f1.txt")
            f2_path = os.path.join(cwd.temp_dir.name, "f2.txt")
            f3_path = os.path.join(cwd.temp_dir.name, "f3.txt")

            f1 = self.tracker.open_file(f1_path, "wt")
            f2 = self.tracker.open_file(f2_path, "wt")
            self.assertEqual(self.tracker.get_open_file_count(), 2)

            opened_f3 = []

            def open_f3():
                f3 = self.tracker.open_file(f3_path, "wt", timeout=2.0)
                opened_f3.append(f3)

            t = threading.Thread(target=open_f3)
            t.start()

            # f3 should wait because limit 2 is reached
            time.sleep(0.05)
            self.assertEqual(len(opened_f3), 0)

            # Close f1 -> f3 should now acquire slot and open
            f1.close()
            t.join(timeout=2.0)
            self.assertEqual(len(opened_f3), 1)
            self.assertEqual(self.tracker.get_open_file_count(), 2)

            f2.close()
            opened_f3[0].close()
            self.assertEqual(self.tracker.get_open_file_count(), 0)

    def test_timeout_fallback_prevents_deadlock(self):
        with base.KeepLocalDirClean() as cwd:
            self.tracker.set_max_open_files(1)
            f1_path = os.path.join(cwd.temp_dir.name, "deadlock1.txt")
            f2_path = os.path.join(cwd.temp_dir.name, "deadlock2.txt")

            f1 = self.tracker.open_file(f1_path, "wt")
            # f2 with short timeout of 0.1s should log warning and burst to prevent deadlock
            f2 = self.tracker.open_file(f2_path, "wt", timeout=0.1)
            self.assertEqual(self.tracker.get_open_file_count(), 2)
            f1.close()
            f2.close()
            self.assertEqual(self.tracker.get_open_file_count(), 0)

    def test_verify_all_closed_and_assert_all_closed(self):
        with base.KeepLocalDirClean() as cwd:
            fpath = os.path.join(cwd.temp_dir.name, "leak.txt")
            f = self.tracker.open_file(fpath, "wt")

            all_closed, leaks = self.tracker.verify_all_closed(log_leaks=True)
            self.assertFalse(all_closed)
            self.assertEqual(len(leaks), 1)
            self.assertIn("leak.txt", leaks[0]["path"])
            self.assertIn("test_verify_all_closed", leaks[0]["caller"])
            self.assertEqual(leaks[0]["type"], "file")
            self.assertGreaterEqual(leaks[0]["age_seconds"], 0)

            with self.assertRaises(AssertionError):
                self.tracker.assert_all_closed()

            f.close()
            all_closed, leaks = self.tracker.verify_all_closed(log_leaks=True)
            self.assertTrue(all_closed)
            self.assertEqual(len(leaks), 0)
            self.tracker.assert_all_closed()

    def test_custom_resource_registration(self):
        token = self.tracker.register_resource("/var/db.sqlite", resource_type="sqlite")
        self.assertEqual(self.tracker.get_open_file_count(), 1)
        records = self.tracker.get_open_files()
        self.assertEqual(records[0]["type"], "sqlite")

        # Unregistering removes the resource
        self.assertTrue(self.tracker.unregister_resource(token))
        self.assertEqual(self.tracker.get_open_file_count(), 0)
        self.assertFalse(self.tracker.unregister_resource(token))

    def test_message_database_resource_tracking(self):
        with base.KeepLocalDirClean() as cwd:
            db_path = os.path.join(cwd.temp_dir.name, "tracked_msg.sqlite")
            storage = db.MessageDatabase(db_path)
            # Active count on global tracker should be 1
            self.assertEqual(file_tracker.get_open_file_count(), 1)

            storage.close()
            self.assertEqual(file_tracker.get_open_file_count(), 0)
            file_tracker.assert_all_closed()

    def test_close_all_cleanup(self):
        with base.KeepLocalDirClean() as cwd:
            f1 = self.tracker.open_file(os.path.join(cwd.temp_dir.name, "c1.txt"), "wt")
            f2 = self.tracker.open_file(os.path.join(cwd.temp_dir.name, "c2.txt"), "wt")
            self.assertEqual(self.tracker.get_open_file_count(), 2)

            self.tracker.close_all()
            self.assertEqual(self.tracker.get_open_file_count(), 0)
            self.assertTrue(f1.closed)
            self.assertTrue(f2.closed)

    def test_garbage_collection_del_handling(self):
        with base.KeepLocalDirClean() as cwd:
            fpath = os.path.join(cwd.temp_dir.name, "gc.txt")
            f = self.tracker.open_file(fpath, "wt")
            self.assertEqual(self.tracker.get_open_file_count(), 1)
            # Simulate garbage collection of unclosed file
            f.__del__()
            self.assertEqual(self.tracker.get_open_file_count(), 0)
            self.assertTrue(f.closed)

    def test_open_nonexistent_file_cleans_up_token(self):
        with base.KeepLocalDirClean() as cwd:
            bad_path = os.path.join(cwd.temp_dir.name, "nonexistent_dir", "file.txt")
            with self.assertRaises(FileNotFoundError):
                self.tracker.open_file(bad_path, "rt")
            self.assertEqual(self.tracker.get_open_file_count(), 0)
