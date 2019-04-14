#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from influxdb import InfluxDBClient

INFLUXDB_ADDR = '192.168.2.20'
INFLUXDB_PORT = 8086
INFLUXDB_DB = 'sensor'

QUERY = """
SELECT mean("touchpad") FROM "sensor.esp32" WHERE ("hostname" = \'ESP32-raindrop\') AND time >= now() - 1h GROUP BY time(5m) fill(previous) LIMIT 1
"""

WET_THRESHOLD = 380

def is_soil_wet():
    try:
        client = InfluxDBClient(host=INFLUXDB_ADDR, port=INFLUXDB_PORT, database=INFLUXDB_DB)
        result = client.query(QUERY)
        return result.get_points().__next__()['mean'] < WET_THRESHOLD
    except:
        pass

    return False

if __name__ == '__main__':
    print(is_soil_wet())
