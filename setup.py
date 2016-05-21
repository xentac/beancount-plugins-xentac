#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup

INSTALL_REQUIRES = (
)

setup(
    name='beancount-plugins-xentac',
    version='0.0.1',
    description="Library of user contributed plugins for beancount",
    long_description="",
    license='GPLv2',
    author='Jason Chu',
    author_email='xentac@gmail.com',
    url='https://github.com/xentac/beancount-plugins',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Financial and Insurance Industry',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Utilities',
    ],
    install_requires=INSTALL_REQUIRES,
    packages=['beancount_plugins_xentac',
              'beancount_plugins_xentac.plugins',
              ],
    zip_safe=False,
)
