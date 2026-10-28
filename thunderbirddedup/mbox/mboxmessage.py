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
import hashlib
import re
import logging

from thunderbirddedup.utils import encoder

LOG = logging.getLogger(__name__)


def Atoi(s):
    intMap = {
        '{0}'.format(n): n
        for n in range(0, 10)
    }
    result = 0
    for v in s.strip():
        cV = intMap[v]
        result = (result * 10) + cV
    return result


THUNDERBIRD_HEADERS = [
    'X-Mozilla-Status',     # Thunderbird primary status flags (hex)
    'X-Mozilla-Status2',    # Thunderbird extended status flags (hex)
    'X-Mozilla-Keys',       # Thunderbird message tags/keywords
    'X-Mozilla-',           # Other Thunderbird internal headers (e.g., Draft-Info)
    'X-Account-Key',        # Thunderbird account key added on local filter/download
    'X-UIDL',               # POP3/local UIDL tracking header
    'X-Folder',             # Local folder tracking header
    'X-Apparently-To',      # Delivery envelope header
]

MSG_FLAG_READ = 0x0001
MSG_FLAG_REPLIED = 0x0002
MSG_FLAG_MARKED = 0x0004
MSG_FLAG_EXPUNGED = 0x0008
MSG_FLAG_FORWARDED = 0x1000
MSG_FLAG_IMAP_DELETED = 0x00200000


