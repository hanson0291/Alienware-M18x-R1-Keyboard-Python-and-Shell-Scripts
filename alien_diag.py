#!/usr/bin/env python3
"""Deep probe: HID descriptor + raw read + packet bruteforce."""
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

VID, PID = 0x187C, 0x0518

dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    print("Device not found."); sys.exit(1)

try:
    if dev.is_kernel_driver_active(0):
        dev.detach_kernel_driver(0)
    dev.set_configuration()
    usb.util.claim_interface(dev, 0)
except Exception as e:
    print(f"Setup warning: {e}")

cfg    = dev.get_active_configuration()
ep_out = usb.util.find_descriptor(cfg[(0,0)], custom_match=lambda e:
    usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
ep_in  = usb.util.find_descriptor(cfg[(0,0)], custom_match=lambda e:
    usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)

# ── 1. Read HID report descriptor ────────────────────────────────────────────
print("=== HID Report Descriptor ===")
try:
    desc = dev.ctrl_transfer(0x81, 0x06, 0x2200, 0x0000, 256, timeout=500)
    print(f"  Length: {len(desc)} bytes")
    print(f"  Hex: {' '.join(f'{b:02x}' for b in desc)}")
except Exception as e:
    print(f"  Error: {e}")

# ── 2. Read device descriptor details ────────────────────────────────────────
print("\n=== Full USB descriptor (lsusb -v) ===")
import subprocess
try:
    out = subprocess.check_output(
        ["lsusb", "-v", "-d", f"{VID:#06x}:{PID:#06x}"],
        stderr=subprocess.DEVNULL, text=True)
    print(out[:3000])
except Exception as e:
    print(f"  lsusb error: {e}")

# ── 3. Listen on IN endpoint (unprompted) ─────────────────────────────────────
print("\n=== Unsolicited IN reads (3 sec) ===")
start = time.time()
while time.time() - start < 3.0:
    try:
        data = ep_in.read(ep_in.wMaxPacketSize, timeout=100)
        print(f"  Got: {[hex(x) for x in data]}")
    except usb.core.USBTimeoutError:
        pass
    except Exception as e:
        print(f"  read err: {e}")
        break
print("  (done listening)")

# ── 4. Send RESET and immediately read response ───────────────────────────────
print("\n=== Send bare RESET packets, read response ===")
test_packets = [
    ("9-byte [02 03 00...]",  bytes([0x02, 0x03] + [0]*7)),
    ("10-byte [02 03 00...]", bytes([0x02, 0x03] + [0]*8)),
    ("10-byte [02 07 03...]", bytes([0x02, 0x07, 0x03] + [0]*7)),
    ("10-byte [00 02 03...]", bytes([0x00, 0x02, 0x03] + [0]*7)),  # report-ID prefix
    ("10-byte [ff ff ff...]", bytes([0xff]*10)),
    ("10-byte [01 00...]",    bytes([0x01] + [0]*9)),
]

for label, pkt in test_packets:
    try:
        ep_out.write(pkt, timeout=500)
        sent = "OK"
    except Exception as e:
        sent = f"ERR:{e}"
    time.sleep(0.05)
    try:
        resp = ep_in.read(ep_in.wMaxPacketSize, timeout=300)
        resp_str = ' '.join(f'{b:02x}' for b in resp)
    except Exception:
        resp_str = "none"
    print(f"  [{label}] sent={sent}  resp={resp_str}")
    time.sleep(0.1)

usb.util.release_interface(dev, 0)
usb.util.dispose_resources(dev)
print("\nDone.")
