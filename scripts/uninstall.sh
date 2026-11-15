#!/usr/bin/env bash
# ==============================================================================
# VEIL UNINSTALLER
# Safely removes Veil binaries, manifests, desktop shortcuts, and services
# ==============================================================================

set -e

RED="\033[1;31m"
GREEN="\033[1;32m"
AMBER="\033[38;2;245;158;11m"
RESET="\033[0m"

echo -e "${RED}✦ Veil Uninstallation Utility${RESET}"

# Stop systemd service
if systemctl --user is-active --quiet veil.service 2>/dev/null; then
    echo "Stopping veil.service..."
    systemctl --user stop veil.service || true
    systemctl --user disable veil.service || true
fi

# Remove autostart and desktop files
rm -f "${HOME}/.config/autostart/veil.desktop"
rm -f "${HOME}/.config/systemd/user/veil.service"
rm -f "${HOME}/.local/share/applications/veil.desktop"

# Remove binaries and installed application sources
rm -f "${HOME}/.local/bin/veil"
rm -f "${HOME}/.local/bin/veil-native-host"
rm -rf "${HOME}/.local/share/veil/app"

# Remove native messaging manifests
rm -f "${HOME}/.config/google-chrome/NativeMessagingHosts/com.veil.privacy.json"
rm -f "${HOME}/.config/chromium/NativeMessagingHosts/com.veil.privacy.json"
rm -f "${HOME}/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts/com.veil.privacy.json"
rm -f "${HOME}/.config/microsoft-edge/NativeMessagingHosts/com.veil.privacy.json"
rm -f "${HOME}/.config/vivaldi/NativeMessagingHosts/com.veil.privacy.json"
rm -f "${HOME}/.mozilla/native-messaging-hosts/com.veil.privacy.json"

read -p "Would you also like to purge encrypted vault data (~/.config/veil)? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if command -v secret-tool >/dev/null 2>&1; then
        if secret-tool clear application veil purpose live-vault-key vault "${HOME}/.config/veil"; then
            echo -e "${GREEN}✓ Desktop wallet entry removed.${RESET}"
        else
            echo -e "${AMBER}Could not clear the wallet entry. Remove the Veil encrypted vault key manually from your desktop wallet.${RESET}"
        fi
    else
        echo -e "${AMBER}secret-tool missing. Remove Veil encrypted vault key from your desktop wallet manually.${RESET}"
    fi
    rm -rf "${HOME}/.config/veil"
    echo -e "${GREEN}✓ Vault storage removed.${RESET}"
else
    echo -e "${AMBER}Vault data preserved at ~/.config/veil${RESET}"
fi

echo -e "${GREEN}✓ Veil has been uninstalled successfully.${RESET}"
