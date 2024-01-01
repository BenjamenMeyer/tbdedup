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
import os
import tempfile
import unittest


class TestCase(unittest.TestCase):

    def setUp(self):
        super(TestCase, self).setUp()

    def tearDown(self):
        super(TestCase, self).tearDown()


class AsyncioTestCase(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        super(unittest.IsolatedAsyncioTestCase, self).setUp()

    async def asyncSetUp(self):
        pass

    def tearDown(self):
        super(unittest.IsolatedAsyncioTestCase, self).tearDown()

    async def asyncTearDown(self):
        pass


class ValueSwap(object):

    def __init__(self, module, value_to_replace, new_value):
        self.module = module
        self.value_to_replace = value_to_replace
        self.new_value = new_value
        self.old_value = getattr(self.module, self.value_to_replace)

    def __enter__(self):
        setattr(self.module, self.value_to_replace, self.new_value)

    def __exit__(self, exc_type, exc_value, traceback):
        setattr(self.module, self.value_to_replace, self.old_value)


class GenericOptions(object):

    def __init__(self, **kv):
        for k, v in kv.items():
            setattr(self, k, v)


class KeepLocalDirClean(object):

    def __init__(self):
        self.cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()

    def __enter__(self):
        os.chdir(self.temp_dir.name)

    def __exit__(self, exc_type, exc_value, traceback):
        os.chdir(self.cwd)
