#!/usr/bin/env python3

#
# (c) 2019-2022 Antmicro <www.antmicro.com>
# License: Apache
#


import datetime
import os
import socket
import subprocess
import sys
import time

from common import *

global gnuplot

GNUPLOT_VERSION_EXPECTED = 5.0


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


# Plot a single column of values from data.txt
def plot(ylabel, title, column):
    g(f"set ylabel '{ylabel}'")
    g(f"set title '{title}'")
    g(f"plot 'data.txt' using 1:{column}:{column} title 'cpu' with boxes palette")


# Check if the avaliable gnuplot has a required version
p = run_process("gnuplot", "--version", stdout=subprocess.PIPE)
version = scan(r"gnuplot (\S+)", float, p.stdout.readline().decode())
if version < GNUPLOT_VERSION_EXPECTED:
    print(f"Error: Gnuplot version too low. Need at least {GNUPLOT_VERSION_EXPECTED} found {version[0]}")
    sys.exit(1)


START_DATE = ""
END_DATE = ""
AVERAGE_LOAD = 0.0
MAX_USED_RAM = 0
MAX_USED_FS = 0
TOTAL_RAM = 0
TOTAL_FS = 0
NAME_FS = "unknown"

uname="unknown"
cpus=0
cpu_name="unknown"
duration = 0.0


labels = []
with open("data.txt", "r") as f:
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

        value = scan("machine: ([^,]+)", str, line)
        if value is not None:
            uname = value

        value = scan("cpu count: ([^,]+)", int, line)
        if value is not None:
            cpus = value

        value = scan("cpu: ([^,\n]+)", str, line)
        if value is not None:
            cpu_name = value

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
            duration = value

        value = scan("max disk used: (\S+)", stof, line)
        if value is not None:
            MAX_USED_FS = value

        value = scan("average load: (\S+)", stof, line)
        if value is not None:
            AVERAGE_LOAD = value


# Initialize the plot
OUTPUT_TYPE="pngcairo"
OUTPUT_EXT="png"
try:
    if os.environ["SARGRAPH_OUTPUT_TYPE"] == "svg":
        OUTPUT_TYPE="svg"
        OUTPUT_EXT="svg"
except:
    pass

# The number of plots on the graph
NUMBER_OF_PLOTS = 3

gnuplot = run_process("gnuplot", stdin=subprocess.PIPE, stdout=subprocess.PIPE)

sdt = datetime.datetime.strptime(START_DATE, '%Y-%m-%d-%H:%M:%S')
edt = datetime.datetime.strptime(END_DATE, '%Y-%m-%d-%H:%M:%S')

seconds_between = (edt - sdt).total_seconds()
if seconds_between < 100:
 seconds_between = 100

nsdt = sdt - datetime.timedelta(seconds = (seconds_between * 0.01))
nedt = edt + datetime.timedelta(seconds = (seconds_between * 0.01))

host = socket.gethostname()

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

g(f"set terminal {OUTPUT_TYPE} size 1200,800 background '#222222' font 'Courier-New,8'")

g(f"set output 'plot.{OUTPUT_EXT}'")

g(f"set multiplot layout {NUMBER_OF_PLOTS},1 title \"\\n\\n\\n\"")

g("set title tc rgb 'white' font 'Courier-New,8'")

g(f"set xrange ['{nsdt.strftime('%Y-%m-%d-%H:%M:%S')}':'{nedt.strftime('%Y-%m-%d-%H:%M:%S')}']");

g(f"set label 101 at screen 0.02, screen 0.95 'Running on {{/:Bold {host}}} \@ {{/:Bold {uname}}}, {{/:Bold {cpus}}} threads x {{/:Bold {cpu_name}}}, total ram: {{/:Bold {TOTAL_RAM:.2f} GB}}, total disk space: {{/:Bold {TOTAL_FS:.2f} GB}}' tc rgb 'white'")
g(f"set label 102 at screen 0.02, screen 0.93 'duration: {{/:Bold {START_DATE}}} .. {{/:Bold {END_DATE}}} ({duration:.2f} minutes)' tc rgb 'white'")

i = 0
for label in labels:
    i = i + 1
    g(f"set arrow nohead from '{label[0]}', graph 0.01 to '{label[0]}', graph 0.87 front lc rgb 'red' dt 2")
    g(f"set object rect at '{label[0]}', graph 0.90 size char {len('%d' % i)+1}, char 1.5 fc rgb 'red'")
    g(f"set object rect at '{label[0]}', graph 0.0 size char 0.5, char 0.5 front fc rgb 'red'")
    g(f"set label at '{label[0]}', graph 0.90 '{i}' center tc rgb 'black' font 'Courier-New,7'")
    g(f"set label at '{label[0]}', graph 0.95 '{label[1][0:20]}' center tc rgb 'white' font 'Courier-New,7'")

if i > 0:
    g("set yrange [0:119]")
else:
    g("set yrange [0:100]")

g("set object rectangle from graph 0, graph 0 to graph 2, graph 2 behind fillcolor rgb '#111111' fillstyle solid noborder")
g(f"set object rectangle from '{START_DATE.replace(' ', '-')}', 0 to '{END_DATE.replace(' ', '-')}', 100 behind fillcolor rgb '#000000' fillstyle solid noborder")

plot("cpu % load (user)", f"cpu load (average = {AVERAGE_LOAD:.2f} %)", 2)
plot("ram % usage", f"ram usage (max = {MAX_USED_RAM:.2f} GB)", 3)
plot(f"{NAME_FS}'", f"{NAME_FS} usage (max = {MAX_USED_FS:.2f} MB)", 4)

g("unset multiplot")
g("unset output")
g("quit")
