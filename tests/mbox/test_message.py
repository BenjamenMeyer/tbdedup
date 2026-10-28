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
import ddt
import hashlib
import re
from unittest import mock

from thunderbirddedup.mbox import mboxmessage
from thunderbirddedup.utils import encoder

from tests import base


@ddt.ddt
class TestAtoi(base.TestCase):

    @ddt.data(
        ("9876543210", 9876543210),
        ("  9876543210", 9876543210),
        ("9876543210  ", 9876543210),
        ("   9876543210  ", 9876543210),
    )
    @ddt.unpack
    def test_atoi(self, input_data, expected_result):
        result = mboxmessage.Atoi(input_data)
        self.assertEqual(result, expected_result)


@ddt.ddt
class TestMboxMessage(base.TestCase):

    @ddt.data(
        (123, "FROM Jan 2024", 29395),
    )
    @ddt.unpack
    def test_init(self, input_index, input_from_line, input_start_offset):
        msg = mboxmessage.Message(input_index, input_from_line, input_start_offset)
        self.assertEqual(msg.index, input_index)
        self.assertEqual(msg.getMsgId(), input_index)
        self.assertEqual(msg.fromLine, input_from_line)
        self.assertEqual(msg.start_offset, input_start_offset)
        self.assertEqual(msg.end_offset, input_start_offset)
        self.assertEqual(msg.content_length, 0)
        self.assertDictEqual(msg.headers, {})
        self.assertEqual(msg.lines, [])
        self.assertEqual(msg.rawLines, [input_from_line,])

    @ddt.data(
        (False, False, "body", "foo"),
        (True, False, "nonbody", "bar"),
        (True, True, "nonbody", "bar"),
    )
    @ddt.unpack
    def test_add_data(self, is_header, add_before, input_key, input_data):
        rawLines = ["FROM Jan 2024",]
        msg = mboxmessage.Message(0, rawLines[0], 0)
        self.assertDictEqual(msg.headers, {})
        self.assertEqual(msg.lines, [])
        self.assertEqual(msg.rawLines, rawLines)
        if add_before:
            msg.headers[input_key] = []

        msg.addData(input_key, input_data)
        if is_header:
            self.assertEqual(msg.lines, [])
            self.assertIn(input_key, msg.headers)
            self.assertEqual(msg.headers[input_key], [input_data,])
        else:
            self.assertEqual(msg.lines, [input_data,])
        rawLines.append(input_data)
        self.assertEqual(
            msg.rawLines,
            rawLines,
        )

    @ddt.data(
        (
            [b'foo', b'bar', b'fantasy'],
            {},
            'body',
            b'foobarfantasy',
        ),
        (
            [],
            {
                'foo': [b'bar',],
            },
            'foo',
            b'bar',
        ),
        (
            [],
            {},
            'bar',
            None
        ),
    )
    @ddt.unpack
    def test_get_data(self, prep_lines, prep_headers, input_key, expected_data):
        rawLines = ["FROM Jan 2024",]
        msg = mboxmessage.Message(0, rawLines[0], 0)
        msg.lines = prep_lines
        msg.headers = prep_headers

        result = msg.getData(input_key)
        self.assertEqual(result, expected_data)

    def test_set_content_length(self):
        rawLines = ["FROM Jan 2024",]
        msg = mboxmessage.Message(0, rawLines[0], 0)

        contentLength = 1024
        strContentLength = f" {contentLength} "
        self.assertEqual(msg.content_length, 0)
        msg.setContentLength(strContentLength)
        self.assertEqual(type(msg.content_length), type(contentLength))
        self.assertEqual(msg.content_length, contentLength)

    @ddt.data(
        False,
        True,
    )
    def test_get_message_id_header(self, is_valid):
        rawLines = ["FROM Jan 2024",]
        msg = mboxmessage.Message(0, rawLines[0], 0)
        byteMsgId = b'gorilla gang'

        for y_index in range(20):
            for x_index in range(30):
                msg.addData(f"{y_index:05}", f"{x_index:06}")

        if is_valid:
            msg.addData("MeSsAgE-iD fOr ThUnDeRbIrD", byteMsgId)

        result = msg.getMessageIDHeader()

        if is_valid:
            self.assertEqual(result, byteMsgId.decode('latin1'))
        else:
            self.assertIsNone(result)

    @ddt.data(
        False,
        True,
    )
    def test_get_message_id_header_hash(self, is_valid):
        rawLines = ["FROM Jan 2024",]
        msg = mboxmessage.Message(0, rawLines[0], 0)
        byteMsgId = b'gorilla gang'

        for y_index in range(20):
            for x_index in range(30):
                msg.addData(f"{y_index:05}", f"{x_index:06}")

        if is_valid:
            msg.addData("MeSsAgE-iD fOr ThUnDeRbIrD", byteMsgId)

        result = msg.getMessageIDHeaderHash()

        m = hashlib.sha256()
        m.update(encoder.to_encoding(msg.getMessageIDHeader()))

        self.assertEqual(result, m.hexdigest())

    @ddt.data(
        (None, 0),
        (b"X-Mozilla-Status: 0009\r\n", 0x0009),
        (b"0015", 0x0015),
        (b"X-Mozilla-Status: invalid\r\n", 0),
    )
    @ddt.unpack
    def test_get_mozilla_status(self, header_val, expected_status):
        msg = mboxmessage.Message(0, b"From - Mon Jan 01 00:00:00 2024\r\n", 0)
        if header_val is not None:
            msg.addData("X-Mozilla-Status", header_val)
        self.assertEqual(msg.getMozillaStatus(), expected_status)

    @ddt.data(
        (None, 0),
        (b"X-Mozilla-Status2: 00200000\r\n", 0x00200000),
        (b"10000000", 0x10000000),
        (b"X-Mozilla-Status2: nothex\r\n", 0),
    )
    @ddt.unpack
    def test_get_mozilla_status2(self, header_val, expected_status2):
        msg = mboxmessage.Message(0, b"From - Mon Jan 01 00:00:00 2024\r\n", 0)
        if header_val is not None:
            msg.addData("X-Mozilla-Status2", header_val)
        self.assertEqual(msg.getMozillaStatus2(), expected_status2)

    @ddt.data(
        (None, ""),
        (b"X-Mozilla-Keys:   $label1   $label2  \r\n", "$label1 $label2"),
        (b"X-Mozilla-Keys:                                \r\n", ""),
    )
    @ddt.unpack
    def test_get_mozilla_keys(self, header_val, expected_keys):
        msg = mboxmessage.Message(0, b"From - Mon Jan 01 00:00:00 2024\r\n", 0)
        if header_val is not None:
            msg.addData("X-Mozilla-Keys", header_val)
        self.assertEqual(msg.getMozillaKeys(), expected_keys)

    def test_merge_and_update_mozilla_headers(self):
        messages = [
            {
                "mozilla_status": 0x0009,  # Read | Expunged
                "mozilla_status2": 0x00200000,  # IMAPDeleted
                "mozilla_keys": "$label1 important",
            },
            {
                "mozilla_status": 0x0006,  # Replied | Marked
                "mozilla_status2": 0x10000000,  # Attachment
                "mozilla_keys": "important $label2",
            },
        ]
        status, status2, keys = mboxmessage.Message.mergeMozillaMetadata(messages)
        # 0x0009 | 0x0006 = 0x000f; clearing 0x0008 -> 0x0007 (Read | Replied | Marked)
        self.assertEqual(status, 0x0007)
        # 0x00200000 | 0x10000000 -> clearing 0x00200000 -> 0x10000000
        self.assertEqual(status2, 0x10000000)
        self.assertEqual(keys, "$label1 important $label2")

        raw_msg = (
            b"From - Mon Jan 01 00:00:00 2024\r\n"
            b"X-Mozilla-Status: 0009\r\n"
            b"X-Mozilla-Status2: 00200000\r\n"
            b"X-Mozilla-Keys:                                         \r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"X-Mozilla-Status: 9999\r\n"
            b"Body text\r\n"
        )
        updated = mboxmessage.Message.updateMozillaHeaders(raw_msg, status, status2, keys)
        self.assertIn(b"X-Mozilla-Status: 0007\r\n", updated)
        self.assertIn(b"X-Mozilla-Status2: 10000000\r\n", updated)
        self.assertIn(b"X-Mozilla-Keys: $label1 important $label2", updated)
        # Ensure body line looking like X-Mozilla-Status was not modified
        self.assertIn(b"\r\n\r\nX-Mozilla-Status: 9999\r\n", updated)

        # Also test when the first copy came from an IMAP move and lacked X-Mozilla-* headers
        raw_imap_msg = (
            b"From - Mon Jan 01 00:00:00 2024\n"
            b"Subject: IMAP Moved\n"
            b"\n"
            b"Body text\n"
        )
        updated_imap = mboxmessage.Message.updateMozillaHeaders(
            raw_imap_msg,
            status,
            status2,
            keys,
        )
        self.assertIn(b"X-Mozilla-Status: 0007\n", updated_imap)
        self.assertIn(b"X-Mozilla-Status2: 10000000\n", updated_imap)
        self.assertIn(b"X-Mozilla-Keys: $label1 important $label2\n", updated_imap)
        self.assertEqual(mboxmessage.Message.updateMozillaHeaders(b"", status, status2, keys), b"")

    def test_get_hash(self):
        rawLines = ["FROM Jan 2024",]
        msg = mboxmessage.Message(0, rawLines[0], 0)

        for y_index in range(20):
            for x_index in range(30):
                value = f"{x_index:06}"
                msg.addData(f"{y_index:05}", value)

        for z_index in range(50):
            value = f"line data {z_index:030}"
            msg.addData('body', value)

        msg.addData('X-Mozilla-Status', 'some value')
        msg.addData('X-Mozilla-Status2', 'some other value')
        msg.addData('X-Mozilla-Keys', 'some keyed value')
        msg.addData('X-Account-Key', 'account2')
        msg.addData('X-UIDL', 'uidl123')
        msg.addData('X-Apparently-To', 'some receipient')
        msg.addData('Message-ID', 'some id value')

        non_disk_hash = hashlib.sha256()
        disk_hash = hashlib.sha256()

        # disk hash is just the lines added in order of how they
        # were received by the message object
        for rl in msg.rawLines:
            disk_hash.update(encoder.to_encoding(rl))

        # non-disk hash sorts headers case-insensitively aside from those
        # that are excluded, normalizes CRLF -> LF, and strips trailing blank body lines
        matcher = [
            re.compile(f"^{skipper}", flags=re.I)
            for skipper in mboxmessage.THUNDERBIRD_HEADERS
        ]
        for k, v in sorted(msg.headers.items(), key=lambda kv: kv[0].lower()):
            if any(m.match(k) for m in matcher):
                continue
            for vln in v:
                non_disk_hash.update(
                    encoder.to_encoding(vln).replace(b'\r\n', b'\n')
                )
        # then it adds the body lines
        for ln in msg.lines:
            non_disk_hash.update(
                encoder.to_encoding(ln).replace(b'\r\n', b'\n')
            )

        disk_hash_value = msg.getHash(diskHash=True)
        non_disk_hash_value = msg.getHash(diskHash=False)

        self.assertEqual(disk_hash_value, disk_hash.hexdigest())
        self.assertEqual(non_disk_hash_value, non_disk_hash.hexdigest())

    def test_get_hash_canonicalization_and_message_id(self):
        msg1 = mboxmessage.Message(0, b"From - Mon Jan 01 00:00:00 2024\r\n", 0)
        msg1.addData("Subject", b"Subject: Order Confirmation\r\n")
        msg1.addData("To", b"To: user@example.com\r\n")
        msg1.addData("Message-ID", b"Message-ID: <abc-123@example.com>\r\n")
        msg1.addData("X-Mozilla-Status", b"X-Mozilla-Status: 0001\r\n")
        msg1.addData("X-Account-Key", b"X-Account-Key: account1\r\n")
        msg1.addData("body", b"\r\n")
        msg1.addData("body", b"Thank you for your order.\r\n")
        msg1.addData("body", b"\r\n")

        # Same logical message with LF line endings, different header order, no trailing blank line
        msg2 = mboxmessage.Message(1, b"From - Tue Jan 02 12:34:56 2024\n", 500)
        msg2.addData("Message-ID", b"Message-ID: <abc-123@example.com>\n")
        msg2.addData("To", b"To: user@example.com\n")
        msg2.addData("Subject", b"Subject: Order Confirmation\n")
        msg2.addData("X-Mozilla-Status", b"X-Mozilla-Status: 0009\n")
        msg2.addData("X-UIDL", b"X-UIDL: 9999\n")
        msg2.addData("body", b"\n")
        msg2.addData("body", b"Thank you for your order.\n")

        self.assertEqual(msg1.getHash(diskHash=False), msg2.getHash(diskHash=False))

        # Distinct message with identical Subject/To/body but different Message-ID
        msg3 = mboxmessage.Message(2, b"From - Tue Jan 02 12:34:56 2024\n", 900)
        msg3.addData("Message-ID", b"Message-ID: <xyz-789@example.com>\n")
        msg3.addData("To", b"To: user@example.com\n")
        msg3.addData("Subject", b"Subject: Order Confirmation\n")
        msg3.addData("body", b"\n")
        msg3.addData("body", b"Thank you for your order.\n")

        self.assertNotEqual(
            msg2.getHash(diskHash=False),
            msg3.getHash(diskHash=False),
        )
