# Alienware M18x R1 Keyboard Python and Shell Scripts

Linux tools for controlling the **AlienFX lighting** on an **Alienware M18x R1** laptop (they should also work on the M18x R2). You can set colors per zone, turn every LED off, keep them off across reboots and suspend/resume, and probe the controller's USB protocol.

Alienware never shipped AlienFX software for Linux. These scripts talk to the lighting controller directly over USB with [PyUSB](https://github.com/pyusb/pyusb).

| | |
|---|---|
| **Device** | AlienFX controller, USB ID `187c:0518` |
| **Tested on** | Alienware M18x R1, Ubuntu 22.04 (kernel 5.15), Python 3.10 |
| **Protocol** | Legacy AlienFX: 9-byte HID reports, 4-bit-per-channel color |

---

## Contents

| File | What it does |
|---|---|
| [`alienfw_ctrl.py`](alienfw_ctrl.py) | **The main CLI.** Sets any zone or group of zones to a color: `sudo python3 alienfw_ctrl.py <zone> <color>` |
| [`alienfw.sh`](alienfw.sh) | Interactive terminal menu that wraps `alienfw_ctrl.py`: pick a zone, then a color |
| [`leds_off.py`](leds_off.py) | Turns off every AlienFX zone (keyboard, logo, speakers, touchpad, power button, and so on) |
| [`install_leds_off_service.sh`](install_leds_off_service.sh) | Installs a systemd service and a sleep hook so the LEDs turn off at boot and after every resume |
| [`leds_off_watch.sh`](leds_off_watch.sh) | Alternative to the installer: a long-running watcher that turns the LEDs off at startup, then listens on D-Bus for logind's `PrepareForSleep(false)` and turns them off again after each wake |
| [`alienware_setup.sh`](alienware_setup.sh) | One-time setup: installs `pyusb` and `evdev`, adds a udev rule for non-root USB access, and adds the user to the `input` and `plugdev` groups |
| [`alienware_led_controller.py`](alienware_led_controller.py) | Tkinter GUI with zone color pickers, color and brightness presets, and an evdev listener for the macro keys. Experimental: its command constants come from an earlier guess at the protocol (see [Status](#status--caveats)) |
| [`alienfw_probe.py`](alienfw_probe.py) | Research script that tries several packet and transport combinations (control transfer and interrupt endpoint) and reports which ones the device accepts |
| [`alien_diag.py`](alien_diag.py) | Deep diagnostic: dumps the HID report descriptor and `lsusb -v` output, listens for unsolicited input reports, and sends test packets |

---

## Requirements

- Linux with `libusb` (installed by default on most distributions)
- Python 3.8 or newer
- [`pyusb`](https://pypi.org/project/pyusb/) for all of the scripts
- [`evdev`](https://pypi.org/project/evdev/) only for the GUI's macro key listener
- `python3-tk` only for the GUI

```bash
pip3 install pyusb evdev
sudo apt install python3-tk     # only needed for the GUI
```

Check that the controller is visible:

```bash
lsusb -d 187c:0518
# Bus 002 Device 005: ID 187c:0518 Alienware Corporation ...
```

---

## Quick start

### Set a color

```bash
sudo python3 alienfw_ctrl.py keyboard blue
sudo python3 alienfw_ctrl.py alien-head red
sudo python3 alienfw_ctrl.py all off
sudo python3 alienfw_ctrl.py touchpad 15,6,0    # custom R,G,B with values 0-15
```

### Interactive menu

```bash
./alienfw.sh
```

```
┌────────────────────────────────────────┐
│     Alienware M18x R1 - LED Control    │
├────────────────────────────────────────┤
│  All Zones:                            │
│   [1] All zones same color             │
│   [2] Off (all zones)                  │
├────────────────────────────────────────┤
│  Keyboard Zones:                       │
│   [3] All keyboard                     │
│   [4] Left  (Macro keys M1-M18)        │
│   ...                                  │
```

### Turn off every LED

```bash
sudo python3 leds_off.py
```

---

## Zones

| Name (`alienfw_ctrl.py`) | Bitmask | Area |
|---|---|---|
| `right` | `0x0001` | Right keyboard section and numpad |
| `middle-right` | `0x0002` | Middle-right keyboard section |
| `middle-left` | `0x0004` | Middle-left keyboard section |
| `left` | `0x0008` | Left keyboard section, including macro keys M1–M18 |
| `right-speaker` | `0x0020` | Right speaker grille |
| `left-speaker` | `0x0040` | Left speaker grille |
| `alien-head` | `0x0080` | Alien head on the lid |
| `logo` | `0x0100` | "ALIENWARE" logo |
| `touchpad` | `0x0200` | Touchpad |
| `media-bar` | `0x0800` | Touch media bar |
| `power` | `0x2000` | Power button |
| `hdd` | `0x4000` | HDD activity LEDs |

**Groups:** `keyboard` (all four keyboard zones), `speakers` (both speakers), and `all` (every zone).

**Named colors:** `off`, `red`, `green`, `blue`, `yellow`, `white`, `cyan`, `magenta`, `orange`, `purple`. You can also pass a custom color as `R,G,B`, where each channel is 0–15.

---

## Keeping the LEDs off at boot and after suspend

The M18x turns its lights back on at every boot and after every resume. There are two ways to keep them off.

**Option A: system service and sleep hook (recommended)**

```bash
sudo bash install_leds_off_service.sh
```

The installer creates:
- `/etc/systemd/system/alienfx-leds-off.service`, a oneshot service that runs `leds_off.py` at boot
- `/lib/systemd/system-sleep/alienfx-leds-off`, a hook that runs `leds_off.py` after resume

**Option B: user-level watcher**

Run `leds_off_watch.sh` from a systemd **user** service or a desktop autostart entry. It retries for up to 30 seconds while the USB device appears, then watches `org.freedesktop.login1` on D-Bus for wake events. Running it without root needs the udev rule from `alienware_setup.sh`.

> ⚠️ `install_leds_off_service.sh`, `leds_off_watch.sh`, and `leds_off.py` contain hardcoded paths (`/home/scorpio/Desktop/KeyboardCode/...` and `~scorpio/.local/...`). Edit them to match your username and clone location before you install.

---

## Running without sudo

```bash
sudo bash alienware_setup.sh
```

The setup script writes `/etc/udev/rules.d/99-alienware-alienFX.rules`:

```
SUBSYSTEM=="usb", ATTRS{idVendor}=="187c", ATTRS{idProduct}=="0518", \
    MODE="0666", GROUP="plugdev", TAG+="uaccess"
```

Log out and back in afterwards so the new group memberships take effect. The script adds the user `scorpio`; change that name to yours first.

---

## Protocol notes

The M18x R1/R2 controller uses the **legacy AlienFX protocol**. The protocol details here come from [trackmastersteve/alienfx](https://github.com/trackmastersteve/alienfx) and were confirmed by testing on real hardware with the probe scripts in this repo.

**Transport:** HID `SET_REPORT` control transfers (`bmRequestType=0x21`, `bRequest=0x09`, `wValue=0x0202`) with a 9-byte report. Byte 0 is the report ID, `0x02`. `alienfw_ctrl.py` tries the interrupt OUT endpoint first and falls back to the control transfer. You can force either one with `ALIENFW_TRANSPORT=interrupt` or `ALIENFW_TRANSPORT=control`.

**Status:** HID `GET_REPORT` (`0xA1`, `0x01`, `wValue=0x0101`). A status byte of `0x11` means the controller is busy.

| Command | Byte 1 | Payload |
|---|---|---|
| `SET_COLOUR` | `0x03` | `block, zone[23:16], zone[15:8], zone[7:0], (R<<4 \| G), (B<<4)` |
| `LOOP_BLOCK_END` | `0x04` | — |
| `TRANSMIT_EXECUTE` | `0x05` | — |
| `GET_STATUS` | `0x06` | — |
| `RESET` | `0x07` | Reset type: `0x03` = all lights off, `0x04` = all lights on |

**Sequence to set colors:**

```
RESET → wait-until-ready → SET_COLOUR × N zones → LOOP_BLOCK_END → TRANSMIT_EXECUTE → wait-until-ready
```

Colors use **4 bits per channel** (0–15), so the controller can show 4,096 colors rather than full 24-bit RGB.

---

## Status and caveats

- ✅ `alienfw_ctrl.py`, `alienfw.sh`, and `leds_off.py` work on real M18x R1 hardware.
- 🧪 `alienware_led_controller.py` (the GUI) predates the protocol work. Its command constants and zone map don't match the table above, so treat it as a UI starting point rather than a working controller. Porting it to the `alienfw_ctrl.py` backend is the obvious next step.
- 🧪 `alienfw_probe.py` and `alien_diag.py` send experimental packets. They're useful for reverse engineering but aren't needed for everyday use.
- Per-key RGB isn't possible. The M18x keyboard has only four lighting zones.
- These scripts detach the kernel HID driver from the AlienFX interface while they run and reattach it afterwards. This doesn't affect normal keyboard input, which comes from a separate device.

---

## Credits

- [trackmastersteve/alienfx](https://github.com/trackmastersteve/alienfx) for the reference AlienFX protocol implementation and the M18x R2 zone map
- [PyUSB](https://github.com/pyusb/pyusb)

## Disclaimer

This project isn't affiliated with or endorsed by Dell or Alienware. It sends raw USB commands to your hardware, so use it at your own risk.
