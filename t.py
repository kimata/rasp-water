# Standard Library
import datetime
import time
from multiprocessing.pool import ThreadPool

# Third Party Library
import schedule

nowtime = str(datetime.datetime.now())


def schedule_worker():
    schedule.clear()

    def job(t):
        print("I'm working...", str(datetime.datetime.now()), t)

    schedule_setting = {"wday": [True, True, True, True, True, True, True]}

    for i in ["13:19"]:
        if schedule_setting["wday"][0]:
            schedule.every().sunday.at(i).do(job, i)
        if schedule_setting["wday"][1]:
            schedule.every().monday.at(i).do(job, i)
        if schedule_setting["wday"][2]:
            schedule.every().monday.at(i).do(job, i)
        if schedule_setting["wday"][3]:
            schedule.every().monday.at(i).do(job, i)
        if schedule_setting["wday"][4]:
            schedule.every().monday.at(i).do(job, i)
        if schedule_setting["wday"][5]:
            schedule.every().monday.at(i).do(job, i)
        if schedule_setting["wday"][6]:
            schedule.every().monday.at(i).do(job, i)

        # schedule.every().monday.at(i).do(job, i)
        # schedule.every().tuesday.at(i).do(job, i)
        # schedule.every().wednesday.at(i).do(job, i)
        # schedule.every().thursday.at(i).do(job, i)
        # schedule.every().friday.at(i).do(job, i)

    for job in schedule.get_jobs():
        print("Next run: {next_run}".format(next_run=job.next_run))


pool = ThreadPool(processes=1)
result = pool.apply_async(schedule_worker)
result.get()

# while True:
#     schedule.run_pending()
#     time.sleep(30)
