#!/usr/bin/env python
from setuptools import setup
import os.path


ETC = os.path.join(os.path.dirname(__file__), 'etc')

with open(os.path.join(ETC, 'requirements.pip')) as f:
    reqs = [l.strip() for l in f if '://' not in l]
reqs.append('distribute')

setup(
        name='bang',
        version='0.1',
        author='fr33jc',
        author_email='fr33jc@gmail.com',
        packages=['bang', 'bang.deployers'],
        license='GPLv3',
        description='Server and cloud resource deployment automation',
        platforms='POSIX',
        url='https://github.com/fr33jc/bang',
        install_requires=reqs,
        scripts=['bin/bang'],
        )
