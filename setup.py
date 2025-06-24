# setup.py
from setuptools import setup, find_packages

setup(
    name='openterface_py',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    version='0.1.0',
)
