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
from unittest import mock

from tbdedup import (
    db,
    dedup,
    mbox,
)
from tbdedup.mbox import (
    mboxfile,
    mboxmessage,
)

from tests import base

class MockStorage(object):
    def __init__(self, side_effect):
        self.side_effect = side_effect

    def add_message(self, *args, **kwargs):
        if self.side_effect:
            raise self.side_effect

@ddt.ddt
class TestDeduplicator(base.AsyncioTestCase):

    @ddt.data(
        ('disk', True),
        ('hash', False),
    )
    @ddt.unpack
    def test_source_option_to_boolean(self, msg_hash_source, expected_result):
        result = dedup.source_option_to_boolean(msg_hash_source)
        self.assertEqual(result, expected_result)

    @ddt.data(
        (True, None, 1, None),
        (False, None, 1, None),
        (True, [mbox.ErrInvalidFileFormat,], 1, None),
        (False, [mbox.ErrInvalidFileFormat,], 1, None),
        (True, None, 10001, None),
        (True, [mbox.ErrInvalidFileFormat,], 10001, None),
        (True, None, 10001, [mbox.ErrInvalidFileFormat,]),
    )
    @ddt.unpack
    async def test_process_file(
        self,
        has_counter_update,
        box_side_effect,
        msg_count,
        storage_side_effect,
    ):
        def do_counter_update():
            pass
        counter_update = (
            None
            if has_counter_update
            else do_counter_update
        )

        with mock.patch(
            'tbdedup.dedup.mbox.Mailbox.buildSummary',
        ) as mock_mbox_mailbox:
            msgs = []
            for index in range(msg_count):
                theMsg = mboxmessage.Message(index, f"foo{index}", index)
                theMsg.headers = {}
                theMsg.rawLines = ["foo", "bar", f"{index}"]
                msgs.append(theMsg)
            if box_side_effect is None:
                mock_mbox_mailbox.return_value = msgs
            else:
                mock_mbox_mailbox.side_effect = box_side_effect
            mock_storage = mock.Mock()
            mock_storage.add_message = mock.Mock()
            mock_storage.add_message.side_effect = storage_side_effect


            filename = 'foo'
            await dedup.processFile(filename, mock_storage, counter_update)

    @ddt.data(
        (0, False, 5),
    )
    @ddt.unpack
    async def test_dedupper(
        self,
        mbox_file_count,
        use_disk_data_for_hash,
        msg_count,
    ):
        with base.KeepLocalDirClean() as cwd:
            mbox_files = []
            for index in range(msg_count):
                hash_storage_location = 'mbox_results.sqlite'
                msg_filename = f'mbox_{index:05}.mbox'
                with open(msg_filename, "wt") as mbox_file:
                    dt = (
                        datetime.datetime.utcnow() +
                        datetime.timedelta(days=index)
                    )
                    # MBox Marker
                    # Start Line: `^FROM - [DOW] [MOY] [DD] [hh]:[mm]:[ss] [yyyy]$`
                    print(f'FROM - {dt.strftime("%a %b %d %H:%M:%S %Y")}')
                    # write a few email headers
                    print('X-Mozilla-Status: 0001', file=mbox_file)
                    print('X-Mozilla-Status2: 00000000', file=mbox_file)
                    print(f'X-Apprently-To: foo@bar.com; {dt.strftime("%a, %d %b %Y %H:%M:%S +0000")}', file=mbox_file)
                    print('To: <foo@bar.com>', file=mbox_file)
                    print('Date: {dt.strftime("%a, %d %b %Y %H:%M:%S +0000")}', file=mbox_file)
                    email_data = f"""
                    Hello, World!
                    - Foo{index:02}
                    """
                    print(f'Content-Length: {len(email_data)}', file=mbox_file)
                    # Write an email
                    print(f'{email_data}', file=mbox_file)
                    # leave a blank line for the email separator
                    print('\n', file=mbox_file)
                    mbox_files.append(msg_filename)

            output_filename = await dedup.dedupper(
                mbox_files,
                hash_storage_location,
                use_disk_data_for_hash,
                cwd,
            )
            # how to check the result?
