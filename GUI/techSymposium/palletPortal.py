"""
palletPortal.py
Main Pallet Portal GUI launcher.

This file coordinates:
- essentials.py   (USB watcher, LED worker, ping worker, barcode worker, glitch)
- welcome.py      (glitch welcome screen)
- mode.py         (mode select screen)
- ping.py         (radar + distance screen)
- ship.py         (shipment in progress screen)
- order.py        (view orders screen)
- wait.py         (idle bouncing logo screen)

Screen flow:
1. Welcome → USB found → Mode Select
2. Mode:
      SHIP  → Ping → Ship
      VIEW ORDER → ViewOrder
3. Ship → completion → ViewOrder or back to Welcome
4. Idle timeout on Welcome → Wait Screen → any key → Welcome
"""

import sys
from PyQt5.QtWidgets import QApplication, QStackedWidget

# --- essentials ---
from essentials import (
    USBWatcher,
    LEDWorker,
    ShipmentList,
)

# --- separate screens ---
from welcome import WelcomeScreen
from mode import ModeScreen
from ping import PingScreen
from ship import ShipScreen
from order import ViewOrderScreen
from wait import WaitScreen


class PalletPortal(QStackedWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Pallet Portal")
        self.showFullScreen()

        # ---------------------------------------------------------
        #  LED Worker (global, shared across screens)
        # ---------------------------------------------------------
        self.leds = LEDWorker(num_leds=5)
        self.leds.start()
        self.leds.to_standby.emit()

        # ---------------------------------------------------------
        #  Screens
        # ---------------------------------------------------------
        self.welcome = WelcomeScreen()
        self.mode = ModeScreen()
        self.ping = PingScreen()
        self.ship = ShipScreen()
        self.order = ViewOrderScreen()
        self.wait = WaitScreen()

        # Order list storage
        self.completed_orders = []

        # Add screens in fixed index order
        self.addWidget(self.welcome)  # 0
        self.addWidget(self.mode)     # 1
        self.addWidget(self.ping)     # 2
        self.addWidget(self.ship)     # 3
        self.addWidget(self.order)    # 4
        self.addWidget(self.wait)     # 5

        self.setCurrentIndex(0)

        # ---------------------------------------------------------
        #  USB detection → WelcomeScreen
        # ---------------------------------------------------------
        self.watcher = USBWatcher()
        self.welcome.inject_usb_watcher(self.watcher)

        self.watcher.validListFound.connect(self._usb_ready)

        # ---------------------------------------------------------
        #  ModeScreen signals
        # ---------------------------------------------------------
        self.mode.shipSelected.connect(lambda: self.setCurrentIndex(2))
        self.mode.viewOrderSelected.connect(lambda: self._open_orders())

        # ---------------------------------------------------------
        #  PingScreen → ShipScreen
        # ---------------------------------------------------------
        self.ping.readyToShip.connect(self._start_ship_mode)

        # ---------------------------------------------------------
        #  ShipScreen completion
        # ---------------------------------------------------------
        self.ship.orderCompleted.connect(self._add_completed_order)

        # ---------------------------------------------------------
        #  Idle → Wait Screen
        # ---------------------------------------------------------
        self.welcome.timeoutToWait.connect(self._open_wait_screen)
        self.wait.returnToWelcome.connect(self._return_to_welcome)

    # -------------------------------------------------------------
    #  USB scanned → Move to ModeScreen
    # -------------------------------------------------------------
    def _usb_ready(self, shipmentList: ShipmentList, mount_dir: str):
        self.ship.set_manifest_codes(shipmentList.barcodes)
        self.ship.set_current_usb_path(mount_dir)
        self.setCurrentIndex(1)

    # -------------------------------------------------------------
    #  ModeScreen → View Orders
    # -------------------------------------------------------------
    def _open_orders(self):
        self.order.setFocus()
        self.setCurrentIndex(4)

    # -------------------------------------------------------------
    #  PingScreen → ShipScreen
    # -------------------------------------------------------------
    def _start_ship_mode(self, dist):
        self.setCurrentIndex(3)
        self.ship.start_scanning()

    # -------------------------------------------------------------
    #  Ship finished scanning manifest
    # -------------------------------------------------------------
    def _add_completed_order(self, order_dict):
        self.completed_orders.append(order_dict)
        self.order.add_order(
            order_dict["trailer"],
            order_dict["start"],
            order_dict["end"],
            order_dict["scanned"]
        )
        self._return_to_welcome()

    # -------------------------------------------------------------
    #  Idle → Wait screen
    # -------------------------------------------------------------
    def _open_wait_screen(self):
        self.setCurrentIndex(5)

    # -------------------------------------------------------------
    #  Return to Welcome screen
    # -------------------------------------------------------------
    def _return_to_welcome(self):
        self.leds.to_standby.emit()
        self.setCurrentIndex(0)

    # -------------------------------------------------------------
    #  Shutdown
    # -------------------------------------------------------------
    def closeEvent(self, e):
        try:
            self.leds.stop()
            self.leds.wait(500)
        except:
            pass
        super().closeEvent(e)


# Entry point
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = PalletPortal()
    gui.showFullScreen()
    sys.exit(app.exec_())
