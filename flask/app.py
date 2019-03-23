#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import datetime
import subprocess

from flask import Flask

from rasp_water import rasp_water

app = Flask(__name__)

app.register_blueprint(rasp_water)

if __name__ == '__main__':
    subprocess.call(
        'echo "{} に再起動しました．" | mail -s "rasp-water 再起動" root'.format(
            datetime.datetime.today()
        ), shell=True
    )
    app.debug = True
    app.run(host='0.0.0.0', threaded=True, use_reloader=False)
