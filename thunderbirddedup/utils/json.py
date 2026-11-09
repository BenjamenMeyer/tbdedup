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

import io
import json

from thunderbirddedup.utils import file_tracker


def _json_dumper(obj):
    if hasattr(obj, "__json__"):
        return obj.__json__()

    # File objects - just report the name
    if isinstance(obj, io.IOBase):
        return obj.name

    return obj


def dump_to_file(filename, data):
    with file_tracker.open_file(filename, "wt") as json_output:
        json.dump(
            data,
            json_output,
            indent=4,
            sort_keys=False,
            # default=lambda __o: __o.__json__() if hasattr(__o, "__json__") else __o
            default=_json_dumper,
        )


def load_from_file(filename):
    with file_tracker.open_file(filename, "rt", encoding="utf-8") as json_input:
        return json.load(json_input)


def load_from_string(data):
    return json.loads(data)
