"""
GUIvTechSymposium002.py

pallet portal gui (modular, tech symposium version)

modules used:
- ledWorkerv001.py        → LEDWorker (dual ws2812 strips)
- manifestWatcherv001.py  → ShipmentList, USBWatcher (used inside welcomeScreenv002)
- glitchEffectv001.py     → GlitchText (used by welcome + others)
- welcomeScreenv002.py    → WelcomeScreen (usb-gated + idle timeout)
- modeSelectScreenv002.py → modeScreen (ship / view order menu)
- pingScreenv006.py       → PingScreen (distance radar pre-scan)
- shipScreenv010.py       → ShipScreen (scanning + progress + manifest handling)
- viewOrderScreenv004.py  → ViewOrderScreen (completed orders table)
- waitScreenv005.py       → WaitScreen (bouncing logo + exit back to welcome)
"""

import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QStackedWidget

from ledWorkerv001 import LEDWorker  #this drives the physical led strips
from welcomeScreenv002 import WelcomeScreen
from modeSelectScreenv002 import modeScreen
from pingScreenv006 import PingScreen
from shipScreenv010 import ShipScreen
from viewOrderScreenv004 import ViewOrderScreen
from waitScreenv005 import WaitScreen


class MainWindow(QStackedWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Pallet Portal GUI (Tech Symposium)")
        self.completed_usb_paths = set()  #tracks which usb roots have been processed

        #----- led worker (shared) -----
        self.leds = LEDWorker(num_leds=5)
        self.leds.start()
        self.leds.to_standby.emit()  #rainbow on startup

        #----- screens -----
        self.welcome = WelcomeScreen()       #index 0
        self.menu = modeScreen()             #index 1
        self.ship = ShipScreen()             #index 2
        self.view = ViewOrderScreen()        #index 3
        self.ping = PingScreen()             #index 4
        self.wait = WaitScreen()             #index 5

        #order matters; shipScreenv010 expects:
        # 0 → welcome, 3 → view for its own setCurrentIndex() logic
        self.addWidget(self.welcome)  #idx 0
        self.addWidget(self.menu)     #idx 1
        self.addWidget(self.ship)     #idx 2
        self.addWidget(self.view)     #idx 3
        self.addWidget(self.ping)     #idx 4
        self.addWidget(self.wait)     #idx 5

        #indices for readability
        self.WELCOME_IDX = 0
        self.MENU_IDX = 1
        self.SHIP_IDX = 2
        self.VIEW_IDX = 3
        self.PING_IDX = 4
        self.WAIT_IDX = 5

        #make these visible to shipScreenv010._return_to_welcome()
        self.completed_usb_paths = set()

        #wire shared services into ship / ping if they expose on_attach
        if hasattr(self.ship, "on_attach"):
            self.ship.on_attach(self)
        if hasattr(self.ping, "on_attach"):
            try:
                self.ping.on_attach(self)
            except Exception:
                pass

        #welcome → menu (after manifest found)
        self.welcome.proceed.connect(self._on_manifest_ready)
        self.welcome.idleTimeout.connect(self._on_welcome_idle_timeout)

        #menu selection
        self.menu.shipSelected.connect(self._goto_ping)
        self.menu.viewOrderSelected.connect(self._goto_view_orders)

        #ping → ship (once distance trigger hits)
        #try a couple of common signal names depending on which version is on disk
        if hasattr(self.ping, "ready_to_scan"):
            self.ping.ready_to_scan.connect(self._on_ping_ready)
        elif hasattr(self.ping, "ready"):
            self.ping.ready.connect(self._on_ping_ready)

        #wait screen exit back to welcome
        if hasattr(self.wait, "exitRequested"):
            self.wait.exitRequested.connect(self._from_wait_to_welcome)
        elif hasattr(self.wait, "exit_to_welcome"):
            self.wait.exit_to_welcome.connect(self._from_wait_to_welcome)

        #start at welcome
        self.setCurrentIndex(self.WELCOME_IDX)
        self._focus_current()

    #---------- helpers ----------
    def _focus_current(self):
        w = self.currentWidget()
        try:
            w.setFocus()
        except Exception:
            pass

    #---------- navigation callbacks ----------
    def _on_manifest_ready(self, shipment, mount_dir: str):
        """
        called when welcomeScreenv002 finds a valid manifest.
        shipment.barcodes is the list of codes; mount_dir is the usb path root.
        """
        #hand manifest into ship screen
        if hasattr(self.ship, "set_manifest_codes"):
            try:
                self.ship.set_manifest_codes(shipment.barcodes)
            except Exception:
                pass

        #hand mount_dir so ship screen can log / derive trailer name
        if hasattr(self.ship, "set_current_usb_path"):
            try:
                self.ship.set_current_usb_path(mount_dir)
            except Exception:
                pass

        #store for completed-usb tracking (shipScreenv010._return_to_welcome expects this attr)
        self.current_usb_root = mount_dir

        #go to menu so operator can choose ship vs view order
        self.setCurrentIndex(self.MENU_IDX)
        self._focus_current()

    def _on_welcome_idle_timeout(self):
        """
        30 s passed on welcome with no manifest → go to wait screen
        """
        #only if still on welcome; if we already left, ignore
        if self.currentIndex() != self.WELCOME_IDX:
            return
        self.setCurrentIndex(self.WAIT_IDX)
        self._focus_current()

    def _from_wait_to_welcome(self):
        """
        wait screen signaled an exit (one of the 4 keys pressed) → back to welcome
        """
        self.setCurrentIndex(self.WELCOME_IDX)
        #when returning to welcome, leds back to standby
        try:
            self.leds.to_standby.emit()
        except Exception:
            pass
        self._focus_current()

    def _goto_ping(self):
        """
        from menu, go to ping screen before ship
        """
        self.setCurrentIndex(self.PING_IDX)
        #let ping screen reset itself if it exposes start/stop
        if hasattr(self.ping, "start_ping"):
            try:
                self.ping.start_ping()
            except Exception:
                pass
        self._focus_current()

    def _goto_view_orders(self):
        """
        from menu, go straight to view order screen
        """
        self.setCurrentIndex(self.VIEW_IDX)
        self._focus_current()

    def _on_ping_ready(self, *args):
        """
        called when ping screen says the pallet is close enough.
        we don't care about the distance value here; just move to ship screen.
        """
        #switch leds to green if led worker supports it
        try:
            if hasattr(self.leds, "to_green"):
                self.leds.to_green.emit()
        except Exception:
            pass

        #go to ship screen
        self.setCurrentIndex(self.SHIP_IDX)
        self._focus_current()

    #---------- close handling ----------
    def closeEvent(self, e):
        #cleanly stop leds on app exit
        try:
            if hasattr(self, "leds") and self.leds.isRunning():
                self.leds.stop()
                self.leds.wait(800)
        except Exception:
            pass
        super().closeEvent(e)


#-------------------- entry point --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.showFullScreen()  #always fullscreen on the 1024x600 panel
    sys.exit(app.exec_())
