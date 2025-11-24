"""
welcomeScreenv002.py

this is the usb-gated welcome screen for pallet portal

goals:
- fullscreen-friendly black theme
- centered glitch "WELCOME" title (from glitchEffectv001.py)
- status + debug log for usb watcher
- emits proceed(shipment_list, mount_dir) when a valid manifest is found
- after 30 seconds on this screen with no manifest, emits idleTimeout()
- supports 4-button exit combo (ctrl + c + v + enter/return)
"""

import os, sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QHBoxLayout,
    QFrame,
)

from manifestWatcherv001 import ShipmentList, USBWatcher  #this handles the usb + manifest
from glitchEffectv001 import GlitchText  #this draws the spiderverse-style welcome text


class WelcomeScreen(QWidget):
    proceed = pyqtSignal(object, str)  #(ShipmentList, mount_dir)
    idleTimeout = pyqtSignal()  #fired after 30 s on this screen with no manifest

    def __init__(self, mount_roots=None, parent=None):
        super().__init__(parent)
        self.setObjectName("welcomeRoot")
        self.setFocusPolicy(Qt.StrongFocus)  #so key events land here
        self._pressed = set()  #tracks keys for exit combo
        self._manifest_loaded = False  #set true once we get a valid list

        #---------- root layout ----------
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(20)

        #glitch title (from glitchEffectv001)
        self.glitch_title = GlitchText(text="WELCOME", led_driver=None)  #leds handled elsewhere
        self.glitch_title.setMinimumHeight(140)
        root.addWidget(self.glitch_title)

        #subtitle inside a soft white pill
        pill = QFrame()
        pill.setObjectName("welcomePill")
        pill.setFrameShape(QFrame.NoFrame)
        pill_layout = QHBoxLayout(pill)
        pill_layout.setContentsMargins(40, 18, 40, 18)

        sub = QLabel("insert flash drive with barcodes file to begin")
        sub.setAlignment(Qt.AlignCenter)
        sub.setFont(QFont("Arial", 20))
        sub.setStyleSheet("color:#000000;")
        pill_layout.addWidget(sub)

        root.addWidget(pill)

        #status label (live usb watcher messages)
        self.status = QLabel("waiting for usb...")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont("Arial", 14))
        self.status.setStyleSheet("color:#eaeaea;")
        root.addWidget(self.status)

        #debug log
        self.debug = QTextEdit()
        self.debug.setReadOnly(True)
        self.debug.setStyleSheet(
            "QTextEdit {background-color:#101010;color:#d0d0d0;border-radius:8px;}"
        )
        root.addWidget(self.debug, stretch=1)

        #hint at bottom
        hint = QLabel(
            "insert flash drive with barcodes.txt to begin\n"
            "press C then V to force a manual rescan\n"
            "hold ctrl + c + v and press enter/return to exit"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setFont(QFont("Arial", 11))
        hint.setStyleSheet("color:#888888;")
        root.addWidget(hint)

        #apply theme styles
        self.setStyleSheet(
            """
            QWidget#welcomeRoot {
                background-color:#000000;
            }
            QFrame#welcomePill {
                background-color:#ffffff;
                border-radius:40px;
            }
            """
        )

        #---------- usb watcher ----------
        self.watcher = USBWatcher(mount_roots=mount_roots)
        self.watcher.status.connect(self._on_status)
        self.watcher.validListFound.connect(self._on_valid)
        self.watcher.start()

        #---------- idle timer (for wait screen fallback) ----------
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)
        self._start_idle_timer()

    #---------- internal helpers ----------
    def _start_idle_timer(self):
        self._idle_timer.stop()
        self._idle_timer.start(30000)  #30 s

    def _cancel_idle_timer(self):
        self._idle_timer.stop()

    def _on_idle_timeout(self):
        if self._manifest_loaded:
            return  #already moving on
        #still on welcome with no manifest → let main window decide to show wait screen
        self.idleTimeout.emit()

    def _on_status(self, msg: str):
        self.status.setText(msg)
        self.debug.append(msg)

    def _on_valid(self, shipment: ShipmentList, root_dir: str):
        #valid manifest found → stop idle + watcher and hand off to main
        self._manifest_loaded = True
        self._cancel_idle_timer()
        try:
            self.watcher.stop()
        except Exception:
            pass

        self.status.setText(f"valid manifest found at: {root_dir}")
        self.debug.append(f"proceeding with manifest from: {root_dir}")
        self.proceed.emit(shipment, root_dir)

    #---------- lifecycle ----------
    def showEvent(self, e):
        super().showEvent(e)
        #reset state each time welcome becomes visible again
        self._pressed.clear()
        self._manifest_loaded = False
        self._start_idle_timer()
        try:
            self.watcher.start()
        except Exception:
            pass
        self.status.setText("waiting for usb...")
        self.setFocus()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._cancel_idle_timer()
        try:
            self.watcher.stop()
        except Exception:
            pass

    #---------- key handling ----------
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)

        mods = e.modifiers()

        #secret exit combo: hold ctrl + c + v and press enter/return
        if (
            (mods & Qt.ControlModifier)
            and Qt.Key_C in self._pressed
            and Qt.Key_V in self._pressed
            and k in (Qt.Key_Return, Qt.Key_Enter)
        ):
            from PyQt5.QtWidgets import QApplication

            QApplication.quit()
            return

        #manual rescan shortcut: C then V (no modifiers)
        if k == Qt.Key_C and not mods:
            self._last_key = "C"
            e.accept()
            return

        if k == Qt.Key_V and not mods and getattr(self, "_last_key", None) == "C":
            self._on_status("manual rescan requested.")
            try:
                self.watcher.scan_once()
            except Exception:
                pass
            self._last_key = None
            e.accept()
            return

        #anything else resets the simple C→V sequence
        self._last_key = None
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)


#standalone test harness
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    w = WelcomeScreen()
    w.showFullScreen()
    sys.exit(app.exec_())
