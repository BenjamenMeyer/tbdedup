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

    def __init__(base):
        self.base = base
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
        return self.items.__length_hint__()

    def __contains__(self, item):
        return self.items.__contains__(item)

    def in_dir(self, item):
        return item.startswith(self.base + os.sep)

    def add_file(self, filename):
        base = os.path.basename(filename)
        root = os.path.dirname(filename)

    def add_dir(self, dirname):
        # ensure that dirname is under self.base
        if not self.in_dir(dirname):
            return False

        base = os.path.basename(dirname)
        root = os.path.dirname(dirname)

        # direct subdirectory
        if root == self.base:
            if base in self.items:
                # already in the tree
                return

            self.items[base + os.sep] = DiskTracker(dirname)
        else:  # it's somewhere down the tree
            while True:
                child_name = root[len(self.base + os.sep):].split(os.sep)[0]
                if child_name in self.items:
                    self.items[child_name].add_dir(dirname)
                    break
                else:
                    pass

        """
        parent = (
            self.items[root]
            if root in self.items
            else None
        )
        if parent is None:
            pass
        else:
            #self.items[dirname].
            pass
        """
