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
"""
import datetime
import time as pytime

from tbdedup.utils import time

from tests import base


class TestUtilsTimeTracker(base.TestCase):

    def test_create(self):
        expected_name = "foo"
        time_tracker = time.TimeTracker(expected_name)

        self.assertEqual(expected_name, time_tracker.name)
        self.assertIsNone(time_tracker.start)
        self.assertIsNone(time_tracker.end)
        self.assertIsNone(time_tracker.duration)

    def test_record(self):
        time_tracker = time.TimeTracker("test-record-log")
        time_tracker.start = datetime.datetime.utcnow()
        expected_seconds = 50
        time_tracker.end = time_tracker.start + datetime.timedelta(seconds=expected_seconds)
        time_tracker.record_log()
        self.assertEqual(
            expected_seconds,
            time_tracker.duration.total_seconds(),
        )

    def test_with(self):
        expected_duration = 1
        time_tracker = time.TimeTracker("test-with")
        with time_tracker:
            # Sleep isn't precise; it is at least as long as method
            pytime.sleep(expected_duration)
        self.assertEqual(
            expected_duration,
            int(time_tracker.duration.total_seconds()),  # round it for slip
        )
