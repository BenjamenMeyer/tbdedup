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
import builtins
import datetime
import logging
import os
import threading
import traceback

LOG = logging.getLogger(__name__)

DEFAULT_MAX_OPEN_FILES = 64


class FileRecord(object):
    """Information about an active tracked resource/file."""

    def __init__(
        self,
        token,
        path,
        mode,
        resource_type="file",
        caller=None,
        handle=None,
    ):
        self.token = token
        self.path = os.path.abspath(path) if path else path
        self.mode = mode
        self.resource_type = resource_type
        self.caller = caller
        self.opened_at = datetime.datetime.now(datetime.timezone.utc)
        self.handle = handle

    def to_dict(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        return {
            "token": self.token,
            "path": self.path,
            "mode": self.mode,
            "type": self.resource_type,
            "caller": self.caller,
            "opened_at": self.opened_at.isoformat(),
            "age_seconds": (now - self.opened_at).total_seconds(),
        }


class TrackedFile(object):
    """File wrapper that unregisters itself from FileTracker upon close."""

    def __init__(self, tracker, token, real_file, filename, mode, caller):
        self._tracker = tracker
        self._token = token
        self._file = real_file
        self.filename = filename
        self.mode = mode
        self.caller = caller
        self._closed = False

    @property
    def closed(self):
        return self._closed or self._file.closed

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._file.close()
            finally:
                self._tracker.unregister_resource(self._token)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __iter__(self):
        return iter(self._file)

    def __next__(self):
        return next(self._file)

    def read(self, *args, **kwargs):
        return self._file.read(*args, **kwargs)

    def readline(self, *args, **kwargs):
        return self._file.readline(*args, **kwargs)

    def readlines(self, *args, **kwargs):
        return self._file.readlines(*args, **kwargs)

    def write(self, *args, **kwargs):
        return self._file.write(*args, **kwargs)

    def writelines(self, *args, **kwargs):
        return self._file.writelines(*args, **kwargs)

    def seek(self, *args, **kwargs):
        return self._file.seek(*args, **kwargs)

    def tell(self, *args, **kwargs):
        return self._file.tell(*args, **kwargs)

    def flush(self, *args, **kwargs):
        return self._file.flush(*args, **kwargs)

    def fileno(self):
        return self._file.fileno()

    def readable(self):
        return self._file.readable()

    def writable(self):
        return self._file.writable()

    def seekable(self):
        return self._file.seekable()

    def __getattr__(self, name):
        return getattr(self._file, name)

    def __del__(self):
        if not self._closed:
            LOG.warning(
                f"TrackedFile garbage collected without close(): {self.filename} "
                f"(caller={self.caller})"
            )
            self.close()


class FileTracker(object):
    """Tracks active open files and limits concurrent open file count."""

    def __init__(self, max_open_files=DEFAULT_MAX_OPEN_FILES):
        self._max_open_files = max_open_files
        self._active_resources = {}
        self._token_counter = 0
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._wait_timeout = 30.0

    @property
    def max_open_files(self):
        with self._lock:
            return self._max_open_files

    def set_max_open_files(self, limit):
        with self._lock:
            self._max_open_files = int(limit) if limit is not None else None
            self._cond.notify_all()

    def get_max_open_files(self):
        return self.max_open_files

    def get_open_file_count(self):
        with self._lock:
            return len(self._active_resources)

    def get_open_files(self):
        with self._lock:
            return [rec.to_dict() for rec in self._active_resources.values()]

    def _get_caller(self, skip_frames=2):
        stack = traceback.extract_stack()
        current_file = os.path.basename(__file__)
        for frame in reversed(stack[:-1]):
            if os.path.basename(frame.filename) != current_file:
                return f"{frame.filename}:{frame.lineno} in {frame.name}"
        if len(stack) > skip_frames:
            f = stack[-skip_frames]
            return f"{f.filename}:{f.lineno} in {f.name}"
        return "unknown"

    def register_resource(
        self,
        path,
        resource_type="resource",
        caller=None,
        handle=None,
        timeout=None,
    ):
        if caller is None:
            caller = self._get_caller()
        if timeout is None:
            timeout = self._wait_timeout

        with self._cond:
            if self._max_open_files is not None:
                start_time = datetime.datetime.now()
                while len(self._active_resources) >= self._max_open_files:
                    elapsed = (
                        datetime.datetime.now() - start_time
                    ).total_seconds()
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        sample_paths = [
                            r.path
                            for r in list(self._active_resources.values())[:5]
                        ]
                        LOG.warning(
                            f"FileTracker: Open file limit ({self._max_open_files}) "
                            f"reached; wait timed out after {timeout}s for {path}. "
                            f"Temporarily allowing open to prevent deadlock. "
                            f"Active open files ({len(self._active_resources)}): "
                            f"{sample_paths}"
                        )
                        break
                    self._cond.wait(remaining)

            self._token_counter += 1
            token = self._token_counter
            record = FileRecord(
                token=token,
                path=path,
                mode=getattr(handle, "mode", ""),
                resource_type=resource_type,
                caller=caller,
                handle=handle,
            )
            self._active_resources[token] = record
            return token

    def unregister_resource(self, token):
        with self._cond:
            if token in self._active_resources:
                del self._active_resources[token]
                self._cond.notify_all()
                return True
            return False

    def open_file(self, filename, mode="r", *args, timeout=None, **kwargs):
        caller = self._get_caller()
        token = self.register_resource(
            path=filename,
            resource_type="file",
            caller=caller,
            timeout=timeout,
        )
        try:
            real_file = builtins.open(filename, mode, *args, **kwargs)
        except Exception:
            self.unregister_resource(token)
            raise

        with self._lock:
            if token in self._active_resources:
                self._active_resources[token].handle = real_file
                self._active_resources[token].mode = mode

        return TrackedFile(self, token, real_file, filename, mode, caller)

    def verify_all_closed(self, log_leaks=True):
        with self._lock:
            open_files = self.get_open_files()
            all_closed = (len(open_files) == 0)
            if not all_closed and log_leaks:
                for item in open_files:
                    LOG.warning(
                        f"Unclosed resource detected: {item['path']} "
                        f"(type={item['type']}, mode={item['mode']}, "
                        f"opened_at={item['opened_at']}, caller={item['caller']})"
                    )
            return all_closed, open_files

    def assert_all_closed(self):
        all_closed, leaks = self.verify_all_closed(log_leaks=True)
        if not all_closed:
            raise AssertionError(
                f"Expected all files to be closed, but {len(leaks)} remained open: "
                f"{leaks}"
            )

    def close_all(self):
        with self._lock:
            tokens = list(self._active_resources.keys())
            for token in tokens:
                rec = self._active_resources.get(token)
                if rec and rec.handle is not None and hasattr(rec.handle, "close"):
                    try:
                        rec.handle.close()
                    except Exception as ex:
                        LOG.debug(f"Error closing tracked resource {rec.path}: {ex}")
                self.unregister_resource(token)


DEFAULT_FILE_TRACKER = FileTracker()

open_file = DEFAULT_FILE_TRACKER.open_file
get_open_files = DEFAULT_FILE_TRACKER.get_open_files
get_open_file_count = DEFAULT_FILE_TRACKER.get_open_file_count
verify_all_closed = DEFAULT_FILE_TRACKER.verify_all_closed
assert_all_closed = DEFAULT_FILE_TRACKER.assert_all_closed
set_max_open_files = DEFAULT_FILE_TRACKER.set_max_open_files
get_max_open_files = DEFAULT_FILE_TRACKER.get_max_open_files
register_resource = DEFAULT_FILE_TRACKER.register_resource
unregister_resource = DEFAULT_FILE_TRACKER.unregister_resource
close_all = DEFAULT_FILE_TRACKER.close_all
