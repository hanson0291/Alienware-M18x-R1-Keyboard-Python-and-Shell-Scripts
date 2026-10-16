#!/usr/bin/env python3
"""
Alienware M18x LED Zone Controller
USB ID: 187c:0518 | AlienFX Protocol

Controls all keyboard LED zones and maps macro keys M1-M5
to brightness presets. Run with sudo or after applying udev rules.

Setup (one-time):
    sudo python3 alienware_led_controller.py --setup-udev
    sudo usermod -aG input $USER
    # Then log out and back in
"""

import sys
import os
import threading
import argparse
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox

# When run with sudo the user's local site-packages are not on the path.
# Add them so pyusb / evdev are found regardless.
_user_site = os.path.expanduser("~scorpio/.local/lib/python3.10/site-packages")
if os.path.isdir(_user_site) and _user_site not in sys.path:
    sys.path.insert(0, _user_site)

# ── Optional deps ──────────────────────────────────────────────────────────────
try:
    import usb.core, usb.util
    HAS_USB = True
except ImportError:
    HAS_USB = False

try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False

# ── AlienFX USB constants ──────────────────────────────────────────────────────
ALIENWARE_VID   = 0x187C
M18X_PID        = 0x0518   # Bus 002 Device 005

# AlienFX HID commands (9-byte payload sent via ctrl_transfer)
CMD_RESET            = 0x02
CMD_LOOP_START       = 0x01
CMD_SET_COLOR        = 0x03
CMD_GET_STATUS       = 0x04
CMD_LOOP_END         = 0x05
CMD_TRANSMIT_EXECUTE = 0x21
CMD_SAVE_NEXT        = 0x06
CMD_SAVE             = 0x07

STATUS_BUSY    = 0x11
STATUS_READY   = 0x10
STATUS_UNKNOWN = 0xFF

# ── Zone definitions for M18x (187c:0518) ──────────────────────────────────────
# Each value is the 16-bit zone bitmask used in SET_COLOR packets
ZONES = {
    "Right Keyboard":        0x0001,
    "Middle Right Keyboard": 0x0002,
    "Middle Left Keyboard":  0x0004,
    "Left Keyboard":         0x0008,
    "Alien Head Logo":       0x0020,
    "Media Bar":             0x0040,
    "Touchpad":              0x0080,
    "Power Button":          0x0100,
}

# ── Brightness presets mapped to Macro keys M1-M5 ─────────────────────────────
MACRO_DEFAULTS = {
    "M1": 0,    # Off
    "M2": 64,   # 25 %
    "M3": 128,  # 50 %
    "M4": 192,  # 75 %
    "M5": 255,  # Full
}

BRIGHTNESS_PRESETS = {
    "Off (0)":      0,
    "Dim 25%":      64,
    "Medium 50%":   128,
    "Bright 75%":   192,
    "Full 100%":    255,
}

COLOR_PRESETS = [
    ("Alien Blue",       0,   212, 255),
    ("Matrix Green",     0,   255,  65),
    ("Demon Red",      220,    20,  60),
    ("Cyberpunk Gold", 255,   213,   0),
    ("Royal Purple",   148,     0, 211),
    ("Sunset Orange",  255,   100,   0),
    ("Arctic White",   255,   255, 255),
    ("Midnight Blue",    0,     0, 139),
    ("Hot Pink",       255,    20, 147),
]

# ── Known macro key codes on Alienware keyboards (evdev) ──────────────────────
# These are common codes; run `evtest` to verify yours if they differ.
MACRO_KEYCODES = {
    190: "M1",
    191: "M2",
    192: "M3",
    193: "M4",
    194: "M5",
    # Some firmware variants use F13-F17
    183: "M1",   # KEY_F13
    184: "M2",   # KEY_F14
    185: "M3",   # KEY_F15
    186: "M4",   # KEY_F16
    187: "M5",   # KEY_F17
}


