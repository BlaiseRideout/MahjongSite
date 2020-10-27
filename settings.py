#!/usr/bin/env python3

import sys

import defaults
try:
    import mysettings
except ImportError:
    mysettings = None

settings = sys.modules[__name__]
for setting in [i for i in dir(defaults) + dir(mysettings) if i[0] != "_"]:
    if mysettings is None or not hasattr(mysettings, setting):
        setattr(settings, setting, getattr(defaults, setting))
    else:
        setattr(settings, setting, getattr(mysettings, setting))
