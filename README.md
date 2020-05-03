# sargraph

This is a simple python tool that uses "sysstat" ("sar") and "gnuplot" to plot cpu and ram usage.

Usage:
```
$ python sargraph.py [session_name] [command] [arg]
```

Background use (requires "screen" tool):

```
$ python sargraph.py chart start
$ sleep 1
$ python sargraph.py chart label "label1"
$ sleep 1
$ python sargraph.py chart label "label2"
$ sleep 1
$ python sargraph.py chart stop
```

Or just:
```
$ python sargraph.py
# wait 1 sec
# type label1\n
# wait 1 sec
# type label2\n
# wait 1 sec
# type q\n
# wait until sargraph generates plot.png
```


Copyright (c) 2019-2020 Antmicro <www.antmicro.com>

Licensed under Apache License.
