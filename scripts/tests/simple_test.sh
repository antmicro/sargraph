#!/bin/bash

dd if=/dev/zero of=$FAKE_DISK bs=1M count=130
mkfs.ext4 $FAKE_DISK
mkdir -p $FAKE_MOUNTPOINT && mount $FAKE_DISK $FAKE_MOUNTPOINT

sargraph chart start -m $FAKE_MOUNTPOINT

pushd $FAKE_MOUNTPOINT
df -h .
stress -c 16 -i 1 -m 1 --vm-bytes 512M -d 1 --hdd-bytes 70M -t 160s

popd

sargraph chart save plot.svg
sargraph chart save plot.png
sargraph chart save plot.ascii
sargraph chart stop

test -f plot.svg
test -f plot.png
test -f plot.ascii

cat chart.log
echo '------Sample plot------'
cat plot.ascii