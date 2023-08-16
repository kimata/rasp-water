#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime
import pathlib

import pytz

APP_URL_PREFIX = "/rasp-water"

TIMEZONE = datetime.timezone(datetime.timedelta(hours=+9), "JST")
TIMEZONE_PYTZ = pytz.timezone("Asia/Tokyo")  # schedule 用
TIMEZONE_OFFSET = "+9"

STATIC_FILE_PATH = pathlib.Path(__file__).parent.parent.parent / "dist" / "rasp-water"

SCHEDULE_DATA_PATH = pathlib.Path(__file__).parent.parent / "data" / "schedule.dat"
LOG_DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "log.db"

STAT_DIR_PATH = pathlib.Path("/dev/shm") / "rasp-water"
