#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, current_app, Response, send_from_directory

from rasp_water import rasp_water

os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)

app.register_blueprint(rasp_water)

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', threaded=True)
