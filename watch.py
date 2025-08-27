#!/usr/bin/env python3

#
# (c) 2019-2023 Antmicro <www.antmicro.com>
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
import psutil
import sched
import platform
import logging
from threading import Thread, Lock
import threading
from logging.handlers import DatagramHandler

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
TOTAL_FS = 0
MAX_TX = 0
MAX_RX = 0
START_TX = 0
START_RX = 0
END_TX = 0
END_RX = 0

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

class UDPHandler(DatagramHandler):
    def emit(self, msg):
        try:
            if self.sock is None:
                self.createSocket()
            self.sock.sendto(self.format(msg).encode(), self.address)
        except Exception as e:
            pass


logger = logging.getLogger("sargraph")
logger.setLevel(logging.INFO)

# Read a single table from sar output
def read_table(psar):
    # Find the header
    f = psar.stdout
    while True:
        header = f.readline().decode().split()
        if len(header) > 0:
            break
        if psar.poll() is not None:
            raise ValueError("The subprocess has exited")

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
        if psar.poll() is not None:
            raise ValueError("The subprocess has exited")

        for i, value in enumerate(row):
            table[header[i]].append(value)

    return table


# Read received/sent bytes from a given interface's sys stats
def read_iface_stats(iface):
    with open(f"/sys/class/net/{iface}/statistics/rx_bytes") as f:
        rx = scan(r"(\d+)", int, f.readline())
    with open(f"/sys/class/net/{iface}/statistics/tx_bytes") as f:
        tx = scan(r"(\d+)", int, f.readline())
    return rx, tx


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

    logger.info(", ".join(header))

def initialize_darwin(session):
    global TOTAL_RAM
    global TOTAL_GPU_RAM

    TOTAL_RAM = int(psutil.virtual_memory().total / 1024)

    cpus = psutil.cpu_count(logical=True)

    cpu_name = platform.processor() or "unknown"

    header = [
        f"# psutil version: {psutil.__version__}",
        f"pid: {os.getpid()}",
        f"machine: {platform.system()}",
        f"cpu count: {cpus}",
        f"cpu: {cpu_name}"
    ]
    logger.info(", ".join(header))


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
    total_tx = END_TX-START_TX
    total_rx = END_RX-START_RX

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
        f"max received: {max_rx:.2f} Mb/s",
        f"max sent: {max_tx:.2f} Mb/s",
        f"observed network: {IFACE_NAME}",
        f"duration: {delta_t} seconds",
        f"total received: {total_rx} b",
        f"total sent: {total_tx} b"
    ]

    if TOTAL_GPU_RAM != 0:
        summary.extend([
            f"total gpu ram: {TOTAL_GPU_RAM * 1024 * 1024:.2f} B",  # default units are MiB
            f"max gpu ram used: {MAX_USED_GPU_RAM * 1024 * 1024:.2f} B",  # default units are MiB
            f"average gpu load: {TOTAL_GPU_LOAD / SAMPLE_NUMBER:.2f} %"
        ])

    logger.info(", ".join([str(i) for i in summary]))

def get_meminfo(scheduler):
    global MAX_USED_RAM
    scheduler.enter(0.1, 1, get_meminfo, (scheduler,))
    now = datetime.datetime.now()
    date = now.strftime("%Y-%m-%d")
    daytime = now.strftime("%H:%M:%S.%f")
    ram_data = psutil.virtual_memory()
    used = (ram_data.total - ram_data.free)
    if used // 1024 > MAX_USED_RAM:
        MAX_USED_RAM = used // 1024
    if is_darwin():
        line = [
            date + "-" + daytime,
            100 * ram_data.free / ram_data.total,
            0,
            100 * used / ram_data.total,
            0
        ]
    else:
        line = [
            date + "-" + daytime,
            100 * ram_data.free / ram_data.total,
            100 * ram_data.cached / ram_data.total,
            100 * ram_data.used / ram_data.total,
            100 * ram_data.shared / ram_data.total
        ]
    msg = " ".join(["psu"]+[str(i) for i in line])
    logger.info(msg)


