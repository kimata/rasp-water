#!/usr/bin/env python3
import datetime
import os
import tracemalloc

import psutil
import tzlocal
import uptime
from flask_util import support_jsonp
from webapp_config import APP_URL_PREFIX, TIMEZONE

from flask import Blueprint, jsonify

blueprint = Blueprint("webapp-util", __name__, url_prefix=APP_URL_PREFIX)

snapshot_prev = None


@blueprint.route("/api/memory", methods=["GET"])
@support_jsonp
def print_memory():
    return {"memory": psutil.Process(os.getpid()).memory_info().rss}


# NOTE: メモリリーク調査用
@blueprint.route("/api/snapshot", methods=["GET"])
@support_jsonp
def snap():
    global snapshot_prev  # noqa: PLW0603

    if not snapshot_prev:
        tracemalloc.start()
        snapshot_prev = tracemalloc.take_snapshot()

        return {"msg": "taken snapshot"}
    else:
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.compare_to(snapshot_prev, "lineno")
        snapshot_prev = snapshot

        return jsonify([str(stat) for stat in top_stats[:10]])


@blueprint.route("/api/sysinfo", methods=["GET"])
@support_jsonp
def api_sysinfo():
    return jsonify(
        {
            "date": datetime.datetime.now(TIMEZONE).isoformat(),
            "timezone": str(tzlocal.get_localzone()),
            "image_build_date": os.environ.get("IMAGE_BUILD_DATE", ""),
            "uptime": uptime.boottime().isoformat(),
            "loadAverage": "{:.2f}, {:.2f}, {:.2f}".format(*os.getloadavg()),
        }
    )
