"""
GUIvTechSymposium003.py

main stacked gui shell for pallet portal tech symposium demo

screens (separate modules):
 - welcomeScreenv002.WelcomeScreen
 - pingScreenv006.PingScreen
 - shipScreenv010.ShipScreen
 - viewOrderScreenv004.ViewOrderScreen
 - waitScreenv005.WaitScreen (used as idle screensaver overlay)

other helpers:
 - ledWorkerv001.DualStripDriver  (physical led strips, optional)
 - glitchEffectv001.GlitchText    (used inside welcome + others)

behavior:
 - app starts full screen on the welcome screen
 - while on welcome, an idle timer runs; after 30 seconds it shows the
   bouncing-logo wait screen as a full-screen overlay
 - any of the four nav keys (Ctrl, C, V, Enter/Return) will close the
   wait screen and return to the welcome screen, restarting the timer
 - global "panic" exit: hold Ctrl + C + V, then press Enter/Return

dev navigation (for now, to move between screens easily):
 - '1' = welcome
 - '2' = ping screen
 - '3' = ship screen
 - '4' = view orders
"""

import sys
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication, QStackedWidget

# ------------------------------------------------------------
#  optional led driver
# ------------------------------------------------------------
try:
    from ledWorkerv001 import DualStripDriver
except Exception:
    DualStripDriver = None

    class DualStripDriverDummy:
        def set_all(self, rgb):
            pass

        def to_cyan(self):
            pass

        def to_red(self):
            pass

        def to_green(self):
            pass

        def to_magenta(self):
            pass

        def to_white(self):
            pass

        def pulse_cyan(self, enable=True):
            pass

        def flash(self, rgb, flashes=3, duration=0.15):
            pass

        def stop(self):
            pass


# ------------------------------------------------------------
#  screen imports
# ------------------------------------------------------------
from welcomeScreenv002 import WelcomeScreen
from pingScreenv006 import PingScreen
from shipScreenv010 import ShipScreen
from viewOrderScreenv004 import ViewOrderScreen
from waitScreenv005 import WaitScreen as BaseWaitScreen


# ------------------------------------------------------------
#  idle wait screen wrapper
# ------------------------------------------------------------
class IdleWaitScreen(BaseWaitScreen):
    """
    wraps the standalone waitScreenv005.WaitScreen so that:
      - it behaves as a temporary overlay (no app quit)
      - any of the four nav keys (ctrl, c, v, enter/return) closes it
    """

    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__()
        self._parent = parent

    def keyPressEvent(self, e):
        k = e.key()
        # keys that should dismiss the wait screen and return to welcome
        if k in (Qt.Key_Control, Qt.Key_C, Qt.Key_V, Qt.Key_Return, Qt.Key_Enter):
            self.exit_requested.emit()
            self.close()
            return

        # ignore other keys (do NOT call super() to avoid the old quit combo)
        # super().keyPressEvent(e)


# ------------------------------------------------------------
#  main stacked window
# ------------------------------------------------------------
class MainWindow(QStackedWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Pallet Portal - Tech Symposium GUI")
        self._pressed = set()  # for global exit combo
        self.wait_screen = None

        # -----------------------------------------------------------------
        # leds
        # -----------------------------------------------------------------
        if DualStripDriver is not None:
            try:
                self.leds = DualStripDriver(num_per_strip=5)
            except Exception:
                self.leds = DualStripDriverDummy()
        else:
            self.leds = DualStripDriverDummy()

        # -----------------------------------------------------------------
        # screens
        # -----------------------------------------------------------------
        # 0: welcome
        self.welcome = WelcomeScreen(led_driver=self.leds)
        self.addWidget(self.welcome)

        # 1: ping screen
        self.ping = PingScreen()
        self.addWidget(self.ping)

        # 2: ship screen
        self.ship = ShipScreen()
        self.addWidget(self.ship)

        # 3: view orders
        self.view = ViewOrderScreen()
        self.addWidget(self.view)

        self.setCurrentIndex(0)

        # -----------------------------------------------------------------
        # idle timer for welcome -> wait screen
        # -----------------------------------------------------------------
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self._show_wait_screen)

        # start the idle countdown now that we're on welcome
        self._start_idle_timer()

    # -----------------------------------------------------------------
    #  idle wait screen control
    # -----------------------------------------------------------------
    def _start_idle_timer(self):
        # only counts down while on welcome screen
        if self.currentIndex() == 0:
            self.idle_timer.start(30_000)  # 30 seconds

    def _cancel_idle_timer(self):
        self.idle_timer.stop()

    def _show_wait_screen(self):
        # only show if we are still on the welcome screen
        if self.currentIndex() != 0:
            return

        if self.wait_screen is not None:
            try:
                self.wait_screen.close()
            except Exception:
                pass
            self.wait_screen = None

        self.wait_screen = IdleWaitScreen(parent=self)
        self.wait_screen.exit_requested.connect(self._on_wait_exit)
        self.wait_screen.showFullScreen()

    def _on_wait_exit(self):
        # when the wait screen closes, we remain on welcome and restart timer
        self.wait_screen = None
        self._start_idle_timer()

    # -----------------------------------------------------------------
    #  navigation helpers (for now via keyboard)
    # -----------------------------------------------------------------
    def go_welcome(self):
        self._cancel_idle_timer()
        self.setCurrentIndex(0)
        self._start_idle_timer()

    def go_ping(self):
        self._cancel_idle_timer()
        self.setCurrentIndex(1)

    def go_ship(self):
        self._cancel_idle_timer()
        self.setCurrentIndex(2)

    def go_view_orders(self):
        self._cancel_idle_timer()
        self.setCurrentIndex(3)

    # -----------------------------------------------------------------
    #  key handling (global nav + global exit combo)
    # -----------------------------------------------------------------
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        # global 4-button exit combo:
        # hold ctrl + c + v and press enter/return
        if (
            (mods & Qt.ControlModifier)
            and Qt.Key_C in self._pressed
            and Qt.Key_V in self._pressed
            and k in (Qt.Key_Return, Qt.Key_Enter)
        ):
            # clean up leds best-effort
            try:
                if hasattr(self, "leds") and self.leds:
                    self.leds.stop()
            except Exception:
                pass
            QApplication.quit()
            return

        # dev navigation keys for now
        if k == Qt.Key_1:
            self.go_welcome()
            return
        if k == Qt.Key_2:
            self.go_ping()
            return
        if k == Qt.Key_3:
            self.go_ship()
            return
        if k == Qt.Key_4:
            self.go_view_orders()
            return

        # otherwise, pass to current screen
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)

    # keep idle timer aligned if index is changed programmatically
    def setCurrentIndex(self, index: int):
        super().setCurrentIndex(index)
        if index == 0:
            self._start_idle_timer()
        else:
            self._cancel_idle_timer()

    # best-effort led shutdown when window closes
    def closeEvent(self, e):
        try:
            if hasattr(self, "leds") and self.leds:
                self.leds.stop()
        except Exception:
            pass
        super().closeEvent(e)


# ------------------------------------------------------------
#  entry point
# ------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.showFullScreen()
    sys.exit(app.exec_())
