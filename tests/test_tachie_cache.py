import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auto_movie_edit.models import Character, TimelineRow, WorkbookData
from auto_movie_edit.ymmp import ProjectBuilder, _resolve_tachie_expression_path


class TachieResolutionCacheTest(unittest.TestCase):
    def test_cache_usage_and_fallback_preserved(self) -> None:
        with TemporaryDirectory() as tmpdir:
            base_path = str(Path(tmpdir) / "{expression}.png")
            happy_path = Path(tmpdir) / "happy.png"
            happy_path.touch()
            expected_path = str(happy_path.resolve())

            data = WorkbookData(
                characters={"ch": Character(name="キャラ", parts={"目": base_path})}
            )
            builder = ProjectBuilder(data)

            original_resolve = _resolve_tachie_expression_path
            call_records: list[tuple[str, str]] = []

            def fake_resolve(path: str, expression: str):
                call_records.append((path, expression))
                return original_resolve(path, expression)

            with patch("auto_movie_edit.ymmp._resolve_tachie_expression_path", side_effect=fake_resolve):
                row1 = TimelineRow(
                    index=0,
                    start=None,
                    end=None,
                    subtitle=None,
                    telop=None,
                    character="ch",
                    expressions={"目": "happy"},
                )
                items1 = builder._build_row_items(row1)
                self.assertEqual(len(items1), 1)
                params1 = items1[0]["TachieItemParameter"]
                self.assertEqual(params1["Eye"], expected_path)
                self.assertEqual(len(call_records), 1)

                row2 = TimelineRow(
                    index=1,
                    start=None,
                    end=None,
                    subtitle=None,
                    telop=None,
                    character="ch",
                    expressions={"目": "happy"},
                )
                builder._build_row_items(row2)
                self.assertEqual(len(call_records), 1, "Resolution should be cached for identical expressions")

                row3 = TimelineRow(
                    index=2,
                    start=None,
                    end=None,
                    subtitle=None,
                    telop=None,
                    character="ch",
                    expressions={"目": "missing"},
                )
                items3 = builder._build_row_items(row3)
                self.assertEqual(len(call_records), 2)
                params3 = items3[0]["TachieItemParameter"]
                self.assertEqual(
                    params3["Eye"],
                    expected_path,
                    "Missing expressions should reuse last successful path",
                )

                row4 = TimelineRow(
                    index=3,
                    start=None,
                    end=None,
                    subtitle=None,
                    telop=None,
                    character="ch",
                    expressions={"目": "missing"},
                )
                items4 = builder._build_row_items(row4)
                self.assertEqual(
                    len(call_records),
                    2,
                    "Failed resolution should also be cached to avoid repeat lookups",
                )
                params4 = items4[0]["TachieItemParameter"]
                self.assertEqual(params4["Eye"], expected_path)


if __name__ == "__main__":
    unittest.main()
