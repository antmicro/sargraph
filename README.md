# sargraph

This is a simple python tool that uses sysstat (sar) to plot cpu and ram usage.

Best used with screen:

```console
$ screen -dmSL chart python sargraph.py
$ sleep 1
$ screen -S chart -X stuff "label1\n"
$ sleep 1
$ screen -S chart -X stuff "label2\n"
$ sleep 1
$ screen -S chart -X stuff "q\n"
$ sleep 3
```

Or just:
```console
$ python sargraph.py
# wait 1 sec
# type label1\n
# wait 1 sec
# type label2\n
# wait 1 sec
# type q\n
# wait until sargraph generates plot.png
```


(c) 2019 Antmicro <www.antmicro.com>

Licensed under Apache License.
