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
import sys
from setuptools import setup, find_packages

REQUIRES = [
    'mailbox',
    #'asyncqt',
    #'qasync',
    #'PySide6',
    'asyncSlot',
    'PyQt5',
]
EXTRA_REQUIRES = {
}

setup(
    name='thunderbirddedup',
    version='0.1',
    description='Tool to dedup Thunderbird MBox Files',
    license='Apache License 2.0',
    url='TBD',
    author='Benjamen R. Meyer',
    author_email='bm_witness@yahoo.com',
    install_requires=REQUIRES,
    extras_require=EXTRA_REQUIRES,
    entry_points={
        'console_scripts': [
            'tb-dedup=tbdedup.cmd:main',
            'tb-dedup-gui=tbdedup.gui2:main',
        ],
    },
    test_suite='tbdedup',
    packages=find_packages(exclude=['tests*', 'tbdedup/tests']),
    zip_safe=True,
    classifiers=[
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Topic :: Software Development :: Testing"
    ],
)
