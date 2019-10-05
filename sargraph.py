#!/usr/bin/env python

#
# (c) 2019 Antmicro <www.antmicro.com>
# License: Apache
#

from datetime import datetime, timedelta
from select import select
import signal
import os
import subprocess
import sys
from fcntl import fcntl, F_GETFL, F_SETFL

global die
die = 0

def kill_handler(a, b):
        global die
        die = 1


def merge_dicts(x, y):
    res = x.copy()
    res.update(y)
    return res

my_env = os.environ
my_env["S_TIME_FORMAT"] = "ISO"

TOTAL_RAM = 0

with open("/proc/meminfo") as f:
    TOTAL_RAM = int(f.read().split("\n")[0].replace("  ", " ").replace("  ", " ").replace("  ", " ").replace("  ", " ").replace(" kB", "").split(" ")[1])/1024.0/1024.0


try:
    p = subprocess.Popen(["gnuplot", "--version"], stdout=subprocess.PIPE)
except:
    print("Gnuplot not found")
    sys.exit(1)

VERSION_EXPECTED = [5, 2]

version = p.stdout.readline().decode().split(" ")[1].split(".")
if (int(version[0]) < VERSION_EXPECTED[0]):
    print("Gnuplot version too low. Need at least %d.%d found %s.%s" % (VERSION_EXPECTED[0], VERSION_EXPECTED[1], version[0], version[1]))
    sys.exit(1)
if (int(version[0]) == VERSION_EXPECTED[0]) and (int(version[1]) < VERSION_EXPECTED[1]):
    print("Gnuplot version too low. Need at least %d.%d found %s.%s" % (VERSION_EXPECTED[0], VERSION_EXPECTED[1], version[0], version[1]))
    sys.exit(1)
    

try:
    gnuplot = subprocess.Popen(["gnuplot"], stdin=subprocess.PIPE)
except:
    print("Gnuplot not found")
    sys.exit(1)

def g(command):
    print ("gnuplot> %s" % command)
    try:
        command = b"%s\n" % command
    except:
        command = b"%s\n" % str.encode(command)
    gnuplot.stdin.write(b"%s\n" % command)

try:
    p = subprocess.Popen(["sar", "-u","-r", "1"], stdout=subprocess.PIPE, env = my_env)
except:
    print("Error starting sar")
    sys.exit(1)


print("%d" % os.getpid())

machine = p.stdout.readline().decode()

uname = machine.split(" ")[0:2]
uname = "%s %s" % (uname[0], uname[1])

cpus = int(machine.split(" CPU)")[0].split("(")[-1])


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

g("set terminal pngcairo size 1200,800 background '#222222' font 'Courier-New,8'")
g("set output 'plot.png'")

g("set multiplot layout 2,1 title \"%s\"" % "\\n\\n\\n")

signal.signal(signal.SIGTERM, kill_handler)
i = 0

f = open("data.txt", "w")

START_DATE = ""
END_DATE = ""
MAX_USED_RAM = 0
AVERAGE_LOAD = 0.0

flags = fcntl(sys.stdin, F_GETFL)
fcntl(sys.stdin, F_SETFL, flags | os.O_NONBLOCK)
labels = []

f.write("# machine: %s, cpu count: %d\n" % (uname, cpus))