# ══════════════════════════════════════════════════════════════════════════════
class AlienFXController:
    """Low-level AlienFX USB HID communication for M18x (0x0518)."""

    def __init__(self):
        self.device   = None
        self.endpoint = None
        self.connected = False
        self._lock    = threading.Lock()

    # ── Connection ─────────────────────────────────────────────────────────────
    def connect(self):
        if not HAS_USB:
            return False, "pyusb not installed — run: pip3 install pyusb"

        self.device = usb.core.find(idVendor=ALIENWARE_VID, idProduct=M18X_PID)
        if self.device is None:
            return False, f"Device 187c:{M18X_PID:04x} not found. Need sudo or udev rule."

        try:
            if self.device.is_kernel_driver_active(0):
                self.device.detach_kernel_driver(0)
            self.device.set_configuration()
            cfg  = self.device.get_active_configuration()
            intf = cfg[(0, 0)]
            # Grab the Interrupt OUT endpoint (0x01)
            self.endpoint = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                                       == usb.util.ENDPOINT_OUT
            )
            self.connected = True
            return True, f"Connected: Alienware M18x (187c:{M18X_PID:04x})"
        except Exception as exc:
            return False, f"USB error: {exc}"

    def disconnect(self):
        if self.device:
            try:
                usb.util.dispose_resources(self.device)
            except Exception:
                pass
        self.device    = None
        self.endpoint  = None
        self.connected = False

    # ── Low-level send ────────────────────────────────────────────────────────
    def _send(self, command, *args):
        """Send a 9-byte AlienFX HID packet. Tries ctrl_transfer then interrupt write."""
        if not self.connected or not self.device:
            return False
        packet = [command] + list(args)
        packet = packet[:9]
        packet += [0x00] * (9 - len(packet))
        with self._lock:
            # Try 1: HID Set_Report via control transfer (report ID=2)
            for wval in (0x0202, 0x0200):
                try:
                    self.device.ctrl_transfer(0x21, 0x09, wval, 0x0000, packet, timeout=500)
                    return True
                except usb.core.USBError:
                    pass
            # Try 2: raw interrupt write
            try:
                if self.endpoint:
                    self.endpoint.write(bytes(packet), timeout=500)
                    return True
            except Exception:
                pass
            print(f"[AlienFX] All send methods failed for cmd=0x{command:02x}")
            return False

    def _wait_ready(self, retries=100, delay=0.02):
        """Poll HID Get_Report until device reports STATUS_READY (0x10)."""
        import time
        for _ in range(retries):
            try:
                resp = self.device.ctrl_transfer(
                    0xA1, 0x01, 0x0101, 0x0000, 9, timeout=200)
                if resp and resp[0] == STATUS_READY:
                    return True
                if resp and resp[0] != STATUS_BUSY:
                    return True   # unknown status — proceed
            except Exception:
                pass
            time.sleep(delay)
        return True   # timeout — proceed anyway

    # ── High-level API ────────────────────────────────────────────────────────
    def reset(self):
        ok = self._send(CMD_RESET, 0x03)
        self._wait_ready()
        return ok

    def set_zone_color(self, zone_id: int, r: int, g: int, b: int) -> bool:
        """Set a single zone. Batches into one LOOP transaction."""
        return self._send_color_batch([(zone_id, r, g, b)])

    def set_all_zones(self, r: int, g: int, b: int):
        """Set every zone to the same color in one USB transaction."""
        self._send_color_batch([(zid, r, g, b) for zid in ZONES.values()])

    def _send_color_batch(self, zone_colors: list) -> bool:
        """
        Core protocol sequence:
          RESET → wait → LOOP_START → SET_COLOR(s) → LOOP_END → TRANSMIT_EXECUTE
        Tries 0x21 and 0x28 as the execute command.
        """
        import time
        self._send(CMD_RESET, 0x03)
        self._wait_ready()
        self._send(CMD_LOOP_START, 0xFF)
        for zone_id, r, g, b in zone_colors:
            hi = (zone_id >> 8) & 0xFF
            lo = zone_id & 0xFF
            self._send(CMD_SET_COLOR, hi, lo, 0x00, r, g, b)
        self._send(CMD_LOOP_END)
        # Try both known execute commands
        ok = self._send(CMD_TRANSMIT_EXECUTE)          # 0x21
        time.sleep(0.05)
        self._send(0x28)                               # alternate execute seen on some M18x
        return ok

    def apply_brightness_to_color(self, color: tuple, brightness: int) -> tuple:
        """Scale an RGB tuple by a brightness factor 0-255."""
        factor = brightness / 255.0
        return tuple(max(0, min(255, int(c * factor))) for c in color)


