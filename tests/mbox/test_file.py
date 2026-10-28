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
import datetime
import ddt
import os
import os.path

from thunderbirddedup import (
    db
)
from thunderbirddedup.mbox import (
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
            storage.close()

    def test_buildSummary_sender_envelope_and_colon_in_body(self):
        with base.KeepLocalDirClean() as cwd:
            mbox_file = os.path.join(cwd.temp_dir.name, "sender_envelope_mbox")
            raw_content = (
                b"From user@example.com Mon Jan 01 00:00:00 2024\n"
                b"X-Mozilla-Status: 0001\n"
                b"Subject: First message\n"
                b"\n"
                b"Note: This body line has a colon right after the blank line!\n"
                b">From - Escaped body line that should not split the message\n"
                b"\n"
                b"From another@example.com Tue Jan 02 00:00:00 2024\n"
                b"X-Mozilla-Status: 0009\n"
                b"Subject: Second message\n"
                b"\n"
                b"Second body\n"
            )
            with open(mbox_file, "wb") as f:
                f.write(raw_content)

            mb = mboxfile.Mailbox(None, mbox_file)
            msgs = list(mb.buildSummary())
            self.assertEqual(len(msgs), 2)
            self.assertNotIn("Note", msgs[0].headers)
            self.assertIn(b"Note: This body line has a colon", msgs[0].getData("body"))
            self.assertIn(b">From - Escaped body line", msgs[0].getData("body"))
            self.assertEqual(msgs[0].getMozillaStatus(), 0x0001)
            self.assertEqual(msgs[1].getMozillaStatus(), 0x0009)

    def test_buildSummary_no_blank_line_before_from_and_from_in_body_sentence(self):
        with base.KeepLocalDirClean() as cwd:
            mbox_file = os.path.join(cwd.temp_dir.name, "no_blank_sep_mbox")
            # Message 1 has no extra blank line before Message 2's From line,
            # and contains a sentence starting with 'From the desk of...'
            # Message 2 is an identical copy of Message 1 at EOF with a trailing blank line
            raw_content = (
                b"From - Mon Jan 01 00:00:00 2024\n"
                b"Message-ID: <same-id@example.com>\n"
                b"Subject: Tightly packed\n"
                b"\n"
                b"From the desk of Alice: hello!\n"
                b"From - Tue Jan 02 00:00:00 2024\n"
                b"Message-ID: <same-id@example.com>\n"
                b"Subject: Tightly packed\n"
                b"\n"
                b"From the desk of Alice: hello!\n"
                b"\n"
            )
            with open(mbox_file, "wb") as f:
                f.write(raw_content)

            mb = mboxfile.Mailbox(None, mbox_file)
            msgs = list(mb.buildSummary())
            self.assertEqual(len(msgs), 2)
            self.assertEqual(
                msgs[0].getHash(diskHash=False),
                msgs[1].getHash(diskHash=False),
            )

    def test_buildSummary_empty_and_invalid_and_unquoted_boundary(self):
        with base.KeepLocalDirClean() as cwd:
            empty_file = os.path.join(cwd.temp_dir.name, "empty_mbox")
            with open(empty_file, "wb"):
                pass
            mb_empty = mboxfile.Mailbox(None, empty_file)
            with self.assertRaises(mboxfile.ErrEmptyFile):
                list(mb_empty.buildSummary())

            invalid_file = os.path.join(cwd.temp_dir.name, "invalid_mbox")
            with open(invalid_file, "wb") as f:
                f.write(b"Not a valid From line\n")
            mb_invalid = mboxfile.Mailbox(None, invalid_file)
            with self.assertRaises(mboxfile.ErrInvalidFileFormat):
                list(mb_invalid.buildSummary())

            boundary_file = os.path.join(cwd.temp_dir.name, "boundary_mbox")
            with open(boundary_file, "wb") as f:
                f.write(
                    b"From - Mon Jan 01 00:00:00 2024\r\n"
                    b"Content-Type: multipart/mixed;\r\n"
                    b" boundary=unquoted_boundary_123\r\n"
                    b"Subject: Boundary test\r\n"
                    b"--unquoted_boundary_123\r\n"
                    b"Body content inside boundary\r\n"
                    b"\r\n"
                    b"From - Tue Jan 02 00:00:00 2024\r\n"
                    b"Subject: Second msg\r\n"
                    b"\r\n"
                    b"Second body\r\n"
                )
            mb_boundary = mboxfile.Mailbox(None, boundary_file)
            mb_boundary.debug_enabled = True
            msgs = list(mb_boundary.buildSummary())
            self.assertEqual(len(msgs), 2)

            # Test getMessageFromFile edge cases (empty file, zero length, negative length)
            self.assertEqual(
                mboxfile.Mailbox.getMessageFromFile(
                    {"location": empty_file, "messageid": 0, "start_offset": 0, "end_offset": 10}
                ),
                b"",
            )
            self.assertEqual(
                mboxfile.Mailbox.getMessageFromFile(
                    {"location": boundary_file, "messageid": 0, "start_offset": 5, "end_offset": 5}
                ),
                b"",
            )
            with self.assertRaises(mboxfile.ErrInvalidRecordLength):
                mboxfile.Mailbox.getMessageFromFile(
                    {"location": boundary_file, "messageid": 0, "start_offset": 10, "end_offset": 5}
                )
