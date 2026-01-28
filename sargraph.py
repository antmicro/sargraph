#!/usr/bin/env python3

#
# (c) 2019-2026 Antmicro <www.antmicro.com>
# License: Apache-2.0
#

import argparse
import sys

import graph
import watch
import warnings

from common import *

# Declare and parse command line flags
parser = argparse.ArgumentParser()
parser.add_argument('session', metavar='SESSION-NAME', type=str, nargs='?',                                       help='sargraph session name')
parser.add_argument('command', metavar='COMMAND',      type=str, nargs='*',                                       help='send command')
parser.add_argument('-f',      metavar='DEVICE-NAME',  type=str, nargs='?', default=None,      dest='fsdev',      help='observe a chosen filesystem')
parser.add_argument('-m',      metavar='MOUNT-DIR',    type=str, nargs='?', default=None,      dest='fspath',     help='observe a chosen filesystem')
parser.add_argument('-n',      metavar='IFACE-NAME',   type=str, nargs='?', default=None,      dest='iface',      help='observe chosen network iface')
parser.add_argument('-o',      metavar='OUTPUT-NAME',  type=str, nargs='?', default='data',    dest='name',       help='set output base names')
parser.add_argument('-t',      metavar='TMPFS-COLOR',  type=str, nargs='?', default='#f2c71b', dest='tmpfs',      help='set tmpfs plot color' )
parser.add_argument('-c',      metavar='CACHE-COLOR',  type=str, nargs='?', default='#ee7af0', dest='cache',      help='set cache plot color' )
parser.add_argument('-u',      metavar='UDP',          type=str, nargs='?', default=None,      dest='udp',        help='set udp server address')
parser.add_argument('-C',      metavar='UDP_COOKIE',   type=str, nargs='?', default=None,      dest='udp_cookie', help='set udp message cookie')
parser.add_argument('-p',      action='store_true',                                            dest='psutil',     help='use psutil instead of sar')
args = parser.parse_args()

def send(session: str, message: str):
    socket_path = watch.get_socket_path(session)
    if not file_exists(socket_path):
        fail(f"Session '{session}' does not exist")

    sock = watch.get_socket()
    sock.connect(socket_path)
    sock.send(message.encode("utf-8"))
    sock.close()

def create_session():
    # Find requested disk device
    if args.fspath:
        args.fspath = os.path.realpath(args.fspath)
        with open("/proc/self/mounts", "r") as f:
            while args.fsdev is None:
                args.fsdev = scan(f"^(/dev/\\S+)\\s+{re.escape(args.fspath)}\\s+", str, f.readline())
        if not args.fsdev:
            fail(f"No device is mounted on {args.fspath}")

    params = (args.session, args.fsdev, args.iface, args.tmpfs, args.cache, args.udp, args.udp_cookie)
    if is_darwin() or args.psutil or is_windows():
        watcher = watch.PsUtilWatcher(*params)
    else:
        watcher = watch.SarWatcher(*params)

    watcher.start()
    sys.exit(0)

# Check if sar is available
if not (is_darwin() or is_windows()):
    p = run_or_fail("sar", "-V", stdout=subprocess.PIPE)

if args.name != "data":
    warnings.warn("'-o' is deprecated, session name is default output base name")

# Check if a command was provided, if that session exists, yell at user for lack of commands, else spawn
if len(args.command) == 0:
    if file_exists(watch.get_socket_path(args.session)):
        fail("Command not provided")
    
    else:
        print(f"Starting sargraph session '{args.session}'")
        create_session()

if args.command[0] == "start":
    socket_path = watch.get_socket_path(args.session)
    if file_exists(socket_path):
        fail("Session with this name already exists")
    
    # Start watcher process
    p = subprocess.Popen(
        args=[sys.executable, os.path.realpath(__file__), args.session, *sys.argv[3:]],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    # Spinloop to see whether the subprocess even starts
    if spinloop(lambda: file_exists(socket_path), 0.1, 5):
        print(f"Session '{args.session}' started")
        sys.exit(0)
    
    fail("Session did not start")

elif args.command[0] == "stop":
    socket_path = watch.get_socket_path(args.session)
    
    print(f"Terminating sargraph session '{args.session}'")
    if len(args.command) < 2:
        send(args.session, "command:q:")
    else:
        send(args.session, f"command:q:{args.command[1]}")

    # Spinloop to see whether the subprocess even dies
    if spinloop(lambda: not file_exists(socket_path), 0.5, 5):
        print(f"Session '{args.session}' killed")
        sys.exit(0)

    fail("Session did not respond")


elif args.command[0] == "label":
    # Check if the label name was provided
    if len(args.command) < 2:
        fail("label command requires an additional parameter")

    print(f"Adding label '{args.command[1]}' to sargraph session '{args.session}'.")
    send(args.session, f"label:{args.command[1]}")


elif args.command[0] == 'save':
    print(f"Saving graph from session '{args.session}'.")
    if len(args.command) < 2:
        send(args.session, "command:s:")
    else:
        send(args.session, f"command:s:{args.command[1]}")

elif args.command[0] == 'plot':
    if len(args.command) < 2:
        graph.graph(args.session, args.tmpfs, args.cache)
    else:
        graph.graph(args.session, args.tmpfs, args.cache, args.command[1])
else:
    fail(f"unknown command '{args.command[0]}'")
