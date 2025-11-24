"""
manifestMatcherv001.py

this module provides a simple manifest matcher for pallet portal

goals:
- keep a cleaned list of manifest barcodes
- support fast case-insensitive exact lookup
- return (value, score, method) tuples like the old inline version

this does not handle:
- usb scanning or file discovery (see manifestWatcherv001.py)
- camera or barcode reading (see barcodeReaderv001.py)
"""

from typing import List, Tuple, Optional


class SimpleManifestMatcher:
    """
    core manifest matcher used by the ship screen and barcode workers

    usage:
        matcher = SimpleManifestMatcher(["1234", "ABC-999"])
        rec, score, method = matcher.match("abc-999")
        if rec:
            print("match:", rec, score, method)
    """

    def __init__(self, codes):
        #normalize and keep only non-empty codes
        cleaned = []
        for c in codes or []:
            s = str(c).strip()
            if s:
                cleaned.append(s)

        self.codes: List[str] = cleaned  #original order list
        #lowercase lookup for case-insensitive exact matches
        self._lut = {c.lower(): c for c in self.codes}  #this mirrors your old gui map

    def match(self, code: str) -> Tuple[Optional[str], int, str]:
        """
        try to match an input barcode against the manifest

        returns:
            (value, score, method)
            value: original manifest string or None
            score: 0..100 (100 for exact case-insensitive match)
            method: "exact" or "none"
        """
        if not code:
            return None, 0, "none"

        key = str(code).strip().lower()
        if not key:
            return None, 0, "none"

        if key in self._lut:
            return self._lut[key], 100, "exact"

        return None, 0, "none"

    @classmethod
    def from_text(cls, text: str) -> "SimpleManifestMatcher":
        """
        build a matcher from raw text like a barcodes.txt file
        splits on whitespace and commas, strips, and removes duplicates
        """
        if not text:
            return cls([])

        #handle optional utf-8 bom
        if text and text[0] == "\ufeff":
            text = text[1:]

        import re

        parts = [t.strip() for t in re.split(r"[\s,]+", text) if t.strip()]
        seen = set()
        uniq = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                uniq.append(p)

        return cls(uniq)

    @classmethod
    def from_file(cls, path: str) -> "SimpleManifestMatcher":
        """
        convenience helper to load from a barcodes.txt path
        this is optional; manifestWatcherv001.py will usually feed codes directly
        """
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
        except Exception:
            return cls([])

        return cls.from_text(txt)
