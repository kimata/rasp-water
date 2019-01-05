#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import (
    request, jsonify, current_app, Response, send_from_directory,
    after_this_request,
    Blueprint
)

from functools import wraps
import re
import sqlite3
import subprocess
import threading
import time
import json
from crontab import CronTab
import os
import functools
import gzip
from io import BytesIO
# import pprint

# 電磁弁が接続されている GPIO
CTRL_GPIO = 18
# 流量計のアナログ出力値 (ADS1015 のドライバが公開)
FLOW_PATH = '/sys/class/hwmon/hwmon0/device/in4_input'
# 流量計が計れる最大流量
FLOW_MAX = 12
# 流量計の積算から除外する期間[秒]
MEASURE_IGNORE = 3
# 流量計を積算する間隔[秒]
MEASURE_INTERVAL = 0.5

APP_PATH = '/rasp-water'
ANGULAR_DIST_PATH = '../dist/rasp-water'

EVENT_TYPE_LOG = 'log'
EVENT_TYPE_SCHEDULE = 'schedule'

event_count = {
    EVENT_TYPE_LOG: 0,
    EVENT_TYPE_SCHEDULE: 0,
}

SCHEDULE_MARKER = 'WATER SCHEDULE'
WATER_CTRL_CMD = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'script', 'water_ctrl.py')
)

rasp_water = Blueprint('rasp-water', __name__, url_prefix=APP_PATH)

sqlite = sqlite3.connect(':memory:', check_same_thread=False)
sqlite.execute('CREATE TABLE log(date INT, message TEXT)')
sqlite.row_factory = lambda c, r: dict(
    zip([col[0] for col in c.description], r)
)

event_lock = threading.Lock()
schedule_lock = threading.Lock()
measure_lock = threading.Lock()
measure_stop = threading.Event()
measure_sum = 0

def parse_cron_line(line):
    match = re.compile(
        '^(#?)\s*(\d{{1,2}})\s+(\d{{1,2}})\s+.+{}\s+(\d+)'.format(
            re.escape(WATER_CTRL_CMD)
        )
    ).search(str(line))

    if match:
        mg = match.groups()
        return {
            'is_active': mg[0] == '',
            'time': '{:02}:{:02}'.format(int(mg[2]), int(mg[1])),
            'period': int(mg[3])
        }
    else:
        match = re.compile(
            '^(#?)\s*@daily.+{}\s+(\d+)'.format(WATER_CTRL_CMD)
        ).search(str(line))
        if match:
            mg = match.groups()

            return {
                'is_active': mg[0] == '',
                'time': '00:00',
                'period': int(mg[1])
            }

    return None


def cron_read():
    cron = CronTab(user=True)
    schedule = []
    for i in range(2):
        item = None
        try:
            item = parse_cron_line(
                next(cron.find_comment('{} {}'.format(SCHEDULE_MARKER, i)))
            )
        except:
            pass
        if (item is None):
            item = {
                'is_active': False,
                'time': '00:00',
                'period': 0,
            }
        schedule.append(item)

    return schedule


def cron_create_job(cron, schedule, i):
    job = cron.new(
        command='{} {}'.format(WATER_CTRL_CMD, schedule[i]['period'])
    )
    time = schedule[i]['time'].split(':')
    time.reverse()
    job.setall('{} {} * * *'.format(*time))
    job.set_comment('{} {}'.format(SCHEDULE_MARKER, i))
    job.enable(schedule[i]['is_active'])

    return job


def cron_write(schedule):
    cron = CronTab(user=True)
    new_cron = CronTab()

    # NOTE: remove* 系のメソッドを使うとどんどん空行が増えるので，
    # append して更新を行う．

    for job in cron:
        for i in range(2):
            if re.compile(
                    '{} {}'.format(re.escape(SCHEDULE_MARKER), i)
            ).search(job.comment):
                job = cron_create_job(cron, schedule, i)
                schedule[i]['append'] = True
        # NOTE: Ubuntu の場合 apt でインストールした python-crontab
        # では動かない．pip3 でインストールした python-crontab が必要．
        new_cron.append(job)

    for i in range(2):
        if ('append' not in schedule[i]):
            new_cron.append(cron_create_job(cron, schedule, i))

    new_cron.write_to_user(user=True)


def schedule_entry_str(entry):
    return '{} 開始 {} 分間 {}'.format(
        entry['time'], entry['period'], '有効' if entry['is_active'] else '無効'
    )


def schedule_str(schedule):
    return ', '.join(map(lambda entry: schedule_entry_str(entry), schedule))


def log_impl(message):
    global event_count
    with event_lock:
        sqlite.execute(
            'INSERT INTO log ' +
            'VALUES (DATETIME("now", "localtime"), ?)',
            [message]
        )
        sqlite.execute(
            'DELETE FROM log ' +
            'WHERE date <= DATETIME("now", "localtime", "-2 days")'
        )
        event_count[EVENT_TYPE_LOG] += 1


def log(message):
    threading.Thread(target=log_impl, args=(message,)).start()


def gzipped(f):
    @functools.wraps(f)
    def view_func(*args, **kwargs):
        @after_this_request
        def zipper(response):
            accept_encoding = request.headers.get('Accept-Encoding', '')

            if 'gzip' not in accept_encoding.lower():
                return response

            response.direct_passthrough = False

            if (response.status_code < 200 or
                response.status_code >= 300 or
                'Content-Encoding' in response.headers):
                return response
            gzip_buffer = BytesIO()
            gzip_file = gzip.GzipFile(mode='wb',
                                      fileobj=gzip_buffer)
            gzip_file.write(response.data)
            gzip_file.close()

            response.data = gzip_buffer.getvalue()
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Vary'] = 'Accept-Encoding'
            response.headers['Content-Length'] = len(response.data)
            response.headers['Cache-Control'] = 'max-age=31536000'

            return response

        return f(*args, **kwargs)

    return view_func


