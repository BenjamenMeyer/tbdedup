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
import ddt
import os
import os.path

from tbdedup import (
    db
)
from tbdedup.mbox import (
    mboxfile,
    mboxmessage,
)

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
        ("> From", False, 10, False, mboxfile.Mailbox.MBOXRD),  # MBOXRD
        ("From", False, 10, False, mboxfile.Mailbox.MBOXO),  # MBOXO
        ("> From", True, 10, False, mboxfile.Mailbox.MBOXCL),  # MBOXCL
        ("From", True, 10, False, mboxfile.Mailbox.MBOXCL2),  # MBOXCL2
        ("> From", False, 10, True, mboxfile.Mailbox.MBOXRD),  # MBOXRD + Boundaries
        ("From", False, 10, True, mboxfile.Mailbox.MBOXO),  # MBOXO + Boundaries
        ("> From", True, 10, True, mboxfile.Mailbox.MBOXCL),  # MBOXCL + Boundaries
        ("From", True, 10, True, mboxfile.Mailbox.MBOXCL2),  # MBOXCL2 + Boundaries
        ("From", True, 1005, True, mboxfile.Mailbox.MBOXCL2),  # MBOXCL2 + Boundaries
    )
    @ddt.unpack
    def test_detect_mbox_type(
        self,
        from_line_format, has_content_length,
        email_count, use_content_boundary,
        expected_format,
    ):

        with base.KeepLocalDirClean() as cwd:
            mbox_file = os.path.join(
                cwd.temp_dir.name,
                # cwd.cwd,  # use this for debugging
                base.generate_mbox_filename(expected_format, use_content_boundary),
            )
            base.EmailGenerator.GenerateMboxFile(
                mbox_file,
                email_count,
                from_line_format,
                has_content_length,
                use_content_boundary,
            )

            detected_format = mboxfile.Mailbox.detect_mbox_type(mbox_file)
            self.assertEqual(detected_format, expected_format)

    @ddt.data(
        (0, "FROM", 0, False),
        (0, "FROM", 0, True),
    )
    @ddt.unpack
    def test_parseBoundaryMarker(
        self,
        input_index, input_from_line_format, input_previous_file_location,
        input_has_boundary,
    ):
        with base.KeepLocalDirClean() as cwd:
            # generat an email
            email_headers, email_body, expected_boundary = base.EmailGenerator.generate_email(
                input_index,
                True,
                input_has_boundary,
            )
            # convert the email to a string
            dt = datetime.datetime.utcnow()
            from_line = f"{input_from_line_format} - {base.EmailGenerator.generate_date(dt)}"
            email_record_data = base.EmailGenerator.email_to_string(
                from_line,
                email_headers,
                email_body,
            )
            # convert email string to a list of individual lines
            email_lines = email_record_data.split('\n')
            currentRecord = mboxmessage.Message(
                input_index,
                email_lines[0],  # should match from_line
                input_previous_file_location,
            )
            mb = mboxfile.Mailbox(None, None)

            for ln in email_lines:
                isFrom = mb.mboxMessageStart.match(ln)
                isHeader = mb.mboxHeaderStart.match(ln)

                if isFrom:
                    continue

                if isHeader:
                    hKey = isHeader.groups()[0]
                    hValue = isHeader.groups()[1]
                    currentRecord.addData(hKey, bytes(ln, 'utf-8'))
                    if hKey.lower() == "content-length":
                        currentRecord.setContentLength(hValue)
                    continue

                currentRecord.addData('body', bytes(ln, 'utf-8'))

            result = mb.parseBoundaryMarker(currentRecord, 'Content-Type')
            self.assertEqual(result, expected_boundary)

    @ddt.data(
        ("From", False, 10, False, mboxfile.Mailbox.MBOXRD, False),  # MBOXRD
        ("From", False, 10, False, mboxfile.Mailbox.MBOXO, False),  # MBOXO
        ("From", True, 10, False, mboxfile.Mailbox.MBOXCL, False),  # MBOXCL
        ("From", True, 10, False, mboxfile.Mailbox.MBOXCL2, False),  # MBOXCL2
        ("From", False, 10, True, mboxfile.Mailbox.MBOXRD, False),  # MBOXRD + Boundaries
        ("From", False, 10, True, mboxfile.Mailbox.MBOXO, False),  # MBOXO + Boundaries
        ("From", True, 10, True, mboxfile.Mailbox.MBOXCL, False),  # MBOXCL + Boundaries
        ("From", True, 10, True, mboxfile.Mailbox.MBOXCL2, False),  # MBOXCL2 + Boundaries
        ("From", True, 1005, True, mboxfile.Mailbox.MBOXCL2, True),  # MBOXCL2 + Boundaries
    )
    @ddt.unpack
    def test_buildSummary(
        self,
        from_line_format, has_content_length,
        email_count, use_content_boundary,
        mbox_file_format, with_debug_enabled,
    ):
        with base.KeepLocalDirClean() as cwd:
            mbox_file = os.path.join(
                cwd.temp_dir.name,
                # cwd.cwd,  # use this for debugging
                base.generate_mbox_filename(mbox_file_format, use_content_boundary),
            )
            # generat an email
            base.EmailGenerator.GenerateMboxFile(
                mbox_file,
                email_count,
                from_line_format,
                has_content_length,
                use_content_boundary,
            )
            mb = mboxfile.Mailbox(None, mbox_file)

            msgs = []
            for msg in mb.buildSummary():
                msgs.append(msg)

            self.assertEqual(len(msgs), email_count)

    @ddt.data(
        ("From", False, 10, False, mboxfile.Mailbox.MBOXRD, False),  # MBOXRD
        ("From", False, 10, False, mboxfile.Mailbox.MBOXO, False),  # MBOXO
        ("From", True, 10, False, mboxfile.Mailbox.MBOXCL, False),  # MBOXCL
        ("From", True, 10, False, mboxfile.Mailbox.MBOXCL2, False),  # MBOXCL2
        ("From", False, 10, True, mboxfile.Mailbox.MBOXRD, False),  # MBOXRD + Boundaries
        ("From", False, 10, True, mboxfile.Mailbox.MBOXO, False),  # MBOXO + Boundaries
        ("From", True, 10, True, mboxfile.Mailbox.MBOXCL, False),  # MBOXCL + Boundaries
        ("From", True, 10, True, mboxfile.Mailbox.MBOXCL2, False),  # MBOXCL2 + Boundaries
        ("From", True, 1005, True, mboxfile.Mailbox.MBOXCL2, True),  # MBOXCL2 + Boundaries
    )
    @ddt.unpack
    def test_getMessageFromFile(
        self,
        from_line_format, has_content_length,
        email_count, use_content_boundary,
        mbox_file_format, with_debug_enabled,
    ):
        with base.KeepLocalDirClean() as cwd:
            mbox_file = os.path.join(
                cwd.temp_dir.name,
                # cwd.cwd,  # use this for debugging
                base.generate_mbox_filename(mbox_file_format, use_content_boundary),
            )
            # generat an email
            base.EmailGenerator.GenerateMboxFile(
                mbox_file,
                email_count,
                from_line_format,
                has_content_length,
                use_content_boundary,
            )
            storage = db.MessageDatabase(None)
            mb = mboxfile.Mailbox(storage, mbox_file)

            for msg in mb.buildSummary():
                storage.add_message(
                    msg.getHash(diskHash=False),  # hash for comparisons
                    msg.getMsgId(),  # id
                    mbox_file,  # location
                    msg.getMessageIDHeader(),  # 2nd id from the headers
                    msg.getMessageIDHeaderHash(),  # 2nd hash
                    msg.start_offset,
                    msg.end_offset,
                    msg.getHash(diskHash=True),  # hash to ensure we read the right thing
                )

            msg_data = []
            for unique_hashid in storage.get_message_hashes(
                use_disk=True
            ):
                for msg_for_hash in storage.get_messages_by_hash(
                    unique_hashid,
                    use_disk=True,
                ):
                    msgData = mboxfile.Mailbox.getMessageFromFile(msg_for_hash)
                    msg_data.append(msgData)

            self.assertEqual(len(msg_data), email_count)
