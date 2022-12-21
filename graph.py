#!/usr/bin/env python3

#
# (c) 2019-2022 Antmicro <www.antmicro.com>
# License: Apache-2.0
#


import datetime
import os
import socket
import subprocess
import time
from common import *
from pathlib import Path

global gnuplot

GNUPLOT_VERSION_EXPECTED = "5.0"

# Every summary variable requires a default value in case it missed in a session log
START_DATE = ""
END_DATE = ""
AVERAGE_LOAD = 0.0
MAX_USED_RAM = 0
MAX_USED_FS = 0
MAX_TX = 0
MAX_RX = 0
TOTAL_RAM = 0
TOTAL_FS = 0
NAME_FS = "unknown"
NAME_IFACE = "unknown"

UNAME = "unknown"
CPUS = 0
CPU_NAME = "unknown"
DURATION = 0.0

HOST = socket.gethostname()

# The number of plots on the graph
NUMBER_OF_PLOTS = 5

# The default format
OUTPUT_TYPE = "pngcairo"
OUTPUT_EXT = "png"

labels = []


# Check if the avaliable gnuplot has a required version
p = run_or_fail("gnuplot", "--version", stdout=subprocess.PIPE)
version = scan(r"gnuplot (\S+)", str, p.stdout.readline().decode())
if not is_version_ge(version, GNUPLOT_VERSION_EXPECTED):
    fail(
        f"gnuplot version too low. Need at least {GNUPLOT_VERSION_EXPECTED} found {version}")


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
def plot(ylabel, title, session, column, space=3, autoscale=None):
    if autoscale is None:
        g("set yrange [0:100]")
        g("set cbrange [0:100]")
    else:
        g("unset xdata")
        g("set yrange [0:*]")
        g(f"stats '{session}.txt' using {column}")
        g(f"set yrange [0:STATS_max*{autoscale}]")
        g(f"set cbrange [0:STATS_max*{autoscale}]")
        g("set xdata time")
    g(f"set ylabel '{ylabel}'")
    g(f"set title \"{{/:Bold {title}}}" + ("\\n" * space) + "\"")
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
    global MAX_RX
    global MAX_TX
    global NAME_IFACE

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

            # Override summary variables. If they're missing, their default values are kept
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

            value = scan("observed network: ([^,]+)", str, line)
            if value is not None:
                NAME_IFACE = value

            value = scan("total ram: (\S+)", stof, line)
            if value is not None:
                TOTAL_RAM = value

            value = scan("max ram used: (\S+)", stof, line)
            if value is not None:
                MAX_USED_RAM = value

            value = scan("total disk space: (\S+)", stof, line)
            if value is not None:
                TOTAL_FS = value

            value = scan("max data received: (\S+)", stof, line)
            if value is not None:
                MAX_RX = value

            value = scan("max data sent: (\S+)", stof, line)
            if value is not None:
                MAX_TX = value

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

    MAX_RX = unit_str(MAX_RX, SPEED_UNITS)
    MAX_TX = unit_str(MAX_TX, SPEED_UNITS)

    DURATION = unit_str(DURATION, TIME_UNITS, 60)


