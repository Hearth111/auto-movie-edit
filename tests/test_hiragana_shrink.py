import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auto_movie_edit.ymmp import apply_hiragana_shrink, _determine_hiragana_scale


class HiraganaZoomShrinkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_path = Path(__file__).resolve().parent / "data" / "hiragana_shrink_sample.ymmp"
        self.sample_data = json.loads(self.sample_path.read_text("utf-8"))

    def test_constant_zoom_is_scaled(self) -> None:
        with TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.ymmp"
            output_path = Path(tmpdir) / "output.ymmp"
            input_path.write_text(
                json.dumps(self.sample_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            apply_hiragana_shrink(input_path, output_path, scale=0.8)
            result = json.loads(Path(output_path).read_text("utf-8"))

        original_item = self.sample_data["Timelines"][0]["Items"][0]
        scaled_item = result["Timelines"][0]["Items"][0]
        expected_scale = _determine_hiragana_scale(original_item, 0.8)

        self.assertIsInstance(scaled_item["Zoom"], float)
        self.assertAlmostEqual(
            scaled_item["Zoom"],
            round(original_item["Zoom"] * expected_scale, 4),
        )

    def test_keyframe_zoom_values_are_scaled(self) -> None:
        with TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.ymmp"
            output_path = Path(tmpdir) / "output.ymmp"
            input_path.write_text(
                json.dumps(self.sample_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            apply_hiragana_shrink(input_path, output_path, scale=0.8)
            result = json.loads(Path(output_path).read_text("utf-8"))

        original_item = self.sample_data["Timelines"][0]["Items"][1]
        scaled_item = result["Timelines"][0]["Items"][1]
        expected_scale = _determine_hiragana_scale(original_item, 0.8)

        original_values = original_item["Zoom"]["Values"]
        scaled_values = scaled_item["Zoom"]["Values"]

        self.assertEqual(len(original_values), len(scaled_values))

        for original_entry, scaled_entry in zip(original_values, scaled_values):
            self.assertAlmostEqual(
                scaled_entry["Value"],
                round(original_entry["Value"] * expected_scale, 4),
            )
            # Ensure metadata such as Frame/Ease stays untouched
            for key, value in original_entry.items():
                if key != "Value":
                    self.assertEqual(scaled_entry.get(key), value)


if __name__ == "__main__":
    unittest.main()
