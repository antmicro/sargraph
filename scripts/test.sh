#!/bin/bash

if [[ "$@" =~ 'html' ]] 
then 
    pip install git+https://github.com/antmicro/servis#egg=servis[bokeh] 
fi

dd if=/dev/zero of=$FAKE_DISK bs=1M count=130
mkfs.ext4 $FAKE_DISK
mkdir -p $FAKE_MOUNTPOINT && mount $FAKE_DISK $FAKE_MOUNTPOINT

sargraph chart start -m $FAKE_MOUNTPOINT

pushd $FAKE_MOUNTPOINT
df -h .
stress -c 16 -i 1 -m 1 --vm-bytes 512M -d 1 --hdd-bytes 70M -t 160s

popd

for ext in "$@"
do
    sargraph chart save "plot.${ext}"
done

sargraph chart stop

for ext in "$@"
do
    test -f "plot.${ext}"
done

cat chart.log

if [[ "$@" =~ 'ascii' ]] 
then    
    echo '------Sample plot------'
    cat plot.ascii
fi