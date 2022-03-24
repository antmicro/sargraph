#!/usr/bin/env python3

#
# (c) 2019-2022 Antmicro <www.antmicro.com>
# License: Apache-2.0
#


import datetime
import os
import socket
import subprocess
import sys
import time

from common import *

global gnuplot

GNUPLOT_VERSION_EXPECTED = "5.0"

START_DATE = ""
END_DATE = ""
AVERAGE_LOAD = 0.0
MAX_USED_RAM = 0
MAX_USED_FS = 0
TOTAL_RAM = 0
TOTAL_FS = 0
NAME_FS = "unknown"

UNAME="unknown"
CPUS=0
CPU_NAME="unknown"
DURATION = 0.0

HOST = socket.gethostname()

# The number of plots on the graph
NUMBER_OF_PLOTS = 3

# The default format
OUTPUT_TYPE="pngcairo"
OUTPUT_EXT="png"

labels = []


# Check if the avaliable gnuplot has a required version
p = run_or_fail("gnuplot", "--version", stdout=subprocess.PIPE)
version = scan(r"gnuplot (\S+)", str, p.stdout.readline().decode())
if not is_version_ge(version, GNUPLOT_VERSION_EXPECTED):
    fail(f"gnuplot version too low. Need at least {GNUPLOT_VERSION_EXPECTED} found {version}")


# Run a command in a running gnuplot process
def g(command):
    global gnuplot

    if not (gnuplot.poll() is None):
        print("Error: gnuplot not running!")
        return
    # print ("gnuplot> %s" % command)
    try:
        command = b"%s\n" % command
    except:
        command = b"%s\n" % str.encode(command)
    gnuplot.stdin.write(b"%s\n" % command)
    gnuplot.stdin.flush()

    if command == b"quit\n":
        while gnuplot.poll() is None:
            time.sleep(0.25)


# Get gnuplot font size with respect to differences betwen SVG and PNG terminals
def fix_size(size):
    if OUTPUT_TYPE == "svg":
        size = int(size*1.25)
    return size


# Plot a single column of values from data.txt
def plot(ylabel, title, session, column):
    g(f"set ylabel '{ylabel}'")
    g(f"set title \"\\n{{/:Bold {title}}}\\n\\n\\n\"")
    g(f"plot '{session}.txt' using 1:{column}:{column} title 'cpu' with boxes palette")


# Read additional information from 'data.txt' comments
def read_comments(session):
    global START_DATE
    global END_DATE
    global AVERAGE_LOAD
    global MAX_USED_RAM
    global MAX_USED_FS
    global TOTAL_RAM
    global TOTAL_FS
    global NAME_FS
    global UNAME
    global CPUS
    global CPU_NAME
    global DURATION

    data_version = None

    with open(f"{session}.txt", "r") as f:
        for line in f:
            value = None

            if len(line) <= 0:
                continue

            if line[0] != '#':
                if not START_DATE:
                    START_DATE = scan("^(\S+)", str, line)
                END_DATE = scan("^(\S+)", str, line)

            value = scan("label: (.+)", str, line)
            if value is not None:
                key = scan("(\S+) label:", str, line)
                labels.append([key, value])

                # Comments are not mixed with anything else, so skip
                continue

            value = scan("sargraph version: (\d+\.\d+)", str, line)
            if value is not None:
                data_version = value

            value = scan("machine: ([^,]+)", str, line)
            if value is not None:
                UNAME = value

            value = scan("cpu count: ([^,]+)", int, line)
            if value is not None:
                CPUS = value

            value = scan("cpu: ([^,\n]+)", str, line)
            if value is not None:
                CPU_NAME = value

            value = scan("observed disk: ([^,]+)", str, line)
            if value is not None:
                NAME_FS = value

            value = scan("total ram: (\S+)", stof, line)
            if value is not None:
                TOTAL_RAM = value

            value = scan("max ram used: (\S+)", stof, line)
            if value is not None:
                MAX_USED_RAM = value

            value = scan("total disk space: (\S+)", stof, line)
            if value is not None:
                TOTAL_FS = value

            value = scan("duration: (\S+)", stof, line)
            if value is not None:
                DURATION = value

            value = scan("max disk used: (\S+)", stof, line)
            if value is not None:
                MAX_USED_FS = value

            value = scan("average load: (\S+)", stof, line)
            if value is not None:
                AVERAGE_LOAD = value

    if data_version != scan("^(\d+\.\d+)", str, SARGRAPH_VERSION):
        print("Warning: the data comes from an incompatible version of sargraph")

    # Translate the values to their value-unit representations
    TOTAL_RAM = unit_str(TOTAL_RAM, DATA_UNITS)
    MAX_USED_RAM = unit_str(MAX_USED_RAM, DATA_UNITS)

    TOTAL_FS = unit_str(TOTAL_FS, DATA_UNITS)
    MAX_USED_FS = unit_str(MAX_USED_FS, DATA_UNITS)

    DURATION = unit_str(DURATION, TIME_UNITS, 60)


