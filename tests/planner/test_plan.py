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
import asyncio
import ddt
import datetime
import json
import os.path
import random
import tempfile
from unittest import mock

from tbdedup.planner import (
    keys,
    plan,
    # walk,
)

from tests import base


@ddt.ddt
class TestAsyncRunner(base.AsyncioTestCase):

    async def test_null(self):
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                limit_pattern=None,
            )
            with base.KeepLocalDirClean():
                # this method doesn't return anything to be checked
                # and everything it does will be tested elsewhere
                # so just ignore anything
                await plan.asyncPlanner(the_options)

    @ddt.data(
        (0, ),
        (1, ),
        (10, ),
    )
    @ddt.unpack
    async def test_generator(self, match_count):
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                limit_pattern=None,
            )
            with base.KeepLocalDirClean() as runner_dir:
                output_directory = os.path.join(
                    runner_dir.temp_dir.name,
                    "output",
                )
                os.makedirs(
                    output_directory,
                    exist_ok=True,
                )
                matched_files = []
                file_mapping = {
                    keys.plan_file_map: {}
                }

                home_directory = os.path.join(
                    location,
                    "home",
                )
                os.makedirs(
                    home_directory,
                    exist_ok=True,
                )
                for index in range(match_count):
                    mname = os.path.join(
                        home_directory,
                        f"matched_file_{index:010}",
                    )
                    with open(mname, "wt") as mwriter:
                        mwriter.write(f"{index:010}")
                    matched_files.append(mname)

                self.assertNotIn(keys.plan_counter, file_mapping)
                self.assertNotIn(keys.plan_map_file, file_mapping)
                await plan.generate(
                    output_directory,
                    matched_files,
                    file_mapping,
                )
                self.assertIn(keys.plan_counter, file_mapping)
                self.assertIn(keys.plan_map_file, file_mapping)
                self.assertTrue(
                    os.path.isfile(
                        file_mapping[keys.plan_map_file],
                    ),
                )
                self.assertEqual(
                    file_mapping[keys.plan_counter],
                    match_count,
                )
                self.assertEqual(
                    file_mapping[keys.plan_counter],
                    len(matched_files),
                )

                for linked_file, linked_source in file_mapping[keys.plan_file_map].items():
                    full_linked_file = os.path.join(
                        output_directory,
                        linked_file,
                    )
                    self.assertTrue(os.path.islink(full_linked_file))
                    self.assertTrue(os.path.isfile(linked_source))
                    self.assertFalse(os.path.islink(linked_source))
                    self.assertTrue(
                        os.path.samefile(
                            full_linked_file,
                            linked_source,
                        )
                    )
                    self.assertIn(
                        linked_source,
                        matched_files,
                    )

                json_string = json.dumps(
                    file_mapping,
                    indent=4,
                    sort_keys=False,
                    default=lambda __o: __o.__json__() if hasattr(__o, "__json__") else __o
                )

                with open(file_mapping[keys.plan_map_file], "rt") as json_input:
                    json_data = json_input.read()
                    self.assertEqual(json_data, json_string)

    async def test_generator_raises(self):
        match_count = 10
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                limit_pattern=None,
            )
            with base.KeepLocalDirClean() as runner_dir:
                output_directory = os.path.join(
                    runner_dir.temp_dir.name,
                    "output",
                )
                os.makedirs(
                    output_directory,
                    exist_ok=True,
                )
                matched_files = []
                file_mapping = {
                    keys.plan_file_map: {}
                }

                home_directory = os.path.join(
                    location,
                    "home",
                )
                os.makedirs(
                    home_directory,
                    exist_ok=True,
                )
                for index in range(match_count):
                    mname = os.path.join(
                        home_directory,
                        f"matched_file_{index:010}",
                    )
                    mlname = os.path.join(
                        output_directory,
                        f"{index:06}.mbox",
                    )
                    with open(mname, "wt") as mwriter:
                        mwriter.write(f"{index:010}")
                    with open(mlname, "wt") as mlwriter:
                        mlwriter.write(f"cause failure - {index:06}")
                    matched_files.append(mname)

                self.assertNotIn(keys.plan_counter, file_mapping)
                self.assertNotIn(keys.plan_map_file, file_mapping)
                with self.assertRaises(plan.GenerationError):
                    await plan.generate(
                        output_directory,
                        matched_files,
                        file_mapping,
                    )
                self.assertNotIn(keys.plan_counter, file_mapping)
                self.assertNotIn(keys.plan_map_file, file_mapping)

    async def test_planner_limit_pattern_error(self):
        match_count = 10
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                limit_pattern=r'$(^',
            )
            with base.KeepLocalDirClean() as runner_dir:
                with self.assertRaises(plan.LimitPatternError):
                    await plan.planner(the_options, [])

    @ddt.data(
        (0, None),
        (1, None),
        (10, None),
        (0, r".*file_[0-9]*.*"),
        (1, r".*file_[0-9]*.*"),
        (10, r".*file_[0-9]*.*"),
    )
    @ddt.unpack
    async def test_planner(self, match_count, input_pattern):
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                limit_pattern=input_pattern,
            )
            with base.KeepLocalDirClean() as runner_dir:
                matched_files = []
                home_directory = os.path.join(
                    location,
                    "home",
                )
                os.makedirs(
                    home_directory,
                    exist_ok=True,
                )
                for index in range(match_count):
                    mname = os.path.join(
                        home_directory,
                        f"file_{index:010}",
                    )
                    with open(mname, "wt") as mwriter:
                        mwriter.write(f"{index:010}")
                    matched_files.append(mname)

                output_directory, mapping_file = await plan.planner(
                    the_options,
                    matched_files,
                )
                self.assertTrue(
                    os.path.isdir(output_directory),
                )
                self.assertIsNotNone(mapping_file)
                self.assertTrue(
                    os.path.isfile(
                        mapping_file,
                    ),
                )
                with open(mapping_file, "rt") as json_input:
                    json_data = json_input.read()
                    print(f"JSON Data: {json_data}")
                    file_mapping = json.loads(json_data)

                    self.assertIn(keys.plan_counter, file_mapping)
                    self.assertIn(keys.plan_map_file, file_mapping)
                    self.assertEqual(
                        mapping_file,
                        file_mapping[keys.plan_map_file],
                    )
                    self.assertEqual(
                        file_mapping[keys.plan_counter],
                        match_count,
                    )
                    self.assertEqual(
                        file_mapping[keys.plan_counter],
                        len(matched_files),
                    )
                    for linked_file, linked_source in file_mapping[keys.plan_file_map].items():
                        full_linked_file = os.path.join(
                            output_directory,
                            linked_file,
                        )
                        self.assertTrue(os.path.islink(full_linked_file))
                        self.assertTrue(os.path.isfile(linked_source))
                        self.assertFalse(os.path.islink(linked_source))
                        self.assertTrue(
                            os.path.samefile(
                                full_linked_file,
                                linked_source,
                            )
                        )
                        self.assertIn(
                            linked_source,
                            matched_files,
                        )
