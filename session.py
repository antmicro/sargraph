#!/usr/bin/env python3

#
# (c) 2019-2026 Antmicro <www.antmicro.com>
# License: Apache-2.0
#

from pathlib import Path
from common import *
import socket
import time
import os


SARGRAPH_DB = Path(__file__).parent / ".run"
SESSION_FILE = SARGRAPH_DB / "sessions.txt"
LISTEN_HOST = "127.0.0.1"
CLIENT_INIT_CONN_TIMEOUT = 5


def init_db():
    SARGRAPH_DB.mkdir(parents=True, exist_ok=True)

def data_file(session):
    return SARGRAPH_DB / f"{session}.dat"

def session2port():
    try:
        with open(SESSION_FILE) as file:
            ports = {}
            for line in file:
                name, port = line.strip().split(":", 1)
                ports[name] = int(port.strip())
            return ports
    except FileNotFoundError as e:
        return {}

def get_address(session):
    ports = session2port()
    if session not in ports:
        return None
    return (LISTEN_HOST, ports[session])

def add(session, port):
    with open(SESSION_FILE, "a") as file:
        file.write(f"{session}:{port}\n")

def remove(session):
    ports = session2port()
    if session not in ports:
        return
    del ports[session]
    with open(SESSION_FILE, "w") as file:
        for name, port in ports.items():
            file.write(f"{name}:{port}\n")

def connect(session):
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if not spinloop(lambda: get_address(session), 1, 3): # low as server should create the session entry first thing in watch()
        raise ConnectionError(f"No adddress found for session '{session}'")
    if not spinloop(lambda: conn.connect_ex(get_address(session)), 1, CLIENT_INIT_CONN_TIMEOUT):
        raise ConnectionError(f"Timeout connecting to server: {address}")
    conn.setblocking(True)
    hello_msg = recv_oneline(conn)
    if not hello_msg.startswith("220"):
        raise RuntimeError(f"Invalid server greeting: {hello_msg}")
    return conn

def create_server(session):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((LISTEN_HOST, 0))
    add(session, sock.getsockname()[1])
    sock.listen(10)
    return sock
