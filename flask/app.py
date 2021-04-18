#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import subprocess

from flask import Flask

from rasp_water import rasp_water,app_init

app = Flask(__name__)

app.register_blueprint(rasp_water)

@app.before_first_request
def initialize():
    app_init()


if __name__ == '__main__':
    app.debug = True
    # NOTE: スクリプトの自動リロード停止したい場合は use_reloader=False にする
    app.run(host='0.0.0.0', threaded=True, use_reloader=True)