# ══════════════════════════════════════════════════════════════════════════════
class MacroKeyListener:
    """Listen for M1-M5 macro key presses via evdev."""

    def __init__(self, on_macro):
        self.on_macro  = on_macro
        self._running  = False
        self._thread   = None
        self._dev      = None

    def _find_device(self):
        if not HAS_EVDEV:
            return None, "evdev not installed — run: pip3 install evdev"
        try:
            paths = evdev.list_devices()
        except Exception:
            return None, "Cannot list input devices — add yourself to the 'input' group:\n  sudo usermod -aG input $USER\n  (then log out and back in)"
        if not paths:
            return None, "No input devices accessible. Add user to 'input' group."

        best = None
        for path in paths:
            try:
                dev  = InputDevice(path)
                caps = dev.capabilities()
                keys = caps.get(ecodes.EV_KEY, [])
                if any(k in keys for k in MACRO_KEYCODES):
                    return dev, f"Found macro device: {dev.name}"
                if "alienware" in dev.name.lower() or "Alienware" in dev.name:
                    best = dev
            except Exception:
                pass
        if best:
            return best, f"Using Alienware device: {best.name} (macro codes unconfirmed)"
        return None, "Macro keyboard not found. Check dmesg or run evtest to identify keys."

    def start(self):
        if self._running:
            return False, "Already running"
        dev, msg = self._find_device()
        if dev is None:
            return False, msg
        self._dev     = dev
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True, msg

    def stop(self):
        self._running = False
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass

    def _loop(self):
        try:
            for event in self._dev.read_loop():
                if not self._running:
                    break
                if event.type == ecodes.EV_KEY:
                    key_ev = categorize(event)
                    if key_ev.keystate == key_ev.key_down:
                        macro = MACRO_KEYCODES.get(event.code)
                        if macro:
                            self.on_macro(macro)
        except Exception as exc:
            print(f"[MacroListener] {exc}")


