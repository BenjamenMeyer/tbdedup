"""
"""
import hashlib
import mailbox # builtin
import re
import logging

#from tbdedup import (
#    utils,
#)

from . import mboxmessage

LOG = logging.getLogger(__name__)

class ErrInvalidFileFormat(Exception):
    pass

class Mailbox(object):
    mboxRdMatch = re.compile(r'^>\s?From - ')
    mboxOMatch  = re.compile(r'^From - ')
    mboxCLMatch = re.compile(r'^Content-Length:')

    # Start Line: `^FROM - [DOW] [MOY] [DD] [hh]:[mm]:[ss] [yyyy]$`
    mboxMessageStart = re.compile(r'^From - ')
    # Likely Thunderbird specific headers:
    # X-Mozilla-Status
    # X-Mozilla-Status2
    # X-Mozilla-Keys
    # X-Apparently-To
    # Message-ID

    MBOXO = 0
    MBOXRD = 1
    MBOXCL = 2
    MBOXCL2 = 3

    def __init__(self, db, filename):
        self.db = db
        self.filename = filename

    @classmethod
    def detect_mbox_type(cls, filename):
        LOG.info(f'Checking file {filename}')
        with open(filename, 'rb') as data_input:
            inMessage = False
            fromIsPrepended = False
            hasContentLength = False
            message_counter = 0

            for line in data_input:
                line = line.decode('latin1').strip()
                isRdMatch = cls.mboxRdMatch.match(line)
                isOMatch = cls.mboxOMatch.match(line)

                if isRdMatch or isOMatch:
                    inMessage = True

                if isRdMatch:
                    LOG.info(f"MBOXRD Detected using line '{line}'")
                    fromIsPrepended = True
                    message_counter = message_counter + 1
                    continue

                if isOMatch:
                    LOG.info(f"MBOXO or MBOXOCL2 Detected using line '{line}'")
                    fromIsPrepended = False
                    message_counter = message_counter + 1
                    continue

                if inMessage:
                    isClMatch = cls.mboxCLMatch.match(line)
                    if isClMatch:
                        LOG.info(f"MBOXO or MBOXOCL2 Detected using line '{line}'")
                        hasContentLength = True
                        message_counter = message_counter + 1
                        continue

                if message_counter > 1000:
                    LOG.info("Detected 1000 messags. File format should be known by now")
                    break

            LOG.info(f"Is Prepended: {fromIsPrepended}")
            LOG.info(f"Has Content Length: {hasContentLength}")
            if fromIsPrepended and hasContentLength:
                LOG.info("Detected MBOXCL")
                return cls.MBOXCL

            elif fromIsPrepended and not hasContentLength:
                LOG.info("Detected MBOXRD")
                return cls.MBOXRD

            elif not fromIsPrepended and hasContentLength:
                LOG.info("Detected MBOXCL2")
                return cls.MBOXCL2

            else: # elif not fromIsPrepended and not hasContentLength:
                LOG.info("Detected MBOXO")
                return cls.MBOXO

    @staticmethod
    def getMessages(filename):
        # So we try another method:
        with open(filename, 'rb') as data_input:
            matches = []
            offset = 0
            #re = 
            foundBlankLine = False
            inRecord = False
            recordCounter = 0
            currentRecord = mboxmessage.Message(0, "")
            
            for line in data_input:
                    line = line.decode('latin1').strip()
                    if len(line) == 0:
                        foundBlankLine = True
                        continue

                    isRdMatch = Mailbox.mboxRdMatch.match(line)
                    isOMatch = Mailbox.mboxOMatch.match(line)

                    if (isRdMatch or isOMatch):
                        if foundBlankLine:
                            # new record

                            # pass back the previous record
                            yield currentRecord

                            # increment the record counter and reset
                            recordCounter = recordCounter + 1
                            currentRecord = mboxmessage.Message(recordCounter, line)
                            continue

                        elif recordCounter == 0:
                            # first record is not preceeded by a blank line
                            currentRecord.fromLine = line
                            continue

                    currentRecord.lines.append(line)

                    foundBlankLine = False

    def buildSummary(self):
        with open(self.filename, 'rb') as data_input:
            recordIndex = 0
            recordCounter = 0
            currentRecord = mboxmessage.Message(0, "")
            foundBlankLine = False

            def log_file_tracking(msg):
                LOG.info(f'{self.filename}[{recordIndex}] {msg}')

            def get_msg_file(counter):
                return open(f"msg{counter}", "wb")

            # Create the first file for output
            msg_output = get_msg_file(recordCounter)

            def potential_write(l):
                if msg_output is not None:
                    msg_output.write(l)

            for rawline in data_input:
                line = rawline.decode('latin1').strip()
                isStartLine = self.mboxMessageStart.match(line)

                if recordIndex == 0:
                    if not isStartLine: 
                        # start line does not match properly
                        raise ErrInvalidFileFormat(f"invalid start line: {line}")

                    # start line does match
                    log_file_tracking(f'Found start of file: \"{rawline}\"')
                    currentRecord = mboxmessage.Message(0, rawline)
                    potential_write(rawline)

                elif len(line) == 0:
                    log_file_tracking('Found blank line')
                    foundBlankLine = True
                    currentRecord.lines.append(rawline)
                    potential_write(rawline)

                elif foundBlankLine and isStartLine:
                    # drop the blank line just added
                    currentRecord.lines.pop()
                    log_file_tracking(f'Returning record number {recordCounter}')
                    yield currentRecord
                    log_file_tracking(f'Found start of next message: \"{rawline}\"')

                    if msg_output is not None:
                        msg_output.close()
                        if recordCounter < 10:
                            msg_output = get_msg_file(recordCounter)
                        else:
                            msg_output = None

                    foundBlankLine = False
                    recordCounter = recordCounter + 1
                    currentRecord = mboxmessage.Message(recordCounter, rawline)
                    potential_write(rawline)

                else:
                    foundBlankLine = False
                    currentRecord.lines.append(rawline)
                    potential_write(rawline)

                recordIndex = recordIndex + 1

            if currentRecord is not None:
                yield currentRecord
