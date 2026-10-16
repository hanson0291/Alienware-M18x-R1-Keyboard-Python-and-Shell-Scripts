#!/bin/bash
# Keeps AlienFX LEDs off: runs leds_off.py at boot, then again after every resume.
# Run by the systemd user service alienfx-leds-off.service.
SCRIPT=/home/scorpio/Desktop/KeyboardCode/leds_off.py

leds_off() {
    # The USB controller can take a few seconds to appear after boot/resume
    for _ in $(seq 1 15); do
        /usr/bin/python3 "$SCRIPT" && return 0
        sleep 2
    done
    echo "leds_off.py failed after retries" >&2
}

leds_off

# logind emits PrepareForSleep(false) when the machine wakes up
gdbus monitor --system --dest org.freedesktop.login1 --object-path /org/freedesktop/login1 |
while read -r line; do
    if [[ $line == *PrepareForSleep*false* ]]; then
        sleep 2
        leds_off
    fi
done