class Message(object):

    def __init__(self, index, fromLine, start_offset):
        # LOG.info(f'Record[{index}] - Start Location: {start_offset}')
        # the RAW from line that denotes the message break in MBOX format
        self.fromLine = fromLine
        # the starting and ending offset in the file (integer position) of
        # the entire record
        self.start_offset = start_offset
        self.end_offset = start_offset

        # The index of the record in the file, based on the number of
        # entries in the file the record came from
        self.index = index
        self.content_length = 0
        # The Email Headers
        self.headers = {}
        # The Email Body Data
        self.lines = []
        self.rawLines = []
        self.rawLines.append(self.fromLine)

    def addData(self, key, data):
        self.rawLines.append(data)
        if key == "body":
            self.lines.append(data)
        else:
            if key not in self.headers:
                self.headers[key] = []
            self.headers[key].append(data)

    def getData(self, key):
        if key == "body":
            return b''.join(self.lines)
        else:
            if key in self.headers:
                return b''.join(self.headers[key])
            else:
                return None

    def setContentLength(self, rawDataValue):
        # LOG.info(f'Received Raw Content Length Data: "{rawDataValue}"')
        dv = rawDataValue.strip()
        # LOG.info(f'Removed whitespace: "{dv}"')
        content_length = Atoi(dv)
        # LOG.info(f'Detected Content Length Integer value of {content_length}')
        self.content_length = content_length

    def getHash(self, diskHash=False):
        mhash = hashlib.sha256()
        if diskHash:
            for rl in self.rawLines:
                mhash.update(encoder.to_encoding(rl))
        else:
            matchers = [
                re.compile(f"^{skip_header}", flags=re.I)
                for skip_header in THUNDERBIRD_HEADERS
            ]
            for k, v in sorted(self.headers.items(), key=lambda kv: kv[0].lower()):
                if any(m.match(k) for m in matchers):
                    continue
                for vline in v:
                    encoded_h = encoder.to_encoding(vline).replace(b'\r\n', b'\n')
                    mhash.update(encoded_h)

            body_lines = [
                encoder.to_encoding(line).replace(b'\r\n', b'\n')
                for line in self.lines
            ]
            while body_lines and len(body_lines[-1].strip()) == 0:
                body_lines.pop()
            for bline in body_lines:
                mhash.update(bline)

        return mhash.hexdigest()

    def getMsgId(self):
        return self.index

    def getMessageIDHeader(self):
        idHeader = re.compile("^Message-ID", flags=re.I)
        for k, v in self.headers.items():
            if idHeader.match(k):
                return b''.join(v).decode('latin1')

    def getMessageIDHeaderHash(self):
        idHeader = self.getMessageIDHeader()
        m = hashlib.sha256()
        m.update(encoder.to_encoding(idHeader))
        return m.hexdigest()

    def _getHeaderValueStr(self, header_pattern):
        matcher = re.compile(header_pattern, flags=re.I)
        for k, v in self.headers.items():
            if matcher.match(k):
                raw_val = b''.join(
                    encoder.to_encoding(part)
                    for part in v
                ).decode('latin1')
                if ':' in raw_val:
                    return raw_val.split(':', 1)[1].strip()
                return raw_val.strip()
        return None

    def getMozillaStatus(self):
        val = self._getHeaderValueStr(r'^X-Mozilla-Status$')
        if val:
            try:
                return int(val.split()[0], 16)
            except ValueError:
                LOG.warning(f'Invalid X-Mozilla-Status value: {val}')
        return 0

    def getMozillaStatus2(self):
        val = self._getHeaderValueStr(r'^X-Mozilla-Status2$')
        if val:
            try:
                return int(val.split()[0], 16)
            except ValueError:
                LOG.warning(f'Invalid X-Mozilla-Status2 value: {val}')
        return 0

    def getMozillaKeys(self):
        val = self._getHeaderValueStr(r'^X-Mozilla-Keys$')
        if val:
            return ' '.join(val.split())
        return ''

    @staticmethod
    def mergeMozillaMetadata(messages):
        merged_status = 0
        merged_status2 = 0
        seen_keys = []
        for msg in messages:
            merged_status |= (msg.get('mozilla_status') or 0)
            merged_status2 |= (msg.get('mozilla_status2') or 0)
            raw_keys = msg.get('mozilla_keys') or ''
            for tag in raw_keys.split():
                if tag not in seen_keys:
                    seen_keys.append(tag)

        merged_status &= ~MSG_FLAG_EXPUNGED
        merged_status2 &= ~MSG_FLAG_IMAP_DELETED
        return (
            merged_status,
            merged_status2,
            ' '.join(seen_keys),
        )

    @staticmethod
    def updateMozillaHeaders(raw_bytes, status, status2, keys):
        status_re = re.compile(rb'^(X-Mozilla-Status:\s*)([0-9a-fA-F]+)(\r?\n)$', re.I)
        status2_re = re.compile(rb'^(X-Mozilla-Status2:\s*)([0-9a-fA-F]+)(\r?\n)$', re.I)
        keys_re = re.compile(rb'^(X-Mozilla-Keys:)([^\r\n]*)(\r?\n)$', re.I)

        lines = raw_bytes.splitlines(keepends=True)
        if not lines:
            return raw_bytes

        eol = b'\r\n' if lines[0].endswith(b'\r\n') else b'\n'
        found_status = False
        found_status2 = False
        found_keys = False

        for idx, line in enumerate(lines):
            if idx == 0:
                continue
            if line in (b'\n', b'\r\n'):
                break
            m_status = status_re.match(line)
            if m_status:
                found_status = True
                prefix, old_val, line_eol = m_status.groups()
                width = max(4, len(old_val))
                new_val = f'{status:0{width}x}'.encode('ascii')
                lines[idx] = prefix + new_val + line_eol
                continue
            m_status2 = status2_re.match(line)
            if m_status2:
                found_status2 = True
                prefix, old_val, line_eol = m_status2.groups()
                width = max(8, len(old_val))
                new_val = f'{status2:0{width}x}'.encode('ascii')
                lines[idx] = prefix + new_val + line_eol
                continue
            m_keys = keys_re.match(line)
            if m_keys:
                found_keys = True
                if keys:
                    prefix, old_val, line_eol = m_keys.groups()
                    encoded_keys = b' ' + keys.encode('latin1')
                    if len(old_val) > len(encoded_keys):
                        encoded_keys = encoded_keys.ljust(len(old_val), b' ')
                    lines[idx] = prefix + encoded_keys + line_eol
                continue

        insert_headers = []
        if not found_status and status:
            insert_headers.append(f'X-Mozilla-Status: {status:04x}'.encode('ascii') + eol)
        if not found_status2 and status2:
            insert_headers.append(f'X-Mozilla-Status2: {status2:08x}'.encode('ascii') + eol)
        if not found_keys and keys:
            insert_headers.append(b'X-Mozilla-Keys: ' + keys.encode('latin1') + eol)

        if insert_headers:
            lines[1:1] = insert_headers

        return b''.join(lines)
