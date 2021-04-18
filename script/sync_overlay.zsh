#!/usr/bin/zsh

if [ -e /media/root-ro ]; then
    sudo mount -o remount,rw /media/root-ro
    sudo cp -f /var/spool/cron/crontabs/root /media/root-ro/var/spool/cron/crontabs/root
    sudo mount -o remount,ro /media/root-ro
fi
