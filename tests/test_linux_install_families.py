"""Installer package-manager selection."""

import subprocess
from pathlib import Path

import pytest


INSTALLER = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"


@pytest.mark.parametrize(
    ("distribution", "family", "manager"),
    [
        ("fedora", "", "dnf"),
        ("rocky", "rhel centos fedora", "dnf"),
        ("desktop-spin", "fedora", "dnf"),
        ("ubuntu", "debian", "apt-get"),
        ("linuxmint", "ubuntu debian", "apt-get"),
        ("zorin", "ubuntu debian", "apt-get"),
        ("arch", "", "pacman"),
        ("garuda", "arch", "pacman"),
        ("cachyos", "arch", "pacman"),
        ("opensuse-tumbleweed", "suse", "zypper"),
        ("desktop-variant", "suse", "zypper"),
    ],
)
def test_package_manager_selection(distribution, family, manager):
    script = INSTALLER.read_text()
    function = script.split("install_dependencies() {", 1)[1].split(
        "\n# Dependency installation is optional", 1
    )[0]
    command = (
        "set -e\n"
        f"DISTRO_ID='{distribution}'\n"
        f"DISTRO_LIKE='{family}'\n"
        'DIM=""; RESET=""\n'
        'sudo() { printf "package-manager:%s\\n" "$1"; }\n'
        "install_dependencies() {" + function + "\n"
        "install_dependencies\n"
    )
    result = subprocess.run(["bash", "-c", command], check=True, text=True, capture_output=True)
    calls = [line.removeprefix("package-manager:") for line in result.stdout.splitlines()
             if line.startswith("package-manager:")]
    assert calls
    assert set(calls) == {manager}


def test_install_completes_without_browser_profile(tmp_path):
    import os

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    result = subprocess.run(
        ["bash", str(INSTALLER), "--no-deps"],
        env=env, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "registration is pending" in result.stdout
    assert (tmp_path / ".local/bin/veil").is_file()
    assert (tmp_path / ".config/systemd/user/veil.service").is_file()
