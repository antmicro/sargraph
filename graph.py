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
import plotext as plt
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
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

UNAME = "unknown"
CPUS = 0
CPU_NAME = "unknown"
DURATION = 0.0

HOST = socket.gethostname()

# The number of plots on the graph
NUMBER_OF_PLOTS = 3

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
def plot(ylabel, title, session, column, space=3):
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
    OUTPUT_TYPE = "pngcairo"
    OUTPUT_EXT = "png"
    if "SARGRAPH_OUTPUT_TYPE" in os.environ:
        if os.environ["SARGRAPH_OUTPUT_TYPE"] == "svg":
            OUTPUT_TYPE = "svg"
            OUTPUT_EXT = "svg"
    elif fname.lower().endswith('.svg'):
        OUTPUT_TYPE = "svg"
        OUTPUT_EXT = "svg"
    elif fname.lower().endswith('.png'):
        # Otherwise leave the default png
        pass
    else:
        pass
        # fail("unknown graph extension")

    # Leave just the base name
    fname = fname[:-4]

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

    g(f"set terminal {OUTPUT_TYPE} size 1200,1200 background '#332d37' font 'monospace,{fix_size(8)}'")

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
    g("set cbrange [0:100]")
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
    g("set yrange [0:100]")

    g("set object rectangle from graph 0, graph 0 to graph 2, graph 2 behind fillcolor rgb '#111111' fillstyle solid noborder")
    g(f"set object rectangle from '{START_DATE.replace(' ', '-')}', 0 to '{END_DATE.replace(' ', '-')}', 100 behind fillcolor rgb '#000000' fillstyle solid noborder")

    plot("cpu % load (user)",
         f"cpu load (average = {AVERAGE_LOAD:.2f} %)", session, 2, space=space)
    plot("ram % usage",
         f"ram usage (max = {MAX_USED_RAM})", session, 3, space=space)
    plot(f"{NAME_FS}", f"{NAME_FS} usage (max = {MAX_USED_FS})",
         session, 4, space=space)

    g("unset multiplot")
    g("unset output")
    g("quit")


def read_data(session):
    xdata = list()
    ydata = [[], [], []]
    with open(f"{session}.txt", "r") as f:
        for line in f:
            if(line[0] != '#'):
                line = line.split(" ")
                date = datetime.datetime.strptime(line[0], '%Y-%m-%d-%H:%M:%S')
                xdata.append(date)
                for i in range(3):
                    ydata[i].append(float(line[i+1]))
    return (xdata, ydata)


def create_ascii_plot(
        title: str,
        xtitle: str,
        xunit: str,
        ytitle: str,
        yunit: str,
        xdata: List,
        ydata: List,
        xrange: Optional[Tuple] = (0, 10),
        yrange: Optional[Tuple] = (0, 100),
        trimxvalues: bool = True,
        skipfirst: bool = False,
        figsize: Tuple = (90, 30),
        switchtobarchart: bool = False):

    plt.clear_figure()
    start = 1 if skipfirst else 0
    xdata = np.array(xdata[start:], copy=True)
    ydata = np.array(ydata[start:], copy=True)

    if trimxvalues:
        minx = min(xdata)
        xdata = [x - minx for x in xdata]

    xlabel = xtitle
    if xunit is not None:
        xlabel += f' [{xunit}]'
    ylabel = ytitle
    if yunit is not None:
        ylabel += f' [{yunit}]'

    if switchtobarchart == True:
        plt.bar(xdata, ydata, width=0.1)
    else:
        plt.scatter(xdata, ydata)
    plt.plot_size(figsize[0], figsize[1])

    if xrange is not None:
        plt.xlim(xrange[0], xrange[1])
    if yrange is not None:
        plt.ylim(yrange[0], yrange[1])
    plt.title(title)
    plt.xlabel(xtitle)
    plt.ylabel(ytitle)
    plt.show()

def render_ascii_plot(
        outpath: Optional[Path],
        title: str,
        subtitles: List,
        xtitles: List,
        xunits: List,
        ytitles: List,
        yunits: List,
        xdata: List,
        ydata: List,
        xrange: Optional[Tuple] = None,
        yrange: Optional[Tuple] = None,
        trimxvalues: bool = True,
        skipfirst: bool = False,
        figsize: Tuple = (1500, 1080),
        bins: int = 20,
        switchtobarchart: bool = True,
        tags: List = [],
        tagstype: str = "single",
        outputext: str = "html"):
    """
    Draws triple time series plot.

    Used i.e. for timeline of resource usage.

    It also draws the histograms of values that appeared throughout the
    experiment.

    Parameters
    ----------
    outpath : Optional[Path]
        Output path for the plot image. If None, the plot will be displayed.
    title : str
        Title of the plot
    xtitle : str
        Name of the X axis
    xuint : str
        Unit for the X axis
    ytitle : str
        Name of the Y axis
    yunit : str
        Unit for the Y axis
    xdata : List
        The values for X dimension
    ydata : List
        The values for Y dimension
    xrange : Optional[Tuple]
        The range of zoom on X axis 
    yrange : Optional[Tuple]
        The range of zoom on Y axis
    trimxvalues : bool
        True if all values for the X dimension should be subtracted by
        the minimal value on this dimension
    skipfirst: bool
        True if the first entry should be removed from plotting.
    figsize: Tuple
        The size of the figure
    bins: int
        Number of bins for value histograms
    tags: list
        List of tags and their timestamps
    tagstype: String
        "single" if given list contain tags with only one timestamp
        "double" if given list contain tags with two (start and end) 
        timestamps.
    outputext: String
        Extension of generated file.
        "html" for HTML file,
        "png" for PNG file,
        "svg" for SVG file,
        "txt" for TXT file
    """
    if outputext == "txt":
        for plot_id in range(3):
            create_ascii_plot(
                title,
                xtitles[plot_id],
                xunits[plot_id],
                ytitles[plot_id],
                yunits[plot_id],
                xdata,
                ydata[plot_id],
                xrange=xrange,
                yrange=yrange,
                trimxvalues=trimxvalues,
                skipfirst=skipfirst,
                switchtobarchart=switchtobarchart
            )
        return


def ascii_graph(session, fname='plot.png'):
    plot_title = f"""Running on <b>{UNAME}</b>, 
        <b>{CPUS}</b> threads x <b>{CPU_NAME}</b><br>
        Total ram: <b>{TOTAL_RAM}</b>,
        Total disk space: <b> {TOTAL_FS}</b><br>
        Duration: <b>{START_DATE}</b> .. <b>{END_DATE}</b> ({DURATION})"""

    data = read_data(session)
    subtitles = [f"""cpu load (average = {AVERAGE_LOAD} %)""",
                 f"""ram usage (max = {MAX_USED_RAM})""",
                 f"""{NAME_FS} usage (max = {MAX_USED_FS})"""]

    y_titles = [f"cpu % load (user)",
                f"ram % usage",
                f"{NAME_FS}"]

    xdata, ydata = data
    xdata_to_int = [int(timestamp.replace(
        tzinfo=datetime.timezone.utc).timestamp()*1000)/1000 
        for timestamp in xdata]

    render_ascii_plot(
        fname,
        plot_title,
        subtitles,
        ["time"]*3,
        ["s"]*3,
        y_titles,
        [None, None, None],
        xdata_to_int,
        ydata,
        xrange=(0, 160),
        yrange=(0, 100),
        trimxvalues=True,
        skipfirst=True,
        switchtobarchart=True,
        outputext="txt"
    )
