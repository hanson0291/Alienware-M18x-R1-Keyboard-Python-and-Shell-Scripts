#!/bin/bash
# Alienware M18x LED Controller — one-time setup
# Run: sudo bash ~/Desktop/alienware_setup.sh

set -e

echo "=== Alienware M18x LED Setup ==="

# 1. Install Python packages system-wide
echo "[1/4] Installing pyusb and evdev system-wide..."
pip3 install pyusb evdev

# 2. Write udev rule for USB access without sudo
echo "[2/4] Writing udev rule for 187c:0518..."
cat > /etc/udev/rules.d/99-alienware-alienFX.rules << 'EOF'
# Alienware M18x AlienFX LED controller (187c:0518)
SUBSYSTEM=="usb", ATTRS{idVendor}=="187c", ATTRS{idProduct}=="0518", \
    MODE="0666", GROUP="plugdev", TAG+="uaccess"
EOF

# 3. Add user to input group (for macro key evdev access)
echo "[3/4] Adding scorpio to 'input' and 'plugdev' groups..."
usermod -aG input scorpio
usermod -aG plugdev scorpio

# 4. Reload udev
echo "[4/4] Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger

echo ""
echo "=== Done! ==="
echo "Replug your keyboard, then log out and back in."
echo "After that, run WITHOUT sudo:"
echo "  python3 ~/Desktop/alienware_led_controller.py"
echo ""
echo "To test USB access right now (before logout):"
echo "  sudo python3 ~/Desktop/alienware_led_controller.py"
