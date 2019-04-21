#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from influxdb import InfluxDBClient
from datetime import datetime


INFLUXDB_ADDR = '192.168.2.20'
INFLUXDB_PORT = 8086
INFLUXDB_DB = 'sensor'

INFLUXDB_QUERY = """
SELECT mean("touchpad") FROM "sensor.esp32" WHERE ("hostname" = \'ESP32-raindrop\') AND time >= now() - 1h GROUP BY time(5m) fill(previous) ORDER by time desc LIMIT 10
"""

WET_THRESHOLD = 370

def is_soil_wet():
    try:
        client = InfluxDBClient(host=INFLUXDB_ADDR, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        result = client.query(INFLUXDB_QUERY)

        points = list(filter(lambda x: not x is None,
                             map(lambda x: x['mean'], result.get_points())))

        with open("solwet.log", mode='a') as f:
            print('{} {}'.format(datetime.now(), list(points)), file=f)

        val = points[0]
        if val is None:
            return False
        return val < WET_THRESHOLD
    except:
        pass

    return False

if __name__ == '__main__':
    print(is_soil_wet())
