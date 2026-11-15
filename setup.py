#!/usr/bin/env python3
from pathlib import Path
import shutil
from setuptools import setup, find_packages
from setuptools.command.build_py import build_py as setuptools_build_py


class build_py(setuptools_build_py):
    """Ship the extension and tray assets with system Python packages."""

    def run(self):
        super().run()
        root = Path(__file__).resolve().parent
        for name in ("assets", "browser-extension"):
            shutil.copytree(root / name, Path(self.build_lib) / "veil" / "resources" / name,
                            dirs_exist_ok=True)


setup(
    name="veil",
    cmdclass={"build_py": build_py},
    version="1.0",
    description="Linux browser privacy companion",
    author="Bluenochian",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "veil": [],
    },
    install_requires=[
        "cryptography>=41.0.0",
        "PySide6>=6.5.0",
    ],
    entry_points={
        "console_scripts": [
            "veil = veil.cli:main",
            "veil-native-host = veil.native_host:run_bridge",
        ],
    },
)
