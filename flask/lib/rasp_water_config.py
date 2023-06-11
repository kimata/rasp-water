#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pathlib

should_terminate = False

APP_URL_PREFIX = "/rasp-water"

SCHEDULE_DATA_PATH = pathlib.Path(__file__).parent.parent / "data" / "schedule.dat"
LOG_DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "log.db"

STAT_DIR_PATH = pathlib.Path("/dev/shm") / "rasp-water"

ANGULAR_DIST_PATH = "../../dist/rasp-water"
