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
import os.path


# impossible to mock `datetime.datetime.utcnow`
# so this makes it easy to mock for testing
utcnow = datetime.datetime.utcnow


# loop control so things cannot end up in infinite loops
max_looping = 100000000


class ExcessiveLoopError(Exception):
    pass


def generate_name(utc_time, name, extension, counter):
    timestamped = utc_time.strftime(f"%Y%m%d_%H%M%S")
    numeric = ""
    if counter > 0:
        numeric = f"_{counter:03}"
    return (
        f"{timestamped}{numeric}_{name}"
        if len(extension) == 0
        else f"{timestamped}{numeric}_{name}.{extension}"
    )


def get_filename():
    counter = 0
    utc_time = utcnow()
    while True:
        output_filename = generate_name(utc_time, "dedup_preplanner", "json", counter)
        if counter > max_looping:
            raise ExcessiveLoopError("too many iterations to find a valid filename")

        if os.path.exists(output_filename):
            counter = counter + 1
            # try again
            continue
        else:
            return output_filename


def get_directory():
    counter = 0
    utc_time = utcnow()
    while True:
        output_directory = generate_name(utc_time, "dedup_planner", "", counter)

        if counter > max_looping:
            raise ExcessiveLoopError("too many iterations to find a valid filename")

        try:
            os.mkdir(output_directory)
        except (FileExistsError, FileNotFoundError):
            counter = counter + 1
            # try again
            continue
        else:
            return output_directory
