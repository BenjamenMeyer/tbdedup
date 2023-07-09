"""
"""

import re
import logging

LOG = logging.getLogger(__name__)

class Mailbox(object):
    mboxRdMatch = re.compile(r'^>\s?From - ')
    mboxOMatch  = re.compile(r'^From - ')
    mboxCLMatch = re.compile(r'^Content-Length:')

    MBOXO = 0
    MBOXRD = 1
    MBOXCL = 2
    MBOXCL2 = 3
    
    def __init__(self, db):
        pass

    @staticmethod
    def detect_mbox_type(filename):
        LOG.info(f'Checking file {filename}')
        with open(filename, 'r', encoding='latin1') as data_input:
            inMessage = False
            fromIsPrepended = False
            hasContentLength = False
            for line in data_input:
                line = line.strip()
                isRdMatch = Mailbox.mboxRdMatch.match(line)
                isOMatch = Mailbox.mboxOMatch.match(line)

                if isRdMatch or isOMatch:
                    inMessage = True

                if isRdMatch:
                    LOG.info(f"MBOXRD Detected using line '{line}'")
                    fromIsPrepended = True
                    continue

                if isOMatch:
                    LOG.info(f"MBOXO or MBOXOCL2 Detected using line '{line}'")
                    fromIsPrepended = False
                    continue

                if inMessage:
                    isClMatch = Mailbox.mboxCLMatch.match(line)
                    if isClMatch:
                        LOG.info(f"MBOXO or MBOXOCL2 Detected using line '{line}'")
                        hasContentLength = True

            LOG.info(f"Is Prepended: {fromIsPrepended}")
            LOG.info(f"Has Content Length: {hasContentLength}")
            if fromIsPrepended and hasContentLength:
                LOG.info("Detected MBOXCL")
                return Mailbox.MBOXCL

            elif fromIsPrepended and not hasContentLength:
                LOG.info("Detected MBOXRD")
                return Mailbox.MBOXRD

            elif not fromIsPrepended and hasContentLength:
                LOG.info("Detected MBOXCL2")
                return Mailbox.MBOXCL2

            else: # elif not fromIsPrepended and not hasContentLength:
                LOG.info("Detected MBOXO")
                return Mailbox.MBOXO


