import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auto_movie_edit.cli import _strip_runtime_fields
from auto_movie_edit.models import Pack, TimelineRow, WorkbookData
from auto_movie_edit.utils import Timecode
from auto_movie_edit.ymmp import ProjectBuilder


class PackTimingTest(unittest.TestCase):
    def test_strip_runtime_fields_preserves_relative_offsets(self) -> None:
        source = {
            "Items": [
                {"Frame": 120, "Length": 45, "Name": "first"},
                {"Frame": 150, "Length": 15, "Name": "second"},
            ]
        }

        sanitized = _strip_runtime_fields(source, preserve_timing=True)
        self.assertIn("Items", sanitized)
        self.assertNotIn("Frame", sanitized["Items"][0])
        self.assertEqual(sanitized["Items"][0]["FrameOffset"], 0)
        self.assertEqual(sanitized["Items"][1]["FrameOffset"], 30)
        self.assertEqual(sanitized["Items"][0]["LengthFrames"], 45)
        self.assertEqual(sanitized["Items"][1]["LengthFrames"], 15)

    def test_pack_instantiation_applies_frame_offsets(self) -> None:
        pack_template = {
            "Items": [
                {"$type": "SampleType", "FrameOffset": 0, "LengthFrames": 30},
                {"$type": "SampleType", "FrameOffset": 45, "LengthFrames": 10},
            ]
        }

        data = WorkbookData(packs={"pack1": Pack(pack_id="pack1", overrides=pack_template)})
        builder = ProjectBuilder(data)
        row = TimelineRow(
            index=0,
            start=Timecode(0, 0, 1, 0),
            end=Timecode(0, 0, 2, 0),
            subtitle=None,
            telop=None,
        )

        instantiated = builder._instantiate_pack(data.packs["pack1"], row)
        self.assertEqual(len(instantiated), 2)
        self.assertEqual([item["Frame"] for item in instantiated], [60, 105])
        self.assertEqual([item["Length"] for item in instantiated], [30, 10])


if __name__ == "__main__":
    unittest.main()
