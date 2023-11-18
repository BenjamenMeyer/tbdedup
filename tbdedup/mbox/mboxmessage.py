"""
"""
import hashlib
import mailbox # builtin
import re
import logging

#from tbdedup import (
#    utils,
#)

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
    BAD_KEY = 'X-tbdedup-bad-key'
    CONTENT_KEY = 'X-tbdedup-CONTENT'
    CONTENT_VALUE_KEY = 'X-tbdedup-CONTENT-LENGTH'
    CONTENT_LENGTH_KEY = "Content-Length"
    MESSAGE_ID = "Message-ID"

    def __init__(self, index, fromLine):
        self.lines = []
        self.fromLine = fromLine
        self.dataLines = []
        self.headerLines = []
        self.index = index
        self.messageInfo = {
            self.BAD_KEY: [],
            self.CONTENT_KEY: [],
            self.CONTENT_LENGTH_KEY: 0,
        }

    def getMBoxMessage(self):
        data = "\n".join(self.lines)
        return mailbox.mboxMessage(message=data)

    def buildData(self):
        marker = 4
        if len(self.lines) > marker:
            self.headerLines = self.lines[:marker]
            self.dataLines = self.lines[marker:]

        currentKey = None
        contentLength = 0
        lineCount = 0
        totalCount = 0
        for rawline in self.lines:
            line = rawline.decode('latin1').strip()
            if currentKey == self.CONTENT_KEY:
                #self.messageInfo[self.CONTENT_KEY] += "\n".encode('latin1') + rawline
                self.messageInfo[self.CONTENT_KEY] += rawline[:-1]
                lineCount = lineCount + 1
            else:
                parts = line.split(':')
                if len(parts) > 1:
                    currentKey = parts[0]
                    data = ':'.join(parts[1:])

                    if currentKey.lower() == self.CONTENT_LENGTH_KEY.lower():
                        contentLength = Atoi(data)
                        currentKey = self.CONTENT_KEY
                    else:
                        if currentKey in self.messageInfo:
                            self.messageInfo[currentKey] += data
                        else:
                            self.messageInfo[currentKey] = data
                elif currentKey == None:
                    self.messageInfo[self.BAD_KEY] += rawline.decode('latin1')
                else:
                    self.messageInfo[currentKey] += rawline.decode('latin1')
            totalCount = totalCount + 1

        self.messageInfo[self.CONTENT_KEY] = self.messageInfo[self.CONTENT_KEY][:-1]
        self.messageInfo[self.CONTENT_VALUE_KEY] = contentLength
        # if all is good then the line of the content should match the value of contentLength
        storedContentLength = len(self.messageInfo[self.CONTENT_KEY])
        if storedContentLength != contentLength:
            direction = 'over' if storedContentLength > contentLength else 'under'
            delta = storedContentLength - contentLength
            LOG.warn(f"MESSAGE[{self.index}]: Detected bad content length: {len(self.messageInfo[self.CONTENT_KEY])} != {contentLength} - {direction} - Delta: {delta} - Line Count: {lineCount} - Key Count: {len(self.messageInfo)} - line count: {lineCount} - total line count: {totalCount}")

    def getHash(self):
        mhash = hashlib.sha256()
        skip_keys = [
            'X-Mozilla-Status',
            'X-Mozilla-Status2',
            'X-Mozilla-Keys',
            'X-Apparently-To',
            'Message-iD',
            self.BAD_KEY,
            self.CONTENT_VALUE_KEY,
            self.CONTENT_LENGTH_KEY,
        ]
        #for l in self.dataLines:
        #    try:
        #        s = l.decode('latin1')
        #    except TypeError:
        #        s = l
        #    m.update(s)
        #for k, v in self.messageInfo.items():
        #    if k not in skip_keys:
        #        d = ''.join(v)
        #        try:
        #            e = d.encode('latin1')
        #        except TypeError:
        #            e = d
        #        m.update(e)
        matchers = [
            re.compile(f"^{skip_header}", flags=re.I)
            for skip_header in THUNDERBIRD_HEADERS
        ]
        for k, v in self.messageInfo.items():
            if k.startswith('X-tbdedup-'):
                # internal field, skip
                continue

            # check for TB headers that get skipped
            for m in matchers:
                if m.match(k):
                    continue

            if type(v) == type(''):
                mhash.update(v.encode('latin1'))
            elif type(v) == type(bytes()):
                mhash.update(v)
            elif type(v) == type(0):
                d = f'{v}'.encode('latin1')
                mhash.update(d)
            elif type(v) == type([]):
                LOG.info(f'KEY[{k}]: Found list: {v}')
                d = ''.join(v).encode('latin1')
                mhash.update(d)
            else:
                LOG.info(f'KEY[{k}]: Entry Type: {type(v)} - "{v}"')
                mhash.update(v)

        mhash.update(bytes(self.messageInfo[self.CONTENT_KEY]))
        return mhash.hexdigest()

    def getMsgId(self):
        return self.index

    def getMessageIDHeader(self):
        idHeader = re.compile("^Message-ID", flags=re.I)
        for k, v in self.messageInfo.items():
            if idHeader.match(k):
                return v

    def getMessageIDHeaderHash(self):
        idHeader = self.getMessageIDHeader()
        m = hashlib.sha256()
        if type(idHeader) == bytes:
            m.update(idHeader)
        elif type(idHeader) == str:
            m.update(bytes(idHeader, 'utf-8'))
        else:
            m.update(bytes(str(idHeader), 'utf-8'))
        return m.hexdigest()
