"""
barcodeReaderv001.py

Threaded CSI camera barcode reader for Pallet Portal.
Handles:
- camera initialization
- YOLO barcode detection
- decoding + emitting signals
- retry logic
- clean camera shutdown

Does NOT handle:
- manifest matching (see manifestMatcherv001.py)
- ping or USB logic (separate worker files)

Signals:
- log(str)
- decoded(str)
- matched(val, score, method)
- finished_all()

Author: Pallet Portal System
"""

import cv2
import time
from PyQt5.QtCore import QThread, pyqtSignal
from ultralytics import YOLO


class BarcodeReaderWorker(QThread):
    log = pyqtSignal(str)
    decoded = pyqtSignal(str)
    matched = pyqtSignal(str, float, str)
    finished_all = pyqtSignal()

    def __init__(
        self,
        model_path="my_model.pt",
        sensor_id=0,
        width=1920,
        height=1080,
        framerate=5,
        min_conf=0.25,
        iou=0.45,
        max_rois=6,
        decode_every=1,
        fallback_interval=15,
        manifest_codes=None,
    ):
        super().__init__()
        self.model_path = model_path
        self.sensor_id = sensor_id
        self.width = width
        self.height = height
        self.framerate = framerate
        self.min_conf = min_conf
        self.iou = iou
        self.max_rois = max_rois
        self.decode_every = decode_every
        self.fallback_interval = fallback_interval
        self.manifest_codes = manifest_codes or []

        self._stop = False
        self._frame_count = 0
        self._found = set()

    def stop(self):
        self._stop = True

    # Build the CSI GStreamer pipeline
    def _gstream_pipeline(self, sensor_id):
        return (
            f"nvarguscamerasrc sensor-id={sensor_id} ! "
            f"video/x-raw(memory:NVMM), width={self.width}, height={self.height}, "
            f"format=NV12, framerate={self.framerate}/1 ! "
            f"nvvidconv flip-method=0 ! "
            f"video/x-raw, width={self.width}, height={self.height}, format=BGRx ! "
            f"videoconvert ! video/x-raw, format=BGR ! appsink"
        )

    def run(self):
        try:
            model = YOLO(self.model_path)
        except Exception as e:
            self.log.emit(f"ERROR loading YOLO model: {e}")
            return

        pipeline = self._gstream_pipeline(self.sensor_id)
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

        if not cap.isOpened():
            self.log.emit(f"ERROR: camera {self.sensor_id} failed to open")
            return

        self.log.emit(f"camera {self.sensor_id} active — starting barcode scan loop")

        last_decode_time = time.time()

        try:
            while not self._stop:
                ret, frame = cap.read()
                if not ret or frame is None:
                    self.log.emit(f"camera {self.sensor_id} — frame read failed")
                    time.sleep(0.1)
                    continue

                self._frame_count += 1

                # decode only at interval
                if self._frame_count % self.decode_every != 0:
                    continue

                results = model(
                    frame,
                    conf=self.min_conf,
                    iou=self.iou,
                    max_det=self.max_rois,
                    verbose=False,
                )

                now = time.time()
                fallback = (now - last_decode_time) > self.fallback_interval

                for r in results:
                    if not hasattr(r, "boxes") or r.boxes is None:
                        continue

                    for b in r.boxes:
                        cls_id = int(b.cls[0])
                        conf = float(b.conf[0])
                        xyxy = b.xyxy[0].tolist()

                        # YOLO class 0 is your barcode category
                        if cls_id != 0:
                            continue

                        # extract ROI
                        x1, y1, x2, y2 = map(int, xyxy)
                        x1 = max(0, x1)
                        y1 = max(0, y1)
                        x2 = min(frame.shape[1], x2)
                        y2 = min(frame.shape[0], y2)

                        roi = frame[y1:y2, x1:x2]
                        if roi.size == 0:
                            continue

                        # TEXT DECODING — using CV2 QRDecoder fallback
                        # Since actual barcode decoding logic varies,
                        # keep compatible with your current version
                        try:
                            decoder = cv2.QRCodeDetector()
                            text, pts, _ = decoder.detectAndDecode(roi)
                        except Exception:
                            text = ""

                        if text:
                            text = text.strip()
                            last_decode_time = now
                            self.decoded.emit(text)
                            self.log.emit(
                                f"[cam {self.sensor_id}] decoded → {text} (conf {conf:.2f})"
                            )

                            # check against manifest
                            if text in self.manifest_codes:
                                if text not in self._found:
                                    self._found.add(text)
                                    self.matched.emit(text, conf, "YOLO+ROI")
                                    self.log.emit(
                                        f"manifest match → {text} ({len(self._found)}/{len(self.manifest_codes)})"
                                    )

                                    # all done?
                                    if len(self._found) == len(self.manifest_codes):
                                        self.log.emit("all manifest barcodes found")
                                        self.finished_all.emit()
                                        self._stop = True
                                        break

                if fallback:
                    self.log.emit("fallback decode interval hit — no barcodes recently")

        except Exception as e:
            self.log.emit(f"barcode reader error: {e}")

        finally:
            try:
                cap.release()
            except Exception:
                pass
            self.log.emit(f"camera {self.sensor_id} closed")
