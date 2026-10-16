#!/usr/bin/env python3
"""
Probe the AlienFX 187c:0518 device - try different protocol approaches
and report what works.
"""
import os
import site
import sys
import time


def ensure_pyusb():
    try:
        import usb.core  # noqa: F401
        import usb.util  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    candidates = []
    user_site = site.getusersitepackages()
    if isinstance(user_site, str):
        candidates.append(user_site)
    else:
        candidates.extend(user_site)
    candidates.append(
        os.path.join(
            os.path.expanduser("~"),
            ".local",
            "lib",
            f"python{sys.version_info.major}.{sys.version_info.minor}",
            "site-packages",
        )
    )

    for path in candidates:
        if path and path not in sys.path and os.path.isdir(path):
            sys.path.insert(0, path)


ensure_pyusb()
import usb.core
import usb.util

VID, PID = 0x187c, 0x0518

dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    print("Device not found"); sys.exit(1)
print(f"Found: {dev}")

try:
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
        print("Detached kernel driver")
    dev.set_configuration()
except Exception as e:
    print(f"Config error: {e}")

cfg  = dev.get_active_configuration()
intf = cfg[(0, 0)]
ep_out = usb.util.find_descriptor(intf, custom_match=lambda e:
    usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
ep_in  = usb.util.find_descriptor(intf, custom_match=lambda e:
    usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)

print(f"EP OUT: {ep_out.bEndpointAddress:#x}  maxPkt={ep_out.wMaxPacketSize}")
print(f"EP IN:  {ep_in.bEndpointAddress:#x}   maxPkt={ep_in.wMaxPacketSize}")

def ctrl(packet):
    """Send via HID Set_Report (ctrl_transfer)."""
    try:
        n = dev.ctrl_transfer(0x21, 0x09, 0x0202, 0x00, packet, timeout=1000)
        return True, n
    except Exception as e:
        return False, str(e)

def intr(packet):
    """Send via interrupt OUT endpoint."""
    try:
        n = ep_out.write(bytes(packet), timeout=1000)
        return True, n
    except Exception as e:
        return False, str(e)

def read_status():
    try:
        data = dev.ctrl_transfer(0xA1, 0x01, 0x0101, 0x00, 9, timeout=500)
        return list(data)
    except Exception as e:
        return [f"err: {e}"]

# Packets to try
RESET   = [0x02, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
LSTART  = [0x01, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
# SET pure red on zone 0x0001 (right keyboard)
RED_Z1  = [0x03, 0x00, 0x01, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00]
# SET pure red on ALL zones bitmask (try 0xFFFF)
RED_ALL = [0x03, 0xFF, 0xFF, 0x00, 0xFF, 0x00, 0x00, 0x00, 0x00]
LEND    = [0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
EXEC    = [0x21, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
EXEC2   = [0x28, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

print("\n--- Attempt 1: ctrl_transfer with RESET sequence ---")
for name, pkt in [("RESET", RESET), ("LSTART", LSTART), ("RED_Z1", RED_Z1),
                   ("LEND", LEND), ("EXEC", EXEC)]:
    ok, r = ctrl(pkt)
    print(f"  ctrl {name}: ok={ok}  result={r}")
    time.sleep(0.05)
time.sleep(0.3)
print(f"  status: {read_status()}")

time.sleep(1)
print("\n--- Attempt 2: interrupt write with EXEC2 (0x28) ---")
for name, pkt in [("RESET", RESET), ("LSTART", LSTART), ("RED_ALL", RED_ALL),
                   ("LEND", LEND), ("EXEC2", EXEC2)]:
    ok, r = intr(pkt)
    print(f"  intr  {name}: ok={ok}  result={r}")
    time.sleep(0.05)
time.sleep(0.3)
print(f"  status: {read_status()}")

print("\nDone. Did any zone turn red? Check the keyboard.")
