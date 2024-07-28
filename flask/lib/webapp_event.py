#!/usr/bin/env python3
import logging
import multiprocessing
import threading
import time
import traceback
from enum import Enum

from webapp_config import APP_URL_PREFIX

from flask import Blueprint, Response, request, stream_with_context

blueprint = Blueprint("webapp-event", __name__, url_prefix=APP_URL_PREFIX)


class EVENT_TYPE(Enum):  # noqa: N801
    CONTROL = "control"
    SCHEDULE = "schedule"
    LOG = "log"


# NOTE: サイズは上の Enum の個数+1 にしておく
event_count = multiprocessing.Array("i", 4)

is_stop_watch = False


def notify_watch_impl(queue):
    global is_stop_watch

    logging.info("Start notify watch thread")

    while True:
        if is_stop_watch:
            break
        try:
            if not queue.empty():
                notify_event(queue.get())
            time.sleep(0.1)
        except OverflowError:  # pragma: no cover
            # NOTE: テストする際，freezer 使って日付をいじるとこの例外が発生する
            logging.debug(traceback.format_exc())

    logging.info("Stop notify watch thread")


def notify_watch(queue):
    global is_stop_watch  # noqa: PLW0603

    is_stop_watch = False
    threading.Thread(target=notify_watch_impl, args=(queue,)).start()


def stop_watch():
    global is_stop_watch  # noqa: PLW0603

    is_stop_watch = True


def event_index(event_type):
    if event_type == EVENT_TYPE.CONTROL:
        return 0
    elif event_type == EVENT_TYPE.SCHEDULE:
        return 1
    elif event_type == EVENT_TYPE.LOG:
        return 2
    else:  # pragma: no cover
        return 3


def notify_event(event_type):
    global event_count
    event_count[event_index(event_type)] += 1


@blueprint.route("/api/event", methods=["GET"])
def api_event():
    count = request.args.get("count", 0, type=int)

    def event_stream():
        global event_count

        last_count = event_count[:]

        i = 0
        j = 0
        while True:
            time.sleep(0.5)
            for event_type in EVENT_TYPE.__members__.values():
                index = event_index(event_type)

                if last_count[index] != event_count[index]:
                    logging.debug("notify event: %s", event_type.value)
                    yield f"data: {event_type.value}\n\n"
                    last_count[index] = event_count[index]

                    i += 1
                    if i == count:
                        return

            # NOTE: クライアントが切断された時にソケットを解放するため，定期的に yield を呼ぶ
            j += 1
            if j == 100:
                yield "data: dummy\n\n"
                j = 0

    res = Response(stream_with_context(event_stream()), mimetype="text/event-stream")
    res.headers.add("Access-Control-Allow-Origin", "*")
    res.headers.add("Cache-Control", "no-cache")
    res.headers.add("X-Accel-Buffering", "no")

    return res
