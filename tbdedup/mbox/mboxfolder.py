"""
"""

import asyncio
import logging
import os
import os.path

LOG = logging.getLogger(__name__)


class MailboxFolder(object):
    
    def __init__(self, foldername):
        self.foldername = foldername

    async def getMboxFiles(self):
        fileResult = []
        for root, dirs, files in os.walk(self.foldername):
            LOG.info(f"[{root}] Found {len(dirs)} sub-directories and {len(files)} files")
            for filename in files:
                LOG.info(f"[{root}] Found file: {filename}")
                if "." in filename:
                    LOG.debug(f"[{root}] Skipping file {filename}")
                    continue
                fileResult.append(
                    os.path.join(
                        root,
                        filename,
                    ),
                )
            for dirname in dirs:
                LOG.info(f"[{root}] Found folder: {dirname}")

        allFiles = '\n'.join(fileResult)
        LOG.info(f"[{self.foldername}] Found {len(fileResult)} files to process:\n{allFiles}")

        return fileResult
