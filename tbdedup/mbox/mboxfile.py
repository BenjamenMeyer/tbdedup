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
import logging
import mailbox # builtin
import re
import sys

#from tbdedup import (
#    utils,
#)

from . import mboxmessage

LOG = logging.getLogger(__name__)

class ErrInvalidFileFormat(Exception):
    pass

class ErrInvalidRecordLength(Exception):
    pass

class Mailbox(object):
    mboxRdMatch = re.compile(r'^>\s?From - ')
    mboxOMatch  = re.compile(r'^From - ')
    mboxCLMatch = re.compile(r'^Content-Length:')

    # Start Line: `^FROM - [DOW] [MOY] [DD] [hh]:[mm]:[ss] [yyyy]$`
    mboxMessageStart = re.compile(r'^From - ')
    mboxHeaderStart = re.compile(r'(^[\S-]*):(.*)')
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

    def parseBoundaryMarker(self, currentRecord, header_name):
        record_boundary_marker = ""
        header_value = currentRecord.getData(header_name).decode('latin1')
        #'='.join(y.split(':')[1].split("\r\n")[1].strip().split('=')[1:])
        value_components = header_value.split(":")[1].split("\r\n")
        #LOG.info(f'Found Content Type Components: {value_components}')
        for value_line in value_components:
            vline = value_line.strip()
            if '=' in vline:
                #LOG.info(f'Found potential Content Boundary Marker: "{vline}"')
                vline_components = vline.split('=')
                vline_key = vline_components[0]
                vline_data = '='.join(vline_components[1:])
                if vline_key.lower() == 'boundary':
                    try:
                        #LOG.info(f'Found Content Boundary Marker: RAW = "{vline_data}"')
                        if '"' in vline_data:
                            record_boundary_marker = '--' + vline_data.split('"')[1]
                        else:
                            record_boundary_marker = '--' + vline_data
                        #LOG.info(f'Found Content Boundary Marker: "{record_boundary_marker}"')
                    except Exception:
                        LOG.info(f'Found Content Boundary Marker: RAW = "{vline_data}"')
                        LOG.exception(f'Failed to parse boundary marker')
                        sys.exit(1)

        return record_boundary_marker

    def buildSummary(self):
        with open(self.filename, 'rb') as data_input:
            recordIndex = 0
            recordCounter = 0
            currentRecord = mboxmessage.Message(0, "", 0)
            foundBlankLine = False

            def log_file_tracking(msg, old_pos, new_pos):
                # Enable the below for debugging
                LOG.debug(f'{self.filename}[{recordIndex}][Old Pos: {old_pos} New Pos: {new_pos}] {msg}')

            def get_msg_file(counter):
                #return open(f"msg{counter}", "wb")
                return None

            # Create the first file for output
            msg_output = get_msg_file(recordCounter)

            def potential_write(l):
                if msg_output is not None:
                    msg_output.write(l)

            # so file_location will escape the loop
            file_location = 0
            previous_file_location = 0
            header_name = ""
            current_field_data = ""
            record_boundary_marker = ""
            for rawline in data_input:
                previous_file_location = file_location
                file_location = data_input.tell()
                #log_file_tracking(f"Old Location: {previous_file_location} New Location: {file_location}")
                rawline2 = rawline.decode('latin1')
                line = rawline2.strip()
                isStartLine = self.mboxMessageStart.match(line)
                isHeaderLine = self.mboxHeaderStart.match(rawline2)

                if recordIndex == 0:
                    if not isStartLine:
                        # start line does not match properly
                        raise ErrInvalidFileFormat(f"invalid start line: {line}")

                    # start line does match
                    #log_file_tracking(f'Found start of file: \"{rawline}\"', previous_file_location, file_location)
                    currentRecord = mboxmessage.Message(0, rawline, previous_file_location)
                    potential_write(rawline)

                elif len(line) == 0:
                    #log_file_tracking('Found blank line', previous_file_location, file_location)
                    foundBlankLine = True
                    currentRecord.addData(header_name, rawline)
                    potential_write(rawline)

                elif isHeaderLine and header_name != 'body':
                    foundBlankLine = False
                    # before capturing the new header value
                    # check the existing one to see if we need
                    # to process it for anything
                    if len(header_name) > 0:
                        lower_header_name = header_name.lower()
                        if lower_header_name == "content-type":
                            record_boundary_marker = self.parseBoundaryMarker(currentRecord, header_name)
                            #log_file_tracking(f'Found Content Type: {header_name}: "{currentRecord.getData(header_name)}"', previous_file_location, file_location)
                            #record_boundary_marker = ""
                            #header_value = currentRecord.getData(header_name).decode('latin1')
                            ##'='.join(y.split(':')[1].split("\r\n")[1].strip().split('=')[1:])
                            #value_components = header_value.split(":")[1].split("\r\n")
                            #log_file_tracking(f'Found Content Type Components: {value_components}', previous_file_location, file_location)
                            #for value_line in value_components:
                            #    vline = value_line.strip()
                            #    if '=' in vline:
                            #        log_file_tracking(f'Found potential Content Boundary Marker: "{vline}"', previous_file_location, file_location)
                            #        vline_components = vline.split('=')
                            #        vline_key = vline_components[0]
                            #        vline_data = '='.join(vline_components[1:])
                            #        if vline_key.lower() == 'boundary':
                            #            record_boundary_marker = '--' + vline_data.split('"')[1]
                            #            log_file_tracking(f'Found Content Boundary Marker: "{record_boundary_marker}"', previous_file_location, file_location)
                            #
                            #matches = self.mboxHeaderStart.match(raw_header_value, re.MULTILINE)
                            #hname = matches.groups()[0]
                            #hvalue = matches.groups()[1]
                            #log_file_tracking(f'Content Type has value: {hvalue}', previous_file_location, file_location)

                    # capture the new header
                    header_name = isHeaderLine.groups()[0]
                    header_data = isHeaderLine.groups()[1]
                    #log_file_tracking(f'Found Header field: {header_name} = "{header_data}"', previous_file_location, file_location)
                    currentRecord.addData(header_name, rawline)

                    if header_name.lower() == "content-length":
                        #log_file_tracking(f'Found Content Length: {header_name}: "{currentRecord.getData(header_name)}"', previous_file_location, file_location)
                        currentRecord.setContentLength(header_data)

                elif line == record_boundary_marker:
                    foundBlankLine = False
                    #log_file_tracking(f'Found Content Boundary Marker - {record_boundary_marker}', previous_file_location, file_location)
                    # denote that the body is now being processed
                    header_name = 'body'
                    currentRecord.addData(header_name, rawline)

                elif foundBlankLine and isStartLine:
                    #log_file_tracking(f'Found start of new record', previous_file_location, file_location)
                    # point the end_offset at the previous line
                    currentRecord.end_offset = previous_file_location
                    # drop the blank line just added
                    if len(currentRecord.lines) != 0:
                        currentRecord.lines.pop()
                    #log_file_tracking(f'Returning record number {recordCounter}', previous_file_location, file_location)
                    yield currentRecord

                    #log_file_tracking(f'Start of next message: \"{rawline}\"', previous_file_location, file_location)
                    if msg_output is not None:
                        msg_output.close()
                        if recordCounter < 10:
                            msg_output = get_msg_file(recordCounter)
                        else:
                            msg_output = None
                    foundBlankLine = False
                    header_name = ''
                    # should not hurt to reset the boundary marker when
                    # a new record is being generated
                    record_boundary_marker = ''
                    recordCounter = recordCounter + 1
                    currentRecord = mboxmessage.Message(recordCounter, rawline, previous_file_location)
                    potential_write(rawline)

                elif foundBlankLine and (not isHeaderLine) and record_boundary_marker == '':
                    # Found a blank line on the previous iteration,
                    # there is no boundary marker,
                    # and the current line is not a header line
                    # then the data must be the message body
                    header_name = 'body'
                    currentRecord.addData(header_name, rawline)

                else:
                    #log_file_tracking(f'Content[{header_name}]: "{rawline}"', previous_file_location, file_location)
                    foundBlankLine = False
                    currentRecord.addData(header_name, rawline)
                    potential_write(rawline)

                recordIndex = recordIndex + 1

            if currentRecord is not None:
                currentRecord.end_offset = data_input.tell()
                yield currentRecord

    def getMessageData(self, hash_id):
        for msgData in self.db.get_messages_by_hash(hash_id):
            # they should all be the same so just return the first one
            return msgData

    @classmethod
    def getMessageFromFile(cls, msgData) -> bytes:
        with open(msgData['location'], 'rb') as data_input:
            length = msgData['end_offset'] - msgData['start_offset']
            LOG.info(f'Reading - Record[{msgData["messageid"]}] Start Offset: {msgData["start_offset"]} End Ofset: {msgData["end_offset"]} - Length: {length}')
            if length > 0:
                data_input.seek(msgData['start_offset'])
                return data_input.read(length)
            else:
                raise ErrInvalidRecordLength(f"{msgData['end_offset']} - {msgData['start_offset']} = {length} <= 0")
