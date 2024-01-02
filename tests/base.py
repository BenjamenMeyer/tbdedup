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
import os
import random
import tempfile
import unittest


class TestCase(unittest.TestCase):

    def setUp(self):
        super(TestCase, self).setUp()

    def tearDown(self):
        super(TestCase, self).tearDown()


class AsyncioTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        super(unittest.IsolatedAsyncioTestCase, self).setUp()

    async def asyncSetUp(self):
        pass

    def tearDown(self):
        super(unittest.IsolatedAsyncioTestCase, self).tearDown()

    async def asyncTearDown(self):
        pass


class ValueSwap(object):

    def __init__(self, module, value_to_replace, new_value):
        self.module = module
        self.value_to_replace = value_to_replace
        self.new_value = new_value
        self.old_value = getattr(self.module, self.value_to_replace)

    def __enter__(self):
        setattr(self.module, self.value_to_replace, self.new_value)

    def __exit__(self, exc_type, exc_value, traceback):
        setattr(self.module, self.value_to_replace, self.old_value)


class GenericOptions(object):

    def __init__(self, **kv):
        for k, v in kv.items():
            setattr(self, k, v)


class KeepLocalDirClean(object):

    def __init__(self):
        self.cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()

    def __enter__(self):
        os.chdir(self.temp_dir.name)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        os.chdir(self.cwd)


def GenerateMboxFile(filename, email_count, from_line_format, has_content_length, use_boundary_markers):
    """
    Generates MBOX file data to make valid MBOX files for testing purposes.

    :param from_line_format: format to use for the FROM line; caller should pass
        in `"FROM"` or `> FROM`. The method will add the timestamp
    :param has_content_length: boolean value for whether or not to generate
        a `Content-Length` header should be included in the email header data

    MBOX files contain copies of Emails. Each entry is denoted by a blank line
    followed by a `FROM -` line, with the exception of the very first record which
    lacks the preceding blank line and just starts with the `FROM -` line. The
    `FROM -` line is differentiated from the `FROM` header field as the header
    fields are semi-colon separated key-value entries.

    There are 4 types of MBOX files:

        MBOXO
            MBOX FROM Format: "FROM - <timestamp>>"
            Content Length header is missing

        MBOXRD
            MBOX FROM Format: "><optional whitespace>FROM - <timestamp>"
            Content Length header is missing

        MBOXCL
            MBOX FROM Format: "><optional whitespace>FROM - <timestamp>"
            Content Length header set

        MBOXCL2
            MBOX FROM Format: "FROM - <timestamp>"
            Content Length header set

    .. note:: The MBOXRD and MBOXCL formats do not validate using the mfck tool
        due the FROM line formatting. however, MBOXO and MBOXCL2 do validate
        just fine. MBOXRD and MBOXCL are against the current code spec which may
        be incorrect - it might be the FROM line being detected is the same
        and the difference is in the header/body data only.
    """
    def generate_email(index, store_content_length, use_content_boundaries):
        def get_email():
            valid_account_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
            valid_domain_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            account = ''
            server = ''
            tld = ''
            for _ in range(random.randrange(3, 40)):
                account = account + random.choice(valid_account_chars)
            for _ in range(random.randrange(10, 40)):
                server = server + random.choice(valid_domain_chars)
            for _ in range(random.randrange(3, 10)):
                tld = tld + random.choice(valid_domain_chars)
            return f"{account}@{server}.{tld}"

        from_email = get_email()
        email_headers = {
            'From': from_email,
            'To': get_email(),
            'Subject': f"Sent {index:030}",
            'Date': datetime.datetime.utcnow().isoformat(),
            'Reply-To': from_email,
            'Message-ID': f"{index:030}",
        }
        email_body = f"Test message number {index:030}"
        if use_content_boundaries:
            email_boundary = "=========boundary-{index:040}===="
            email_boundary_alternate = "-------boundary-{index:010}----"
            email_headers['Content-Type'] = f"multipart/mixed; boundary={email_boundary}"
            bounded_email = '\n'.join(
                [
                    f"--{email_boundary}--",
                    "Content-Type: multipart/altnative;",
                    f"    boundary={email_boundary_alternate}",
                    "",
                    f"--{email_boundary_alternate}",
                    "Content-Type: text/plain; charset=us-ascii",
                    "",
                    email_body,
                    f"--{email_boundary_alternate}",
                    "Content-Type: text/html; charset=us-ascii",
                    "",
                    f"<html><body><div>{email_body}</div></body></html>"
                    f"--{email_boundary_alternate}",
                    f"--{email_boundary}--",
                ],
            )

        if store_content_length:
            email_headers['Content-Length'] = len(email_body) + 1

        return (email_headers, email_body)

    def write_email(file, from_line, headers, body, is_first):
        if not is_first:
            print("", file=file)

        print(from_line, file=file)
        for k, v in headers.items():
            print(f"{k}: {v}", file=file)
        print("", file=file)
        print(body, file=file)

    def generate_date():
        dt = datetime.datetime.utcnow()

        def dow():
            dw = {
                0: "Mon",
                1: "Tue",
                2: "Wed",
                3: "Thu",
                4: "Fri",
                5: "Sat",
                6: "Sun",
            }
            return dw[dt.weekday()]

        def moy():
            my = {
                1: "Jan",
                2: "Feb",
                3: "Mar",
                4: "Apr",
                5: "May",
                6: "Jun",
                7: "Jul",
                8: "Aug",
                9: "Sep",
                10: "Oct",
                11: "Nov",
                12: "Dec",
            }
            return my[dt.month]

        # [DOW] [MOY] [DD] [hh]:[mm]:[ss] [yyyy]
        return f"{dow()} {moy()} {dt.day:02} {dt.hour:02}:{dt.minute:02}:{dt.second:02} {dt.year:04}"

    with open(filename, "wt") as mbox_writer:
        for email_index in range(email_count):
            eh, eb = generate_email(
                email_index,
                has_content_length,
                use_boundary_markers,
            )
            write_email(
                mbox_writer,
                f"{from_line_format} - {generate_date()}",
                eh,
                eb,
                0 == email_index,
            )
