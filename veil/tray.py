"""Veil's PySide6 tray menu.

Violet when protection is on, amber when it's off. The actual popup and
tray-icon behavior still depend on the desktop.
"""

import os
import sys

# X11/Xwayland wants XCB here or placement gets kinda wierd.
if os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ["KSNI_NO_DBUSMENU"] = "1"

import logging
import subprocess
from pathlib import Path
from veil.paths import icon_directory
from PySide6 import QtWidgets, QtGui, QtCore, QtDBus
from veil.service import VeilService


class VeilHeaderWidget(QtWidgets.QWidget):
    """The tray header. Somehow the smallest UI bits take the most fiddling."""
    def __init__(self, is_active: bool = False, counts: dict | None = None, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.is_active = is_active
        self.counts = counts or {"tabs": 0, "bookmarks": 0, "history_urls": 0}
        self.setFixedHeight(92)
        self.setMinimumWidth(330)
        self._init_ui()

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(330, 92)

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(330, 92)

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(10)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._update_icon()
        top_row.addWidget(self.icon_label)

        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(1)
        self.title_lbl = QtWidgets.QLabel("VEIL")
        self.sub_lbl = QtWidgets.QLabel("Living Horizon Companion")
        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.sub_lbl)
        top_row.addLayout(title_box)

        top_row.addStretch()

        self.badge = QtWidgets.QLabel()
        top_row.addWidget(self.badge)
        layout.addLayout(top_row)

        self.stats_lbl = QtWidgets.QLabel()
        self.stats_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stats_lbl)

        self._apply_style()

    def _update_icon(self):
        config_dir = Path.home() / ".config" / "veil" / "icons"
        asset_dir = icon_directory()
        filename = "veil-on-48.png" if self.is_active else "veil-off-48.png"
        p = config_dir / filename
        if not p.exists():
            p = asset_dir / filename
        if not p.exists():
            filename = "veil-on.png" if self.is_active else "veil-off.png"
            p = config_dir / filename
            if not p.exists():
                p = asset_dir / filename

        pix = QtGui.QPixmap(str(p))
        if not pix.isNull():
            pix = pix.scaled(34, 34, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
            self.icon_label.setPixmap(pix)

    def _apply_style(self):
        if self.is_active:
            self.title_lbl.setStyleSheet("font-size: 13.5px; font-weight: 800; letter-spacing: 2.2px; color: #f6eeff;")
            self.sub_lbl.setStyleSheet("font-size: 10px; font-weight: 500; color: #a894b8;")
            self.badge.setText("● SHIELD ACTIVE")
            self.badge.setStyleSheet("""
                background: rgba(171, 101, 235, 0.18);
                color: #d8b4fe;
                border: 1px solid rgba(203, 156, 255, 0.4);
                border-radius: 11px;
                padding: 3px 9px;
                font-size: 9.5px;
                font-weight: 700;
                letter-spacing: 0.6px;
            """)
            stats_text = (
                f"{self.counts.get('tabs', 0)} tabs  ·  {self.counts.get('bookmarks', 0)} bookmarks  ·  "
                f"{self.counts.get('history_urls', 0)} history"
            )
            self.stats_lbl.setText(stats_text)
            self.stats_lbl.setStyleSheet("""
                background: rgba(255, 255, 255, 0.05);
                color: #d1c1de;
                border: 1px solid rgba(203, 156, 255, 0.15);
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 500;
            """)
        else:
            self.title_lbl.setStyleSheet("font-size: 13.5px; font-weight: 800; letter-spacing: 2.2px; color: #fff3e4;")
            self.sub_lbl.setStyleSheet("font-size: 10px; font-weight: 500; color: #b89d89;")
            self.badge.setText("○ STANDBY")
            self.badge.setStyleSheet("""
                background: rgba(255, 160, 62, 0.18);
                color: #ffc98b;
                border: 1px solid rgba(255, 204, 127, 0.4);
                border-radius: 11px;
                padding: 3px 9px;
                font-size: 9.5px;
                font-weight: 700;
                letter-spacing: 0.6px;
            """)
            stats_text = (
                f"{self.counts.get('tabs', 0)} tabs  ·  {self.counts.get('bookmarks', 0)} bookmarks  ·  "
                f"{self.counts.get('history_urls', 0)} history"
            ) if any(self.counts.values()) else "Protected Workspace  ·  Ready"
            self.stats_lbl.setText(stats_text)
            self.stats_lbl.setStyleSheet("""
                background: rgba(255, 255, 255, 0.05);
                color: #d9c5b2;
                border: 1px solid rgba(255, 204, 127, 0.15);
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 500;
            """)

    def update_state(self, is_active: bool, counts: dict):
        self.is_active = is_active
        self.counts = counts
        self._update_icon()
        self._apply_style()
        self.adjustSize()


class VeilHeaderAction(QtWidgets.QWidgetAction):
    def __init__(self, parent_menu: QtWidgets.QMenu, is_active: bool = False, counts: dict | None = None):
        super().__init__(parent_menu)
        self.header_widget = VeilHeaderWidget(is_active=is_active, counts=counts)
        self.setDefaultWidget(self.header_widget)


class LivingHorizonMenu(QtWidgets.QMenu):
    """Rounded QMenu without the ugly square corners. Yes, that was a thing."""
    def __init__(self, title: str = "", parent: QtWidgets.QWidget | None = None):
        super().__init__(title, parent)
        self.radius = 12.0
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog |
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.WindowStaysOnTopHint |
            QtCore.Qt.WindowType.NoDropShadowWindowHint
        )
        self.bg_color = QtGui.QColor("#150e10")
        self.border_color = QtGui.QColor(255, 204, 127, int(255 * 0.35))
        self._focus_timer = QtCore.QTimer(self)
        self._focus_timer.setInterval(100)
        self._focus_timer.timeout.connect(self._check_focus)

    def _check_focus(self):
        if self.isVisible() and not self.isActiveWindow():
            active_win = QtWidgets.QApplication.activeWindow()
            if not (active_win and isinstance(active_win, QtWidgets.QMenu)):
                self.close()

    def _update_mask(self):
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(self.rect()), self.radius, self.radius)
        self.setMask(QtGui.QRegion(path.toFillPolygon().toPolygon()))

    def _reanchor_to_screen(self):
        screen = QtGui.QGuiApplication.primaryScreen()
        if not screen:
            return
        avail = screen.availableGeometry()
        screen_geo = screen.geometry()
        if avail.bottom() < screen_geo.bottom():
            target_bottom = avail.bottom() - 6
            new_y = target_bottom - self.height()
            if self.y() != new_y:
                self.move(self.x(), new_y)

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        self._update_mask()
        self._reanchor_to_screen()

    def showEvent(self, event: QtGui.QShowEvent):
        super().showEvent(event)
        self._update_mask()
        self._reanchor_to_screen()
        self._focus_timer.start()

    def hideEvent(self, event: QtGui.QHideEvent):
        self._focus_timer.stop()
        super().hideEvent(event)

    def changeEvent(self, event: QtCore.QEvent):
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.Type.ActivationChange, QtCore.QEvent.Type.WindowDeactivate):
            if not self.isActiveWindow():
                active_win = QtWidgets.QApplication.activeWindow()
                if not (active_win and isinstance(active_win, QtWidgets.QMenu)):
                    self.close()

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        super().focusOutEvent(event)
        active_win = QtWidgets.QApplication.activeWindow()
        if not (active_win and isinstance(active_win, QtWidgets.QMenu)):
            self.close()

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() in (QtCore.Qt.Key.Key_Escape, QtCore.Qt.Key.Key_Alt):
            self.close()
            return
        super().keyPressEvent(event)

    def set_palette_colors(self, bg_hex: str, border_qcolor: QtGui.QColor):
        self.bg_color = QtGui.QColor(bg_hex)
        self.border_color = border_qcolor
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)

        painter.setPen(QtGui.QPen(self.border_color, 1))
        painter.setBrush(self.bg_color)
        painter.drawPath(path)

        painter.save()
        painter.setClipPath(path)
        super().paintEvent(event)
        painter.restore()