def watch(session, fsdev, iface, tmpfs_color, other_cache_color, use_psutil, udp=None, udp_cookie=None):
    file_handler = logging.FileHandler(f"{session}.txt")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(file_handler)

    if udp is not None:
        spl = udp.rsplit(':', 1)
        udp_handler = UDPHandler(spl[0], int(spl[1]))
        if udp_cookie is None:
            udp_handler.setFormatter(logging.Formatter("%(message)s\n"))
        else:
            udp_handler.setFormatter(logging.Formatter(f"[{udp_cookie}] %(message)s\n"))
        logger.addHandler(udp_handler)

    if is_darwin() or use_psutil:
        return watch_psutil(session, fsdev, iface, tmpfs_color, other_cache_color)
    return watch_sar(session, fsdev, iface, tmpfs_color, other_cache_color)

# Run sar and gather data from it
def watch_sar(session, fsdev, iface, tmpfs_color, other_cache_color):
    global SAMPLE_NUMBER
    global START_DATE
    global END_DATE
    global TOTAL_LOAD
    global MAX_USED_RAM
    global MAX_USED_FS
    global MAX_RX
    global MAX_TX
    global TOTAL_FS
    global START_RX
    global START_TX
    global END_RX
    global END_TX
    global TOTAL_RAM
    global FS_SAR_INDEX
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

    psar = run_or_fail("sar", "-F", "-u", "-n", "DEV", "1", stdout=subprocess.PIPE, env=my_env)

    s = sched.scheduler(time.time, time.sleep)
    mem_ev = s.enter(0, 1, get_meminfo, (s,))
    thread = Thread(target = s.run)
    thread.start()

    # subprocess for GPU data fetching in the background
    try:
        pgpu = subprocess.Popen(
            'nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits -l 1'.split(' '),
            stdout=subprocess.PIPE,
            env=my_env
        )
    except:
        pgpu = None

    machine = psar.stdout.readline().decode()
    initialize(session, machine)
    psar.stdout.readline()

    signal.signal(signal.SIGTERM, kill_handler)

    # Make stdin nonblocking to continue working when no command is sent
    flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
    fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    # Gather data from sar output
    curr_gpu_util = 0
    curr_gpu_mem = 0

    while 1:
        # Await sar output or a command sent from command handler in sargraph.py
        readlist = [psar.stdout, sys.stdin]
        if pgpu:
            readlist.append(pgpu.stdout)
        rlist, _, _ = select.select(readlist, [], [], 0.25)
        now = datetime.datetime.now()
        if sys.stdin in rlist:
            if handle_command(session, s, dont_plot, tmpfs_color, other_cache_color, now):
                break
        if psar.stdout not in rlist:
            continue

        date = now.strftime("%Y-%m-%d")
        daytime = now.strftime("%H:%M:%S")

        # Read and process CPU data
        try:
            cpu_data = read_table(psar)
            if START_DATE == "":
                START_DATE = date + " " + daytime
            TOTAL_LOAD += stof(cpu_data["%user"][0])
            SAMPLE_NUMBER += 1

            if TOTAL_RAM == 0:
                TOTAL_RAM = psutil.virtual_memory().total // 1024

            # Read and process network data
            net_data = read_table(psar)
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
            if START_RX <= 0 or START_TX <= 0:
                START_RX, START_TX = read_iface_stats(IFACE_NAME)
            END_RX, END_TX = read_iface_stats(IFACE_NAME)
            if MAX_RX < stof(net_data['rxkB/s'][IFACE_SAR_INDEX]):
                MAX_RX = stof(net_data['rxkB/s'][IFACE_SAR_INDEX])
            if MAX_TX < stof(net_data['txkB/s'][IFACE_SAR_INDEX]):
                MAX_TX = stof(net_data['txkB/s'][IFACE_SAR_INDEX])

            # Read and process FS data
            fs_data = read_table(psar)
            if FS_SAR_INDEX is None:
                if fsdev:
                    FS_SAR_INDEX = fs_data['FILESYSTEM'].index(fsdev)
                else:
                    maxj, maxv = 0, 0
                    for j, free in enumerate(fs_data['MBfsfree']):
                        v = stof(fs_data['MBfsfree'][j]) + stof(fs_data['MBfsused'][j])
                        # Skip shared memory device
                        if fs_data["FILESYSTEM"][j] == "/dev/shm":
                            continue
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
        except ValueError as e:
            print("Sar process has exited - quitting sargraph")
            break

        if pgpu and pgpu.stdout in rlist:
            line = pgpu.stdout.readline().decode('utf-8')
            if pgpu.poll() is not None:
                    print("nvidia-smi stopped working, reason:")
                    print(line)
                    print(f"Error code:  {pgpu.returncode}")
                    print("Closing the GPU statistics collection")
                    pgpu = None
            else:
                try:
                    curr_gpu_util, curr_gpu_mem = [
                        int(val.strip()) for val in line.split(', ')
                    ]
                    if MAX_USED_GPU_RAM < curr_gpu_mem:
                        MAX_USED_GPU_RAM = curr_gpu_mem
                    TOTAL_GPU_LOAD += curr_gpu_util
                except ValueError:
                    print(f"nvidia-smi error readout:  {line}")
                    if "Unknown Error" in line:
                        # No valid readouts from now on, let's terminate current nvidia-smi session
                        pgpu.terminate()
                        pgpu = None

        line = [
            timestamp,
            cpu_data['%user'][0],
            fs_data['%fsused'][FS_SAR_INDEX],
            stof(net_data['rxkB/s'][IFACE_SAR_INDEX])/128, # kB/s to Mb/s
            stof(net_data['txkB/s'][IFACE_SAR_INDEX])/128, # kB/s to Mb/s
        ]
        if pgpu and TOTAL_GPU_RAM != 0:
            line.extend([
                f'{curr_gpu_util:.2f}',
                f'{curr_gpu_mem / TOTAL_GPU_RAM * 100.0:.2f}'
            ])
        logger.info(" ".join(["sar"]+[str(i) for i in line]))

        if die:
            break

    list(map(s.cancel, s.queue))
    thread.join()

    # This runs if we were stopped by SIGTERM and no plot was made so far
    if not dont_plot:
        summarize(session)
        graph.graph(session, tmpfs_color, other_cache_color)

