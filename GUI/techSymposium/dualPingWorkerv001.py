"""
dualPingWorkerv001.py

this module provides the dual ultrasonic MB1040 ping worker thread
used by pallet portal to detect when a trailer is close enough to begin scanning.

goals:
- isolated QThread worker
- emits log(str) for display
- emits ready(avg_distance_in, "either") when either sensor < trigger distance
- cleans up GPIO safely
- no GUI dependencies
"""

import time
from PyQt5.QtCore import QThread, pyqtSignal


class DualPingWorker(QThread):
    """
    dual MB1040 ping worker
    reads two ultrasonic sensors and emits 'ready' when either is within trigger range
    """

    ready = pyqtSignal(float, str)  # (avg_distance_in, "either")
    log = pyqtSignal(str)

    def __init__(self,
                 sensor1_pin=15,
                 sensor2_pin=32,
                 hard_min_in=6.0,
                 max_in=254.0,
                 trigger_in=13.0,
                 parent=None):
        super().__init__(parent)

        self.sensor1_pin = sensor1_pin
        self.sensor2_pin = sensor2_pin
        self.hard_min_in = hard_min_in
        self.max_in = max_in
        self.trigger_in = trigger_in

        self._stop = False

    def stop(self):
        """request the thread to stop"""
        self._stop = True

    # ---- internal helpers ----
    def _measure_pulse(self, GPIO, pin, timeout=0.05):
        """
        waits for rising edge then falling edge on ultrasonic echo pin
        returns pulse width in microseconds or None
        """
        if GPIO.wait_for_edge(pin, GPIO.RISING, timeout=int(timeout * 1000)) is None:
            return None
        start_ns = time.monotonic_ns()
        if GPIO.wait_for_edge(pin, GPIO.FALLING, timeout=int(timeout * 1000)) is None:
            return None
        end_ns = time.monotonic_ns()
        return (end_ns - start_ns) / 1000.0  # us

    def _read_distance(self, GPIO, pin, label):
        """
        returns distance in inches if valid, else None
        """
        width_us = self._measure_pulse(GPIO, pin)
        if width_us is None:
            self.log.emit(f"{label} → no pulse detected")
            return None

        distance_in = width_us / 147.0
        if not (self.hard_min_in <= distance_in <= self.max_in):
            self.log.emit(f"{label} → out of range ({distance_in:.2f} in)")
            return None

        dist_cm = distance_in * 2.54
        self.log.emit(f"{label} → {distance_in:.2f} in ({dist_cm:.2f} cm)")
        return distance_in

    # ---- thread run loop ----
    def run(self):
        """
        alternating MB1040 readings until either sensor < trigger
        """
        try:
            import Jetson.GPIO as GPIO
        except Exception as e:
            self.log.emit(f"ping error: Jetson.GPIO not available: {e}")
            return

        try:
            GPIO.setmode(GPIO.BOARD)
            GPIO.setup(self.sensor1_pin, GPIO.IN)
            GPIO.setup(self.sensor2_pin, GPIO.IN)

            self.log.emit("alternating MB1040 readings every 3 s (instantaneous mode)...")

            while not self._stop:
                d1 = self._read_distance(GPIO, self.sensor1_pin, "sensor 1")
                time.sleep(0.1)
                d2 = self._read_distance(GPIO, self.sensor2_pin, "sensor 2")

                if d1 is not None and d2 is not None:
                    avg = (d1 + d2) / 2.0
                    diff = d1 - d2
                    self.log.emit(f"→ Fused Avg: {avg:.2f} in | Offset: {diff:.2f} in")

                    if d1 <= self.trigger_in or d2 <= self.trigger_in:
                        self.log.emit("one sensor < trigger — ready to scan")
                        self.ready.emit(avg, "either")
                        break

                elif d1 is not None or d2 is not None:
                    active = d1 if d1 is not None else d2
                    self.log.emit(f"→ Single Sensor Active: {active:.2f} in")

                    if active <= self.trigger_in:
                        self.log.emit("single sensor < trigger — ready to scan")
                        self.ready.emit(active, "either")
                        break

                else:
                    self.log.emit("→ both sensors out of range")

                time.sleep(3.0)

        except Exception as e:
            self.log.emit(f"ping error: {e}")

        finally:
            try:
                GPIO.cleanup()
            except Exception:
                pass
            self.log.emit("ping gpio cleaned up")
