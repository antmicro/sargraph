#!/usr/bin/env python3

#
# (c) 2019-2022 Antmicro <www.antmicro.com>
# License: Apache
#


import argparse
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

global die

die = 0


# Declare and parse command line flags
parser = argparse.ArgumentParser()
parser.add_argument('session', metavar='SESSION-NAME', type=str, nargs='?', default=None,                help='sargraph session name')
parser.add_argument('command', metavar='COMMAND',      type=str, nargs='*',                              help='send command')
parser.add_argument('-f',      metavar='DEVICE-NAME',  type=str, nargs='?', default=None, dest='fsdev',  help='observe a chosen filesystem')
parser.add_argument('-m',      metavar='MOUNT-DIR',    type=str, nargs='?', default=None, dest='fspath', help='observe a chosen filesystem')
args = parser.parse_args()


# Handle SIGTERM
def kill_handler(a, b):
        global die
        die = 1


# Check if a process is running
def pid_running(pid):
    return os.path.exists("/proc/%d" % pid)


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


OUTPUT_TYPE="pngcairo"
OUTPUT_EXT="png"
try:
    if os.environ["SARGRAPH_OUTPUT_TYPE"] == "svg":
        OUTPUT_TYPE="svg"
        OUTPUT_EXT="svg"
except:
    pass

p = run_process("sar", "-V", stdout=subprocess.PIPE)

# If the script was run with parameters, handle them
if args.session:
    # Check if screen provides expected output
    p = run_process("screen", "-v", stdout=subprocess.PIPE)
    version = scan("Screen version (\d+)", int, p.stdout.readline().decode())
    if version is None:
        print("Error: 'screen' tool returned unknown output!")
        sys.exit(1)

    # Check if a command was provided
    if len(args.command) <= 0:
        print("Error: command not provided.")
        sys.exit(1)

    # Get session name and command name
    sid = args.session
    cmd = args.command

    if cmd[0] == "start":
        print("Starting sargraph session '%s'" % sid)
        p = subprocess.Popen(["screen", "-dmSL", sid, os.path.realpath(__file__), *sys.argv[3:]])
        while p.poll() is None:
            time.sleep(0.1)
        gpid = 0
        j = 0
        time.sleep(1)
        print("Session '%s' started" % sid)
    elif cmd[0] == "stop":
        print("Terminating sargraph session '%s'" % sid)

        try:
            gpid = int(os.popen("screen -ls | grep '.%s' | tr -d ' \t' | cut -f 1 -d '.'" % sid).read())
        except:
            print("Warning: cannot find pid.")
            gpid = -1
        p = subprocess.Popen(["screen", "-S", sid, "-X", "stuff", "q\n"])
        while p.poll() is None:
            time.sleep(0.1)
        if gpid == -1:
            print("Waiting 3 seconds.")
            time.sleep(3)
        else:
            #print("Waiting for pid %d" % gpid)
            while pid_running(gpid):
                time.sleep(0.25)
    elif cmd[0] == "label":
        # Check if the label name was provided
        if len(cmd) < 2:
            print("Error: label command requires an additional parameter")
            sys.exit(1)
        label = cmd[1]

        print("Adding label '%s' to sargraph session '%s'." % (label, sid))
        p = subprocess.Popen(["screen", "-S", sid, "-X", "stuff", "%s\n" % label])
        while p.poll() is None:
            time.sleep(0.1)
    else:
        print("Error: Unknown command '%s'" % cmd[0])
        sys.exit(1)
    sys.exit(0)

my_env = os.environ
my_env["S_TIME_FORMAT"] = "ISO"

TOTAL_RAM = 0

with open("/proc/meminfo") as f:
    TOTAL_RAM = int(scan("MemTotal:\s+(\d+)", float, f.read())/1024/1024)


p = run_process("sar", "-F", "-u", "-r", "1", stdout=subprocess.PIPE, env=my_env)

print("%d" % os.getpid())

machine = p.stdout.readline().decode()

uname = machine.split(" ")[0:2]
uname = "%s %s" % (uname[0], uname[1])

cpus = int(machine.split(" CPU)")[0].split("(")[-1])

cpu_name = "unknown"

with open("/proc/cpuinfo") as f:
    for line in f:
        if "model name" in line:
            cpu_name = line.replace("\n", "").split(": ")[1]
            break

with open("data.txt", "w") as f:
    f.write("# pid: %d, machine: %s, cpu count: %d, cpu: %s\n" % (os.getpid(), uname, cpus, cpu_name))

p.stdout.readline()

if args.fspath:
    args.fspath = os.path.realpath(args.fspath)
    with open("/proc/self/mounts", "r") as f:
        while args.fsdev is None:
            args.fsdev = scan("^(/dev/\S+)\s+%s\s+" % re.escape(args.fspath), str, f.readline())
    if not args.fsdev:
        print("Error: no device is mounted on %s" % args.fspath)
        sys.exit(1)

signal.signal(signal.SIGTERM, kill_handler)
i = 0

START_DATE = ""
END_DATE = ""
AVERAGE_LOAD = 0.0
MAX_USED_RAM = 0
MAX_USED_FS = 0
TOTAL_FS = 0

FS_SAR_INDEX = None

flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)
fcntl.fcntl(sys.stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)
labels = []

# Gather data from sar output
while 1:
    rlist, _, _ = select.select([p.stdout, sys.stdin], [], [], 0.25)
    now = datetime.datetime.now()
    if sys.stdin in rlist:
        label_line = sys.stdin.readline().replace("\n", "")
        if label_line == "q":
            die = 1
            break
        labels.append(["%04d-%02d-%02d-%02d:%02d:%02d" % (now.year, now.month, now.day, now.hour, now.minute, now.second), label_line])
        with open("data.txt", "a") as f:
            f.write("# %04d-%02d-%02d-%02d:%02d:%02d label: %s\n" % (now.year, now.month, now.day, now.hour, now.minute, now.second, label_line))
    if (p.stdout not in rlist):
        continue

    date = "%04d-%02d-%02d" % (now.year, now.month, now.day)
    daytime = "%02d:%02d:%02d" % (now.hour, now.minute, now.second)

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
        f.write("%s %s %s %s\n" % (timestamp, cpu_data["%user"][0], ram_data["%memused"][0], fs_data["%fsused"][FS_SAR_INDEX]))

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
    f.write("# total ram: %.2f GB, total disk space: %.2f GB, max ram used: %.2f GB, max disk used: %.2f GB, average load: %.2f %%, observed disk: %s, duration: %.2f minutes\n" % (TOTAL_RAM, TOTAL_FS, MAX_USED_RAM, MAX_USED_FS, AVERAGE_LOAD, FS_NAME, delta_t))