@QtCore.ClassInfo({"D-Bus Interface": "org.kde.StatusNotifierItem"})
class VeilNativeSNIAdaptor(QtDBus.QDBusAbstractAdaptor):
    NewTitle = QtCore.Signal()
    NewIcon = QtCore.Signal()
    NewStatus = QtCore.Signal(str)
    NewToolTip = QtCore.Signal()

    def __init__(self, parent_sni: "VeilNativeSNI"):
        super().__init__(parent_sni)
        self.sni = parent_sni

    @QtCore.Property(str)
    def Category(self):
        return "ApplicationStatus"

    @QtCore.Property(str)
    def Id(self):
        return "Veil"

    @QtCore.Property(str)
    def Title(self):
        if self.sni.app.camouflage_mode:
            return "System Monitor"
        return "Veil"

    @QtCore.Property(str)
    def Status(self):
        return "Active"

    @QtCore.Property(int)
    def WindowId(self):
        return 0

    @QtCore.Property(str)
    def IconThemePath(self):
        return str(self.sni.config_dir)

    @QtCore.Property(str)
    def IconName(self):
        if self.sni.app.camouflage_mode:
            return "utilities-system-monitor"
        return "veil-on-48" if self.sni.app.service.is_active else "veil-off-48"

    @QtCore.Property(bool)
    def ItemIsMenu(self):
        return False

    @QtCore.Property(QtDBus.QDBusObjectPath)
    def Menu(self):
        return QtDBus.QDBusObjectPath("/NO_DBUSMENU")

    @QtCore.Slot(int, int)
    def Activate(self, x, y):
        self.sni.app._do_toggle()

    @QtCore.Slot(int, int)
    def SecondaryActivate(self, x, y):
        self.sni.app._do_toggle()

    @QtCore.Slot(int, int)
    def ContextMenu(self, x, y):
        if hasattr(self.sni.app, "menu") and self.sni.app.menu.isVisible():
            self.sni.app.menu.close()
            return
        self.sni.app._show_tray_context_menu(x, y)

    @QtCore.Slot(int, str)
    def Scroll(self, delta, orientation):
        pass

    @QtCore.Slot(str)
    def ProvideXdgActivationToken(self, token: str):
        pass


