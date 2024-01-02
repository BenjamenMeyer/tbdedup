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

from tbdedup.mbox import mboxfile

from tests import base


@ddt.ddt
class TestMboxMailbox(base.TestCase):

    def test_init(self):
        the_db = "some db"
        the_file = "some file"

        mb = mboxfile.Mailbox(the_db, the_file)
        self.assertEqual(mb.db, the_db)
        self.assertEqual(mb.filename, the_file)

    @ddt.data(
        ("> From", False, False, mboxfile.Mailbox.MBOXRD),  # MBOXRD
        ("From", False, False, mboxfile.Mailbox.MBOXO),  # MBOXO
        ("> From", True, False, mboxfile.Mailbox.MBOXCL),  # MBOXCL
        ("From", True, False, mboxfile.Mailbox.MBOXCL2),  # MBOXCL2
        ("> From", False, True, mboxfile.Mailbox.MBOXRD),  # MBOXRD + Boundaries
        ("From", False, True, mboxfile.Mailbox.MBOXO),  # MBOXO + Boundaries
        ("> From", True, True, mboxfile.Mailbox.MBOXCL),  # MBOXCL + Boundaries
        ("From", True, True, mboxfile.Mailbox.MBOXCL2),  # MBOXCL2 + Boundaries
    )
    @ddt.unpack
    def test_detect_mbox_type(
        self,
        from_line_format, has_content_length,
        use_content_boundary,
        expected_format,
    ):
        def generate_mbox_filename():
            generated_name = "mbox_format_mbox"
            if expected_format == mboxfile.Mailbox.MBOXO:
                generated_name = generated_name + "o"
            elif expected_format == mboxfile.Mailbox.MBOXRD:
                generated_name = generated_name + "rd"
            elif expected_format == mboxfile.Mailbox.MBOXCL:
                generated_name = generated_name + "cl"
            elif expected_format == mboxfile.Mailbox.MBOXCL2:
                generated_name = generated_name + "cl2"
            else:
                # unknown format
                generated_name = generated_name + "u"

            if use_content_boundary:
                generated_name = generated_name + "_content_boundary"

            return generated_name

        with base.KeepLocalDirClean() as cwd:
            mbox_file = os.path.join(
                cwd.temp_dir.name,
                # cwd.cwd,  # use this for debugging
                generate_mbox_filename(),
            )
            base.GenerateMboxFile(
                mbox_file,
                10,
                from_line_format,
                has_content_length,
                use_content_boundary,
            )

            detected_format = mboxfile.Mailbox.detect_mbox_type(mbox_file)
            self.assertEqual(detected_format, expected_format)
