#!/usr/bin/zsh

path=$1

if [ -e /media/root-ro ]; then
    sudo mount -o remount,rw /media/root-ro
    sudo cp -f $path /media/root-ro$path
    sudo mount -o remount,ro /media/root-ro
fi
