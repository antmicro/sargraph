#
# (c) 2019 Antmicro <www.antmicro.com>
# License: Apache
#

from Gnuplot import Gnuplot, Data, File
from time import sleep
from datetime import datetime, timedelta
import signal
import os
import subprocess
import sys

global die
die = 0

def kill_handler(a, b):
        global die
        die = 1


def merge_dicts(x, y):
    res = x.copy()
    res.update(y)
    return res


print os.getpid()


my_env = os.environ
my_env["S_TIME_FORMAT"] = "ISO"

try:
    p = subprocess.Popen(["sar", "-u","-r", "1"], stdout=subprocess.PIPE, env = my_env)
except:
    print "Error starting sar"
    sys.exit(1)


g = Gnuplot(debug=1)

machine = p.stdout.readline()

uname = machine.split(" ")[0:2]
uname = "%s %s" % (uname[0], uname[1])

cpus = int(machine.split(" CPU)")[0].split("(")[-1])


p.stdout.readline()

g.ylabel("cpu % usage (user)")

g("set ylabel tc rgb 'white' font 'Courier-New,8'")

g("set timefmt '%s'")
g("set xdata time")
g("set xtics 6000")
g("set terminal pngcairo size 1200,800 background '#222222' font 'Courier-New,8'")
g("set border lc rgb 'white'")
g("set key tc rgb 'white'")
g("set timefmt '%Y-%m-%d-%H:%M:%S'")
g("set xtics format '%H:%M'")
g("set xtics font 'Courier-New,8'")
g("set ytics font 'Courier-New,8'")
g("set grid xtics ytics ls 12 lc rgb '#444444'")
g("set style fill solid")
g("set palette defined ( 0.2 '#00ff00', 0.8 '#ff0000' )")
g("set cbrange [0:100]")
g("unset colorbox")
g("unset key")


g("set output 'plot.png'")
g("set multiplot layout 2,1 title \"%s\"" % "\\n\\n\\n")

signal.signal(signal.SIGTERM, kill_handler)
i = 0

f = open("data.txt", "w")

START_DATE = ""
END_DATE = ""
TOTAL_RAM = 0
MAX_USED_RAM = 0
AVERAGE_LOAD = 0.0


while 1:
    now = datetime.now()
    now = "%04d-%02d-%02d" % (now.year, now.month, now.day);
    cpu_names = p.stdout.readline().replace("  ", " ").replace("  ", " ").replace("  ", " ").replace("\n", "").replace("%", "").split(" ")
    cpu_names[0] = "time"
    cpu_values = p.stdout.readline().replace("  ", " ").replace("  ", " ").replace("  ", " ").replace("\n", "").replace("%", "").split(" ")
    if START_DATE == "":
        START_DATE = "%s %s" % (now, cpu_values[0])
    cpu_values[0] = now + "-" + cpu_values[0]
    cpu_data = dict(zip(cpu_names, cpu_values))
    AVERAGE_LOAD += float(cpu_data["user"])
    i = i + 1
    p.stdout.readline()
    ram_names = p.stdout.readline().replace("  ", " ").replace("  ", " ").replace("  ", " ").replace("\n", "").replace("%", "").split(" ")
    ram_names[0] = "time"
    ram_values = p.stdout.readline().replace("  ", " ").replace("  ", " ").replace("  ", " ").replace("\n", "").replace("%", "").split(" ")
    END_DATE = now + " " + ram_values[0]
    ram_values[0] = now + "-" + ram_values[0]
    ram_data = dict(zip(ram_names, ram_values))
    p.stdout.readline()

    values = merge_dicts(ram_data, cpu_data)
    if TOTAL_RAM == 0:
        TOTAL_RAM = (int(values['kbmemused']) + int(values['kbmemfree'])) / 1024 / 1024
    if MAX_USED_RAM < int(values['kbmemused']):
        MAX_USED_RAM = int(values['kbmemused'])
    f.write("%s %s %s\n" % (values["time"], values["user"], values["memused"]))

    if die:
        break

AVERAGE_LOAD = AVERAGE_LOAD / float(i)

f.close()

g.title("cpu load (avarage = %.2f %%)" % AVERAGE_LOAD)
g("set title tc rgb 'white' font 'Courier-New,8'")

sdt = datetime.strptime(START_DATE, '%Y-%m-%d %H:%M:%S')
edt = datetime.strptime(END_DATE, '%Y-%m-%d %H:%M:%S')
delta_t = ((edt - sdt).total_seconds()) / 60.0

seconds_between = (edt - sdt).total_seconds()
if seconds_between < 100:
 seconds_between = 100

nsdt = sdt - timedelta(seconds = (seconds_between * 0.01))
nedt = edt + timedelta(seconds = (seconds_between * 0.01))

g("set xrange ['%s':'%s']" % (nsdt.strftime("%Y-%m-%d-%H:%M:%S"), nedt.strftime("%Y-%m-%d-%H:%M:%S")));


now = datetime.now()
now = "%04d-%02d-%02d %02d:%02d:%02d" % (now.year, now.month, now.day, now.hour, now.minute, now.second);


MAX_USED_RAM = MAX_USED_RAM / 1024.0 / 1024.0

g("set label 101 at screen 0.02, screen 0.95 \"Running on {/:Bold %s} at {/:Bold %s}, cpu count is {/:Bold %d}, total ram is {/:Bold %d GB}\\nduration: {/:Bold %s} .. {/:Bold %s} (%.2f minutes)\" tc rgb 'white'" % (uname, now, cpus, TOTAL_RAM, START_DATE, END_DATE, delta_t))

i = 0
#labels = [[START_DATE.replace(" ", "-"), "start"], [END_DATE.replace(" ", "-"), "stop"]]
labels = []
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


d1 = File("data.txt", using="1:2:2", title="cpu", with_="boxes palette")
g.plot(d1)

g.title("ram usage (max = %.2f GB)" % MAX_USED_RAM);

d2 = File("data.txt", using="1:3:3", title="ram", with_="boxes palette")
g.plot(d2)


