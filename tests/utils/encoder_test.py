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
import ddt

from tbdedup.utils import encoder

from tests import base


@ddt.ddt
class TestUtilsEncoder(base.TestCase):

    @ddt.data(
        (b"alpha", b"alpha"),
        ("alpha", b"alpha"),
        (123, b"123"),
    )
    @ddt.unpack
    def test_encoding(self, input_data, expected_data):
        result = encoder.to_encoding(input_data)
        self.assertEqual(result, expected_data)
