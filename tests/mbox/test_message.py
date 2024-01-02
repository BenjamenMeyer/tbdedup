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
import hashlib
import re
from unittest import mock

from tbdedup.mbox import mboxmessage
from tbdedup.utils import encoder

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
    def test_get_message_id_header(self, is_valid):
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
        msg.addData('X-Apparently-To', 'some receipient')
        msg.addData('Message-ID', 'some id value')

        non_disk_hash = hashlib.sha256()
        disk_hash = hashlib.sha256()

        # disk hash is just the lines added in order of how they
        # were received by the message object
        for rl in msg.rawLines:
            disk_hash.update(encoder.to_encoding(rl))

        # non-disk hash first add the headeres aside from those
        # that are excluded
        matcher = [
            re.compile(f"^{skipper}", flags=re.I)
            for skipper in mboxmessage.THUNDERBIRD_HEADERS
        ]
        for k, v in msg.headers.items():
            do_skip = False
            for m in matcher:
                if m.match(k):
                    do_skip = True
                    continue
            if do_skip:
                continue
            for vln in v:
                non_disk_hash.update(encoder.to_encoding(vln))
        # then it adds the body lines
        for ln in msg.lines:
            non_disk_hash.update(encoder.to_encoding(ln))

        disk_hash_value = msg.getHash(diskHash=True)
        non_disk_hash_value = msg.getHash(diskHash=False)

        self.assertEqual(disk_hash_value, disk_hash.hexdigest())
        self.assertEqual(non_disk_hash_value, non_disk_hash.hexdigest())
