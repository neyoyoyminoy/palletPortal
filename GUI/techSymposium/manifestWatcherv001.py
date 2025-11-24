"""
manifestWatcherv001.py

this module handles:
- guessing usb mount roots on the jetson
- scanning for a barcodes.txt style manifest file
- parsing barcodes into a ShipmentList
- emitting qt signals when a valid list is found

classes:
- ShipmentList: wraps the list of barcodes from the usb text file
- USBWatcher: qt QObject with a timer that polls for barcodes.txt

this does not handle:
- led control
- cameras or barcode reading
- manifest matching (see manifestMatcherv001.py)
"""

import os  #for path + env
import re  #for splitting manifest text
from pathlib import Path  #for file reads

from PyQt5.QtCore import QObject, QTimer, pyqtSignal  #qt base classes


BARCODE_FILENAME_CANDIDATES = ["barcodes.txt"]  #default filenames to look for


def guess_mount_roots():
    """try to guess where usb drives might mount on this system"""
    roots = set()
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""

    #common mount bases
    for base in ["/media", "/mnt", "/run/media"]:
        roots.add(base)
        if user:
            roots.add(os.path.join(base, user))

    #explicit jetson-style path
    roots.add("/media/jetson")

    #scan /proc/mounts for extra vfat/exfat/ntfs style mounts
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3:
                    mnt = parts[1]
                    fstype = parts[2].lower()
                    if any(fs in fstype for fs in ("vfat", "exfat", "ntfs", "fuseblk")):
                        roots.add(mnt)
    except Exception:
        pass

    #only keep paths that still exist
    return [r for r in sorted(roots) if os.path.exists(r)]


DEFAULT_MOUNT_ROOTS = guess_mount_roots()  #default search roots


#-------------------- shipment list wrapper --------------------
class ShipmentList:
    #this just carries the list of barcodes from the text file
    def __init__(self, barcodes):
        self.barcodes = list(barcodes or [])  #store as simple list

    @staticmethod
    def parse(text: str):
        """parse raw text from barcodes file into a ShipmentList or None"""
        if not text:
            return None

        #strip utf-8 bom if present
        if text and text[0] == "\ufeff":
            text = text[1:]

        #split on whitespace and commas, strip, drop empties
        parts = [t.strip() for t in re.split(r"[\s,]+", text) if t.strip()]

        seen = set()
        uniq = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                uniq.append(p)

        return ShipmentList(uniq) if uniq else None


#-------------------- usb watcher --------------------
class USBWatcher(QObject):
    """
    scans the filesystem for a barcodes.txt style file on usb drives

    signals:
        validListFound(ShipmentList, str)  -> (shipment_list, directory_path)
        status(str)                       -> human-readable status message
    """

    validListFound = pyqtSignal(ShipmentList, str)
    status = pyqtSignal(str)

    def __init__(
        self,
        mount_roots=None,
        filename_candidates=None,
        poll_ms=1000,
        parent=None,
    ):
        super().__init__(parent)

        #roots to search under (dirs that might contain usb mounts)
        self.mount_roots = list(mount_roots or DEFAULT_MOUNT_ROOTS)

        #candidate filenames to accept
        self.filename_candidates = [
            c.lower() for c in (filename_candidates or BARCODE_FILENAME_CANDIDATES)
        ]

        #qt timer for periodic polling
        self.timer = QTimer(self)
        self.timer.setInterval(poll_ms)
        self.timer.timeout.connect(self.scan_once)

    def start(self):
        """start periodic usb scanning"""
        self.scan_once()  #run one scan right away
        self.timer.start()

    def stop(self):
        """stop periodic usb scanning"""
        self.timer.stop()

    def scan_once(self):
        """
        run a single scan of all mount roots

        behavior:
        - walks each root up to depth 2
        - looks for any of the candidate filenames (case-insensitive)
        - if a valid list is parsed, emits validListFound and returns
        - if nothing is found, emits a generic scanning status
        """
        any_found = False

        for root in self.mount_roots:
            if not os.path.exists(root):
                continue

            for dirpath, dirnames, filenames in os.walk(root):
                #limit recursion depth so we don't dive forever
                depth = dirpath.strip(os.sep).count(os.sep) - root.strip(os.sep).count(
                    os.sep
                )
                if depth > 2:
                    dirnames[:] = []  #stop recursing deeper
                    continue

                #skip virtual/system dirs just in case
                if any(
                    p in dirpath for p in ("/proc", "/sys", "/dev", "/run/lock")
                ):
                    continue

                #normalized filename map
                lower_files = {fn.lower(): fn for fn in filenames}

                for cand_lower in self.filename_candidates:
                    if cand_lower in lower_files:
                        any_found = True
                        found_name = lower_files[cand_lower]
                        full_path = os.path.join(dirpath, found_name)

                        try:
                            txt = Path(full_path).read_text(
                                encoding="utf-8", errors="ignore"
                            )
                        except Exception as e:
                            self.status.emit(
                                f"found {found_name} at {dirpath}, but couldn't read: {e}"
                            )
                            continue

                        parsed = ShipmentList.parse(txt)
                        if parsed:
                            self.status.emit(f"valid list found at: {full_path}")
                            self.validListFound.emit(parsed, dirpath)
                            return
                        else:
                            self.status.emit(
                                f"{found_name} at {dirpath} did not contain any readable barcodes"
                            )

        if not any_found:
            self.status.emit("scanning for usb + barcodes file...")


#-------------------- simple standalone test --------------------
if __name__ == "__main__":
    #quick headless test (no qt event loop) just to see mount roots + one scan
    print("default mount roots:")
    for r in DEFAULT_MOUNT_ROOTS:
        print("  ", r)

    #note: the full usb watcher behavior depends on a qt event loop,
    #so the proper way to test the signals is inside the actual gui.