def watch_psutil(session, fsdev, iface, tmpfs_color, other_cache_color):
    # Was a graph already produced by save command from sargraph?
    dont_plot = False

    s = sched.scheduler(time.time, time.sleep)
    sar_ev = s.enter(0, 1, psutil_sar_simulation, (s,))
    mem_ev = s.enter(0, 1, get_meminfo, (s,))
    thread = Thread(target = s.run)
    thread.start()


    initialize_darwin(session)
    signal.signal(signal.SIGTERM, kill_handler)

    # Make stdin nonblocking to continue working when no command is sent
    flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
    fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)


    while 1:
        # Await sar output or a command sent from command handler in sargraph.py
        readlist = [sys.stdin]
        rlist, _, _ = select.select(readlist, [], [], 0.25)
        now = datetime.datetime.now()
        if handle_command(session, s, dont_plot, tmpfs_color, other_cache_color, now):
            break
    list(map(s.cancel, s.queue))
    thread.join()

    # This runs if we were stopped by SIGTERM and no plot was made so far
    if not dont_plot:
        summarize(session)
        graph.graph(session, tmpfs_color, other_cache_color)

def handle_command(session, s, dont_plot, tmpfs_color, other_cache_color, now):
    global die
    label_line = sys.stdin.readline().replace("\n", "")
    if label_line.startswith("command:"):
        label_line = label_line[len("command:"):]
        if label_line.startswith("q:"):
            label_line = label_line[len("q:"):]

            list(map(s.cancel, s.queue))
            summarize(session)
            if label_line == "none":
                pass
            elif label_line:
                graph.graph(session, tmpfs_color, other_cache_color, label_line)
            elif not dont_plot:
                graph.graph(session, tmpfs_color, other_cache_color)
            dont_plot = True
            die = 1
            return True
        elif label_line.startswith("s:"):
            label_line = label_line[len("s:"):]

            dont_plot = True

            if label_line != "none":
                summarize(session)
            if not label_line:
                graph.graph(session, tmpfs_color, other_cache_color)
            else:
                graph.graph(session, tmpfs_color, other_cache_color, label_line)
    elif label_line.startswith('label:'):
        label_line = label_line[len('label:'):]
        with open(f"{session}.txt", "a") as f:
            timestamp = now.strftime("%Y-%m-%d-%H:%M:%S")
            print(f"# {timestamp} label: {label_line}", file=f)
    return False

