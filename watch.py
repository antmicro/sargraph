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

import graph

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
MAX_TX = 0
MAX_RX = 0
TOTAL_FS = 0

TOTAL_GPU_LOAD = 0.0
TOTAL_GPU_RAM = 0
MAX_USED_GPU_RAM = 0

FS_NAME = None
FS_SAR_INDEX = None

IFACE_NAME = None
IFACE_SAR_INDEX = None

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
    global TOTAL_GPU_RAM

    with open("/proc/meminfo") as f:
        TOTAL_RAM = int(scan("MemTotal:\s+(\d+)", float, f.read()))

    uname = machine.split(" ")[0:2]
    uname = f"{uname[0]} {uname[1]}"

    cpus = int(machine.split(" CPU)")[0].split("(")[-1])

    cpu_name = "unknown"

    with open("/proc/cpuinfo") as f:
        for line in f:
            if "model name" in line:
                cpu_name = line.replace("\n", "").split(": ")[1]
                break
    header = [
        f"# sargraph version: {SARGRAPH_VERSION}",
        f"pid: {os.getpid()}",
        f"machine: {uname}",
        f"cpu count: {cpus}",
        f"cpu: {cpu_name}"
    ]
    try:
        pgpu = subprocess.run(
            'nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits'.split(' '),
            capture_output=True
        )
        if pgpu.returncode == 0:
            gpuname, gpudriver, memory_total = pgpu.stdout.decode('utf-8').rsplit(', ', 2)
            header.extend([
                f"gpu: {gpuname}",
                f"gpu driver: {gpudriver}"
            ])
            TOTAL_GPU_RAM = int(memory_total)
    except Exception as e:
        print(e)
        pass
    with open(f"{session}.txt", "w") as f:
        print(*header, sep=", ", file=f)


# Add a summary comment to 'data.txt'
def summarize(session):
    # Is there anything to be summarized?
    if SAMPLE_NUMBER == 0:
        return

    average_load = TOTAL_LOAD / float(SAMPLE_NUMBER)
    max_used_ram = MAX_USED_RAM * 1024.0
    total_ram = TOTAL_RAM * 1024.0
    max_used_fs = MAX_USED_FS * 1024.0 * 1024.0
    total_fs = TOTAL_FS * 1024 * 1024
    max_tx = MAX_TX / 128 # kB/s to Mb/s
    max_rx = MAX_RX / 128 # kB/s to Mb/s

    sdt = datetime.datetime.strptime(START_DATE, '%Y-%m-%d %H:%M:%S')
    edt = datetime.datetime.strptime(END_DATE, '%Y-%m-%d %H:%M:%S')
    delta_t = (edt - sdt).total_seconds()

    summary = [
        f"# total ram: {total_ram:.2f} B",
        f"total disk space: {total_fs:.2f} B",
        f"max ram used: {max_used_ram:.2f} B",
        f"max disk used: {max_used_fs:.2f} B",
        f"average load: {average_load:.2f} %",
        f"observed disk: {FS_NAME}",
        f"max data received: {max_rx:.2f} Mb/s",
        f"max data sent: {max_tx:.2f} Mb/s",
        f"observed network: {IFACE_NAME}",
        f"duration: {delta_t} seconds"
    ]

    if TOTAL_GPU_RAM != 0:
        summary.extend([
            f"total gpu ram: {TOTAL_GPU_RAM * 1024 * 1024:.2f} B",  # default units are MiB
            f"max gpu ram used: {MAX_USED_GPU_RAM * 1024 * 1024:.2f} B",  # default units are MiB
            f"average gpu load: {TOTAL_GPU_LOAD / SAMPLE_NUMBER} %"
        ])

    with open(f"{session}.txt", "a") as f:
        print(*summary, sep=", ", file=f)


