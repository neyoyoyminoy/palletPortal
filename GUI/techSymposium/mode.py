"""
mode.py

Mode select screen for Pallet Portal.
- Two options: SHIP ORDER / VIEW ORDER
- Glitch highlight on selected option
- Black background, cyan/red/magenta glitch colors
- Signals:
    shipSelected
    viewOrderSelected
- 4-button exit combo: ctrl + c + v + enter/return
"""

import sys
import random
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtWidgets import QApplication, QWidget


class ModeScreen(QWidget):
    shipSelected = pyqtSignal()      # fires when SHIP ORDER is chosen
    viewOrderSelected = pyqtSignal() # fires when VIEW ORDER is chosen

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("mode select")
        self.setStyleSheet("background-color: black;")
        self.setFocusPolicy(Qt.StrongFocus)

        self.options = ["SHIP ORDER", "VIEW ORDER"]
        self.idx = 0  # current selection index

        self.font = QFont("Arial", 72, QFont.Bold)

        # per-option glitch state
        self.scrambled = list(self.options)
        self.glitch_strength = [0, 0]

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_glitch)
        self.timer.start(60)  # ~16 fps

        self._pressed = set()  # for exit combo

    # -------------------- glitch logic --------------------
    def update_glitch(self):
        for i in range(len(self.options)):
            if i == self.idx:
                if random.random() < 0.35:
                    self.glitch_strength[i] = random.randint(3, 12)
                    self.scramble_option(i)
                else:
                    self.scrambled[i] = self.options[i]
                    self.glitch_strength[i] = 0
            else:
                self.scrambled[i] = self.options[i]
                self.glitch_strength[i] = 0

        self.update()

    def scramble_option(self, i):
        base = self.options[i]
        chars = list(base)
        for j in range(len(chars)):
            if random.random() < 0.25:
                chars[j] = random.choice(
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%*"
                )
        self.scrambled[i] = "".join(chars)

    # -------------------- drawing --------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self.font)

        width = self.width()
        height = self.height()

        # background
        p.fillRect(self.rect(), QColor(0, 0, 0))

        fm = p.fontMetrics()
        line_h = fm.height()

        rect_h = int(line_h * 1.4)
        spacing = 40
        total_h = rect_h * 2 + spacing

        top_y = (height - total_h) // 2
        rect_w = int(width * 0.7)
        rect_x = (width - rect_w) // 2

        for i, text in enumerate(self.scrambled):
            is_sel = (i == self.idx)
            rect_y = top_y + i * (rect_h + spacing)

            # pill background
            if is_sel:
                p.setBrush(QColor(0, 40, 40, 230))
                p.setPen(QColor(0, 255, 255, 220))
            else:
                p.setBrush(QColor(15, 15, 15, 230))
                p.setPen(QColor(120, 120, 120, 160))

            p.drawRoundedRect(rect_x, rect_y, rect_w, rect_h, 40, 40)

            # center text
            text_w = fm.horizontalAdvance(text)
            baseline_y = rect_y + (rect_h + line_h) // 2 - fm.descent()
            x = rect_x + (rect_w - text_w) // 2
            y = baseline_y

            base_color = QColor(255, 255, 255) if is_sel else QColor(180, 180, 180)
            p.setPen(base_color)
            p.drawText(x, y, text)

            # glitch overlays
            if is_sel and self.glitch_strength[i] > 0:
                shift = self.glitch_strength[i]

                # red left
                p.setPen(QColor(255, 0, 0, 190))
                p.drawText(x - shift, y, text)

                # cyan right
                p.setPen(QColor(0, 255, 255, 190))
                p.drawText(x + shift, y, text)

                # magenta jitter
                if random.random() < 0.4:
                    jitter_x = x + random.randint(-10, 10)
                    jitter_y = y + random.randint(-20, 20)
                    p.setPen(QColor(255, 0, 255, 220))
                    p.drawText(jitter_x, jitter_y, text)

        p.end()

    # -------------------- helpers --------------------
    def _move_down(self):
        self.idx = (self.idx + 1) % len(self.options)
        self.update_glitch()

    # -------------------- key handling --------------------
    def keyPressEvent(self, e):
        k = e.key()
        self._pressed.add(k)
        mods = e.modifiers()

        # exit combo: ctrl + c + v + enter/return
        if (
            (mods & Qt.ControlModifier)
            and Qt.Key_C in self._pressed
            and Qt.Key_V in self._pressed
            and k in (Qt.Key_Return, Qt.Key_Enter)
        ):
            QApplication.quit()
            return

        # move selection down with Ctrl or Enter/Return
        if k in (Qt.Key_Control, Qt.Key_Return, Qt.Key_Enter):
            self._move_down()
            e.accept()
            return

        # select with 'V'
        if k == Qt.Key_V:
            if self.idx == 0:
                self.shipSelected.emit()
            else:
                self.viewOrderSelected.emit()
            e.accept()
            return

        # 'C' is reserved here (no-op, but consumed)
        if k == Qt.Key_C:
            e.accept()
            return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._pressed.discard(e.key())
        super().keyReleaseEvent(e)


# -------------------- standalone test --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ModeScreen()
    w.showFullScreen()
    sys.exit(app.exec_())
