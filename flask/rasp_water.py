#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import (
    request, jsonify, current_app, Response, send_from_directory,
    after_this_request,
    Blueprint
)

from functools import wraps
import re
import socket
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
from fluent import sender

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

from soilwet_check import is_soil_wet
from forecast_check import is_rain_forecast

# import pprint

# 電磁弁が接続されている GPIO
CTRL_GPIO = 18

# 流量計をモニタする ADC の設定 (ADS1015 のドライバ ti_ads1015 が公開)
SCALE_PATH = '/sys/bus/iio/devices/iio:device0/in_voltage0_scale'
SCALE_VALUE = 2
# 流量計のアナログ出力値 (ADS1015 のドライバ ti_ads1015 が公開)
FLOW_PATH = '/sys/bus/iio/devices/iio:device0/in_voltage0_raw'

# 流量計が計れる最大流量
FLOW_MAX = 12
# 流量計の積算から除外する期間[秒]
MEASURE_IGNORE = 5
# 流量計を積算する間隔[秒]
MEASURE_INTERVAL = 0.3
# バルブを止めてからも水が出流れていると想定される時間[秒]
TAIL_SEC = 60

APP_PATH = '/rasp-water'
ANGULAR_DIST_PATH = '../dist/rasp-water'

FLUENTD_HOST = 'columbia.green-rabbit.net'

EVENT_TYPE_MANUAL = 'manual'
EVENT_TYPE_LOG = 'log'
EVENT_TYPE_SCHEDULE = 'schedule'

event_count = {
    EVENT_TYPE_MANUAL: 0,
    EVENT_TYPE_LOG: 0,
    EVENT_TYPE_SCHEDULE: 0,
}

SCHEDULE_MARKER = 'WATER SCHEDULE'
WATER_CTRL_CMD = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'script', 'water_ctrl.py')
)
SYNC_OVERLAY_CMD = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'script', 'sync_overlay.zsh')
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
ctrl_lock = threading.Lock()
period_lock = threading.Lock()
measure_stop = threading.Event()
ctrl_period = 0

WDAY_STR = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
WDAY_STR_JA = ['日', '月', '火', '水', '木', '金', '土']

def wday_str_list(wday_list, lang='en'):
    wday_str = WDAY_STR
    if (lang == 'ja'):
        wday_str = WDAY_STR_JA

    return map(lambda i: wday_str[i], (i for i in range(len(wday_list)) if wday_list[i]))


def parse_cron_line(line):
    match = re.compile(
        '^(#?)\s*(\d{{1,2}})\s+(\d{{1,2}})\s.+\s(\S+)\s+{}\s+(\d+)'.format(
            re.escape(WATER_CTRL_CMD)
        )
    ).search(str(line))

    if match:
        mg = match.groups()
        wday_str_list = mg[3].split(',')

        return {
            'is_active': mg[0] == '',
            'time': '{:02}:{:02}'.format(int(mg[2]), int(mg[1])),
            'period': int(mg[4]),
            'wday': list(map(lambda str: str in wday_str_list, WDAY_STR)),
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
                'wday': [True] * 7,
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
    job.dow.on(*(wday_str_list(schedule[i]['wday'])))
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

    # すぐに反映されるよう，明示的にリロード
    subprocess.check_call(['sudo', '/etc/init.d/cron', 'restart'])
    # Read only にしてある root にも反映
    subprocess.check_call([SYNC_OVERLAY_CMD])

    with event_lock:
        event_count[EVENT_TYPE_SCHEDULE] += 1


def schedule_entry_str(entry):
    return '{} 開始 {} 分間 {}'.format(
        entry['time'], entry['period'],
        ','.join(wday_str_list(entry['wday'], 'ja'))
    )


def schedule_str(schedule):
    str = []
    for entry in schedule:
        if not entry['is_active']:
            continue
        str.append(schedule_entry_str(entry))

    return ",\n ".join(str)


def gpio_set_state(pin, state):
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, state)


def gpio_get_state(pin):
    return GPIO.input(pin)


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
            'WHERE date <= DATETIME("now", "localtime", "-60 days")'
        )
        event_count[EVENT_TYPE_LOG] += 1


def log(message):
    threading.Thread(target=log_impl, args=(message,)).start()


def alert(message):
    subprocess.call(
        'echo "{}" | mail -s "rasp-water アラート" root'.format(message),
        shell=True
    )


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


def get_valve_state(is_pending=False):
    try:
        state = gpio_get_state(CTRL_GPIO)
        return {
            'state': 1 if (state == GPIO.HIGH) else 0,
            'period': ctrl_period,
            'pending': is_pending,
            'result': 'success'
        }
    except:
        return {
            'state': 0,
            'period': ctrl_period,
            'result': 'fail'
        }


def conv_rawadc_to_flow(adc):
    return (adc * SCALE_VALUE * FLOW_MAX) / 5000.0


def post_fluentd(start_time, time_delta, measure_list):
    fluentd = sender.FluentSender('sensor', host=FLUENTD_HOST)

    hostname = os.uname()[1]
    measure_time = start_time
    post_time = int(measure_time)
    sec_sum = 0
    for measure in measure_list:
        if (int(measure_time) != post_time):
            # NOTE: 秒単位で積算してから Fluentd に投げる
            fluentd.emit_with_time(
                'water', post_time, {'hostname': hostname, 'water': sec_sum }
            )
            post_time = int(measure_time)
            sec_sum = 0
        sec_sum += (measure / 60.0) * time_delta
        measure_time += time_delta
    fluentd.emit_with_time(
        'water', post_time, {'hostname': hostname, 'water': sec_sum }
    )
    fluentd.close()


