#!/usr/bin/env python3

#
# (c) 2019-2022 Antmicro <www.antmicro.com>
# License: Apache
#


import argparse
import os
import signal
import subprocess
import sys
import time

from datetime import datetime, timedelta
from select import select
from fcntl import fcntl, F_GETFL, F_SETFL
from os.path import realpath
from socket import gethostname
from re import search, escape

global gnuplot
global die

die = 0

GNUPLOT_VERSION_EXPECTED = 5.0


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


# Run process, return subprocess object on success, exit script on fail
def run_process(*argv, **kwargs):
    try:
        p = subprocess.Popen(argv, **kwargs)
    except:
        print("Error: '%s' tool not found" % argv[0])
        sys.exit(1)
    return p


# Get the first group from a given match and convert to required type
def scan(regex, conv, string):
    match = search(regex, string)
    if not match:
        return None
    try:
        value = conv(match.group(1))
    except ValueError:
        return None
    return value


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


# Run a command in a running gnuplot process
def g(command):
    global gnuplot

    if not (gnuplot.poll() is None):
        print("Error: gnuplot not running!")
        return
    print ("gnuplot> %s" % command)
    try:
        command = b"%s\n" % command
    except:
        command = b"%s\n" % str.encode(command)
    gnuplot.stdin.write(b"%s\n" % command)
    gnuplot.stdin.flush()

    if command == b"quit\n":
        while gnuplot.poll() is None:
            time.sleep(0.25)


# Check if the avaliable gnuplot has a required version
p = run_process("gnuplot", "--version", stdout=subprocess.PIPE)
version = scan(r"gnuplot (\S+)", float, p.stdout.readline().decode())
if version < GNUPLOT_VERSION_EXPECTED:
    print("Error: Gnuplot version too low. Need at least %g found %g" % (GNUPLOT_VERSION_EXPECTED, version[0]))
    sys.exit(1)


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

# If the script runs in a screen session, initialize the plot and gather data

gnuplot = run_process("gnuplot", stdin=subprocess.PIPE, stdout=subprocess.PIPE)

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
    f.write("# pid: %d, machine: %s, cpu count: %d\n" % (os.getpid(), uname, cpus))

p.stdout.readline()

g("set ylabel 'cpu % load (user)'")

g("set ylabel tc rgb 'white' font 'Courier-New,8'")

g("set datafile commentschars '#'")

g("set timefmt '%s'")
g("set xdata time")
g("set border lc rgb 'white'")
g("set key tc rgb 'white'")
g("set timefmt '%Y-%m-%d-%H:%M:%S'")
g("set xtics format '%H:%M:%S'")
g("set xtics font 'Courier-New,8' tc rgb 'white'")
g("set ytics font 'Courier-New,8' tc rgb 'white'")
g("set grid xtics ytics ls 12 lc rgb '#444444'")
g("set style fill solid")
g("set palette defined ( 0.2 '#00ff00', 0.8 '#ff0000' )")
g("set cbrange [0:100]")
g("unset colorbox")
g("unset key")
g("set rmargin 6")

g("set terminal %s size 1200,800 background '#222222' font 'Courier-New,8'" % OUTPUT_TYPE)

signal.signal(signal.SIGTERM, kill_handler)
i = 0

if not args.fspath and not args.fsdev:
    args.fspath = "/"
if args.fspath:
    args.fspath = realpath(args.fspath)
    with open("/proc/mounts", "r") as f:
        while args.fsdev is None:
            args.fsdev = scan("^(/dev/\S+)\s+%s\s+" % escape(args.fspath), str, f.readline())
    if not args.fsdev:
        print("Error: no device is mounted on %s" % args.fspath)
        sys.exit(1)

START_DATE = ""
END_DATE = ""
AVERAGE_LOAD = 0.0
MAX_USED_RAM = 0
MAX_USED_FS = 0

FS_SAR_INDEX = None

flags = fcntl(sys.stdin, F_GETFL)
fcntl(sys.stdin, F_SETFL, flags | os.O_NONBLOCK)
labels = []