# sar is not available on macOS. This function creates the sar behavior, but use psutil instead. 
def psutil_sar_simulation(scheduler):
    global START_DATE
    global TOTAL_LOAD
    global SAMPLE_NUMBER
    global TOTAL_RAM
    global START_RX
    global START_TX
    global END_TX
    global END_RX
    global MAX_RX
    global MAX_TX
    global IFACE_NAME
    global TOTAL_FS
    global MAX_USED_FS
    global FS_NAME
    global END_DATE

    scheduler.enter(1, 1, psutil_sar_simulation, (scheduler,))
    now = datetime.datetime.now()
    date = now.strftime("%Y-%m-%d")
    daytime = now.strftime("%H:%M:%S")
    if START_DATE == "":
        START_DATE = date + " " + daytime
    cpu_used = psutil.cpu_percent()
    TOTAL_LOAD += cpu_used
    SAMPLE_NUMBER += 1
    if TOTAL_RAM == 0:
        TOTAL_RAM = psutil.virtual_memory().total // 1024
    IFACE_NAME = "all"
    net_stats = psutil.net_io_counters()
    if START_RX <= 0 or START_TX <= 0:
            START_RX, START_TX = net_stats.bytes_recv, net_stats.bytes_sent
            END_RX, END_TX = net_stats.bytes_recv, net_stats.bytes_sent
    curr_rx, curr_tx = (net_stats.bytes_recv - END_RX) / (1024 * 8), (net_stats.bytes_sent - END_TX) / (1024 * 8)
    END_RX, END_TX = net_stats.bytes_recv, net_stats.bytes_sent
    if MAX_RX < curr_rx:
        MAX_RX = curr_rx
    if MAX_TX < curr_tx:
        MAX_TX = curr_tx
    # apfs implements lvm, so it's a better option for visualizing the place in the container (which is shared by all partitions).
    if is_darwin():
        FS_NAME = "apfs container"
        disk_stats = psutil.disk_usage('/')
    else: 
        largest_partition = max(
            psutil.disk_partitions(all=False),
            key=lambda p: psutil.disk_usage(p.mountpoint).total
        )
        disk_stats = psutil.disk_usage(largest_partition.mountpoint)
        FS_NAME = largest_partition.device
        
    curr_used = (disk_stats.total - disk_stats.free) / (1024 * 1024)
    if TOTAL_FS == 0:
        TOTAL_FS = disk_stats.total / (1024 * 1024)
    if MAX_USED_FS < curr_used:
        MAX_USED_FS = curr_used
    END_DATE = date + " " + daytime
    timestamp = date + "-" + daytime

    line = [
        timestamp,
        cpu_used,
        ((disk_stats.total - disk_stats.free) / disk_stats.total) * 100,
        curr_rx / 128,
        curr_tx / 128,
    ]

    logger.info(" ".join(["sar"]+[str(i) for i in line]))