def support_jsonp(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        callback = request.args.get('callback', False)
        if callback:
            content = callback + '(' + f().data.decode() + ')'
            return current_app.response_class(
                content, mimetype='application/json'
            )
        else:
            return f(*args, **kwargs)
    return decorated_function


def get_valve_state():
    out = ''
    try:
        out = subprocess.Popen(
            ['raspi-gpio', 'get', str(CTRL_GPIO)],
            stdout=subprocess.PIPE,
            shell=False).communicate()[0].decode()
    except:
        pass

    m = re.match(r'GPIO \d+:\s+level=(\d)\s', out)
    if m:
        return {
            'state': m.group(1),
            'result': 'success'
        }
    else:
        return {
            'state': 0,
            'result': 'fail'
        }


def conv_volt_to_flow(volt):
    return volt * FLOW_MAX / 5000.0


def measure_flow_rate():
    measure_sum = 0

    time.sleep(MEASURE_IGNORE)
    while not measure_stop.is_set():
        with open(FLOW_PATH, 'r') as f:
            flow = conv_volt_to_flow(int(f.read()))
            # 最初，水圧がかかっていない期間は流量が過大にでるので，
            # 流量が最大値の9割未満の時のみ積算する
            if flow < (FLOW_MAX * 0.9):
                measure_sum += flow
            time.sleep(MEASURE_INTERVAL)
    log(
        '水やり量は約 {:.2f}L でした。'.format(
            (measure_sum / 60.0) * MEASURE_INTERVAL
        )
    )
    measure_stop.clear()
    measure_lock.release()


def set_valve_state(state):
    try:
        subprocess.Popen(
            ['raspi-gpio', 'set', str(CTRL_GPIO), 'op', ['dl', 'dh'][state]],
            stdout=subprocess.PIPE,
            shell=False).communicate()[0]
        if (state == 1):
            if measure_lock.acquire(False):
                threading.Thread(target=measure_flow_rate).start()
        else:
            measure_stop.set()
    except:
        pass

    return get_valve_state()


def get_valve_flow():
    try:
        with open(FLOW_PATH, 'r') as f:
            return {
                'flow': conv_volt_to_flow(int(f.read())),
                'result': 'success'
            }
    except:
        return {
            'flow': 0,
            'result': 'fail'
        }


@rasp_water.route('/api/valve_ctrl', methods=['GET', 'POST'])
@support_jsonp
def api_valve_ctrl():
    state = request.args.get('set', -1, type=int)
    auto = request.args.get('auto', False, type=bool)
    if state != -1:
        log(
            '{auto}で蛇口を{done}ました。'.format(
                auto='自動' if auto else '手動',
                done=['閉じ', '開き'][state % 2]
            )
        )
        return jsonify(dict({'cmd': 'set'}, **set_valve_state(state % 2)))
    else:
        return jsonify(dict({'cmd': 'get'}, **get_valve_state()))


@rasp_water.route('/api/valve_flow', methods=['GET'])
@support_jsonp
def api_valve_flow():
    return jsonify(dict({'cmd': 'get'}, **get_valve_flow()))


@rasp_water.route('/api/schedule_ctrl', methods=['GET', 'POST'])
@support_jsonp
def api_schedule_ctrl():
    state = request.args.get('set', None)
    if (state is not None):
        with schedule_lock:
            schedule = json.loads(state)
            cron_write(schedule)
            log('スケジュールを更新しました。\n({})'.format(schedule_str(schedule)))

    return jsonify(cron_read())


@rasp_water.route('/api/sysinfo', methods=['GET'])
@support_jsonp
def api_sysinfo():
    date = subprocess.Popen(
        ['date', '-R'], stdout=subprocess.PIPE
    ).communicate()[0].decode().strip()

    uptime = subprocess.Popen(
        ['uptime', '-s'], stdout=subprocess.PIPE
    ).communicate()[0].decode().strip()

    loadAverage = re.search(
        r'load average: (.+)',
        subprocess.Popen(
            ['uptime'], stdout=subprocess.PIPE
        ).communicate()[0].decode()
    ).group(1)

    return jsonify({
        'date': date,
        'uptime': uptime,
        'loadAverage': loadAverage
    })


@rasp_water.route('/api/log', methods=['GET'])
@support_jsonp
def api_log():
    cur = sqlite.cursor()
    cur.execute('SELECT * FROM log')
    return jsonify({
        'data': cur.fetchall()[::-1]
    })


@rasp_water.route('/api/event', methods=['GET'])
def api_event():
    def event_stream():
        last_count = event_count.copy()
        while True:
            time.sleep(0.3)
            for method in last_count:
                if (last_count[method] != event_count[method]):
                    yield "data: {}\n\n".format(method)
                    last_count[method] = event_count[method]

    res = Response(event_stream(), mimetype='text/event-stream')
    res.headers.add('Access-Control-Allow-Origin', '*')
    res.headers.add('Cache-Control', 'no-cache')

    return res


@rasp_water.route('/', defaults={'filename': 'index.html'})
@rasp_water.route('<path:filename>')
@gzipped
def angular(filename):
    return send_from_directory(ANGULAR_DIST_PATH, filename)
