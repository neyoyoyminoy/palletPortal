"""
this is rainbowCirclev1.py
this tests the circular rainbow effect used for the corner celebration
it runs standalone so you can verify the led sequence before merging into the wait screen
"""

import sys  #for ctrl + c + v + enter exit combo
import time  #for timing the frames
import spidev  #for ws2812 spi output
from PyQt5.QtWidgets import QApplication, QWidget  #needed only for key capture
from PyQt5.QtCore import Qt, QTimer  #qt key handling


#-------------------- hue to rgb converter --------------------
def hue_to_rgb(h):
    #this converts a hue angle (0-360) into an rgb tuple 0-255
    h = float(h % 360)
    x = (1 - abs((h / 60) % 2 - 1)) * 255

    if h < 60:
        return (255, int(x), 0)
    if h < 120:
        return (int(x), 255, 0)
    if h < 180:
        return (0, 255, int(x))
    if h < 240:
        return (0, int(x), 255)
    if h < 300:
        return (int(x), 0, 255)
    return (255, 0, int(x))


#-------------------- ws2812 driver --------------------
class SPItoWS:
    def __init__(self, ledc=5, bus=0, device=0):
        self.led_count = ledc
        self.X = "100" * (ledc * 8 * 3)

        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 2400000

        self.LED_OFF_ALL()

    def __del__(self):
        try:
            self.spi.close()
        except:
            pass

    def _Bytesto3Bytes(self, num, RGBbits):
        base = num * 24
        for i in range(8):
            pat = '100' if RGBbits[i] == '0' else '110'
            self.X = (
                self.X[: base + i * 3]
                + pat
                + self.X[base + i * 3 + 3 :]
            )

    def LED_show(self):
        Y = []
        for i in range(self.led_count * 9):
            Y.append(int(self.X[i * 8 : (i + 1) * 8], 2))
        self.spi.xfer3(Y, 2400000, 0, 8)

    def RGBto3Bytes(self, led_num, R, G, B):
        RR = format(R, "08b")
        GG = format(G, "08b")
        BB = format(B, "08b")

        self._Bytesto3Bytes(led_num * 3, GG)
        self._Bytesto3Bytes(led_num * 3 + 1, RR)
        self._Bytesto3Bytes(led_num * 3 + 2, BB)

    def LED_OFF_ALL(self):
        self.X = "100" * (self.led_count * 8 * 3)
        self.LED_show()


#-------------------- dual strip wrapper --------------------
class DualStripDriver:
    def __init__(self, num_leds=5):
        self.strip0 = SPItoWS(num_leds, bus=0, device=0)  #left strip
        self.strip1 = SPItoWS(num_leds, bus=1, device=0)  #right strip

    def off(self):
        try:
            self.strip0.LED_OFF_ALL()
        except:
            pass
        try:
            self.strip1.LED_OFF_ALL()
        except:
            pass


#-------------------- main test widget (only for key capture) --------------------
class RainbowTest(QWidget):
    def __init__(self, leds):
        super().__init__()
        self.leds = leds  #dual led strips

        self._pressed = set()  #tracks keys for exit combo
        self.setWindowTitle("rainbow circle test")
        self.showFullScreen()  #fullscreen so keypress focus is guaranteed

        #start the animation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_leds)
        self.timer.start(50)  #20 fps (same as wait screen celebration)

        #counter clockwise led order (0 based)
        self.order = [0, 1, 2, 3, 4, 9, 8, 7, 6, 5]

        self.step = 0  #which led is active

    def update_leds(self):
        #this drives the circular rainbow sweep

        hue = (self.step * 25) % 360
        r, g, b = hue_to_rgb(hue)

        #blank pattern
        pattern = [(0, 0, 0)] * 10

        #choose which led is active
        active = self.order[self.step % len(self.order)]
        pattern[active] = (r, g, b)

        #push leds
        #left strip handles signals 0-4
        for i in range(5):
            rr, gg, bb = pattern[i]
            self.leds.strip0.RGBto3Bytes(i, rr, gg, bb)

        #right strip handles signals 5-9 (mapped to 0-4)
        for i in range(5):
            rr, gg, bb = pattern[5 + i]
            self.leds.strip1.RGBto3Bytes(i, rr, gg, bb)

        self.leds.strip0.LED_show()
        self.leds.strip1.LED_show()

        #increment to next frame
        self.step += 1

    def keyPressEvent(self, e):
        #track pressed keys
        k = e.key()
        self._pressed.add(k)

        mods = e.modifiers()

        #secret combo to quit: hold ctrl + c + v then press enter/return
        if (
            (mods & Qt.ControlModifier)
            and Qt.Key_C in self._pressed
            and Qt.Key_V in self._pressed
            and k in (Qt.Key_Return, Qt.Key_Enter)
        ):
            QApplication.quit()
            return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        try:
            self._pressed.remove(e.key())
        except:
            pass


#-------------------- entry point --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)

    try:
        leds = DualStripDriver(num_leds=5)
    except Exception as e:
        print("led init failed:", e)
        leds = None

    w = RainbowTest(leds)
    w.showFullScreen()

    if leds:
        app.aboutToQuit.connect(leds.off)

    sys.exit(app.exec_())
