import os
import sys

from setuptools import setup, find_packages

import pymr as module

WINDOWS = sys.platform.lower().startswith("win")


def walker(base, *paths):
    file_list = set([])
    cur_dir = os.path.abspath(os.curdir)

    os.chdir(base)
    try:
        for path in paths:
            for dir_name, dirs, files in os.walk(path):
                for f in files:
                    file_list.add(os.path.join(dir_name, f))
    finally:
        os.chdir(cur_dir)

    return list(file_list)


requires = (
    'ruamel.yaml~=0.17.21',
    'ruamel.yaml.clib~=0.2.7',
    'aiohttp~=3.8.3',
    'tenacity~=8.1.0',
    'yarl~=1.8.2',
    'python-dateutil~=2.8.2',
    'setuptools~=65.5.1',
)

setup(
    name='pymr',
    version=module.__version__,
    author=module.__author__,
    author_email=module.email,
    license=module.package_license,
    description=module.package_info,
    platforms="all",
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Operating System :: MacOS',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.10',
        'Topic :: Internet',
        'Topic :: Software Development',
    ],
    long_description=open('README.md').read(),
    packages=find_packages(exclude=(
        'tests', 'tests.*', 'tests_performance', 'tests_migrations',
    )),
    package_data={
        module.__name__: walker(
            os.path.dirname(module.__file__),
        ),
    },
    entry_points={
        'console_scripts': [
            f'mr = {module.__name__}.merge_requests:main',
        ]
    },
    install_requires=requires,
    extras_require={
        'develop': [
            'pytest<3.7',
            'pytest-cov',
        ],
    }
)