def graph(session, fname='plot'):
    global OUTPUT_TYPE
    global OUTPUT_EXT

    global labels

    global gnuplot

    labels = []

    # The default format
    OUTPUT_TYPE = "pngcairo"
    OUTPUT_EXT = "png"
    if "SARGRAPH_OUTPUT_TYPE" in os.environ:
        otype = os.environ["SARGRAPH_OUTPUT_TYPE"].lower()

        # png is the default, so don't change anything
        if otype != "png":
            OUTPUT_TYPE = otype
            OUTPUT_EXT = otype
    elif fname.lower().endswith('.png'):
        # png is the default, so don't change anything
        pass
    elif fname.lower().endswith('.svg'):
        OUTPUT_TYPE = "svg"
        OUTPUT_EXT = "svg"
    elif fname.lower().endswith('.ascii'):
        OUTPUT_TYPE = "ascii"
        OUTPUT_EXT = "ascii"
    elif fname.lower().endswith('.html'):
        OUTPUT_TYPE = "html"
        OUTPUT_EXT = "html"
    else:
        pass
        # fail("unknown graph extension")

    # Leave just the base name
    fname = cut_suffix(fname, f".{OUTPUT_EXT}")

    # ASCII plots have their own routine
    if OUTPUT_TYPE == "ascii":
        return servis_graph(session, fname)

    # HTML plots have their own routine
    if OUTPUT_TYPE == "html":
        return servis_graph(session, fname, "html")

    read_comments(session)

    gnuplot = run_or_fail("gnuplot", stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE)

    sdt = datetime.datetime.strptime(START_DATE, '%Y-%m-%d-%H:%M:%S')
    edt = datetime.datetime.strptime(END_DATE, '%Y-%m-%d-%H:%M:%S')

    seconds_between = (edt - sdt).total_seconds()
    if seconds_between < 100:
        seconds_between = 100

    nsdt = sdt - datetime.timedelta(seconds=(seconds_between * 0.01))
    nedt = edt + datetime.timedelta(seconds=(seconds_between * 0.01))

    g(f"set terminal {OUTPUT_TYPE} size 1200,1600 background '#332d37' font 'monospace,{fix_size(8)}'")

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
    g("set grid xtics ytics ls 12 lc rgb '#c4c2c5'")
    g("set style fill solid")
    g("set palette defined ( 0.0 '#00af91', 0.25 '#00af91', 0.75 '#d83829', 1.0 '#d83829' )")
    g("unset colorbox")
    g("unset key")
    g("set rmargin 6")

    g(f"set output '{fname}.{OUTPUT_EXT}'")

    title_machine = f"Running on {{/:Bold {HOST}}} \@ {{/:Bold {UNAME}}}, {{/:Bold {CPUS}}} threads x {{/:Bold {CPU_NAME}}}"
    title_specs = f"Total ram: {{/:Bold {TOTAL_RAM}}}, Total disk space: {{/:Bold {TOTAL_FS}}}"
    title_times = f"Duration: {{/:Bold {START_DATE}}} .. {{/:Bold {END_DATE}}} ({DURATION})"

    g(f"set multiplot layout {NUMBER_OF_PLOTS},1 title \"\\n{title_machine}\\n{title_specs}\\n{title_times}\" offset screen -0.475, 0 left tc rgb 'white'")

    g(f"set title tc rgb 'white' font 'monospace,{fix_size(11)}'")

    g(f"set xrange ['{nsdt.strftime('%Y-%m-%d-%H:%M:%S')}':'{nedt.strftime('%Y-%m-%d-%H:%M:%S')}']")

    i = 0
    for label in labels:
        if i % 2 == 0:
            offset = 1.08
        else:
            offset = 1.20

        i = i + 1

        content = f"{{[{i}] {label[1][0:30]}"
        length = len(label[1][0:30]) + len(str(i)) + 5
        if OUTPUT_EXT == "svg":
            length *= 0.75

        # Draw the dotted line
        g(f"set arrow nohead from '{label[0]}', graph 0.01 to '{label[0]}', graph {offset-0.04} front lc rgb '#e74a3c' dt 2")

        # Draw the small rectangle at its bottom
        g(f"set object rect at '{label[0]}', graph 0.0 size char 0.5, char 0.5 front lc rgb '#d83829' fc rgb '#f15f32'")

        # Draw the label rectangle
        g(f"set object rect at '{label[0]}', graph {offset} size char {length}, char 1.3 fs border lc rgb '#d83829' fc rgb '#f15f32'")

        # Add text to the label
        g(f"set label at '{label[0]}', graph {offset} '{content}' center tc rgb 'white' font 'monospace,{fix_size(7)}'")

    if i <= 0:
        space = 1
    elif i <= 1:
        space = 2
    else:
        space = 3

    g("set object rectangle from graph 0, graph 0 to graph 2, graph 2 behind fillcolor rgb '#000000' fillstyle solid noborder")

    # Set scale for plots displayed in relative units (%)
    plot("CPU load (%)",
         f"CPU load (average = {AVERAGE_LOAD:.2f} %)", session, 2, space=space)
    plot(f"RAM usage (100% = {TOTAL_RAM})",
         f"RAM usage (max = {MAX_USED_RAM})", session, 3, space=space)
    plot(f"FS usage (100% = {TOTAL_FS})", f"{NAME_FS} usage (max = {MAX_USED_FS})",
         session, 4, space=space)

    # Set scale for plots displayed in absolute units
    plot(f"{NAME_IFACE} received (Mb/s)", f"{NAME_IFACE} data received (max = {MAX_RX})",
         session, 5, space=space, autoscale=1.2)
    plot(f"{NAME_IFACE} sent (Mb/s)", f"{NAME_IFACE} data sent (max = {MAX_TX})",
         session, 6, space=space, autoscale=1.2)

    g("unset multiplot")
    g("unset output")
    g("quit")


