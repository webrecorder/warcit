#!/usr/bin/env python
# vim: set sw=4 et:

from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand
import glob

__version__ = '0.4.0'


class PyTest(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)

    def run_tests(self):
        import pytest
        import sys
        import os
        errcode = pytest.main(['--doctest-modules', './warcit', '--cov', 'warcit', '-v', 'test/'])
        sys.exit(errcode)

setup(
    name='warcit',
    version=__version__,
    author='Ilya Kreymer',
    author_email='ikreymer@gmail.com',
    license='Apache 2.0',
    packages=find_packages(),
    url='https://github.com/webrecorder/warcit',
    description='Convert Directories, Files and Zip Files to Web Archives (WARC)',
    long_description=open('README.rst').read(),
    provides=[
        'warcit',
        ],
    install_requires=[
        'warcio>=1.6.1',
        'cchardet',
        'pyyaml',
        ],
    zip_safe=True,
    package_data={
        'warcit': ['*.yaml']
        },
    entry_points="""
        [console_scripts]
        warcit = warcit.warcit:main
        warcit-converter = warcit.converter:main
    """,
    cmdclass={'test': PyTest},
    test_suite='',
    tests_require=[
        'pytest',
        'pytest-cov',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
    ]
)
