"""
viewOrderScreenv004.py

final orders screen
- black background
- centered white bubble with rounded corners containing table-style columns
- white title "VIEW ORDERS" at top (no glitch here to keep it calm)
- same data api as older ViewOrderScreen:
    add_order(start_time, end_time, scanned_count, trailer_number)
- key X or C to exit when run standalone
"""

import sys  #for argv + exit
from datetime import datetime, timedelta
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QScrollArea,
    QGridLayout,
)


class ViewOrderScreen(QWidget):
    return_to_welcome = pyqtSignal()  #for integration later

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet("background-color:black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(10)

        title = QLabel("VIEW ORDERS")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 40, QFont.Bold))
        title.setStyleSheet("color:#ffffff;")
        layout.addWidget(title)

        layout.addSpacing(30)

        bubble = QWidget()
        bubble.setObjectName("ordersBubble")
        bubble.setAttribute(Qt.WA_StyledBackground, True)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(40, 30, 40, 30)
        layout.addWidget(bubble)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            """
            QScrollArea {
                border:0px;
                background-color:transparent;
            }
            """
        )
        bubble_layout.addWidget(self.scroll_area)

        self.container = QWidget()
        self.scroll_area.setWidget(self.container)

        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid_layout.setHorizontalSpacing(40)
        self.grid_layout.setVerticalSpacing(8)

        headers = ["Trailer", "Archway", "Start", "End", "Duration", "Scanned"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setFont(QFont("Arial", 13, QFont.Bold))
            lbl.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(lbl, 0, col)

        self._next_row = 1
        self.orders = []

        self.status = QLabel("Press X to exit")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFont(QFont("Arial", 12, QFont.Bold))
        self.status.setStyleSheet("color:#ffffff;")
        layout.addWidget(self.status)

        self.setStyleSheet(
            """
            QWidget {
                background-color:black;
            }
            QWidget#ordersBubble {
                background-color:#ffffff;
                border-radius:40px;
            }
            """
        )

    def add_order(self, start_time, end_time, scanned_count, trailer_number):
        duration = end_time - start_time
        archway = "Archway 1"

        order = {
            "start": start_time,
            "end": end_time,
            "duration": duration,
            "scanned_count": scanned_count,
            "archway": archway,
            "trailer": trailer_number,
        }
        self.orders.append(order)

        start_str = start_time.strftime("%H:%M:%S")
        end_str = end_time.strftime("%H:%M:%S")
        duration_str = str(duration).split(".")[0]

        values = [trailer_number, archway, start_str, end_str, duration_str, str(scanned_count)]

        for col, val in enumerate(values):
            lbl = QLabel(val)
            lbl.setFont(QFont("Arial", 11))
            lbl.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(lbl, self._next_row, col)

        self._next_row += 1
        self.status.setText("Press X to exit")

    def clear_orders(self):
        for row in reversed(range(1, self._next_row)):
            for col in range(self.grid_layout.columnCount()):
                item = self.grid_layout.itemAtPosition(row, col)
                if item:
                    w = item.widget()
                    if w:
                        w.setParent(None)
        self.orders.clear()
        self._next_row = 1
        self.status.setText("Press X to exit")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_X, Qt.Key_C):
            self.return_to_welcome.emit()
            QApplication.quit()
            return
        super().keyPressEvent(event)


# -------------------- standalone demo --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ViewOrderScreen()

    now = datetime.now()
    for i in range(5):
        start = now.replace(microsecond=0) - timedelta(minutes=10 + i * 2)
        end = start + timedelta(minutes=3 + i)
        w.add_order(start, end, scanned_count=6 - i, trailer_number=f"T-{101 + i}")

    w.showFullScreen()
    sys.exit(app.exec_())