def read_data(session):
    xdata = list()
    ydata = [[], [], [], [], []]
    with open(f"{session}.txt", "r") as f:
        for line in f:
            if(line[0] != '#'):
                line = line.split(" ")
                date = datetime.datetime.strptime(line[0], '%Y-%m-%d-%H:%M:%S')
                xdata.append(date)
                for i in range(NUMBER_OF_PLOTS):
                    ydata[i].append(stof(line[i+1]))
    return (xdata, ydata)


def convert_labels_to_tags(labels):
    tags = []
    for [label_date, label_name] in labels:
        label_date = datetime.datetime.strptime(
            label_date, '%Y-%m-%d-%H:%M:%S')
        label_ts = int(label_date.replace(
            tzinfo=datetime.timezone.utc).timestamp()*1000)/1000
        tags.append({'name': label_name,
                     'timestamp': label_ts})
    return tags


def servis_graph(session, fname='plot', output_ext='ascii'):
    data = read_data(session)
    read_comments(session)
    titles = [f"""cpu load (average = {AVERAGE_LOAD} %)""",
              f"""ram usage (max = {MAX_USED_RAM})""",
              f"""{NAME_FS} usage (max = {MAX_USED_FS})""",
              f"""{NAME_IFACE} data received (max = {MAX_RX})""",
              f"""{NAME_IFACE} data sent (max = {MAX_TX})"""]

    y_titles = [f"cpu % load (user)",
                f"ram % usage",
                f"{NAME_FS}",
                f"{NAME_IFACE} received",
                f"{NAME_IFACE} sent"]

    xdata, ydata = data
    xdata_to_int = [int(timestamp.replace(
        tzinfo=datetime.timezone.utc).timestamp()*1000)/1000
        for timestamp in xdata]

    summary = f"Running on {UNAME}, {CPUS} threads x {CPU_NAME}\n"
    summary += f"Total ram: {TOTAL_RAM}, Total disk space: {TOTAL_FS}\n"
    summary += f"Duration: {START_DATE} .. {END_DATE} ({DURATION})"

    from servis import render_multiple_time_series_plot
    if output_ext == 'ascii':
        render_multiple_time_series_plot(
            ydata,
            [xdata_to_int]*5,
            summary,
            titles,
            ['time']*5,
            [None]*5,
            y_titles,
            [None]*5,
            [(0, 160)]*5,
            [(0, 100)]*5,
            outpath=Path(fname),
            trimxvalues=False,
            figsize=(90, 70)
        )
    elif output_ext == 'html':
        l = convert_labels_to_tags(labels)
        render_multiple_time_series_plot(
            ydata,
            [xdata_to_int]*5,
            summary,
            titles,
            ['time']*5,
            [None]*5,
            y_titles,
            [None]*5,
            [(0, 160)]*5,
            [(0, 100)]*5,
            outpath=Path(fname),
            outputext=['html'],
            trimxvalues=False,
            figsize=(1200, 1600),
            tags=[l]*5,
            setgradientcolors=True
        )
