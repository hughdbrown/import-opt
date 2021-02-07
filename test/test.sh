#!/bin/sh

cp a.py.orig a.py
../import_opt.py
diff a.py a.py.outcome