while 1:
    rlist, _, _ = select([p.stdout, sys.stdin], [], [], 0.25)
    now = datetime.now()
    if sys.stdin in rlist:
        label_line = sys.stdin.readline().replace("\n", "")
        if label_line == "q":
            die = 1
            break
        labels.append(["%04d-%02d-%02d-%02d:%02d:%02d" % (now.year, now.month, now.day, now.hour, now.minute, now.second), label_line])
        f.write("# %04d-%02d-%02d-%02d:%02d:%02d label: %s\n" % (now.year, now.month, now.day, now.hour, now.minute, now.second, label_line))
    if (p.stdout not in rlist):
        continue
    now = "%04d-%02d-%02d" % (now.year, now.month, now.day);
    cpu_names = p.stdout.readline().decode().replace("  ", " ").replace("  ", " ").replace("  ", " ").replace("\n", "").replace("%", "").split(" ")
    cpu_names[0] = "time"
    cpu_values = p.stdout.readline().decode().replace("  ", " ").replace("  ", " ").replace("  ", " ").replace("\n", "").replace("%", "").split(" ")
    if START_DATE == "":
        START_DATE = "%s %s" % (now, cpu_values[0])
    cpu_values[0] = now + "-" + cpu_values[0]
    cpu_data = dict(zip(cpu_names, cpu_values))
    AVERAGE_LOAD += float(cpu_data["user"])
    i = i + 1
    p.stdout.readline()
    ram_names = p.stdout.readline().decode().replace("  ", " ").replace("  ", " ").replace("  ", " ").replace("\n", "").replace("%", "").split(" ")
    ram_names[0] = "time"
    ram_values = p.stdout.readline().decode().replace("  ", " ").replace("  ", " ").replace("  ", " ").replace("\n", "").replace("%", "").split(" ")
    END_DATE = now + " " + ram_values[0]
    ram_values[0] = now + "-" + ram_values[0]
    ram_data = dict(zip(ram_names, ram_values))
    p.stdout.readline()

    values = merge_dicts(ram_data, cpu_data)
    if TOTAL_RAM == 0:
        TOTAL_RAM = (int(values['kbmemused']) + int(values['kbmemfree'])) / 1024.0 / 1024.0
    if MAX_USED_RAM < int(values['kbmemused']):
        MAX_USED_RAM = int(values['kbmemused'])
    f.write("%s %s %s\n" % (values["time"], values["user"], values["memused"]))

    if die:
        break

AVERAGE_LOAD = AVERAGE_LOAD / float(i)
MAX_USED_RAM = MAX_USED_RAM / 1024.0 / 1024.0

sdt = datetime.strptime(START_DATE, '%Y-%m-%d %H:%M:%S')
edt = datetime.strptime(END_DATE, '%Y-%m-%d %H:%M:%S')
delta_t = ((edt - sdt).total_seconds()) / 60.0

f.write("# total ram: %.2f GB, max ram used: %.2f GB, avarage load: %.2f %%, duration: %.2f minutes\n" % (TOTAL_RAM, MAX_USED_RAM, AVERAGE_LOAD, delta_t))

f.close()

g("set title 'cpu load (avarage = %.2f %%)'" % AVERAGE_LOAD)
g("set title tc rgb 'white' font 'Courier-New,8'")

seconds_between = (edt - sdt).total_seconds()
if seconds_between < 100:
 seconds_between = 100

nsdt = sdt - timedelta(seconds = (seconds_between * 0.01))
nedt = edt + timedelta(seconds = (seconds_between * 0.01))

g("set xrange ['%s':'%s']" % (nsdt.strftime("%Y-%m-%d-%H:%M:%S"), nedt.strftime("%Y-%m-%d-%H:%M:%S")));


now = datetime.now()
now = "%04d-%02d-%02d %02d:%02d:%02d" % (now.year, now.month, now.day, now.hour, now.minute, now.second);


g("set label 101 at screen 0.02, screen 0.95 \"Running on {/:Bold %s} at {/:Bold %s}, cpu count is {/:Bold %d}, total ram is {/:Bold %.2f GB}\\nduration: {/:Bold %s} .. {/:Bold %s} (%.2f minutes)\" tc rgb 'white'" % (uname, now, cpus, TOTAL_RAM, START_DATE, END_DATE, delta_t))

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

g("set object rectangle from graph 0, graph 0 to graph 1, graph 1 behind fillcolor rgb '#111111' fillstyle solid noborder")
g("set object rectangle from '%s', 0 to '%s', 100 behind fillcolor rgb '#000000' fillstyle solid noborder" % (START_DATE.replace(" ", "-"), END_DATE.replace(" ", "-")))


g("plot 'data.txt' using 1:2:2 title 'cpu' with boxes palette")

g("set ylabel 'ram % usage'")
g("set title 'ram usage (max = %.2f GB)'" % MAX_USED_RAM);

g("plot 'data.txt' using 1:3:3 title 'ram' with boxes palette")

g("replot")
g("quit")

