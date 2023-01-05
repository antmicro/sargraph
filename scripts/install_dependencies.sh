#!/bin/bash

apt -qqy update > /dev/null
apt -qqy install --no-install-recommends screen sysstat gnuplot-nox python3 python3-pip git stress coreutils > /dev/null
pip install -r requirements.txt
ln -s $(realpath sargraph.py) /usr/bin/sargraph