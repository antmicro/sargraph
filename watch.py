#!/usr/bin/env python3

#
# (c) 2019-2022 Antmicro <www.antmicro.com>
# License: Apache-2.0
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

from common import *

die = 0


# Initialize summary variables
SAMPLE_NUMBER = 0
TOTAL_RAM = 0
START_DATE = ""
END_DATE = ""
TOTAL_LOAD = 0.0
MAX_USED_RAM = 0
MAX_USED_FS = 0
TOTAL_FS = 0
FS_NAME = None
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


# Initialize 'data.txt' where the data is dumped
def initialize(session, machine):
    global TOTAL_RAM

    with open("/proc/meminfo") as f:
        TOTAL_RAM = int(scan("MemTotal:\s+(\d+)", float, f.read())/1024/1024)

    uname = machine.split(" ")[0:2]
    uname = f"{uname[0]} {uname[1]}"

    cpus = int(machine.split(" CPU)")[0].split("(")[-1])

    cpu_name = "unknown"

    with open("/proc/cpuinfo") as f:
        for line in f:
            if "model name" in line:
                cpu_name = line.replace("\n", "").split(": ")[1]
                break

    with open(f"{session}.txt", "w") as f:
        print(f"# sargraph version: {SARGRAPH_VERSION}",
              f"pid: {os.getpid()}",
              f"machine: {uname}",
              f"cpu count: {cpus}",
              f"cpu: {cpu_name}",
              sep=", ", file=f)


# Add a summary comment to 'data.txt'
def summarize(session):
    average_load = TOTAL_LOAD / float(SAMPLE_NUMBER)
    max_used_ram = MAX_USED_RAM / 1024.0 / 1024.0
    max_used_fs = MAX_USED_FS / 1024.0

    sdt = datetime.datetime.strptime(START_DATE, '%Y-%m-%d %H:%M:%S')
    edt = datetime.datetime.strptime(END_DATE, '%Y-%m-%d %H:%M:%S')
    delta_t = ((edt - sdt).total_seconds()) / 60.0

    with open(f"{session}.txt", "a") as f:
        print(f"# total ram: {TOTAL_RAM:.2f} GB",
              f"total disk space: {TOTAL_FS:.2f} GB",
              f"max ram used: {max_used_ram:.2f} GB",
              f"max disk used: {max_used_fs:.2f} GB",
              f"average load: {average_load:.2f} %",
              f"observed disk: {FS_NAME}",
              f"duration: {delta_t:.2f} minutes",
              sep=", ", file=f)


# Run sar and gather data from it
def watch(session, fsdev):
    global SAMPLE_NUMBER
    global START_DATE
    global END_DATE
    global TOTAL_LOAD
    global MAX_USED_RAM
    global MAX_USED_FS
    global TOTAL_FS
    global FS_SAR_INDEX
    global TOTAL_RAM
    global FS_NAME

    global die

    # Was a graph alreay produced by save command from sargraph?
    dont_plot = False

    my_env = os.environ
    my_env["S_TIME_FORMAT"] = "ISO"
    p = run_or_fail("sar", "-F", "-u", "-r", "1", stdout=subprocess.PIPE, env=my_env)

    machine = p.stdout.readline().decode()
    initialize(session, machine)
    p.stdout.readline()

    signal.signal(signal.SIGTERM, kill_handler)

    flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
    fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    # Gather data from sar output
    while 1:
        # Await sar output or a command sent from command handler in sargraph.py
        rlist, _, _ = select.select([p.stdout, sys.stdin], [], [], 0.25)
        now = datetime.datetime.now()
        if sys.stdin in rlist:
            label_line = sys.stdin.readline().replace("\n", "")
            if label_line.startswith("command:"):
                label_line = label_line[len("command:"):]
                if label_line.startswith("q:"):
                    label_line = label_line[len("q:"):]

                    summarize(session)
                    if label_line == "none":
                        pass
                    elif label_line:
                        import graph
                        graph.graph(session, label_line)
                    elif not dont_plot:
                        import graph
                        graph.graph(session)
                    die = 1
                    break
                elif label_line.startswith("s:"):
                    label_line = label_line[len("s:"):]

                    dont_plot = True

                    if label_line != "none":
                        import graph
                        summarize(session)
                    if not label_line:
                        graph.graph(session)
                    else:
                        graph.graph(session, label_line)
            elif label_line.startswith('label:'):
                label_line = label_line[len('label:'):]
                with open(f"{session}.txt", "a") as f:
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
        TOTAL_LOAD += stof(cpu_data["%user"][0])
        SAMPLE_NUMBER += 1

        # Read and process RAM data
        ram_data = read_table(p.stdout)
        if TOTAL_RAM == 0:
            TOTAL_RAM = (int(ram_data['kbmemused'][0]) + int(ram_data['kbmemfree'][0])) / 1024.0 / 1024.0
        if MAX_USED_RAM < int(ram_data['kbmemused'][0]):
            MAX_USED_RAM = int(ram_data['kbmemused'][0])

        # Read and process FS data
        fs_data = read_table(p.stdout)
        if FS_SAR_INDEX is None:
            if fsdev:
                FS_SAR_INDEX = fs_data['FILESYSTEM'].index(fsdev)
            else:
                maxj, maxv = 0, 0
                for j, free in enumerate(fs_data['MBfsfree']):
                    v = stof(fs_data['MBfsfree'][j]) + stof(fs_data['MBfsused'][j])
                    if maxv < v:
                        maxj, maxv = j, v
                FS_SAR_INDEX = maxj
        if FS_NAME is None:
            FS_NAME = fs_data["FILESYSTEM"][FS_SAR_INDEX]
        if TOTAL_FS == 0:
            TOTAL_FS = (stof(fs_data['MBfsused'][FS_SAR_INDEX]) + stof(fs_data['MBfsfree'][FS_SAR_INDEX])) / 1024.0
        if MAX_USED_FS < int(fs_data['MBfsused'][FS_SAR_INDEX]):
            MAX_USED_FS = int(fs_data['MBfsused'][FS_SAR_INDEX])

        END_DATE = date + " " + daytime
        timestamp = date + "-" + daytime

        with open(f"{session}.txt", "a") as f:
            print(timestamp,
                  cpu_data['%user'][0],
                  ram_data['%memused'][0],
                  fs_data['%fsused'][FS_SAR_INDEX],
                  file=f)

        if die:
            break

    if SAMPLE_NUMBER == 0:
        time.sleep(1)
        sys.exit(0)
