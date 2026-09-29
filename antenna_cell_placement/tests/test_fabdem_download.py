"""The FABDEM downloader must extract exactly verified ZIP members."""

from io import BytesIO
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from tools.download_fabdem import _entries, _fetch_member, bundle_name, tile_name


class FabdemDownloadTests(unittest.TestCase):
    def test_bundle_names_and_verified_range_extraction(self):
        self.assertEqual(bundle_name(32, 22), "N30E020-N40E030_FABDEM_V1-2.zip")
        self.assertEqual(tile_name(32, 22), "N32E022_FABDEM_V1-2.tif")
        buffer = BytesIO()
        payload = b"sample raster bytes" * 100
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            archive.writestr(tile_name(32, 22), payload)
        raw = buffer.getvalue()
        with patch("tools.download_fabdem._range", side_effect=lambda _u, start, length, _s, _e: raw[start:start + length]):
            entry = _entries("memory", len(raw), "")[tile_name(32, 22)]
            self.assertEqual(_fetch_member("memory", entry, len(raw), ""), payload)
            entry["crc32"] ^= 1
            with self.assertRaisesRegex(ValueError, "CRC"):
                _fetch_member("memory", entry, len(raw), "")


if __name__ == "__main__":
    unittest.main()