def measure_flow_rate():
    start_time = time.time()
    measure_list = []

    if not measure_lock.acquire(True, 0.5):
        return

    time.sleep(MEASURE_IGNORE)
    while not measure_stop.is_set():
        with open(FLOW_PATH, 'r') as f:
            flow = conv_rawadc_to_flow(int(f.read()))
            measure_list.append(flow)
            time.sleep(MEASURE_INTERVAL)

    stop_time = time.time()
    while True:
        with open(FLOW_PATH, 'r') as f:
            flow = conv_rawadc_to_flow(int(f.read()))
            if flow < 0.1:
                break
            measure_list.append(flow)
            time.sleep(MEASURE_INTERVAL)

        if (time.time() - stop_time) > TAIL_SEC:
            alert('バルブを閉めても水が流れ続けています．')
            break

    measure_sum = sum(measure_list)
    time_delta = (stop_time - start_time) / (len(measure_list) - 1)
    water_sum = (measure_sum / 60.0) * time_delta
    log('水やり量は約 {:.2f}L でした。'.format(water_sum))

    if ((stop_time - start_time) > 30) and (water_sum < 1):
        alert('元栓が閉まっている可能性があります．(時間: {:.0f}sec, 合計: {:.2f}L)'.format(
            stop_time - start_time, water_sum
        ));

    post_fluentd(start_time, time_delta, measure_list)

    measure_stop.clear()
    measure_lock.release()


def set_valve_state(state, auto, host=''):
    with ctrl_lock:
        if (state == 1) and auto:
            if is_soil_wet():
                log('雨が降ったため、自動での水やりを見合わせました。')
                return get_valve_state(True)
            elif is_rain_forecast():
                log('雨が降る予報があるため、自動での水やりを見合わせました。')
                return get_valve_state(True)

        cur_state = get_valve_state()['state']

        try:
            gpio_set_state(CTRL_GPIO, GPIO.HIGH if (state == 1) else GPIO.LOW)
            if (state == 1):
                threading.Thread(target=measure_flow_rate).start()
            elif (cur_state == 1):
                measure_stop.set()
        except:
            alert('電磁弁の制御に失敗しました．')

        if state != cur_state:
            log(
                '{auto}で蛇口を{done}ました。{by}'.format(
                    auto='自動' if auto else '手動',
                    done=['閉じ', '開き'][state % 2],
                    by='(by {})'.format(host) if host != '' else ''
                )
            )

        return get_valve_state()


def get_valve_flow():
    try:
        with open(FLOW_PATH, 'r') as f:
            return {
                'flow': conv_rawadc_to_flow(int(f.read())),
                'result': 'success'
            }
    except:
        return {
            'flow': 0,
            'result': 'fail'
        }


def manual_ctrl_worker():
    global ctrl_period

    while ctrl_period != 0:
        time.sleep(60)
        with period_lock:
            if (ctrl_period != 0):
                ctrl_period -= 1
        with event_lock:
            event_count[EVENT_TYPE_MANUAL] += 1

    set_valve_state(0, False)


def remote_host(request):
    try:
        return socket.gethostbyaddr(request.remote_addr)[0]
    except:
        return request.remote_addr


@rasp_water.route('/api/valve_ctrl', methods=['GET', 'POST'])
@support_jsonp
def api_valve_ctrl():
    global ctrl_period
    is_worker_start = False

    state = request.args.get('set', -1, type=int)
    period = request.args.get('period',0, type=int)
    auto = request.args.get('auto', False, type=bool)
    if state != -1:
        with period_lock:
            if state == 1:
                is_worker_start = ctrl_period != 0
                ctrl_period = period
            else:
                ctrl_period = 0

        # NOTE: バルブの制御は ctrl_period の変更後にしないと UI 表示が一瞬おかしくなる．
        result = set_valve_state(state % 2, auto, remote_host(request))

        if (state == 1) and (period != 0) and (not is_worker_start):
            threading.Thread(target=manual_ctrl_worker).start()

        return jsonify(dict({'cmd': 'set'}, **result))
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
            host=remote_host(request)
            log('スケジュールを更新しました。\n({schedule} {by})'.format(
                schedule=schedule_str(schedule),
                by='by {}'.format(host) if host != '' else ''
            ))

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


@rasp_water.route('/api/log_view', methods=['GET'])
@support_jsonp
def api_log_view():
    cur = sqlite.cursor()
    cur.execute('SELECT * FROM log')
    return jsonify({
        'data': cur.fetchall()[::-1]
    })


@rasp_water.route('/api/log_clear', methods=['GET'])
@support_jsonp
def api_log_clear():
    with event_lock:
        cur = sqlite.cursor()
        cur.execute('DELETE FROM log')
    log('ログがクリアされました。')

    return jsonify({
        'result': 'success'
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
@rasp_water.route('/<path:filename>')
@gzipped
def angular(filename):
    return send_from_directory(ANGULAR_DIST_PATH, filename)

print('GPIO を L に初期化します...');
GPIO.setup(CTRL_GPIO, GPIO.OUT)
gpio_set_state(CTRL_GPIO, GPIO.LOW)

print('ADC の設定を行います...');
with open(SCALE_PATH, 'w') as f:
    f.write(str(SCALE_VALUE))
