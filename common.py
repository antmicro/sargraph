#!/usr/bin/env python3

#
# (c) 2019-2022 Antmicro <www.antmicro.com>
# License: Apache
#


import os
import subprocess
import sys
import re


# Run process, return subprocess object on success, exit script on fail
def run_process(*argv, **kwargs):
    try:
        p = subprocess.Popen(argv, **kwargs)
    except:
        print("Error: '%s' tool not found" % argv[0])
        sys.exit(1)
    return p


# Convert a string to float, also when the separator is a comma
def stof(s):
    return float(s.replace(',', '.'))


# Get the first group from a given match and convert to required type
def scan(regex, conv, string):
    match = re.search(regex, string)
    if not match:
        return None
    try:
        value = conv(match.group(1))
    except ValueError:
        return None
    return value
