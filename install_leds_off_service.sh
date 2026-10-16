#!/bin/bash
# Installs a boot service + resume hook that runs leds_off.py
# Run: sudo bash ~/Desktop/KeyboardCode/install_leds_off_service.sh
set -e
SCRIPT=/home/scorpio/Desktop/KeyboardCode/leds_off.py

cat > /etc/systemd/system/alienfx-leds-off.service << EOT
[Unit]
Description=Turn off Alienware M18x AlienFX LEDs
After=multi-user.target

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 3
ExecStart=/usr/bin/python3 $SCRIPT

[Install]
WantedBy=multi-user.target
EOT

cat > /lib/systemd/system-sleep/alienfx-leds-off << EOT
#!/bin/sh
[ "\$1" = "post" ] && sleep 2 && /usr/bin/python3 $SCRIPT
EOT
chmod +x /lib/systemd/system-sleep/alienfx-leds-off

systemctl daemon-reload
systemctl enable --now alienfx-leds-off.service
systemctl --no-pager status alienfx-leds-off.service | head -20
echo "Installed."
