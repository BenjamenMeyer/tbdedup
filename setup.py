import sys
from setuptools import setup, find_packages

REQUIRES = ['mailbox']
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
        ],
    },
    test_suite='thunderbirddedup',
    packages=find_packages(exclude=['tests*', 'tbdedup/tests']),
    zip_safe=True,
    classifiers=[
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Topic :: Software Development :: Testing"
    ],
)