# ══════════════════════════════════════════════════════════════════════════════
class AlienwareLEDApp:
    """Tkinter GUI for Alienware M18x LED zone control."""

    # Colour theme
    BG      = "#0d0d1a"
    BG2     = "#16213e"
    BG3     = "#0f3460"
    ACCENT  = "#00d4ff"
    WARN    = "#ff9500"
    DIM     = "#5a6a7a"
    WHITE   = "#e0e8f0"
    FONT    = ("Courier", 10)
    FONT_B  = ("Courier", 10, "bold")
    FONT_LG = ("Courier", 13, "bold")

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Alienware M18x LED Controller")
        root.geometry("860x640")
        root.minsize(780, 560)
        root.configure(bg=self.BG)

        self.fx   = AlienFXController()
        self.ml   = MacroKeyListener(self._on_macro_key)

        # Per-zone state
        self.zone_colors     = {z: (0, 212, 255) for z in ZONES}   # Alien Blue default
        self.zone_brightness = {z: 255            for z in ZONES}

        # Macro assignments
        self.macro_bright_vars: dict[str, tk.IntVar] = {}

        self._build_ui()
        self._connect()

    # ── UI Construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        self._apply_theme()

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=self.BG3, height=50)
        hdr.pack(fill=tk.X, padx=8, pady=(8, 0))
        hdr.pack_propagate(False)
        tk.Label(hdr, text="ALIENWARE M18x  ·  LED ZONE CONTROLLER",
                 bg=self.BG3, fg=self.ACCENT, font=self.FONT_LG).pack(pady=12)

        # ── Status bar ────────────────────────────────────────────────────────
        sb = tk.Frame(self.root, bg=self.BG2)
        sb.pack(fill=tk.X, padx=8, pady=2)
        self._status_var = tk.StringVar(value="Initialising…")
        tk.Label(sb, textvariable=self._status_var,
                 bg=self.BG2, fg=self.WARN, font=("Courier", 9),
                 anchor="w").pack(fill=tk.X, padx=6, pady=2)

        # ── Notebook ──────────────────────────────────────────────────────────
        nb = ttk.Notebook(self.root)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        tab_zones   = ttk.Frame(nb)
        tab_macro   = ttk.Frame(nb)
        tab_presets = ttk.Frame(nb)
        tab_help    = ttk.Frame(nb)

        nb.add(tab_zones,   text="  Zone Control  ")
        nb.add(tab_macro,   text="  Macro Keys  ")
        nb.add(tab_presets, text="  Quick Presets  ")
        nb.add(tab_help,    text="  Help / Setup  ")

        self._build_zone_tab(tab_zones)
        self._build_macro_tab(tab_macro)
        self._build_presets_tab(tab_presets)
        self._build_help_tab(tab_help)

        # ── Bottom toolbar ────────────────────────────────────────────────────
        bar = tk.Frame(self.root, bg=self.BG)
        bar.pack(fill=tk.X, padx=8, pady=(0, 8))

        for text, cmd in [
            ("Apply All Zones",  self._apply_all_zones),
            ("All White",        lambda: self._quick_color(255, 255, 255)),
            ("LEDs Off",         lambda: self._quick_color(0, 0, 0)),
        ]:
            tk.Button(bar, text=text, command=cmd,
                      bg=self.BG3, fg=self.ACCENT, font=self.FONT_B,
                      relief=tk.FLAT, cursor="hand2", padx=10, pady=4).pack(side=tk.LEFT, padx=4)

        tk.Button(bar, text="Reconnect USB", command=self._connect,
                  bg=self.BG2, fg=self.DIM, font=self.FONT,
                  relief=tk.FLAT, cursor="hand2", padx=10, pady=4).pack(side=tk.RIGHT, padx=4)

    def _apply_theme(self):
        style = ttk.Style()
        style.theme_use("clam")
        for w in ("TFrame", "TScrollbar"):
            style.configure(w, background=self.BG)
        style.configure("TLabel",    background=self.BG,  foreground=self.ACCENT, font=self.FONT)
        style.configure("TButton",   background=self.BG3, foreground=self.ACCENT, font=self.FONT_B, borderwidth=0)
        style.map("TButton",         background=[("active", self.BG2)])
        style.configure("TScale",    background=self.BG,  troughcolor=self.BG2, sliderlength=14)
        style.configure("TCombobox", fieldbackground=self.BG2, foreground=self.ACCENT, background=self.BG2)
        style.configure("TNotebook",     background=self.BG,  tabmargins=[2, 2, 2, 0])
        style.configure("TNotebook.Tab", background=self.BG2, foreground=self.DIM,  font=self.FONT_B, padding=[10, 4])
        style.map("TNotebook.Tab",   background=[("selected", self.BG3)], foreground=[("selected", self.ACCENT)])

    # ── Zone Tab ──────────────────────────────────────────────────────────────
    def _build_zone_tab(self, parent):
        canvas = tk.Canvas(parent, bg=self.BG, highlightthickness=0)
        vsb    = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        frame  = tk.Frame(canvas, bg=self.BG)
        frame.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        self._zone_widgets: dict[str, dict] = {}

        for zone_name, zone_id in ZONES.items():
            row_frame = tk.Frame(frame, bg=self.BG2, relief=tk.FLAT, bd=0)
            row_frame.pack(fill=tk.X, padx=8, pady=4)

            # Zone label
            tk.Label(row_frame, text=zone_name, bg=self.BG2, fg=self.ACCENT,
                     font=self.FONT_B, width=22, anchor="w").grid(
                     row=0, column=0, padx=10, pady=8)

            # Color swatch (click to pick)
            r, g, b = self.zone_colors[zone_name]
            swatch = tk.Label(row_frame, bg=f"#{r:02x}{g:02x}{b:02x}",
                              width=5, height=2, relief=tk.RAISED, cursor="hand2")
            swatch.grid(row=0, column=1, padx=8)
            swatch.bind("<Button-1>",
                        lambda e, z=zone_name, s=swatch: self._pick_color(z, s))

            # Brightness slider
            tk.Label(row_frame, text="Brightness", bg=self.BG2,
                     fg=self.DIM, font=("Courier", 8)).grid(row=0, column=2, padx=(12, 2))
            bv = tk.IntVar(value=255)
            slider = ttk.Scale(row_frame, from_=0, to=255, orient=tk.HORIZONTAL,
                               variable=bv, length=220)
            slider.grid(row=0, column=3, padx=4)
            vl = tk.Label(row_frame, text="255", bg=self.BG2, fg=self.ACCENT,
                          font=("Courier", 9), width=4)
            vl.grid(row=0, column=4)
            bv.trace_add("write", lambda *_, vl=vl, bv=bv, z=zone_name:
                         (vl.config(text=str(bv.get())),
                          self.zone_brightness.update({z: bv.get()})))

            # Apply button
            tk.Button(row_frame, text="Apply",
                      command=lambda z=zone_name, zid=zone_id: self._apply_zone(z, zid),
                      bg=self.BG3, fg=self.ACCENT, font=self.FONT_B,
                      relief=tk.FLAT, cursor="hand2", padx=8).grid(
                      row=0, column=5, padx=10)

            self._zone_widgets[zone_name] = {"swatch": swatch, "bv": bv, "vl": vl}

    # ── Macro Tab ─────────────────────────────────────────────────────────────
    def _build_macro_tab(self, parent):
        tk.Label(parent, text="Assign a brightness level (0–255) to each macro key.",
                 bg=self.BG, fg=self.DIM, font=("Courier", 9)).pack(anchor="w", padx=12, pady=(8, 0))
        tk.Label(parent, text="Pressing the key instantly sets ALL zones to that brightness.",
                 bg=self.BG, fg=self.DIM, font=("Courier", 9)).pack(anchor="w", padx=12, pady=(0, 8))

        self._macro_indicators: dict[str, tk.Label] = {}

        for macro, default_val in MACRO_DEFAULTS.items():
            row = tk.Frame(parent, bg=self.BG2)
            row.pack(fill=tk.X, padx=12, pady=4)

            # Key label
            tk.Label(row, text=macro, bg=self.BG2, fg=self.WARN,
                     font=("Courier", 15, "bold"), width=4).grid(row=0, column=0, padx=10, pady=8)

            # Preset drop-down
            tk.Label(row, text="Preset:", bg=self.BG2, fg=self.DIM,
                     font=("Courier", 9)).grid(row=0, column=1, padx=(8, 2))
            preset_var = tk.StringVar()
            closest    = min(BRIGHTNESS_PRESETS.items(), key=lambda x: abs(x[1] - default_val))
            preset_var.set(closest[0])
            cb = ttk.Combobox(row, textvariable=preset_var,
                              values=list(BRIGHTNESS_PRESETS.keys()),
                              width=14, state="readonly")
            cb.grid(row=0, column=2, padx=4)

            # Manual slider
            tk.Label(row, text="Custom:", bg=self.BG2, fg=self.DIM,
                     font=("Courier", 9)).grid(row=0, column=3, padx=(12, 2))
            bv = tk.IntVar(value=default_val)
            sl = ttk.Scale(row, from_=0, to=255, orient=tk.HORIZONTAL,
                           variable=bv, length=160)
            sl.grid(row=0, column=4, padx=4)
            vl = tk.Label(row, text=str(default_val), bg=self.BG2, fg=self.ACCENT,
                          font=("Courier", 9), width=4)
            vl.grid(row=0, column=5)
            bv.trace_add("write", lambda *_, vl=vl, bv=bv: vl.config(text=str(bv.get())))

            # Sync preset → slider
            def _preset_changed(_, p=preset_var, b=bv):
                b.set(BRIGHTNESS_PRESETS.get(p.get(), b.get()))
            cb.bind("<<ComboboxSelected>>", _preset_changed)

            # Flash indicator (lights up when key pressed)
            ind = tk.Label(row, text="●", bg=self.BG2, fg=self.BG,
                           font=("Courier", 16))
            ind.grid(row=0, column=6, padx=8)
            self._macro_indicators[macro] = ind

            # Test button
            tk.Button(row, text="Test",
                      command=lambda b=bv, m=macro: self._test_macro(m, b.get()),
                      bg=self.BG3, fg=self.ACCENT, font=self.FONT_B,
                      relief=tk.FLAT, cursor="hand2", padx=8).grid(
                      row=0, column=7, padx=10)

            self.macro_bright_vars[macro] = bv

        # Listener controls
        sep = tk.Frame(parent, bg=self.DIM, height=1)
        sep.pack(fill=tk.X, padx=12, pady=12)

        ctrl = tk.Frame(parent, bg=self.BG)
        ctrl.pack(fill=tk.X, padx=12)

        self._listener_var = tk.StringVar(value="Macro listener: stopped")
        tk.Label(ctrl, textvariable=self._listener_var,
                 bg=self.BG, fg=self.DIM, font=("Courier", 9)).pack(side=tk.LEFT)

        tk.Button(ctrl, text="Start Listener", command=self._start_listener,
                  bg=self.BG3, fg=self.ACCENT, font=self.FONT_B,
                  relief=tk.FLAT, cursor="hand2", padx=10, pady=3).pack(side=tk.RIGHT, padx=4)
        tk.Button(ctrl, text="Stop Listener", command=self._stop_listener,
                  bg=self.BG2, fg=self.DIM, font=self.FONT_B,
                  relief=tk.FLAT, cursor="hand2", padx=10, pady=3).pack(side=tk.RIGHT, padx=4)

    # ── Presets Tab ───────────────────────────────────────────────────────────
    def _build_presets_tab(self, parent):
        tk.Label(parent, text="Color Presets  —  click to apply to all zones",
                 bg=self.BG, fg=self.DIM, font=("Courier", 9)).pack(pady=(10, 6))

        grid = tk.Frame(parent, bg=self.BG)
        grid.pack(pady=4)
        for i, (name, r, g, b) in enumerate(COLOR_PRESETS):
            row, col = divmod(i, 3)
            hex_col  = f"#{r:02x}{g:02x}{b:02x}"
            txt_col  = "#000000" if (r + g + b) > 400 else "#ffffff"
            tk.Button(grid, text=name,
                      bg=hex_col, fg=txt_col, activebackground=hex_col,
                      font=self.FONT_B, width=16, height=2,
                      relief=tk.RAISED, cursor="hand2",
                      command=lambda rc=r, gc=g, bc=b: self._quick_color(rc, gc, bc)
                      ).grid(row=row, column=col, padx=6, pady=6)

        tk.Label(parent, text="─" * 60, bg=self.BG, fg=self.DIM).pack(pady=8)
        tk.Label(parent, text="Brightness Presets  —  keeps current colour",
                 bg=self.BG, fg=self.DIM, font=("Courier", 9)).pack(pady=(0, 6))

        bf = tk.Frame(parent, bg=self.BG)
        bf.pack()
        for name, val in BRIGHTNESS_PRESETS.items():
            tk.Button(bf, text=f"{name}\n({val})",
                      bg=self.BG2, fg=self.ACCENT, activebackground=self.BG3,
                      font=self.FONT_B, width=12, height=3,
                      relief=tk.RAISED, cursor="hand2",
                      command=lambda v=val: self._apply_global_brightness(v)
                      ).pack(side=tk.LEFT, padx=5, pady=5)

    # ── Help Tab ──────────────────────────────────────────────────────────────
    def _build_help_tab(self, parent):
        txt = tk.Text(parent, bg=self.BG, fg=self.WHITE, font=("Courier", 10),
                      relief=tk.FLAT, wrap=tk.WORD, padx=16, pady=12,
                      insertbackground=self.ACCENT)
        txt.pack(fill=tk.BOTH, expand=True)
        vsb = ttk.Scrollbar(txt, command=txt.yview)
        txt.configure(yscrollcommand=vsb.set)

        help_text = """\
ALIENWARE M18x LED CONTROLLER  —  Setup Guide
═══════════════════════════════════════════════

DETECTED DEVICE
  USB 187c:0518  (Alienware M18x)

── Step 1: USB permissions (AlienFX) ──────────────────────────────
The app needs write access to the AlienFX USB controller.

Option A — run with sudo (quick test):
  sudo python3 /home/scorpio/Desktop/alienware_led_controller.py

Option B — udev rule (permanent, recommended):
  Run the setup script once:
    sudo python3 /home/scorpio/Desktop/alienware_led_controller.py --setup-udev
  Then replug the keyboard and re-run without sudo.

── Step 2: Macro keys (M1–M5) ─────────────────────────────────────
The macro keys are captured via evdev (Linux input subsystem).

  1. Add your user to the 'input' group:
       sudo usermod -aG input $USER
  2. Log out and log back in.
  3. Open the 'Macro Keys' tab and click 'Start Listener'.

  If macro keys still don't respond, run evtest as root to find
  the exact key codes and device path:
       sudo evtest

── Zone IDs (for reference / debugging) ───────────────────────────
  Right Keyboard        : 0x0001
  Middle Right Keyboard : 0x0002
  Middle Left Keyboard  : 0x0004
  Left Keyboard         : 0x0008
  Alien Head Logo       : 0x0020
  Media Bar             : 0x0040
  Touchpad              : 0x0080
  Power Button          : 0x0100

── Troubleshooting ─────────────────────────────────────────────────
  - "Device not found"  → run with sudo or apply udev rule.
  - "USB error Access"  → another process owns the device
                          (try: sudo rmmod alienware_wmi)
  - Colours off/wrong   → zone IDs may vary by firmware version;
                          adjust ZONES dict in the script.
  - No macro events     → run evtest to find correct key codes.
"""
        txt.insert("1.0", help_text)
        txt.configure(state=tk.DISABLED)

    # ── Actions ───────────────────────────────────────────────────────────────
    def _connect(self):
        ok, msg = self.fx.connect()
        self._status(msg)

    def _status(self, msg: str):
        self._status_var.set(msg)

    def _pick_color(self, zone_name: str, swatch: tk.Label):
        r, g, b = self.zone_colors[zone_name]
        result  = colorchooser.askcolor(
            color=f"#{r:02x}{g:02x}{b:02x}",
            title=f"Pick colour — {zone_name}")
        if result[0]:
            r, g, b = (int(c) for c in result[0])
            self.zone_colors[zone_name] = (r, g, b)
            swatch.config(bg=f"#{r:02x}{g:02x}{b:02x}")

    def _apply_zone(self, zone_name: str, zone_id: int):
        color      = self.zone_colors[zone_name]
        brightness = self.zone_brightness[zone_name]
        r, g, b    = self.fx.apply_brightness_to_color(color, brightness)
        if self.fx.connected:
            self.fx.set_zone_color(zone_id, r, g, b)
            self._status(f"Zone '{zone_name}' → RGB({r},{g},{b})")
        else:
            self._status("Not connected — use sudo or apply udev rule (see Help tab)")

    def _apply_all_zones(self):
        if not self.fx.connected:
            self._status("Not connected — see Help tab for setup instructions")
            return
        for zone_name, zone_id in ZONES.items():
            color      = self.zone_colors[zone_name]
            brightness = self.zone_brightness[zone_name]
            r, g, b    = self.fx.apply_brightness_to_color(color, brightness)
            self.fx.set_zone_color(zone_id, r, g, b)
        self._status("All zones updated")

    def _quick_color(self, r: int, g: int, b: int):
        for z in ZONES:
            self.zone_colors[z] = (r, g, b)
            w = self._zone_widgets.get(z)
            if w:
                w["swatch"].config(bg=f"#{r:02x}{g:02x}{b:02x}")
        if self.fx.connected:
            self.fx.set_all_zones(r, g, b)
        self._status(f"All zones → RGB({r},{g},{b})")

    def _apply_global_brightness(self, brightness: int):
        for z in ZONES:
            self.zone_brightness[z] = brightness
            w = self._zone_widgets.get(z)
            if w:
                w["bv"].set(brightness)
        if self.fx.connected:
            for zone_name, zone_id in ZONES.items():
                color   = self.zone_colors[zone_name]
                r, g, b = self.fx.apply_brightness_to_color(color, brightness)
                self.fx.set_zone_color(zone_id, r, g, b)
        self._status(f"Global brightness → {brightness}")

    # ── Macro handling ────────────────────────────────────────────────────────
    def _test_macro(self, macro: str, value: int):
        self._apply_global_brightness(value)
        self._status(f"[Test] {macro} → brightness {value}")

    def _on_macro_key(self, macro: str):
        bv = self.macro_bright_vars.get(macro)
        if bv is None:
            return
        brightness = bv.get()
        self.root.after(0, lambda: self._apply_global_brightness(brightness))
        self.root.after(0, lambda: self._flash_indicator(macro))
        self.root.after(0, lambda: self._status(f"{macro} pressed → brightness {brightness}"))

    def _flash_indicator(self, macro: str):
        ind = self._macro_indicators.get(macro)
        if ind:
            ind.config(fg=self.ACCENT)
            self.root.after(400, lambda: ind.config(fg=self.BG))

    def _start_listener(self):
        ok, msg = self.ml.start()
        self._listener_var.set(f"Macro listener: {msg}")

    def _stop_listener(self):
        self.ml.stop()
        self._listener_var.set("Macro listener: stopped")

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    def on_close(self):
        self.ml.stop()
        self.fx.disconnect()
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════════════════
UDEV_RULE = """\
# Alienware M18x AlienFX LED controller
SUBSYSTEM=="usb", ATTRS{idVendor}=="187c", ATTRS{idProduct}=="0518", \\
    MODE="0666", GROUP="plugdev", TAG+="uaccess"
"""

def setup_udev():
    rule_path = "/etc/udev/rules.d/99-alienware-alienFX.rules"
    print(f"Writing udev rule to {rule_path} …")
    try:
        with open(rule_path, "w") as f:
            f.write(UDEV_RULE)
        os.system("udevadm control --reload-rules")
        os.system("udevadm trigger")
        print("Done. Replug your keyboard, then run the app without sudo.")
    except PermissionError:
        print("Permission denied — run this with sudo:\n"
              "  sudo python3 alienware_led_controller.py --setup-udev")


# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Alienware M18x LED Controller")
    parser.add_argument("--setup-udev", action="store_true",
                        help="Install udev rule for non-root USB access, then exit")
    args = parser.parse_args()

    if args.setup_udev:
        setup_udev()
        return

    if not HAS_USB:
        print("Warning: pyusb not installed — run: pip3 install pyusb")
    if not HAS_EVDEV:
        print("Warning: evdev not installed — run: pip3 install evdev")
    if HAS_USB and os.geteuid() != 0:
        print("Tip: run with sudo or apply the udev rule for USB access.")
        print("     python3 alienware_led_controller.py --setup-udev")

    root = tk.Tk()
    app  = AlienwareLEDApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
