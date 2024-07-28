#!/usr/bin/env python3
import bz2
import io
import logging
import logging.handlers
import os
import pathlib

import coloredlogs

MAX_SIZE = 10 * 1024 * 1024
ROTATE_COUNT = 10

LOG_FORMAT = "{name} %(asctime)s %(levelname)s [%(filename)s:%(lineno)s %(funcName)s] %(message)s"


def log_formatter(name):
    return logging.Formatter(fmt=LOG_FORMAT.format(name=name), datefmt="%Y-%m-%d %H:%M:%S")


class GZipRotator:
    @staticmethod
    def namer(name):
        return name + ".bz2"

    @staticmethod
    def rotator(source, dest):
        with pathlib.Path.open(source, "rb") as fs, bz2.open(dest, "wb") as fd:
            fd.writelines(fs)
        pathlib.Path.unlink(source)


def init(name, level=logging.WARNING, log_dir_path=None, log_queue=None, is_str_log=False):
    if os.environ.get("NO_COLORED_LOGS", "false") != "true":
        coloredlogs.install(fmt=LOG_FORMAT.format(name=name), level=level)

    if log_dir_path is not None:
        log_dir_path = pathlib.Path(log_dir_path)
        log_dir_path.mkdir(exist_ok=True, parents=True)

        log_file_path = str(log_dir_path / f"{name}.log")

        logging.info("Log to %s", log_file_path)

        logger = logging.getLogger()
        log_handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            encoding="utf8",
            maxBytes=MAX_SIZE,
            backupCount=ROTATE_COUNT,
        )
        log_handler.formatter = log_formatter(name)
        log_handler.namer = GZipRotator.namer
        log_handler.rotator = GZipRotator.rotator

        logger.addHandler(log_handler)

    if log_queue is not None:
        handler = logging.handlers.QueueHandler(log_queue)
        logging.getLogger().addHandler(handler)

    if is_str_log:
        str_io = io.StringIO()
        handler = logging.StreamHandler(str_io)
        handler.formatter = log_formatter(name)
        logging.getLogger().addHandler(handler)

        return str_io

    return None


if __name__ == "__main__":
    init("test")
    logging.info("Test")
