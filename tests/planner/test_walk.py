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
    walk,
)

from tests import base


class TestAsyncRunner(base.AsyncioTestCase):

    async def test_null(self):
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                folder_pattern="Inbox.sbd",
            )
            with base.KeepLocalDirClean():
                # this method doesn't return anything to be checked
                # and everything it does will be tested elsewhere
                # so just ignore anything
                await walk.asyncPreplanner(the_options)


@ddt.ddt
class TestPreplannerFileManager(base.TestCase):

    @ddt.data(
        (
            "foo",
        ),
        (
            "bar",
        ),
    )
    @ddt.unpack
    def test_init(self, location):
        pfm = walk.PreplannerFileManager(location)
        self.assertIsNone(pfm.combinatory)
        self.assertEqual(pfm.files, [])
        self.assertEqual(pfm.location, location)

    @ddt.data(
        (
            "bra",
            [],
            [],
        ),
        (
            "braz",
            ["zarb",],
            ["zarb",],
        ),
        (
            "braz",
            ["zarb", "arb", "rb", "b"],
            ["zarb", "arb", "rb", "b"],
        ),
    )
    @ddt.unpack
    def test_add_file(self, location, files, expected_files):
        pfm = walk.PreplannerFileManager(location)
        for f in files:
            pfm.add_file(f)
        self.assertIsNone(pfm.combinatory)
        self.assertEqual(pfm.location, location)
        self.assertEqual(pfm.files, expected_files)

    @ddt.data(
        (
            "foo",
            [],
            None,
            "\n".join(
                [
                    '{',
                    '"location": "foo",',
                    '"files": [],',
                    '"combinatory": null',
                    '}',
                ]
            ),
        ),
    )
    @ddt.unpack
    def test_json_encode(self, location, files, combinatory, expected_json_string):
        pfm = walk.PreplannerFileManager(location)
        pfm.files = files
        pfm.combinatory = combinatory
        json_string = json.dumps(
            pfm,
            indent=0,
            sort_keys=False,
            default=lambda __o: __o.__json__() if hasattr(__o, "__json__") else __o
        )
        self.assertEqual(json_string, expected_json_string)


