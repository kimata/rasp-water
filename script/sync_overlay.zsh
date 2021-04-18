#!/usr/bin/zsh

FILE_LIST=(
    /var/spool/cron/crontabs/root
    /var/log/rasp-water.db
)

if [ -e /media/root-ro ]; then
    # Dummy read
    for file in $FILE_LIST; do
        cat $file
    done

    sudo mount -o remount,rw /media/root-ro

    for file in $FILE_LIST; do
        sudo cp -f $file /media/root-ro$file
    done

    sudo mount -o remount,ro /media/root-ro
fi
