from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.build_content_release import _build_deterministic_pack, _records


class ContentReleaseTests(unittest.TestCase):
    def test_text_line_endings_do_not_change_manifest_records_or_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "data" / "sample.json"
            source.parent.mkdir(parents=True)

            source.write_bytes(b'{\r\n  "value": 1\r\n}\r\n')
            crlf_records = _records(root, [source])
            crlf_pack = root / "crlf.zip"
            _build_deterministic_pack(root, crlf_pack, crlf_records)

            source.write_bytes(b'{\n  "value": 1\n}\n')
            lf_records = _records(root, [source])
            lf_pack = root / "lf.zip"
            _build_deterministic_pack(root, lf_pack, lf_records)

            self.assertEqual(crlf_records, lf_records)
            self.assertEqual(crlf_pack.read_bytes(), lf_pack.read_bytes())


if __name__ == "__main__":
    unittest.main()
