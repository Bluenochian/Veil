#!/usr/bin/env bash
# ==============================================================================
# VEIL LINUX INSTALLER
# Supported package-manager families: DNF, APT, Pacman, and Zypper
# ==============================================================================

set -e

BOLD="\033[1m"
PURPLE="\033[38;2;168;85;247m"
AMBER="\033[38;2;245;158;11m"
GREEN="\033[1;32m"
RED="\033[1;31m"
DIM="\033[2m"
RESET="\033[0m"

echo -e "${PURPLE}${BOLD}"
echo "  ██╗   ██╗███████╗██╗██╗     "
echo "  ██║   ██║██╔════╝██║██║     "
echo "  ██║   ██║█████╗  ██║██║     "
echo "  ╚██╗ ██╔╝██╔══╝  ██║██║     "
echo "   ╚████╔╝ ███████╗██║███████╗"
echo "    ╚═══╝  ╚══════╝╚═╝╚══════╝"
echo -e "${RESET}"
echo -e "${AMBER}${BOLD}✦ Linux browser privacy companion${RESET}\n"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
AUTOSTART_DIR="${HOME}/.config/autostart"
ICONS_DIR="${HOME}/.local/share/icons/hicolor"

mkdir -p "${BIN_DIR}" "${DESKTOP_DIR}" "${SYSTEMD_USER_DIR}" "${AUTOSTART_DIR}"

# Detect distribution and optional dependencies
echo -e "${PURPLE}[1/5] Detecting Linux Distribution and Dependencies...${RESET}"

if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO_ID="${ID:-unknown}"
    DISTRO_LIKE="${ID_LIKE:-unknown}"
else
    DISTRO_ID="unknown"
    DISTRO_LIKE="unknown"
fi

echo -e "      Detected Distribution: ${BOLD}${NAME:-$DISTRO_ID}${RESET}"

install_dependencies() {
    if [[ "$DISTRO_ID" == "fedora" || "$DISTRO_ID" == "rhel" || "$DISTRO_ID" == "centos" || "$DISTRO_ID" == "rocky" || "$DISTRO_ID" == "almalinux" || "$DISTRO_LIKE" == *"rhel"* || "$DISTRO_LIKE" == *"fedora"* || "$DISTRO_LIKE" == *"centos"* ]]; then
        echo -e "      ${DIM}Using dnf to install PySide6, Cryptography, and utilities...${RESET}"
        sudo dnf install -y python3-pyside6 python3-cryptography libsecret libnotify wl-clipboard xclip
    elif [[ "$DISTRO_ID" == "ubuntu" || "$DISTRO_ID" == "debian" || "$DISTRO_ID" == "linuxmint" || "$DISTRO_ID" == "pop" || "$DISTRO_ID" == "elementary" || "$DISTRO_ID" == "zorin" || "$DISTRO_ID" == "neon" || "$DISTRO_LIKE" == *"debian"* || "$DISTRO_LIKE" == *"ubuntu"* ]]; then
        echo -e "      ${DIM}Using apt to install PySide6, Cryptography, and utilities...${RESET}"
        sudo apt-get update
        sudo apt-get install -y python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets python3-pyside6.qtdbus python3-cryptography libsecret-tools libnotify-bin wl-clipboard xclip
    elif [[ "$DISTRO_ID" == "arch" || "$DISTRO_ID" == "manjaro" || "$DISTRO_ID" == "endeavouros" || "$DISTRO_ID" == "garuda" || "$DISTRO_ID" == "cachyos" || "$DISTRO_LIKE" == *"arch"* ]]; then
        echo -e "      ${DIM}Using pacman to install PySide6, Cryptography, and utilities...${RESET}"
        sudo pacman -S --needed --noconfirm python-pyside6 python-cryptography libsecret libnotify wl-clipboard xclip
    elif [[ "$DISTRO_ID" == *"suse"* || "$DISTRO_LIKE" == *"suse"* ]]; then
        echo -e "      ${DIM}Using zypper to install PySide6, Cryptography, and utilities...${RESET}"
        sudo zypper install -y python3-pyside6 python3-cryptography libsecret-tools libnotify-tools wl-clipboard xclip
    else
        echo -e "      ${AMBER}Unknown distro. Ensure Python 3.10+, PySide6, and Cryptography are installed.${RESET}"
    fi
}