class VeilNativeSNI(QtCore.QObject):
    def __init__(self, tray_app: "VeilTrayApp"):
        super().__init__()
        self.app = tray_app
        self.config_dir = Path.home() / ".config" / "veil" / "icons"
        self.adaptor = VeilNativeSNIAdaptor(self)

    def update_state(self, is_active: bool):
        self.adaptor.NewIcon.emit()
        self.adaptor.NewTitle.emit()
        self.adaptor.NewStatus.emit("Active")


class TraySignalBridge(QtCore.QObject):
    state_changed = QtCore.Signal(bool, str)


class VeilTrayApp(QtWidgets.QApplication):
    def __init__(self, argv: list[str], service: VeilService | None = None):
        super().__init__(argv)
        self.setApplicationName("Veil")
        self.setApplicationDisplayName("Veil")
        self.setDesktopFileName("veil")
        self.setQuitOnLastWindowClosed(False)

        self.bridge = TraySignalBridge()
        self.bridge.state_changed.connect(self._on_service_state_changed)

        self.service = service or VeilService()
        self.service.on_state_changed = lambda is_active, msg: self.bridge.state_changed.emit(is_active, msg)

        # Clipboard hooks
        cb = QtGui.QGuiApplication.clipboard()
        self.service.on_clipboard_query = lambda: cb.text()
        self.service.on_clipboard_clear = lambda: cb.clear()

        # Configs
        self.camouflage_mode = (Path.home() / ".config" / "veil" / "camouflage.enabled").exists()
        self.sound_enabled = (Path.home() / ".config" / "veil" / "sound.enabled").exists()
        self.reveal_on_demand = not (Path.home() / ".config" / "veil" / "reveal_on_demand.disabled").exists()

        # Load icons
        asset_dir = icon_directory()
        config_dir = Path.home() / ".config" / "veil" / "icons"

        self.icon_on = QtGui.QIcon()
        for sz in [16, 22, 32, 48, 64, 128, 256, 512, 1024]:
            for d in [config_dir, asset_dir]:
                p = d / f"veil-on-{sz}.png"
                if p.exists():
                    self.icon_on.addFile(str(p), QtCore.QSize(sz, sz))
                    break

        self.icon_off = QtGui.QIcon()
        for sz in [16, 22, 32, 48, 64, 128, 256, 512, 1024]:
            for d in [config_dir, asset_dir]:
                p = d / f"veil-off-{sz}.png"
                if p.exists():
                    self.icon_off.addFile(str(p), QtCore.QSize(sz, sz))
                    break

        self.icon_camo = QtGui.QIcon.fromTheme("utilities-system-monitor")
        if self.icon_camo.isNull():
            self.icon_camo = self.icon_off

        self.setWindowIcon(self.icon_on)

        # KDE prefers StatusNotifierItem. Desktop tray stuff is never univeral.
        self.bus = QtDBus.QDBusConnection.sessionBus()
        self.sni = VeilNativeSNI(self)
        self.bus.registerObject("/StatusNotifierItem", self.sni)

        watcher = QtDBus.QDBusInterface("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher", self.bus)
        if watcher.isValid():
            watcher.call("RegisterStatusNotifierItem", self.bus.baseService())
            self.tray = None
        else:
            # XFCE and friends may need the older tray route. Because of course.
            self.tray = QtWidgets.QSystemTrayIcon(self)
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()

        # Build the tray menu.
        self.menu = LivingHorizonMenu()
        self.menu.setMinimumWidth(330)
        self.menu.aboutToShow.connect(lambda: self._update_tray_ui(self.service.is_active))

        # Custom Header
        self.header_action = VeilHeaderAction(self.menu, is_active=self.service.is_active)
        self.header_widget = self.header_action.header_widget
        self.menu.addAction(self.header_action)

        self.menu.addSeparator()

        # Reveal on Demand is a toggle, not another one-shot button.
        self.action_reveal_on_demand = self.menu.addAction("Reveal on Demand (Phase 2)")
        self.action_reveal_on_demand.setCheckable(True)
        self.action_reveal_on_demand.setChecked(self.reveal_on_demand)
        self.action_reveal_on_demand.triggered.connect(self._toggle_reveal_on_demand)

        # Reveal All only shows in standby, for obvios reasons.
        self.action_reveal_all = self.menu.addAction("Reveal All Concealed Tabs")
        self.action_reveal_all.triggered.connect(self._on_reveal_all_tabs)

        self.menu.addSeparator()

        # Preferences Submenu
        self.preferences_menu = LivingHorizonMenu("Preferences", self.menu)
        self.menu.addMenu(self.preferences_menu)
        self.action_camo = self.preferences_menu.addAction("Camouflage Mode")
        self.action_camo.setCheckable(True)
        self.action_camo.setChecked(self.camouflage_mode)
        self.action_camo.triggered.connect(self._toggle_camouflage_mode)

        self.action_sound = self.preferences_menu.addAction("Discreet Audio Chime")
        self.action_sound.setCheckable(True)
        self.action_sound.setChecked(self.sound_enabled)
        self.action_sound.triggered.connect(self._toggle_sound)

        # Tools Submenu
        self.tools_menu = LivingHorizonMenu("Tools", self.menu)
        self.menu.addMenu(self.tools_menu)
        self.action_boss_key = self.tools_menu.addAction("Emergency Boss Key\tCtrl+Alt+V")
        self.action_boss_key.triggered.connect(self._on_boss_key)

        self.action_panic = self.tools_menu.addAction("Instant Panic (Purge & Minimize)")
        self.action_panic.triggered.connect(self._on_panic)

        self.action_sanitize = self.tools_menu.addAction("Sanitize Clipboard")
        self.action_sanitize.triggered.connect(self._on_sanitize_clipboard)

        self.action_shred = self.tools_menu.addAction("Shred Temporary Caches & Thumbnails")
        self.action_shred.triggered.connect(self._on_shred_caches)

        self.tools_menu.addSeparator()
        self.action_rescan = self.tools_menu.addAction("Rescan Installed Browsers")
        self.action_rescan.triggered.connect(self._on_rescan_profiles)

        self.menu.addSeparator()

        # Quit Action
        self.action_quit = self.menu.addAction("Quit Veil")
        self.action_quit.triggered.connect(self._on_quit)

        self._update_tray_ui(self.service.is_active, show_notification=False)
        if self.tray:
            self.tray.show()

    def _apply_menu_palette(self, is_active: bool):
        surface = "#110b17" if is_active else "#150e10"
        outline = "rgba(203, 156, 255, 0.25)" if is_active else "rgba(255, 204, 127, 0.25)"
        accent = "#d8b4fe" if is_active else "#ffc98b"
        hover = "rgba(171, 101, 235, 0.20)" if is_active else "rgba(255, 160, 62, 0.20)"
        text_main = "#f6eeff" if is_active else "#fff3e4"
        text_muted = "#a795b8" if is_active else "#ba9e8b"

        icon_dir = Path.home() / ".config" / "veil" / "icons"
        if not icon_dir.exists():
            icon_dir = icon_directory()

        check_svg = str(icon_dir / ("menu-check-purple.svg" if is_active else "menu-check-amber.svg"))
        arrow_svg = str(icon_dir / ("menu-arrow-purple.svg" if is_active else "menu-arrow-amber.svg"))

        stylesheet = f"""
            QMenu {{
                min-width: 330px;
                background-color: transparent;
                color: {text_main};
                border: none;
                border-radius: 12px;
                padding: 6px 4px;
                font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
                font-size: 12.5px;
            }}
            QMenu::item {{
                padding: 7px 28px 7px 14px;
                margin: 2px 4px;
                border-radius: 6px;
                color: {text_main};
            }}
            QMenu::item:selected {{
                background-color: {hover};
                color: {accent};
            }}
            QMenu::item:disabled {{
                color: {text_muted};
            }}
            QMenu::separator {{
                height: 1px;
                margin: 6px 12px;
                background: {outline};
            }}
            QMenu::indicator {{
                width: 14px;
                height: 14px;
                margin-left: 6px;
            }}
            QMenu::indicator:checked {{
                image: url("{check_svg}");
                background-color: {accent};
                border: 1px solid {accent};
                border-radius: 4px;
            }}
            QMenu::indicator:unchecked {{
                image: none;
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid {outline};
                border-radius: 4px;
            }}
            QMenu::right-arrow {{
                image: url("{arrow_svg}");
                width: 10px;
                height: 10px;
                margin-right: 8px;
            }}
        """
        self.setStyleSheet(stylesheet)
        self.menu.setStyleSheet(stylesheet)
        border_qcolor = QtGui.QColor(203, 156, 255, int(255 * 0.35)) if is_active else QtGui.QColor(255, 204, 127, int(255 * 0.35))
        if hasattr(self, "menu") and isinstance(self.menu, LivingHorizonMenu):
            self.menu.set_palette_colors(surface, border_qcolor)
        if hasattr(self, "preferences_menu"):
            self.preferences_menu.setStyleSheet(stylesheet)
            if isinstance(self.preferences_menu, LivingHorizonMenu):
                self.preferences_menu.set_palette_colors(surface, border_qcolor)
        if hasattr(self, "tools_menu"):
            self.tools_menu.setStyleSheet(stylesheet)
            if isinstance(self.tools_menu, LivingHorizonMenu):
                self.tools_menu.set_palette_colors(surface, border_qcolor)

    def _show_tray_context_menu(self, x: int = 0, y: int = 0):
        self._update_tray_ui(self.service.is_active)
        if hasattr(self, 'header_widget'):
            self.header_widget.setVisible(True)
        self.menu.adjustSize()
        sz = self.menu.sizeHint()
        screen = QtGui.QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QtCore.QRect(0, 0, 1920, 1034)
        screen_geo = screen.geometry() if screen else QtCore.QRect(0, 0, 1920, 1080)

        if x <= 0 or y <= 0:
            cursor_pos = QtGui.QCursor.pos()
            x, y = cursor_pos.x(), cursor_pos.y()

        px = min(max(avail.left() + 8, x - sz.width() // 2), avail.right() - sz.width() - 8)

        if avail.bottom() < screen_geo.bottom():
            py = avail.bottom() - sz.height() - 6
        elif avail.top() > screen_geo.top():
            py = avail.top() + 6
        else:
            py = max(avail.top() + 6, min(avail.bottom() - sz.height() - 6, y - sz.height() - 6))

        self.menu.popup(QtCore.QPoint(px, py))
        self.menu.raise_()
        self.menu.activateWindow()
        QtCore.QTimer.singleShot(0, self._ensure_header_visible)

    def _ensure_header_visible(self):
        if hasattr(self, "header_widget"):
            self.header_widget.show()
            for child in self.header_widget.findChildren(QtWidgets.QWidget):
                child.show()

    def _on_tray_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            self._do_toggle()
        elif reason == QtWidgets.QSystemTrayIcon.ActivationReason.Context:
            cursor = QtGui.QCursor.pos()
            self._show_tray_context_menu(cursor.x(), cursor.y())

    def _do_toggle(self):
        new_state = self.service.toggle()
        self._play_sound(new_state)

    def _play_sound(self, is_active: bool):
        if not self.sound_enabled:
            return
        sound_name = "device-added" if is_active else "device-removed"
        try:
            subprocess.Popen(["canberra-gtk-play", "-i", sound_name, "-d", "Veil"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _toggle_reveal_on_demand(self):
        self.reveal_on_demand = self.action_reveal_on_demand.isChecked()
        flag = Path.home() / ".config" / "veil" / "reveal_on_demand.disabled"
        flag.parent.mkdir(parents=True, exist_ok=True)
        if not self.reveal_on_demand:
            flag.touch()
        else:
            if flag.exists():
                flag.unlink()
        self.service.ipc.broadcast({
            "type": "reveal_preference",
            "reveal_on_demand": self.reveal_on_demand
        })

    def _toggle_sound(self):
        self.sound_enabled = self.action_sound.isChecked()
        flag = Path.home() / ".config" / "veil" / "sound.enabled"
        flag.parent.mkdir(parents=True, exist_ok=True)
        if self.sound_enabled:
            flag.touch()
            self._play_sound(True)
        else:
            if flag.exists():
                flag.unlink()

    def _on_reveal_all_tabs(self):
        self.service.ipc.broadcast({"type": "reveal_all_tabs"})

    def _on_boss_key(self):
        self.service.boss_key()
        self._play_sound(True)

    def _on_panic(self):
        self.service.panic()
        self._play_sound(True)

    def _on_sanitize_clipboard(self):
        self.service.sanitize_clipboard()

    def _toggle_camouflage_mode(self):
        self.camouflage_mode = self.action_camo.isChecked()
        camo_file = Path.home() / ".config" / "veil" / "camouflage.enabled"
        camo_file.parent.mkdir(parents=True, exist_ok=True)
        if self.camouflage_mode:
            camo_file.touch()
        else:
            if camo_file.exists():
                camo_file.unlink()
        self._update_tray_ui(self.service.is_active, show_notification=False)

    def _on_shred_caches(self):
        self.service.profile_manager.shred_all_caches()

    def _on_rescan_profiles(self):
        self.service.profile_manager.discover_profiles()

    def _on_service_state_changed(self, is_active: bool, message: str):
        self._update_tray_ui(is_active, show_notification=False)

    def _update_tray_ui(self, is_active: bool, show_notification: bool = False):
        try:
            counts = self.service.vault.count_concealed_items()
        except Exception:
            counts = {"tabs": 0, "bookmarks": 0, "history_urls": 0}

        if getattr(self, "_current_palette_is_active", None) != is_active:
            self._apply_menu_palette(is_active)
            self._current_palette_is_active = is_active

        self.action_reveal_all.setVisible(not is_active)

        if hasattr(self, "header_widget"):
            self.header_widget.update_state(is_active, counts)
            self.header_widget.show()
            self.menu.adjustSize()
            if hasattr(self.menu, "_reanchor_to_screen"):
                self.menu._reanchor_to_screen()

        total_concealed = (
            counts.get("bookmarks", 0) +
            counts.get("history_urls", 0) +
            counts.get("tabs", 0) +
            counts.get("search_terms", 0)
        )

        if hasattr(self, "sni") and self.sni:
            self.sni.update_state(is_active)

        if getattr(self, "tray", None):
            if self.camouflage_mode:
                self.tray.setIcon(self.icon_camo)
                self.tray.setToolTip(f"System Monitor: {'Normal' if is_active else 'Idle'}")
            else:
                if is_active:
                    self.tray.setIcon(self.icon_on)
                    tip = f"Veil: Protected ({total_concealed} items shielded)" if total_concealed > 0 else "Veil: Protected"
                    self.tray.setToolTip(tip)
                else:
                    self.tray.setIcon(self.icon_off)
                    self.tray.setToolTip("Veil: Standby")

    def _on_quit(self):
        self.service.stop()
        self.quit()


def main():
    from veil.ipc_server import IPCClient
    client = IPCClient()
    is_running = client.connect(timeout=0.5)

    if "--status" in sys.argv or "status" in sys.argv:
        if is_running:
            client.send({"type": "status"})
            res = client.receive(timeout=1.5)
            client.close()
            active = res.get("active") if res else False
            print(f"Veil is {'ACTIVE (SHIELDED)' if active else 'INACTIVE (RESTORED)'}")
        else:
            from veil.vault import Vault
            v = Vault()
            active = bool(v.get_state("is_active", False))
            print(f"Veil daemon not running. Stored state is {'ACTIVE' if active else 'INACTIVE'}")
        return

    if "--toggle" in sys.argv or "toggle" in sys.argv:
        if is_running:
            client.send({"type": "toggle"})
            res = client.receive(timeout=2.0)
            client.close()
            active = res.get("active") if res else False
            print(f"Veil toggled -> {'ACTIVE' if active else 'INACTIVE'}")
        else:
            srv = VeilService()
            new_state = srv.toggle()
            srv.stop()
            print(f"Veil toggled -> {'ACTIVE' if new_state else 'INACTIVE'}")
        return

    if is_running:
        print("Veil is already running in the system tray.")
        client.close()
        return

    if os.environ.get("DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ["KSNI_NO_DBUSMENU"] = "1"

    app = VeilTrayApp(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
