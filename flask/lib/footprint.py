#!/usr/bin/env python3
import pathlib
import time


def exists(path):
    return path.exists()


def update(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pathlib.Path.open(path, mode="w") as f:
        f.write(str(time.time()))


def elapsed(path):
    diff_sec = time.time()
    if not path.exists():
        return diff_sec

    with pathlib.Path.open(path) as f:
        diff_sec -= float(f.read())

    return diff_sec


def clear(path):
    path.unlink(missing_ok=True)
