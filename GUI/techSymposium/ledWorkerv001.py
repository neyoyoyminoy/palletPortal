"""
ledWorkerv001.py
Contains:
 - SPItoWS: low-level WS2812 driver using Jetson SPI
 - DualStripDriver: high-level LED controller for left/right strips

Notes:
 - Designed for Jetson Orin Nano SPI0 on pin 19 (MOSI)
 - Compatible with Pallet Portal UI screens
 - No Qt dependencies here (safe for headless workers)
"""

import spidev
import time
import threading


# ----------------------------------------------------------------------
#  SPItoWS  —  low-level WS2812 over SPI driver
# ----------------------------------------------------------------------
class SPItoWS:
    """
    Uses SPI to drive WS2812 LEDs.
    Bit encoding:
      0 → 100
      1 → 110
    """

    def __init__(self, num_leds=10, spi_bus=0, spi_dev=0, mhz=3.2):
        self.num_leds = num_leds
        self.spi = spidev.SpiDev()

        try:
            self.spi.open(spi_bus, spi_dev)
            self.spi.max_speed_hz = int(mhz * 1_000_000)
            self.spi.mode = 0
        except Exception as e:
            print(f"[SPItoWS] ERROR: Could not open SPI: {e}")

        # Reusable buffer
        self._buf = [0] * (num_leds * 24 * 3)

        # Precomputed LUT for WS2812 bit encoding
        self._lut = {
            0: [1, 0, 0],
            1: [1, 1, 0],
        }

        # Thread lock for safe writes
        self._lock = threading.Lock()

    def _encode_color(self, r, g, b):
        """ Return WS2812 G,R,B encoded bit sequence """
        bits = []
        for byte in (g, r, b):  # WS2812 uses GRB order
            for i in range(8):
                bit = (byte >> (7 - i)) & 1
                bits.extend(self._lut[bit])
        return bits

    def show(self, colors):
        """ colors = [(r,g,b), (r,g,b), ...] """
        with self._lock:
            pos = 0
            for (r, g, b) in colors:
                encoded = self._encode_color(r, g, b)
                self._buf[pos:pos + 24 * 3] = encoded
                pos += 24 * 3

            try:
                self.spi.xfer2(self._buf)
            except Exception as e:
                print(f"[SPItoWS] Write error: {e}")

    def off(self):
        """ Turn all LEDs off. """
        self.show([(0, 0, 0)] * self.num_leds)


# ----------------------------------------------------------------------
#  DualStripDriver  —  high-level LED behavior used in UI screens
# ----------------------------------------------------------------------
class DualStripDriver:
    """
    Controls two LED strips (left and right) as a unified system.
    Each strip is 5 LEDs by default:
        left: indices 0–4
        right: indices 5–9
    """

    def __init__(self, num_per_strip=5):
        self.total = num_per_strip * 2
        self.strip = SPItoWS(self.total)
        self._colors = [(0, 0, 0)] * self.total
        self._lock = threading.Lock()

        # Background animation thread
        self._running = True
        self._anim_thread = threading.Thread(target=self._anim_loop, daemon=True)
        self._anim_thread.start()

        # animation state
        self._pulse = False
        self._pulse_level = 0
        self._pulse_up = True

    # ---------------------------------------------------------
    #  Internal animation loop
    # ---------------------------------------------------------
    def _anim_loop(self):
        while self._running:
            time.sleep(0.03)

            if self._pulse:
                if self._pulse_up:
                    self._pulse_level += 5
                    if self._pulse_level >= 255:
                        self._pulse_up = False
                else:
                    self._pulse_level -= 5
                    if self._pulse_level <= 60:
                        self._pulse_up = True

                self.set_all((0, self._pulse_level, 255))  # cyan-ish pulse

    # ---------------------------------------------------------
    #   Control functions
    # ---------------------------------------------------------
    def set_all(self, rgb):
        with self._lock:
            self._colors = [rgb] * self.total
            self.strip.show(self._colors)

    def set_left(self, rgb):
        with self._lock:
            for i in range(self.total // 2):
                self._colors[i] = rgb
            self.strip.show(self._colors)

    def set_right(self, rgb):
        with self._lock:
            for i in range(self.total // 2, self.total):
                self._colors[i] = rgb
            self.strip.show(self._colors)

    # ---------------------------------------------------------
    #   Animations
    # ---------------------------------------------------------
    def pulse_cyan(self, enable=True):
        self._pulse = enable
        if not enable:
            self._pulse_level = 0
            self._pulse_up = True

    def flash(self, rgb, flashes=3, duration=0.15):
        for _ in range(flashes):
            self.set_all(rgb)
            time.sleep(duration)
            self.set_all((0, 0, 0))
            time.sleep(duration)

    # Convenience color shortcuts
    def to_cyan(self):
        self.set_all((0, 255, 255))

    def to_red(self):
        self.set_all((255, 0, 0))

    def to_green(self):
        self.set_all((0, 255, 0))

    def to_magenta(self):
        self.set_all((255, 0, 255))

    def to_white(self):
        self.set_all((255, 255, 255))

    # ---------------------------------------------------------
    #  Shutdown
    # ---------------------------------------------------------
    def stop(self):
        self._running = False
        self.set_all((0, 0, 0))
        time.sleep(0.05)
        self.strip.off()
