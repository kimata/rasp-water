import pytz
import datetime
import schedule

print("datetime.now() = {date}".format(date=datetime.datetime.now()))
print("datetime.now(JST) = {date}".format(date=datetime.datetime.now(pytz.timezone("Asia/Tokyo"))))

schedule.clear()

job = schedule.every().day.at("23:30").do(lambda: True)
job = schedule.every().day.at("23:30", pytz.timezone("Asia/Tokyo")).do(lambda: True)

for i, job in enumerate(schedule.get_jobs()):
    print("schedule [{i}]: {next_run}".format(i=i, next_run=job.next_run))


print("Time to next jobs = {idle:.1f} sec".format(idle=schedule.idle_seconds()))


# TIMEZONE = datetime.timezone(datetime.timedelta(hours=int(TIMEZONE_OFFSET)), "JST")

# logging.debug(
#     "datetime.now()                 = {date}".format(date=datetime.datetime.now()),
# )
# logging.debug("datetime.now(JST)              = {date}".format(date=datetime.datetime.now(TIMEZONE)))

# schedule.clear()
# job_time_str = time_str(time_test(1))
# logging.debug("set schedule at {time}".format(time=job_time_str))

# job_add = schedule.every().day.at(job_time_str, TIMEZONE_PYTZ).do(lambda: True)

# for i, job in enumerate(schedule.get_jobs()):
#     logging.debug("Current schedule [{i}]: {next_run}".format(i=i, next_run=job.next_run))

# idle_sec = schedule.idle_seconds()
# logging.error("Time to next jobs is {idle:.1f} sec".format(idle=idle_sec))
# logging.debug("Next run is {time}".format(time=job_add.next_run))
