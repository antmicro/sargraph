#!/usr/bin/env python3

#
# (c) 2019-2022 Antmicro <www.antmicro.com>
# License: Apache
#


import datetime
import fcntl
import os
import re
import select
import signal
import subprocess
import sys
import time

# Get access to main module information
import __main__

from common import *

global die

die = 0


# Initialize summary variables
TOTAL_RAM = 0
START_DATE = ""
END_DATE = ""
AVERAGE_LOAD = 0.0
MAX_USED_RAM = 0
MAX_USED_FS = 0
TOTAL_FS = 0
FS_SAR_INDEX = None


# Handle SIGTERM
def kill_handler(a, b):
    global die
    die = 1


# Read a single table from sar output
def read_table(f):
    # Find the header
    while True:
        header = f.readline().decode().split()
        if len(header) > 0:
            break

    # The first columns is always just time
    header[0] = 'time'

    table = {}
    for title in header:
        table[title] = []

    # Read rows
    while True:
        row = f.readline().decode().split()
        if len(row) <= 0:
            break

        for i, value in enumerate(row):
            table[header[i]].append(value)

    return table


my_env = os.environ
my_env["S_TIME_FORMAT"] = "ISO"

with open("/proc/meminfo") as f:
    TOTAL_RAM = int(scan("MemTotal:\s+(\d+)", float, f.read())/1024/1024)


p = run_process("sar", "-F", "-u", "-r", "1", stdout=subprocess.PIPE, env=my_env)

print(os.getpid())

machine = p.stdout.readline().decode()

uname = machine.split(" ")[0:2]
uname = f"{uname[0]} {uname[1]}"

cpus = int(machine.split(" CPU)")[0].split("(")[-1])

cpu_name = "unknown"

with open("/proc/cpuinfo") as f:
    for line in f:
        if "model name" in line:
            cpu_name = line.replace("\n", "").split(": ")[1]
            break

with open("data.txt", "w") as f:
    print(f"# pid: {os.getpid()}",
          f"machine: {uname}",
          f"cpu count: {cpus}",
          f"cpu: {cpu_name}",
          sep=", ", file=f)

p.stdout.readline()

if args.fspath:
    args.fspath = os.path.realpath(args.fspath)
    with open("/proc/self/mounts", "r") as f:
        while args.fsdev is None:
            args.fsdev = scan(f"^(/dev/\S+)\s+{re.escape(args.fspath)}\s+", str, f.readline())
    if not args.fsdev:
        print(f"Error: no device is mounted on {args.fspath}")
        sys.exit(1)

signal.signal(signal.SIGTERM, kill_handler)
i = 0

flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)

# Gather data from sar output
while 1:
    # Await sar output or a command sent from command handler in sargraph.py
    rlist, _, _ = select.select([p.stdout, sys.stdin], [], [], 0.25)
    now = datetime.datetime.now()
    if sys.stdin in rlist:
        label_line = sys.stdin.readline().replace("\n", "")
        if label_line == "q":
            die = 1
            break

        with open("data.txt", "a") as f:
            timestamp = now.strftime("%Y-%m-%d-%H:%M:%S")
            print(f"# {timestamp} label: {label_line}", file=f)
    if (p.stdout not in rlist):
        continue

    date = now.strftime("%Y-%m-%d")
    daytime = now.strftime("%H:%M:%S")

    # Read and process CPU data
    cpu_data = read_table(p.stdout)
    if START_DATE == "":
        START_DATE = date + " " + daytime
    AVERAGE_LOAD += stof(cpu_data["%user"][0])
    i = i + 1

    # Read and process RAM data
    ram_data = read_table(p.stdout)
    if TOTAL_RAM == 0:
        TOTAL_RAM = (int(ram_data['kbmemused'][0]) + int(ram_data['kbmemfree'][0])) / 1024.0 / 1024.0
    if MAX_USED_RAM < int(ram_data['kbmemused'][0]):
        MAX_USED_RAM = int(ram_data['kbmemused'][0])

    # Read and process FS data
    fs_data = read_table(p.stdout)
    if FS_SAR_INDEX is None:
        if args.fsdev:
            FS_SAR_INDEX = fs_data['FILESYSTEM'].index(args.fsdev)
        else:
            maxj, maxv = 0, 0
            for j, free in enumerate(fs_data['MBfsfree']):
                v = stof(fs_data['MBfsfree'][j]) + stof(fs_data['MBfsused'][j])
                if maxv < v:
                    maxj, maxv = j, v
            FS_SAR_INDEX = maxj
    if TOTAL_FS == 0:
        TOTAL_FS = (stof(fs_data['MBfsused'][FS_SAR_INDEX]) + stof(fs_data['MBfsfree'][FS_SAR_INDEX])) / 1024.0
    if MAX_USED_FS < int(fs_data['MBfsused'][FS_SAR_INDEX]):
        MAX_USED_FS = int(fs_data['MBfsused'][FS_SAR_INDEX])

    END_DATE = date + " " + daytime
    timestamp = date + "-" + daytime

    with open("data.txt", "a") as f:
        print(timestamp,
              cpu_data['%user'][0],
              ram_data['%memused'][0],
              fs_data['%fsused'][FS_SAR_INDEX],
              file=f)

    if die:
        break

if i == 0:
    time.sleep(1)
    sys.exit(0)

FS_NAME = fs_data["FILESYSTEM"][FS_SAR_INDEX]

AVERAGE_LOAD = AVERAGE_LOAD / float(i)
MAX_USED_RAM = MAX_USED_RAM / 1024.0 / 1024.0
MAX_USED_FS /= 1024.0

sdt = datetime.datetime.strptime(START_DATE, '%Y-%m-%d %H:%M:%S')
edt = datetime.datetime.strptime(END_DATE, '%Y-%m-%d %H:%M:%S')
delta_t = ((edt - sdt).total_seconds()) / 60.0

with open("data.txt", "a") as f:
    print(f"# total ram: {TOTAL_RAM:.2f} GB",
          f"total disk space: {TOTAL_FS:.2f} GB",
          f"max ram used: {MAX_USED_RAM:.2f} GB",
          f"max disk used: {MAX_USED_FS:.2f} GB",
          f"average load: {AVERAGE_LOAD:.2f} %",
          f"observed disk: {FS_NAME}",
          f"duration: {delta_t:.2f} minutes",
          sep=", ", file=f)
