#!/usr/bin/env python3
"""AlienFX LED controller for Alienware M18x R1/R2 (187c:0518).

Usage:
  sudo python3 alienfw_ctrl.py <zone> <color>

Zones:
  all            All zones
  keyboard       All 4 keyboard zones
  left           Left keyboard (includes macro keys M1-M18)
  middle-left    Middle-left keyboard
  middle-right   Middle-right keyboard
  right          Right keyboard + numpad
  alien-head     Alien head logo
  logo           Alienware logo
  touchpad       Touchpad
  media-bar      Media bar
  power          Power button
  speakers       Both speakers
  left-speaker   Left speaker
  right-speaker  Right speaker
  hdd            HDD LEDs

Colors:
  off, red, green, blue, yellow, white, cyan, magenta, orange, purple
  or R,G,B  (nibble values 0-15, e.g. 15,0,0 for red)
"""
import os
import site
import sys
import time
from dataclasses import dataclass


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

    try:
        import usb.core  # noqa: F401
        import usb.util  # noqa: F401
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "PyUSB is not installed for this Python interpreter. "
            "Install it for python3, then rerun this script."
        ) from exc


ensure_pyusb()
import usb.core
import usb.util

VID, PID = 0x187C, 0x0518
INPUT_REPORT_ID = 0x01
OUTPUT_REPORT_ID = 0x02
REPORT_DATA_LEN = 8
REPORT_WIRE_LEN = REPORT_DATA_LEN + 1
USB_TIMEOUT_MS = 1000

# Zone codes (M18x R2 codes; R1 uses same PID 0x0518)
ZONE_MAP = {
    "right":         0x0001,
    "middle-right":  0x0002,
    "middle-left":   0x0004,
    "left":          0x0008,
    "right-speaker": 0x0020,
    "left-speaker":  0x0040,
    "alien-head":    0x0080,
    "logo":          0x0100,
    "touchpad":      0x0200,
    "media-bar":     0x0800,
    "power":         0x2000,
    "hdd":           0x4000,
}

ZONE_GROUPS = {
    "speakers": ["left-speaker", "right-speaker"],
    "keyboard": ["left", "middle-left", "middle-right", "right"],
    "all":      list(ZONE_MAP.keys()),
}

# Colors as 4-bit nibbles (0-15 per channel)
COLOR_MAP = {
    "off":     (0,  0,  0),
    "red":     (15, 0,  0),
    "green":   (0,  15, 0),
    "blue":    (0,  0,  15),
    "yellow":  (15, 15, 0),
    "white":   (15, 15, 15),
    "cyan":    (0,  15, 15),
    "magenta": (15, 0,  15),
    "orange":  (15, 6,  0),
    "purple":  (8,  0,  15),
}


@dataclass
class DeviceConnection:
    dev: object
    interface_number: int
    ep_out: object
    detached_kernel_driver: bool = False


def parse_rgb_nibbles(color_arg):
    if color_arg in COLOR_MAP:
        return COLOR_MAP[color_arg]

    parts = [part.strip() for part in color_arg.split(",")]
    if len(parts) != 3:
        raise ValueError("Custom colors must be in R,G,B format.")

    try:
        rgb = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("Custom colors must use integers from 0 to 15.") from exc

    if any(value < 0 or value > 15 for value in rgb):
        raise ValueError("Custom colors must use integers from 0 to 15.")

    return rgb


def build_output_report(payload):
    if len(payload) > REPORT_DATA_LEN:
        raise ValueError(f"AlienFX payload must be at most {REPORT_DATA_LEN} bytes.")
    if any(not 0 <= int(byte) <= 0xFF for byte in payload):
        raise ValueError("AlienFX payload bytes must be in the range 0..255.")
    return bytes([OUTPUT_REPORT_ID, *payload, *([0x00] * (REPORT_DATA_LEN - len(payload)))])

