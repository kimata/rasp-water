#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask_util import gzipped
from webapp_config import APP_URL_PREFIX, STATIC_FILE_PATH

from flask import Blueprint, redirect, send_from_directory

blueprint = Blueprint("webapp-base", __name__, url_prefix=APP_URL_PREFIX)


@blueprint.route("/", defaults={"filename": "index.html"})
@blueprint.route("/<path:filename>")
@gzipped
def webapp(filename):
    return send_from_directory(STATIC_FILE_PATH, filename)


blueprint_default = Blueprint("webapp-default", __name__)


@blueprint_default.route("/")
@gzipped
def root():
    return redirect("{webapp_prefix}/".format(webapp_prefix=APP_URL_PREFIX))
