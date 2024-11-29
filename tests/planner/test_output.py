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
import ddt
import datetime
from unittest import mock

from tbdedup.planner import output

from tests import base


@ddt.ddt
class TestPlannerOutput(base.TestCase):

    @ddt.data(
        (
            datetime.datetime.fromisoformat('2011-11-04 00:05:23.283+00:00'),  # 20111104_000523
            "foo",
            "",
            0,
            "20111104_000523_foo",
        ),
        (
            datetime.datetime.fromisoformat('2011-11-04 00:05:23.283+00:00'),  # 20111104_000523
            "foo",
            "bar",
            0,
            "20111104_000523_foo.bar",
        ),
        (
            datetime.datetime.fromisoformat('2011-11-04 00:05:23.283+00:00'),  # 20111104_000523
            "foo",
            "",
            1,
            "20111104_000523_001_foo",
        ),
        (
            datetime.datetime.fromisoformat('2011-11-04 00:05:23.283+00:00'),  # 20111104_000523
            "foo",
            "bar",
            2,
            "20111104_000523_002_foo.bar",
        ),
    )
    @ddt.unpack
    def test_generate_name(
        self,
        input_time, input_name, input_ext, input_counter,
        expected_result,
    ):
        result = output.generate_name(
            input_time,
            input_name,
            input_ext,
            input_counter,
        )
        self.assertEqual(result, expected_result)

    @ddt.data(
        (
            10000,
            datetime.datetime.fromisoformat('2011-11-04 00:05:23.283+00:00'),  # 20111104_000523
            [False,],
            "20111104_000523_dedup_preplanner.json",
            False,
        ),
        (
            10000,
            datetime.datetime.fromisoformat('2011-11-04 00:05:23.283+00:00'),  # 20111104_000523
            [True, False, ],
            "20111104_000523_001_dedup_preplanner.json",
            False,
        ),
        (
            3,
            datetime.datetime.fromisoformat('2011-11-04 00:05:23.283+00:00'),  # 20111104_000523
            [
                True
                for _ in range(30)
            ],
            "20111104_000523_001_dedup_preplanner.json",
            True,
        )
    )
    @ddt.unpack
    def test_get_filename(
        self,
        input_max_counter, input_time, input_path_exists,
        expected_output, expected_exception
    ):
        with mock.patch(
            "tbdedup.planner.output.utcnow"
        ) as mock_time:
            mock_time.return_value = input_time
            with mock.patch(
                "os.path.exists",
            ) as mock_path_exists:
                mock_path_exists.side_effect = input_path_exists
                with base.ValueSwap(
                    output,
                    "max_looping",
                    input_max_counter,
                ):
                    try:
                        result = output.get_filename()
                    except Exception as ex:
                        if expected_exception:
                            self.assertIsInstance(ex, output.ExcessiveLoopError)
                        else:
                            self.assertTrue(False, msg="Unexpected exception received")
                    else:
                        self.assertEqual(result, expected_output)

    @ddt.data(
        (
            10000,
            datetime.datetime.fromisoformat('2011-11-04 00:05:23.283+00:00'),  # 20111104_000523
            [None, ],
            "20111104_000523_dedup_planner",
            False,
        ),
        (
            10000,
            datetime.datetime.fromisoformat('2011-11-04 00:05:23.283+00:00'),  # 20111104_000523
            [FileExistsError, None, ],
            "20111104_000523_001_dedup_planner",
            False,
        ),
        (
            3,
            datetime.datetime.fromisoformat('2011-11-04 00:05:23.283+00:00'),  # 20111104_000523
            [
                FileExistsError
                for _ in range(30)
            ],
            "20111104_000523_001_dedup_planner",
            True,
        )
    )
    @ddt.unpack
    def test_get_directory(
        self,
        input_max_counter, input_time, input_dir_exists,
        expected_output, expected_exception
    ):
        with mock.patch(
            "tbdedup.planner.output.utcnow"
        ) as mock_time:
            mock_time.return_value = input_time
            with mock.patch(
                "os.mkdir",
            ) as mock_dir_exists:
                mock_dir_exists.side_effect = input_dir_exists
                with base.ValueSwap(
                    output,
                    "max_looping",
                    input_max_counter,
                ):
                    try:
                        result = output.get_directory()
                    except Exception as ex:
                        if expected_exception:
                            self.assertIsInstance(ex, output.ExcessiveLoopError)
                        else:
                            self.assertTrue(False, msg=f"Unexpected exception received - {ex}")
                    else:
                        self.assertEqual(result, expected_output)