# Gather data from sar output
while 1:
    rlist, _, _ = select([p.stdout, sys.stdin], [], [], 0.25)
    now = datetime.now()
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

    now = "%04d-%02d-%02d" % (now.year, now.month, now.day)

    # Read and process CPU data
    cpu_data = read_table(p.stdout)
    if START_DATE == "":
        START_DATE = "%s %s" % (now, cpu_data['time'][0])
    cpu_data['time'][0] = now + "-" + cpu_data['time'][0]
    AVERAGE_LOAD += float(cpu_data["%user"][0])
    i = i + 1

    # Read and process RAM data
    ram_data = read_table(p.stdout)
    ram_data['time'][0] = now + "-" + ram_data['time'][0]
    if TOTAL_RAM == 0:
        TOTAL_RAM = (int(ram_data['kbmemused'][0]) + int(ram_data['kbmemfree'][0])) / 1024.0 / 1024.0
    if MAX_USED_RAM < int(ram_data['kbmemused'][0]):
        MAX_USED_RAM = int(ram_data['kbmemused'][0])

    # Read and process FS data
    fs_data = read_table(p.stdout)
    if FS_SAR_INDEX is None:
      FS_SAR_INDEX = fs_data['FILESYSTEM'].index(args.fsdev)
    END_DATE = now + " " + fs_data['time'][FS_SAR_INDEX]
    fs_data['time'][FS_SAR_INDEX] = now + "-" + fs_data['time'][FS_SAR_INDEX]
    if MAX_USED_FS < int(fs_data['MBfsused'][FS_SAR_INDEX]):
        MAX_USED_FS = int(fs_data['MBfsused'][FS_SAR_INDEX])

    with open("data.txt", "a") as f:
        f.write("%s %s %s %s\n" % (cpu_data["time"][0], cpu_data["%user"][0], ram_data["%memused"][0], fs_data["%fsused"][FS_SAR_INDEX]))

    if die:
        break

if i == 0:
    g("quit")
    time.sleep(1)
    sys.exit(0)

g("set output 'plot.%s'" % OUTPUT_EXT)

g("set multiplot layout 3,1 title \"%s\"" % "\\n\\n\\n")


AVERAGE_LOAD = AVERAGE_LOAD / float(i)
MAX_USED_RAM = MAX_USED_RAM / 1024.0 / 1024.0

sdt = datetime.strptime(START_DATE, '%Y-%m-%d %H:%M:%S')
edt = datetime.strptime(END_DATE, '%Y-%m-%d %H:%M:%S')
delta_t = ((edt - sdt).total_seconds()) / 60.0

with open("data.txt", "a") as f:
    f.write("# total ram: %.2f GB, max ram used: %.2f GB, average load: %.2f %%, duration: %.2f minutes\n" % (TOTAL_RAM, MAX_USED_RAM, AVERAGE_LOAD, delta_t))

g("set title 'cpu load (average = %.2f %%)'" % AVERAGE_LOAD)
g("set title tc rgb 'white' font 'Courier-New,8'")

seconds_between = (edt - sdt).total_seconds()
if seconds_between < 100:
 seconds_between = 100

nsdt = sdt - timedelta(seconds = (seconds_between * 0.01))
nedt = edt + timedelta(seconds = (seconds_between * 0.01))

g("set xrange ['%s':'%s']" % (nsdt.strftime("%Y-%m-%d-%H:%M:%S"), nedt.strftime("%Y-%m-%d-%H:%M:%S")));

g("set label 101 at screen 0.02, screen 0.95 'Running on {/:Bold %s} \@ {/:Bold %s}, {/:Bold %d} threads x {/:Bold %s}, total ram is {/:Bold %.2f GB}' tc rgb 'white'" % (gethostname(), uname, cpus, cpu_name, TOTAL_RAM))
g("set label 102 at screen 0.02, screen 0.93 'duration: {/:Bold %s} .. {/:Bold %s} (%.2f minutes)' tc rgb 'white'" % (START_DATE, END_DATE, delta_t))

i = 0
for label in labels:
    i = i + 1
    g("set arrow nohead from '%s', graph 0.01 to '%s', graph 0.87 front lc rgb 'red' dt 2" % (label[0],label[0]))
    g("set object rect at '%s', graph 0.90 size char %d, char 1.5 fc rgb 'red'" % (label[0],len("%d" % i)+1))
    g("set object rect at '%s', graph 0.0 size char 0.5, char 0.5 front fc rgb 'red'" % label[0])
    g("set label at '%s', graph 0.90 '%d' center tc rgb 'black' font 'Courier-New,7'" % (label[0],i))
    g("set label at '%s', graph 0.95 '%s' center tc rgb 'white' font 'Courier-New,7'" % (label[0], label[1][0:20]))

if i > 0:
    g("set yrange [0:119]")
else:
    g("set yrange [0:100]")

g("set object rectangle from graph 0, graph 0 to graph 2, graph 2 behind fillcolor rgb '#111111' fillstyle solid noborder")
g("set object rectangle from '%s', 0 to '%s', 100 behind fillcolor rgb '#000000' fillstyle solid noborder" % (START_DATE.replace(" ", "-"), END_DATE.replace(" ", "-")))


g("plot 'data.txt' using 1:2:2 title 'cpu' with boxes palette")

g("set ylabel 'ram % usage'")
g("set title 'ram usage (max = %.2f GB)'" % MAX_USED_RAM);
g("plot 'data.txt' using 1:3:3 title 'ram' with boxes palette")

g("set ylabel '%s %% usage'" % fs_data['FILESYSTEM'][FS_SAR_INDEX])
g("set title '%s usage (max = %.2f MB)'" % (fs_data['FILESYSTEM'][FS_SAR_INDEX], MAX_USED_FS));
g("plot 'data.txt' using 1:4:4 title 'fs' with boxes palette")

g("unset multiplot")
g("unset output")
g("quit")