def graph(session, fname='plot.png'):
    global OUTPUT_TYPE
    global OUTPUT_EXT

    global labels

    global gnuplot

    labels = []

    # The default format
    OUTPUT_TYPE="pngcairo"
    OUTPUT_EXT="png"
    if "SARGRAPH_OUTPUT_TYPE" in os.environ:
        if os.environ["SARGRAPH_OUTPUT_TYPE"] == "svg":
            OUTPUT_TYPE="svg"
            OUTPUT_EXT="svg"
    elif fname.lower().endswith('.svg'):
        OUTPUT_TYPE="svg"
        OUTPUT_EXT="svg"
    elif fname.lower().endswith('.png'):
        # Otherwise leave the default png
        pass
    else:
        fail("unknown graph extension")

    # Leave just the base name
    fname = fname[:-4]

    read_comments(session)

    gnuplot = run_or_fail("gnuplot", stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    sdt = datetime.datetime.strptime(START_DATE, '%Y-%m-%d-%H:%M:%S')
    edt = datetime.datetime.strptime(END_DATE, '%Y-%m-%d-%H:%M:%S')

    seconds_between = (edt - sdt).total_seconds()
    if seconds_between < 100:
        seconds_between = 100

    nsdt = sdt - datetime.timedelta(seconds = (seconds_between * 0.01))
    nedt = edt + datetime.timedelta(seconds = (seconds_between * 0.01))

    g(f"set terminal {OUTPUT_TYPE} size 1200,1200 background '#222222' font 'monospace,{fix_size(8)}'")

    g(f"set ylabel tc rgb 'white' font 'monospace,{fix_size(8)}'")

    g("set datafile commentschars '#'")

    g("set timefmt '%s'")
    g("set xdata time")
    g("set border lc rgb 'white'")
    g("set key tc rgb 'white'")
    g("set timefmt '%Y-%m-%d-%H:%M:%S'")
    g("set xtics format '%H:%M:%S'")
    g(f"set xtics font 'monospace,{fix_size(8)}' tc rgb 'white'")
    g(f"set ytics font 'monospace,{fix_size(8)}' tc rgb 'white'")
    g("set grid xtics ytics ls 12 lc rgb '#444444'")
    g("set style fill solid")
    g("set palette defined ( 0.2 '#00ff00', 0.8 '#ff0000' )")
    g("set cbrange [0:100]")
    g("unset colorbox")
    g("unset key")
    g("set rmargin 6")


    g(f"set output '{fname}.{OUTPUT_EXT}'")

    title_machine = f"Running on {{/:Bold {HOST}}} \@ {{/:Bold {UNAME}}}, {{/:Bold {CPUS}}} threads x {{/:Bold {CPU_NAME}}}"
    title_specs = f"Total ram: {{/:Bold {TOTAL_RAM}}}, Total disk space: {{/:Bold {TOTAL_FS}}}"
    title_times = f"Duration: {{/:Bold {START_DATE}}} .. {{/:Bold {END_DATE}}} ({DURATION})"

    g(f"set multiplot layout {NUMBER_OF_PLOTS},1 title \"\\n{title_machine}\\n{title_specs}\\n{title_times}\\n\" offset screen -0.475, 0 left tc rgb 'white'")

    g(f"set title tc rgb 'white' font 'monospace,{fix_size(11)}'")

    g(f"set xrange ['{nsdt.strftime('%Y-%m-%d-%H:%M:%S')}':'{nedt.strftime('%Y-%m-%d-%H:%M:%S')}']")

    i = 0
    for label in labels:
        if i%2 == 0:
            offset = 1.10
        else:
            offset = 1.22

        i = i + 1

        content = f"{{[{i}] {label[1][0:30]}"
        length = len(label[1][0:30]) + len(str(i)) + 5
        if OUTPUT_EXT == "svg":
          length *= 0.75

        g(f"set arrow nohead from '{label[0]}', graph 0.01 to '{label[0]}', graph {offset-0.04} front lc rgb 'red' dt 2")
        g(f"set object rect at '{label[0]}', graph 0.0 size char 0.5, char 0.5 front fc rgb 'red'")
        g(f"set object rect at '{label[0]}', graph {offset} size char {length}, char 1.3 fs border lc rgb 'red' fc rgb '#222222'")
        g(f"set label at '{label[0]}', graph {offset} '{content}' center tc rgb 'white' font 'monospace,{fix_size(7)}'")

    if i > 0:
        g("set yrange [0:100]")
    else:
        g("set yrange [0:100]")

    g("set object rectangle from graph 0, graph 0 to graph 2, graph 2 behind fillcolor rgb '#111111' fillstyle solid noborder")
    g(f"set object rectangle from '{START_DATE.replace(' ', '-')}', 0 to '{END_DATE.replace(' ', '-')}', 100 behind fillcolor rgb '#000000' fillstyle solid noborder")

    plot("cpu % load (user)", f"cpu load (average = {AVERAGE_LOAD:.2f} %)", session, 2)
    plot("ram % usage", f"ram usage (max = {MAX_USED_RAM})", session, 3)
    plot(f"{NAME_FS}", f"{NAME_FS} usage (max = {MAX_USED_FS})", session, 4)

    g("unset multiplot")
    g("unset output")
    g("quit")
