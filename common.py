#!/usr/bin/env python3

#
# (c) 2019-2023 Antmicro <www.antmicro.com>
# License: Apache-2.0
#


import os
import subprocess
import sys
import re


# Increase major number for general changes, middle number for smaller changes
# that can cause incompatibilities and minor number for regular fixes
SARGRAPH_VERSION = "2.2.1"

# Define units for use with unit_str
TIME_UNITS = ['seconds', 'minutes', 'hours']
DATA_UNITS = ['B', 'kB', 'MB', 'GB', 'TB', 'PB']
SPEED_UNITS = ['Mb/s', 'Gb/s', 'Tb/s', 'Pb/s']

# Print an error message and exit with non-zero status
def fail(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


# Run process, return subprocess object on success, exit script on failure
def run_or_fail(*argv, **kwargs):
    try:
        p = subprocess.Popen(argv, **kwargs)
    except:
        fail(f"'{argv[0]}' tool not found")
    return p


# Check if a process is running
def pid_running(pid):
    return os.path.exists(f"/proc/{pid}")


# Convert a string to float, also when the separator is a comma
def stof(s):
    return float(s.replace(',', '.'))


# Return a string without given suffix or unchange if it doesn't have it
def cut_suffix(s, sfx):
    if s.endswith(sfx):
        s = s[:-len(sfx)]
    return s


# Scale a value until it has a convenient size and unit, round the value
# and return a string representation with the new value and its unit
def unit_str(value, units, step=1024):
    value = float(value)
    biggest = len(units) - 1
    unit = 0

    while value >= step and unit < biggest:
        value /= step
        unit += 1
    return f"{round(value, 2)} {units[unit]}"


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


# Return True iff version string `a` is greater than or equal to `b`
def is_version_ge(a, b):
    a = [int(n) for n in a.split('.')]
    b = [int(n) for n in b.split('.')]

    if len(a) != len(b):
        return len(a) > len(b)
    for i, _ in enumerate(a):
        if a[i] != b[i]:
            break
    return a[i] >= b[i]