@ddt.ddt
class TestPreplanner(base.AsyncioTestCase):

    def test_init(self):
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                folder_pattern="Inbox.sbd",
            )

            p = walk.Preplanner(the_options)
            self.assertEqual(p.options, the_options)
            self.assertEqual(p.folder_pattern, the_options.folder_pattern)
            self.assertEqual(p.location, location)
            self.assertIsNone(p.output_filename)
            self.assertIn(keys.preplan_location, p.preplanner)
            self.assertEqual(
                p.preplanner[keys.preplan_location],
                location,
            )
            self.assertIn(keys.preplan_planning, p.preplanner)
            self.assertDictEqual(
                p.preplanner[keys.preplan_planning],
                {},
            )

    @ddt.data(
        ({}, "foo", False),
        ({"bar": "foo"}, "bar", True),
    )
    @ddt.unpack
    def test_has_file(self, input_preplan, check_file, expected_result):
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                folder_pattern="Inbox.sbd",
            )

            p = walk.Preplanner(the_options)
            p.preplanner[keys.preplan_planning] = input_preplan

            result = p.has_file(check_file)
            self.assertEqual(result, expected_result)

    @ddt.data(
        (
            "foo", "bar", "fallacy",
        ),
    )
    @ddt.unpack
    def test_init_file(self, input_rootfile, input_location, input_absfile):
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                folder_pattern="Inbox.sbd",
            )

            p = walk.Preplanner(the_options)
            self.assertFalse(p.has_file(input_rootfile))

            p.init_file(input_rootfile, input_location, input_absfile)
            self.assertTrue(p.has_file(input_rootfile))

    @ddt.data(
        (
            "foo_foo",
            "foo_bar",
        ),
    )
    @ddt.unpack
    def test_append_file(self, input_rootfile, input_absfile):
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                folder_pattern="Inbox.sbd",
            )

            p = walk.Preplanner(the_options)
            p.init_file(input_rootfile, "bar_foo", "bar_bar")
            self.assertNotIn(
                input_absfile,
                p.preplanner[keys.preplan_planning][input_rootfile].files,
            )
            p.append_file(input_rootfile, input_absfile)
            self.assertIn(
                input_absfile,
                p.preplanner[keys.preplan_planning][input_rootfile].files,
            )

    def test_plans(self):
        with tempfile.TemporaryDirectory() as location:
            # leave the directory empty so the test is quick and
            # the result is predictable - as long as it runs it's good
            the_options = base.GenericOptions(
                location=location,
                folder_pattern="Inbox.sbd",
            )

            p = walk.Preplanner(the_options)

            plan_set = {
                f"root_{i:03}": f"abs_{i:03}"
                for i in range(1, 100)
            }
            for k, v in plan_set.items():
                p.init_file(
                    k,
                    location,
                    os.path.join(location, v),
                )

            self.assertEqual(len(plan_set), p.plan_count())
            for root_file, plan in p.plans():
                self.assertIn(root_file, plan_set)
                self.assertIn(
                    os.path.join(
                        location,
                        plan_set[root_file],
                    ),
                    plan.files
                )

    @ddt.data(
        (0, 0,),
        (5, 0,),
        (5, 2,),
    )
    @ddt.unpack
    async def test_preplan(self, input_file_count, max_sub_file_counts):
        with tempfile.TemporaryDirectory() as location:
            with base.KeepLocalDirClean():
                # leave the directory empty so the test is quick and
                # the result is predictable - as long as it runs it's good
                folder_pattern = "Inbox.sbd"
                the_options = base.GenericOptions(
                    location=location,
                    folder_pattern=folder_pattern,
                )

                p = walk.Preplanner(the_options)

                mboxfiles = []
                base_location = os.path.join(
                    location,
                    folder_pattern,
                )
                os.makedirs(
                    base_location,
                    exist_ok=True,
                )
                base_files = {}
                for i in range(0, input_file_count):
                    basename = f"index_{i:010}.junk"
                    fname = os.path.join(base_location, basename)
                    with open(fname, "wt") as fwriter:
                        fwriter.write(f"{i:010}")
                    mboxfiles.append(fname)

                    fkey = os.path.join(
                        folder_pattern,
                        basename,
                    )
                    base_files[fkey] = [
                        fname,
                    ]

                    recursive_location = os.path.join(
                        base_location,
                        folder_pattern,
                    )
                    if max_sub_file_counts > 0:
                        for j in range(random.randrange(0, max_sub_file_counts)):
                            os.makedirs(
                                recursive_location,
                                exist_ok=True,
                            )
                            sfname = os.path.join(
                                recursive_location,
                                basename,
                            )
                            with open(sfname, "wt") as sfwriter:
                                sfwriter.write(f"{i:010}.{j:010}")
                            mboxfiles.append(sfname)
                            base_files[fkey].append(
                                sfname,
                            )
                            recursive_location = os.path.join(
                                recursive_location,
                                folder_pattern,
                            )

                self.assertIsNone(p.output_filename)
                preplanner = await p.preplan(mboxfiles)
                self.assertIsNotNone(p.output_filename)

                generated_sets = p.preplanner[keys.preplan_planning]
                self.assertEqual(
                    list(p.preplanner[keys.preplan_planning].keys()),
                    list(base_files.keys()),
                )
                for bf_key, bf_value in base_files.items():
                    self.assertEqual(
                        p.preplanner[keys.preplan_planning][bf_key].files,
                        bf_value,
                    )

                self.assertTrue(os.path.isfile(p.output_filename))

                json_string = json.dumps(
                    p.preplanner,
                    indent=4,
                    sort_keys=False,
                    default=lambda __o: __o.__json__() if hasattr(__o, "__json__") else __o
                )
                with open(p.output_filename, "rt") as json_input:
                    json_data = json_input.read()
                    self.assertEqual(json_string, json_data)

                print(f"json data: {json_string}")
