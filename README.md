# sargraph

Copyright (c) 2019-2022 [Antmicro](https://www.antmicro.com)

This is a simple python tool that uses "sysstat" ("sar") and "gnuplot" to plot cpu and ram usage.

# Usage
```
$ python sargraph.py [session_name] [command] [arg]
```

Background use (requires "screen" tool):

```
$ python3 sargraph.py chart start
$ sleep 1
$ python3 sargraph.py chart label "label1"
$ sleep 1
$ python3 sargraph.py chart label "label2"
$ sleep 1
$ python3 sargraph.py chart stop
```

Or just:
```
$ python3 sargraph.py
# wait 1 sec
# type label1\n
# wait 1 sec
# type label2\n
# wait 1 sec
# type q\n
# wait until sargraph generates plot.png
```

# Example graph

![graph](graph.png)
