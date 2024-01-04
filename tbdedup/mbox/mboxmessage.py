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
import hashlib
import re
import logging

from tbdedup.utils import encoder

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
    'X-Mozilla-Status',     # Status Field
    'X-Mozilla-Status2',    # 2nd Status Field
    'X-Mozilla-Keys',       # ??
    'X-Apparently-To',      # Differentiate between soruces?
    'Message-ID',           # Unique Message ID
]


class Message(object):
    MESSAGE_ID = "Message-ID"

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
            skip_keys = [
                'X-Mozilla-Status',
                'X-Mozilla-Status2',
                'X-Mozilla-Keys',
                'X-Apparently-To',
                'Message-iD',
            ]
            matchers = [
                re.compile(f"^{skip_header}", flags=re.I)
                for skip_header in THUNDERBIRD_HEADERS
            ]
            for k, v in self.headers.items():
                for m in matchers:
                    if m.match(k):
                        continue
                for vline in v:
                    mhash.update(encoder.to_encoding(vline))
            for line in self.lines:
                mhash.update(encoder.to_encoding(line))

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
