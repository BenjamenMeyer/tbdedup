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
import os.path

from thunderbirddedup.utils import json as tb_json

from tests import base


class CustomJsonObj(object):
    def __json__(self):
        return {"custom": "value"}


class PlainObj(object):
    pass


class TestUtilsJson(base.TestCase):

    def test_json_dumper_and_dump_to_file(self):
        with base.KeepLocalDirClean() as cwd:
            sample_file = os.path.join(cwd.temp_dir.name, "sample.txt")
            with open(sample_file, "wt") as f:
                f.write("hello")
                self.assertEqual(tb_json._json_dumper(f), sample_file)

            self.assertEqual(
                tb_json._json_dumper(CustomJsonObj()),
                {"custom": "value"},
            )
            plain = PlainObj()
            self.assertIs(tb_json._json_dumper(plain), plain)

            out_json = os.path.join(cwd.temp_dir.name, "out.json")
            tb_json.dump_to_file(out_json, {"obj": CustomJsonObj()})
            self.assertTrue(os.path.isfile(out_json))
