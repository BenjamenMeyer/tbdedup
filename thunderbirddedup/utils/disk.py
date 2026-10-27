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
import os
import os.path


class DiskTracker(object):

    def __init__(self, base):
        self.base = base.rstrip(os.sep)
        self.items = {}

    def __getitem__(self, key):
        return self.items[key]

    def __setitem__(self, key, value):
        self.items[key] = value

    def __iter__(self):
        return self.items.__iter__()

    def __reversed__(self):
        return self.items.__reversed__()

    def __len__(self):
        return len(self.items)

    def __length_hint__(self):
        return len(self.items)

    def __contains__(self, item):
        return self.items.__contains__(item)

    def in_dir(self, item):
        return item.startswith(self.base + os.sep)

    def add_file(self, filename):
        if not self.in_dir(filename):
            return False

        base = os.path.basename(filename)
        root = os.path.dirname(filename)
        if root == self.base:
            self.items[base] = filename
            return True

        self.add_dir(root)
        child_dir_name = root[len(self.base + os.sep):].split(os.sep)[0]
        return self.items[child_dir_name + os.sep].add_file(filename)

    def add_dir(self, dirname):
        dirname = dirname.rstrip(os.sep)
        # ensure that dirname is under self.base
        if not self.in_dir(dirname):
            return False

        base = os.path.basename(dirname)
        root = os.path.dirname(dirname)

        # direct subdirectory
        if root == self.base:
            key = base + os.sep
            if key in self.items:
                # already in the tree
                return True

            self.items[key] = DiskTracker(dirname)
            return True

        # somewhere down the tree
        child_dir_name = root[len(self.base + os.sep):].split(os.sep)[0]
        child_key = child_dir_name + os.sep
        if child_key not in self.items:
            self.items[child_key] = DiskTracker(
                os.path.join(self.base, child_dir_name)
            )
        return self.items[child_key].add_dir(dirname)
