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

from thunderbirddedup.utils import disk

from tests import base


class TestDiskTracker(base.TestCase):

    def test_disk_tracker_operations(self):
        tracker = disk.DiskTracker("/base/root")
        self.assertEqual(len(tracker), 0)
        self.assertEqual(tracker.__length_hint__(), 0)

        # Outside base directory
        self.assertFalse(tracker.add_dir("/other/dir"))
        self.assertFalse(tracker.add_file("/other/file.txt"))

        # Direct subdirectory and idempotent re-add
        self.assertTrue(tracker.add_dir("/base/root/sub1"))
        self.assertTrue(tracker.add_dir("/base/root/sub1"))
        self.assertIn("sub1" + os.sep, tracker)

        # Nested subdirectory when parent already exists
        self.assertTrue(tracker.add_dir("/base/root/sub1/deep1"))
        self.assertIn("deep1" + os.sep, tracker["sub1" + os.sep])

        # Nested subdirectory when parent does not yet exist
        self.assertTrue(tracker.add_dir("/base/root/sub2/deep2"))
        self.assertIn("sub2" + os.sep, tracker)
        self.assertIn("deep2" + os.sep, tracker["sub2" + os.sep])

        # Add file directly in base and in nested subdirectory
        self.assertTrue(tracker.add_file("/base/root/topfile"))
        self.assertEqual(tracker["topfile"], "/base/root/topfile")

        self.assertTrue(tracker.add_file("/base/root/sub3/nestedfile"))
        self.assertEqual(
            tracker["sub3" + os.sep]["nestedfile"],
            "/base/root/sub3/nestedfile",
        )

        # Collection protocol methods
        tracker["manual"] = "val"
        self.assertEqual(tracker["manual"], "val")
        self.assertEqual(
            list(iter(tracker)),
            ["sub1/", "sub2/", "topfile", "sub3/", "manual"],
        )
        self.assertEqual(
            list(reversed(tracker)),
            ["manual", "sub3/", "topfile", "sub2/", "sub1/"],
        )
