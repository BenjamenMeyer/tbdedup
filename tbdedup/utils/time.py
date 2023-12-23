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
import logging

LOG = logging.getLogger(__name__)


class TimeTracker(object):

    def __init__(self, name):
        self.name = name
        self.start = None
        self.end = None
        self.duration = None

    def __enter__(self):
        self.start = datetime.datetime.utcnow()
        LOG.info(f"Starting {self.name} at {self.start.isoformat()}")

    def __exit__(self, type, value, traceback):
        self.end = datetime.datetime.utcnow()
        LOG.info(f"Completed {self.name} at {self.start.isoformat()}")
        self.record_log()

    def record_log(self):
        self.duration = self.end - self.start
        total_seconds = self.duration.total_seconds()
        # extract the seconds
        minutes_prime = total_seconds // 60
        seconds = total_seconds - (minutes_prime * 60)
        # extract the minutes
        hours_prime = minutes_prime // 60
        minutes = minutes_prime - (hours_prime * 60)
        # extract the hours
        days_prime = hours_prime // 24
        hours = hours_prime - (days_prime * 24)
        # extract days
        weeks = days_prime // 7
        days = days_prime - (weeks * 7)
        # log it
        LOG.info(f"{self.name} ran for {int(weeks)} weeks {int(days)} days {int(hours)}:{int(minutes)}:{seconds:0.03f}")
