#!/usr/bin/env python3

#
# (c) 2019-2022 Antmicro <www.antmicro.com>
# License: Apache
#

import argparse
import sys
import time


from common import *

# Declare and parse command line flags
parser = argparse.ArgumentParser()
parser.add_argument('session', metavar='SESSION-NAME', type=str, nargs='?', default=None,                  help='sargraph session name')
parser.add_argument('command', metavar='COMMAND',      type=str, nargs='*',                                help='send command')
parser.add_argument('-f',      metavar='DEVICE-NAME',  type=str, nargs='?', default=None,   dest='fsdev',  help='observe a chosen filesystem')
parser.add_argument('-m',      metavar='MOUNT-DIR',    type=str, nargs='?', default=None,   dest='fspath', help='observe a chosen filesystem')
parser.add_argument('-o',      metavar='OUTPUT-NAME',  type=str, nargs='?', default='data', dest='name',   help='set output base names')
args = parser.parse_args()

# Check if sar is available
p = run_process("sar", "-V", stdout=subprocess.PIPE)

# Check if screen is available
p = run_process("screen", "-v", stdout=subprocess.PIPE)
version = scan("Screen version (\d+)", int, p.stdout.readline().decode())
if version is None:
    print("Error: 'screen' tool returned unknown output!")
    sys.exit(1)

# If the script was run with no parameters, run in background and gather data
if args.session is None:
    import watch

    # Find requested disk device
    if args.fspath:
        args.fspath = os.path.realpath(args.fspath)
        with open("/proc/self/mounts", "r") as f:
            while args.fsdev is None:
                args.fsdev = scan(f"^(/dev/\S+)\s+{re.escape(args.fspath)}\s+", str, f.readline())
        if not args.fsdev:
            print(f"Error: no device is mounted on {args.fspath}")
            sys.exit(1)

    watch.watch(args.name, args.fsdev)
    sys.exit(0)

# Now handle the commands

# Check if a command was provided
if len(args.command) <= 0:
    print("Error: command not provided.")
    sys.exit(1)

# Get session name and command name
sid = args.session
cmd = args.command

if cmd[0] == "start":
    print(f"Starting sargraph session '{sid}'")

    # Spawn watcher process, *sys.argv[3:] is all arguments after 'chart start'
    p = subprocess.Popen(["screen", "-dmSL", sid, os.path.realpath(__file__), *sys.argv[3:], '-o', sid])

    while p.poll() is None:
        time.sleep(0.1)
    gpid = 0
    j = 0
    time.sleep(1)
    print(f"Session '{sid}' started")
elif cmd[0] == "stop":
    print(f"Terminating sargraph session '{sid}'")

    try:
        gpid = int(os.popen(f"screen -ls | grep '.{sid}' | tr -d ' \t' | cut -f 1 -d '.'").read())
    except:
        print("Warning: cannot find pid.")
        gpid = -1
    if len(cmd) >= 2 and cmd[1] == "none":
        p = subprocess.Popen(["screen", "-S", sid, "-X", "stuff", "command:b\n"])
    else:
        p = subprocess.Popen(["screen", "-S", sid, "-X", "stuff", "command:q\n"])
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

    print(f"Adding label '{label}' to sargraph session '{sid}'.")
    p = subprocess.Popen(["screen", "-S", sid, "-X", "stuff", f"label:{label}\n"])
    while p.poll() is None:
        time.sleep(0.1)
elif cmd[0] == 'save':
    print(f"Saving graph from session '{sid}'.")
    if len(cmd) < 2:
        fname = ''
    else:
        fname = cmd[1]
    p = subprocess.Popen(["screen", "-S", sid, "-X", "stuff", f"command:s:{fname}\n"])
    while p.poll() is None:
        time.sleep(0.1)
elif cmd[0] == 'plot':
    import graph
    if len(cmd) < 2:
        graph.graph(sid)
    else:
        graph.graph(sid, cmd[1])
else:
    print(f"Error: Unknown command '{cmd[0]}'")
    sys.exit(1)
