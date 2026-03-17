#!/usr/bin/env python3

#
# (c) 2019-2026 Antmicro <www.antmicro.com>
# License: Apache-2.0
#

import argparse
import sys

import graph
import watch
import session
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
    if session.get_address(args.session):
        fail(f"Session '{args.session}' already exists, provide command!")
    else:
        print(f"Starting sargraph session '{args.session}'")
        create_session()

# print response from server until status message is received or connection is closed
def print_response(sarconn):
    while True:
        lines = recv_lines(sarconn)
        if not lines:
            return (400, "Connection unexpectedly closed by server")
        for line in lines:
            if line[:3] == "200":
                return (200, line)
            print('[SARGRAPH]', line)

match args.command[0]:
    case "log":
        with open(session.data_file(args.session)) as log:
            for line in log:
                if line.startswith("#"):
                    print(line, end='')
            try:
                while True:
                    new_line = log.readline()
                    if new_line and new_line.startswith("#"):
                        print(new_line, end='')
            except KeyboardInterrupt:
                sys.exit(0)

    case 'plot':
        fname = graph.DEFAULT_PLOT_FNAME
        if len(args.command) > 1:
            fname = args.command[1]
        graph.graph(args.session, args.tmpfs, args.cache, fname)

    case "start":
        if session.get_address(args.session):
            fail(f"Session for '{args.session}' already exists")

        print("Starting sargraph session... ", end='', flush=True)
        p = subprocess.Popen(
            args=[sys.executable, os.path.realpath(__file__), args.session, *sys.argv[3:]],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        time.sleep(1)
        if p.poll() is not None:
            fail(f"Sargraph failed to start with exit code {p.returncode}")
        print("ok")

        print("Wait for sargraph connection... ", end='', flush=True)
        try:
            sarconn = session.connect(args.session)
        except ConnectionError as e:
            fail(e)
        send_line(sarconn, "PING")
        status, msg = print_response(sarconn)
        sarconn.close()
        if status != 200:
            fail(msg)
        print(f"Session '{args.session}' started")
        sys.exit(0)

    case _:
        cmd = ' '.join(args.command)
        try:
            sarconn = session.connect(args.session)
        except ConnectionError as e:
            fail(e)
        except KeyboardInterrupt:
            sys.exit(0)
        send_line(sarconn, cmd)
        status, msg = print_response(sarconn)
        sarconn.close()
        if status != 200:
            fail(msg)
        sys.exit(0)
