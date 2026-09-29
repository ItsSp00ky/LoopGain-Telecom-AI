"""Step 14 provenance must reject altered or missing local terrain evidence."""

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from antenna_cell_placement.fabdem import verify_fabdem_manifest


class FabdemManifestTests(unittest.TestCase):
    def test_manifest_detects_tile_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tile = root / "N32E022_FABDEM_V1-2.tif"
            tile.write_bytes(b"original")
            manifest = {"dataset": "FABDEM V1-2", "tiles": [{
                "filename": tile.name, "bytes": tile.stat().st_size,
                "sha256": sha256(tile.read_bytes()).hexdigest()}]}
            (root / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(verify_fabdem_manifest(root), manifest)
            tile.write_bytes(b"altered!")
            with self.assertRaisesRegex(ValueError, "checksum"):
                verify_fabdem_manifest(root)


if __name__ == "__main__":
    unittest.main()