# Dependency installation is optional
if [ "$1" != "--no-deps" ]; then
    read -p "Install system dependencies now? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        install_dependencies
    fi
fi

if ! command -v secret-tool >/dev/null 2>&1; then
    echo -e "${AMBER}Warning: secret-tool is not installed. Veil cannot open or migrate its encrypted vault without it.${RESET}"
fi
echo -e "${DIM}Veil also requires an unlocked KDE Wallet or GNOME Keyring in the desktop session.${RESET}"

# Install application sources and launchers
# Copy Veil, not the system Python install. We're not wrecking someones OS today.
echo -e "\n${PURPLE}[2/5] Installing Veil CLI & Native Messaging Host...${RESET}"
APP_DIR="${HOME}/.local/share/veil/app"
mkdir -p "${APP_DIR}"
for item in veil bin browser-extension assets packaging; do
    rm -rf "${APP_DIR:?}/${item}"
    cp -a "${REPO_DIR}/${item}" "${APP_DIR}/${item}"
done
find "${APP_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} +
cat > "${BIN_DIR}/veil" <<'VEIL_WRAPPER'
#!/usr/bin/env bash
exec python3 "${HOME}/.local/share/veil/app/bin/veil" "$@"
VEIL_WRAPPER
cat > "${BIN_DIR}/veil-native-host" <<'VEIL_HOST_WRAPPER'
#!/usr/bin/env bash
exec python3 "${HOME}/.local/share/veil/app/bin/veil-native-host" "$@"
VEIL_HOST_WRAPPER
chmod 0755 "${BIN_DIR}/veil" "${BIN_DIR}/veil-native-host"
echo -e "      ${GREEN}✓${RESET} Installed: ${BIN_DIR}/veil and veil-native-host"

# Install icon assets
echo -e "\n${PURPLE}[3/5] Installing Application Icons & High-DPI Assets...${RESET}"
for size in 16 22 24 32 48 64 128 256 512 1024; do
    target_dir="${ICONS_DIR}/${size}x${size}/apps"
    mkdir -p "${target_dir}"
    if [ -f "${REPO_DIR}/assets/icons/veil-on-${size}.png" ]; then
        cp -f "${REPO_DIR}/assets/icons/veil-on-${size}.png" "${target_dir}/veil.png"
    fi
    if [ -f "${REPO_DIR}/assets/icons/veil-off-${size}.png" ]; then
        cp -f "${REPO_DIR}/assets/icons/veil-off-${size}.png" "${target_dir}/veil-off.png"
    fi
done
gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" 2>/dev/null || true
echo -e "      ${GREEN}✓${RESET} System icon cache updated."

# Register native-messaging manifests
echo -e "\n${PURPLE}[4/5] Registering Native Messaging Manifests Across Browsers...${RESET}"
if ! "${BIN_DIR}/veil" install-extension; then
    echo -e "      ${AMBER}Browser registration is pending. Run veil install-extension after installing a supported browser.${RESET}"
fi

# Set up autostart last, when theres actually an app to launch.
echo -e "\n${PURPLE}[5/5] Configuring Desktop Integration & Background Service...${RESET}"
"${BIN_DIR}/veil" autostart --enable

echo -e "\n${GREEN}${BOLD}================================================================${RESET}"
echo -e "${GREEN}${BOLD}           VEIL INSTALLED SUCCESSFULLY               ${RESET}"
echo -e "${GREEN}${BOLD}================================================================${RESET}"
echo -e "  ✦ CLI Suite:            ${BOLD}veil --help${RESET}"
echo -e "  ✦ Multi-Category Test:  ${BOLD}veil test https://example.net${RESET}"
echo -e "  ✦ Browser Diagnostics:  ${BOLD}veil browsers${RESET}"
echo -e "  ✦ Launch Tray Menu:     ${BOLD}veil tray${RESET}"
echo -e "\n${DIM}Add ${BIN_DIR} to your PATH if not already present:${RESET}"
echo -e "  export PATH=\"\$HOME/.local/bin:\$PATH\"\n"
