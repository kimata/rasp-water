#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from influxdb import InfluxDBClient

INFLUXDB_ADDR = '192.168.2.20'
INFLUXDB_PORT = 8086
INFLUXDB_DB = 'sensor'

INFLUXDB_QUERY = """
SELECT mean("touchpad") FROM "sensor.esp32" WHERE ("hostname" = \'ESP32-raindrop\') AND time >= now() - 1h GROUP BY time(5m) fill(previous) ORDER by time desc LIMIT 10
"""

WET_THRESHOLD = 380

def get_latest_mean(result):
    for status in result.get_points():
        if not status['mean'] is None:
            return status['mean']
    return None

def is_soil_wet():
    try:
        client = InfluxDBClient(host=INFLUXDB_ADDR, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        result = client.query(INFLUXDB_QUERY)
        mean = get_latest_mean(result)

        if mean is None:
            return False
        return mean < WET_THRESHOLD
    except:
        pass

    return False

if __name__ == '__main__':
    print(is_soil_wet())
