#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# NOTE: 現時点で使われていない

import os
from datetime import datetime

from influxdb import InfluxDBClient

INFLUXDB_ADDR = "192.168.0.10"
INFLUXDB_PORT = 8086
INFLUXDB_DB = "sensor"

INFLUXDB_QUERY1 = """ SELECT mean("touchpad") FROM "sensor.esp32"
WHERE ("hostname" = \'ESP32-raindrop\') AND time >= now() - 1h GROUP
BY time(5m) fill(previous) ORDER by time desc LIMIT 10 """

INFLUXDB_QUERY2 = """ SELECT sum("rain") FROM "sensor.esp32" WHERE
("hostname" = \'ESP32-rain\') AND time >= now() - 2d GROUP BY
time(12h) fill(0) ORDER by time desc LIMIT 10 """

WET_THRESHOLD1 = 370
WET_THRESHOLD2 = 0.5


def is_soil_wet_1():
    try:
        client = InfluxDBClient(host=INFLUXDB_ADDR, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        result = client.query(INFLUXDB_QUERY1)

        points = list(filter(lambda x: x is not None, map(lambda x: x["mean"], result.get_points())))

        with open(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "soilwet.log"),
            mode="a",
        ) as f:
            print("{} wet1 {}".format(datetime.now(), list(points)), file=f)

        val = points[0]
        if val is None:
            return False
        return val < WET_THRESHOLD1
    except:
        pass

    return False


def is_soil_wet_2():
    try:
        client = InfluxDBClient(host=INFLUXDB_ADDR, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        result = client.query(INFLUXDB_QUERY2)

        points = list(filter(lambda x: x is not None, map(lambda x: x["sum"], result.get_points())))

        with open(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "soilwet.log"),
            mode="a",
        ) as f:
            print("{} wet2 {}".format(datetime.now(), list(points)), file=f)

        val = points[0]
        if val is None:
            return False
        return val > WET_THRESHOLD2
    except:
        pass

    return False


def is_soil_wet():
    return is_soil_wet_1() or is_soil_wet_2()


if __name__ == "__main__":
    print(is_soil_wet())
