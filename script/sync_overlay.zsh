#!/usr/bin/zsh

file_path=$1

if [ -e /media/root-ro ]; then
    sudo mount -o remount,rw /media/root-ro
    sudo cp -f $file_path /media/root-ro$file_path
    sudo mount -o remount,ro /media/root-ro
fi