# Run sar and gather data from it
def watch(session, fsdev, iface):
    global SAMPLE_NUMBER
    global START_DATE
    global END_DATE
    global TOTAL_LOAD
    global MAX_USED_RAM
    global MAX_USED_FS
    global MAX_TX
    global MAX_RX
    global TOTAL_FS
    global TOTAL_RX
    global TOTAL_TX
    global FS_SAR_INDEX
    global TOTAL_RAM
    global FS_NAME
    global IFACE_NAME
    global IFACE_SAR_INDEX
    global TOTAL_GPU_LOAD
    global TOTAL_GPU_RAM
    global MAX_USED_GPU_RAM

    global die

    # Was a graph alreay produced by save command from sargraph?
    dont_plot = False

    my_env = os.environ
    my_env["S_TIME_FORMAT"] = "ISO"
    p = run_or_fail("sar", "-F", "-u", "-r", "-n", "DEV", "1", stdout=subprocess.PIPE, env=my_env)
    # subprocess for GPU data fetching in the background
    try:
        pgpu = subprocess.Popen(
            'nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits -l 1'.split(' '),
            stdout=subprocess.PIPE,
            env=my_env
        )
    except:
        pgpu = None

    machine = p.stdout.readline().decode()
    initialize(session, machine)
    p.stdout.readline()

    signal.signal(signal.SIGTERM, kill_handler)

    # Make stdin nonblocking to continue working when no command is sent
    flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
    fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    readlist = [p.stdout, sys.stdin]
    if pgpu:
        readlist.append(pgpu.stdout)
    # Gather data from sar output
    curr_gpu_util = 0
    curr_gpu_mem = 0

    while 1:
        # Await sar output or a command sent from command handler in sargraph.py
        rlist, _, _ = select.select(readlist, [], [], 0.25)
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
                        graph.graph(session, label_line)
                    elif not dont_plot:
                        graph.graph(session)
                    dont_plot = True
                    die = 1
                    break
                elif label_line.startswith("s:"):
                    label_line = label_line[len("s:"):]

                    dont_plot = True

                    if label_line != "none":
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
        if p.stdout not in rlist:
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
            TOTAL_RAM = (int(ram_data['kbmemused'][0]) + int(ram_data['kbmemfree'][0]))
        if MAX_USED_RAM < int(ram_data['kbmemused'][0]):
            MAX_USED_RAM = int(ram_data['kbmemused'][0])

        # Read and process network data
        net_data = read_table(p.stdout)
        if IFACE_SAR_INDEX is None:
            if iface:
                IFACE_SAR_INDEX = net_data['IFACE'].index(iface)
            else:
                maxj, maxv = 0, 0
                for j, used in enumerate(net_data['IFACE']):
                    v = stof(net_data['rxkB/s'][j])
                    if maxv < v:
                        maxj, maxv = j, v
                    IFACE_SAR_INDEX = maxj
        if IFACE_NAME is None:
            IFACE_NAME = net_data['IFACE'][IFACE_SAR_INDEX]
        if MAX_RX < stof(net_data['rxkB/s'][IFACE_SAR_INDEX]):
            MAX_RX = stof(net_data['rxkB/s'][IFACE_SAR_INDEX])
        if MAX_TX < stof(net_data['txkB/s'][IFACE_SAR_INDEX]):
            MAX_TX = stof(net_data['txkB/s'][IFACE_SAR_INDEX])

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
            TOTAL_FS = (stof(fs_data['MBfsused'][FS_SAR_INDEX]) + stof(fs_data['MBfsfree'][FS_SAR_INDEX]))
        if MAX_USED_FS < int(fs_data['MBfsused'][FS_SAR_INDEX]):
            MAX_USED_FS = int(fs_data['MBfsused'][FS_SAR_INDEX])

        END_DATE = date + " " + daytime
        timestamp = date + "-" + daytime

        if pgpu and pgpu.stdout in rlist:
            line = pgpu.stdout.readline().decode('utf-8')
            curr_gpu_util, curr_gpu_mem = [
                int(val.strip()) for val in line.split(', ')
            ]
            if MAX_USED_GPU_RAM < curr_gpu_mem:
                MAX_USED_GPU_RAM = curr_gpu_mem
            TOTAL_GPU_LOAD += curr_gpu_util
        with open(f"{session}.txt", "a") as f:
            line = [
                timestamp,
                cpu_data['%user'][0],
                ram_data['%memused'][0],
                fs_data['%fsused'][FS_SAR_INDEX],
                stof(net_data['rxkB/s'][IFACE_SAR_INDEX])/128, # kB/s to Mb/s
                stof(net_data['txkB/s'][IFACE_SAR_INDEX])/128 # kB/s to Mb/s
            ]
            if pgpu and TOTAL_GPU_RAM != 0:
                line.extend([
                    curr_gpu_util,
                    curr_gpu_mem / TOTAL_GPU_RAM * 100.0
                ])
            print(*line, file=f)

        if die:
            break

    # This runs if we were stopped by SIGTERM and no plot was made so far
    if not dont_plot:
        summarize(session)
        plot.plot(session)
