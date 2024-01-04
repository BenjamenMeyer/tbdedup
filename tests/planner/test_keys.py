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
from tbdedup.planner import keys

from tests import base


class TestPlannerKeys(base.TestCase):

    def test_keys(self):
        kv = {
            k: getattr(keys, k)
            for k in dir(keys)
            if not k.startswith("__")
        }
        for _, v in kv.items():
            self.assertEqual(type(v), type(""))
