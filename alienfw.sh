#!/usr/bin/env bash
# AlienFX LED menu for Alienware M18x R1
# Requires: sudo python3 alienfw_ctrl.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTRL=(sudo python3 "$SCRIPT_DIR/alienfw_ctrl.py")

run() { "${CTRL[@]}" "$1" "$2"; }

is_valid_nibble() {
    [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 0 && $1 <= 15 ))
}

run_color() {
    local zone="$1"
    local color="$2"

    if run "$zone" "$color"; then
        echo "  Done."
    else
        echo "  Failed."
    fi
    sleep 0.6
}

color_menu() {
    local zone="$1"
    local zone_label="$2"
    while true; do
        clear
        echo "┌─────────────────────────────────┐"
        echo "│  Zone: $zone_label"
        echo "├─────────────────────────────────┤"
        echo "│  [1] Red       [2] Blue         │"
        echo "│  [3] Green     [4] Yellow       │"
        echo "│  [5] White     [6] Cyan         │"
        echo "│  [7] Magenta   [8] Orange       │"
        echo "│  [9] Purple    [0] Off          │"
        echo "│  [c] Custom R,G,B (0-15)        │"
        echo "│  [b] Back                       │"
        echo "└─────────────────────────────────┘"
        printf "  Choice: "
        read -r choice
        case "$choice" in
            1) run_color "$zone" red ;;
            2) run_color "$zone" blue ;;
            3) run_color "$zone" green ;;
            4) run_color "$zone" yellow ;;
            5) run_color "$zone" white ;;
            6) run_color "$zone" cyan ;;
            7) run_color "$zone" magenta ;;
            8) run_color "$zone" orange ;;
            9) run_color "$zone" purple ;;
            0) run_color "$zone" off ;;
            c|C)
                printf "  R (0-15): "; read -r rv
                printf "  G (0-15): "; read -r gv
                printf "  B (0-15): "; read -r bv
                if is_valid_nibble "$rv" && is_valid_nibble "$gv" && is_valid_nibble "$bv"; then
                    run_color "$zone" "${rv},${gv},${bv}"
                else
                    echo "  Invalid RGB. Each value must be an integer from 0 to 15."
                    sleep 1.2
                fi ;;
            b|B) return ;;
        esac
    done
}

main_menu() {
    while true; do
        clear
        echo "┌────────────────────────────────────────┐"
        echo "│     Alienware M18x R1 - LED Control    │"
        echo "├────────────────────────────────────────┤"
        echo "│  All Zones:                            │"
        echo "│   [1] All zones same color             │"
        echo "│   [2] Off (all zones)                  │"
        echo "├────────────────────────────────────────┤"
        echo "│  Keyboard Zones:                       │"
        echo "│   [3] All keyboard                     │"
        echo "│   [4] Left  (Macro keys M1-M18)        │"
        echo "│   [5] Middle-Left                      │"
        echo "│   [6] Middle-Right                     │"
        echo "│   [7] Right (Numpad)                   │"
        echo "├────────────────────────────────────────┤"
        echo "│  Other Zones:                          │"
        echo "│   [8] Alien Head logo                  │"
        echo "│   [9] Alienware logo                   │"
        echo "│   [a] Touchpad                         │"
        echo "│   [s] Speakers (both)                  │"
        echo "│   [m] Media bar                        │"
        echo "│   [p] Power button                     │"
        echo "│   [h] HDD LEDs                         │"
        echo "├────────────────────────────────────────┤"
        echo "│   [q] Quit                             │"
        echo "└────────────────────────────────────────┘"
        printf "  Choice: "
        read -r choice
        case "$choice" in
            1) color_menu "all"          "All Zones" ;;
            2) run "all" "off"; echo "  All zones off."; sleep 0.6 ;;
            3) color_menu "keyboard"     "All Keyboard" ;;
            4) color_menu "left"         "Left Keyboard (Macro keys)" ;;
            5) color_menu "middle-left"  "Middle-Left Keyboard" ;;
            6) color_menu "middle-right" "Middle-Right Keyboard" ;;
            7) color_menu "right"        "Right Keyboard / Numpad" ;;
            8) color_menu "alien-head"   "Alien Head Logo" ;;
            9) color_menu "logo"         "Alienware Logo" ;;
            a|A) color_menu "touchpad"   "Touchpad" ;;
            s|S) color_menu "speakers"     "Speakers (both)" ;;
            m|M) color_menu "media-bar"  "Media Bar" ;;
            p|P) color_menu "power"      "Power Button" ;;
            h|H) color_menu "hdd"        "HDD LEDs" ;;
            q|Q) echo "Bye."; exit 0 ;;
        esac
    done
}

if [[ ! -f "$SCRIPT_DIR/alienfw_ctrl.py" ]]; then
    echo "Missing controller: $SCRIPT_DIR/alienfw_ctrl.py"
    exit 1
fi

# Check for sudo access to the python script
if ! sudo -n python3 --version &>/dev/null 2>&1; then
    echo "This script needs sudo for USB access."
    echo "You'll be prompted for your password on first use."
fi

main_menu
