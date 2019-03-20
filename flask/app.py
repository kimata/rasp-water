#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from flask import Flask

from rasp_water import rasp_water

app = Flask(__name__)

app.register_blueprint(rasp_water)

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', threaded=True)