def parse_args():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    zone_arg  = args[0].lower()
    color_arg = args[1].lower()

    # Resolve zones
    if zone_arg in ZONE_GROUPS:
        zones = [ZONE_MAP[z] for z in ZONE_GROUPS[zone_arg]]
    elif zone_arg in ZONE_MAP:
        zones = [ZONE_MAP[zone_arg]]
    else:
        print(f"Unknown zone: {zone_arg}")
        sys.exit(1)

    try:
        r, g, b = parse_rgb_nibbles(color_arg)
    except ValueError as exc:
        print(f"Invalid color '{color_arg}': {exc}")
        sys.exit(1)

    return zones, r, g, b


def connect():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        print("ERROR: Device not found. Run with sudo."); sys.exit(1)
    detached = False
    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
            detached = True
    except (NotImplementedError, usb.core.USBError):
        pass
    try:
        dev.set_configuration()
        usb.util.claim_interface(dev, 0)
    except Exception as e:
        print(f"Setup warning: {e}")
    cfg = dev.get_active_configuration()
    intf = cfg[(0, 0)]
    ep_out = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT,
    )
    return DeviceConnection(
        dev=dev,
        interface_number=intf.bInterfaceNumber,
        ep_out=ep_out,
        detached_kernel_driver=detached,
    )


def close(conn):
    try:
        usb.util.release_interface(conn.dev, conn.interface_number)
    except Exception:
        pass
    if conn.detached_kernel_driver:
        try:
            conn.dev.attach_kernel_driver(conn.interface_number)
        except Exception:
            pass
    usb.util.dispose_resources(conn.dev)


def write_report(conn, payload):
    report = build_output_report(payload)
    transport = os.environ.get("ALIENFW_TRANSPORT", "auto").strip().lower() or "auto"
    errors = []

    if transport not in {"auto", "interrupt", "control"}:
        raise ValueError("ALIENFW_TRANSPORT must be auto, interrupt, or control.")

    if transport in {"auto", "interrupt"} and conn.ep_out is not None:
        try:
            written = conn.ep_out.write(report, timeout=USB_TIMEOUT_MS)
            if written != len(report):
                raise usb.core.USBError(f"short interrupt write ({written}/{len(report)})")
            return
        except Exception as exc:
            errors.append(f"interrupt: {exc}")
            if transport == "interrupt":
                raise

    if transport in {"auto", "control"}:
        try:
            conn.dev.ctrl_transfer(
                0x21,
                0x09,
                (0x02 << 8) | OUTPUT_REPORT_ID,
                conn.interface_number,
                report,
                timeout=USB_TIMEOUT_MS,
            )
            return
        except Exception as exc:
            errors.append(f"control: {exc}")
            raise RuntimeError(" ; ".join(errors)) from exc

    raise RuntimeError("No usable AlienFX write transport was available.")


def read_report(conn):
    try:
        data = conn.dev.ctrl_transfer(
            0xA1,
            0x01,
            (0x01 << 8) | INPUT_REPORT_ID,
            conn.interface_number,
            REPORT_WIRE_LEN,
            timeout=500,
        )
        return list(data)
    except Exception:
        return None


def wait_ready(conn, retries=50, delay=0.03):
    write_report(conn, [0x06])
    for _ in range(retries):
        r = read_report(conn)
        if r is None or (len(r) > 1 and r[1] != 0x11):
            return
        time.sleep(delay)
        write_report(conn, [0x06])


def set_zones(zones, r, g, b):
    conn = connect()
    try:
        write_report(conn, [0x07, 0x04])   # RESET_ALL_LIGHTS_ON
        wait_ready(conn)

        for zone in zones:
            z2 = (zone & 0xff00) >> 8
            z3 = zone & 0xff
            c1 = ((r & 0xf) << 4) | (g & 0xf)
            c2 = (b & 0xf) << 4
            write_report(conn, [0x03, 0x00, 0x00, z2, z3, c1, c2, 0x00])
            time.sleep(0.02)

        write_report(conn, [0x04])       # LOOP_BLOCK_END
        time.sleep(0.05)
        write_report(conn, [0x05])       # TRANSMIT_EXECUTE
        wait_ready(conn)
    finally:
        close(conn)


if __name__ == "__main__":
    zones, r, g, b = parse_args()
    set_zones(zones, r, g, b)
