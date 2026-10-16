#!/usr/bin/env python3
"""Turn off all AlienFX LED zones on Alienware M18x / M18xR2 (187c:0518).

Protocol from trackmastersteve/alienfx (the authoritative implementation):
- 9-byte ctrl_transfer packets (wValue=0x0202)
- Byte 0:   always 0x02
- Byte 1:   command  (RESET=0x7, SET_COLOUR=0x3, LOOP_BLOCK_END=0x4, EXECUTE=0x5)
- Byte 2:   block / reset-type
- Bytes 3-5: zone (3 bytes: zone>>16, zone>>8, zone&0xff)
- Bytes 6-7: color as 4-bit nibbles: byte6=((r&0xf)<<4)|(g&0xf)  byte7=(b&0xf)<<4

RESET_ALL_LIGHTS_OFF = 3
"""
import sys, time, os
sys.path.insert(0, os.path.expanduser("~scorpio/.local/lib/python3.10/site-packages"))
import usb.core, usb.util

VID, PID = 0x187C, 0x0518

# Zone codes from controller_m18xr2.py
ZONES = {
    "Right Keyboard":        0x0001,
    "Middle Right Keyboard": 0x0002,
    "Middle Left Keyboard":  0x0004,
    "Left Keyboard":         0x0008,
    "Right Speaker":         0x0020,
    "Left Speaker":          0x0040,
    "Alien Head":            0x0080,
    "Logo":                  0x0100,
    "Touchpad":              0x0200,
    "Media Bar":             0x0800,
    "Power Button":          0x2000,
    "HDD LEDs":              0x4000,
}

dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    print("Device not found. Try sudo."); sys.exit(1)

try:
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
    dev.set_configuration()
    usb.util.claim_interface(dev, 0)
except Exception as e:
    print(f"Setup warning: {e}")

def ctrl_write(pkt):
    """Send 9-byte packet via HID Set_Report control transfer."""
    p = list(pkt)[:9] + [0] * (9 - len(list(pkt)[:9]))
    try:
        dev.ctrl_transfer(0x21, 0x09, 0x0202, 0x0000, p, timeout=1000)
        return True
    except Exception as e:
        print(f"  write error: {e}")
        return False

def ctrl_read():
    """Read 9-byte status via HID Get_Report control transfer."""
    try:
        return list(dev.ctrl_transfer(0xa1, 0x01, 0x0101, 0x0000, 9, timeout=500))
    except Exception:
        return None

def wait_ready(retries=50, delay=0.03):
    ctrl_write([0x02, 0x06])   # GET_STATUS
    for _ in range(retries):
        r = ctrl_read()
        if r is None:
            return
        if r[1] != 0x11:       # 0x11 = BUSY
            return
        time.sleep(delay)
        ctrl_write([0x02, 0x06])

def zone_bytes(zone):
    return [(zone & 0xff0000) >> 16, (zone & 0xff00) >> 8, zone & 0xff]

def pack_colour(r, g, b):
    """4-bit nibble color encoding for old controllers."""
    return [((r & 0xf) << 4) | (g & 0xf), (b & 0xf) << 4]

# ── Protocol sequence ─────────────────────────────────────────────────────────
print("Step 1: RESET all-lights-off")
ctrl_write([0x02, 0x07, 3])   # RESET, type=3 (RESET_ALL_LIGHTS_OFF)
wait_ready()

print("Step 2: SET_COLOUR black for each zone")
for name, zone in ZONES.items():
    pkt = [0x02, 0x03, 0x00] + zone_bytes(zone) + pack_colour(0, 0, 0) + [0x00]
    ok = ctrl_write(pkt)
    print(f"  {'OK' if ok else 'FAIL'} {name}  zone={zone:#06x}")
    time.sleep(0.02)

print("Step 3: LOOP_BLOCK_END")
ctrl_write([0x02, 0x04])
time.sleep(0.05)

print("Step 4: TRANSMIT_EXECUTE")
ctrl_write([0x02, 0x05])
wait_ready()

r = ctrl_read()
status = r[1] if r and len(r) > 1 else None
print(f"Final status byte: {hex(status) if status else 'none'}")
print("Done.")

usb.util.release_interface(dev, 0)
usb.util.dispose_resources(dev)
