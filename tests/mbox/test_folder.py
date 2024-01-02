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
import os
import os.path
import random
from unittest import mock

from tbdedup.mbox import mboxfolder

from tests import base


@ddt.ddt
class TestMboxFolder(base.AsyncioTestCase):

    def test_init(self):
        with base.KeepLocalDirClean() as cwd:
            fname = cwd.temp_dir.name
            mf = mboxfolder.MailboxFolder(fname)
            self.assertEqual(mf.foldername, fname)

    @ddt.data(
        (0, 1),
        (1, 0),
        (1, 1),
        (1, 2),
        (20, 0),
        (30, 10),
        (40, 15),
    )
    @ddt.unpack
    async def test_get_mbox_files(self, file_count, dir_count):
        with base.KeepLocalDirClean() as cwd:
            the_cwd = cwd.temp_dir.name
            generated_files = []

            def populate_folder(location, count, with_period=False):
                for index in range(count):
                    if len(generated_files) < file_count or with_period:
                        fname = os.path.join(
                            location,
                            f"{index:030}"
                            if not with_period
                            else f"{index:030}.{index:2}",
                        )
                        with open(fname, "wt") as foutput:
                            foutput.write(f"data for {index:030}")
                        if not with_period:
                            generated_files.append(fname)

            dir_names = []
            for dir_index in range(dir_count):
                dir_name = os.path.join(
                    the_cwd,
                    f"{dir_index:040}",
                )
                os.makedirs(dir_name, exist_ok=True)
                dir_names.append(dir_name)

            # if there are any subdirs then spread some around there
            if len(dir_names):
                copy_dir_names = [
                    dn
                    for dn in dir_names
                ]
                if the_cwd in copy_dir_names:
                    copy_dir_names.remove(the_cwd)

                dir_count_to_use = random.randrange(len(copy_dir_names))
                while dir_count_to_use > 0 and len(copy_dir_names):
                    dn = random.choice(copy_dir_names)
                    dc = random.randrange(
                        (file_count // len(dir_names)) + 1,
                    )
                    if dc > 0:
                        populate_folder(
                            dn,
                            dc,
                        )
                        copy_dir_names.remove(dn)
                    dir_count_to_use = dir_count_to_use - 1
            # put the remaining in the main folder
            populate_folder(the_cwd, file_count)
            populate_folder(the_cwd, 10, with_period=True)

            mf = mboxfolder.MailboxFolder(the_cwd)
            allfiles = await mf.getMboxFiles()
            self.assertEqual(len(allfiles), len(generated_files))
