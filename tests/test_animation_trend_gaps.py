import unittest
from datetime import date
from unittest.mock import patch

from PIL import Image, ImageDraw

from sonntagsfrage.animation import LAYOUT, draw_trend, font


class TrendGapTests(unittest.TestCase):
    def test_connects_up_to_three_months_and_breaks_after_that(self) -> None:
        frames = [
            {"date": "2024-01-31", "values": {"SPD": 24}},
            {"date": "2024-02-15", "values": {"SPD": 26, "CDU": 31}},
            {"date": "2024-04-02", "values": {"SPD": 25, "CDU": 30}},
            {"date": "2024-05-06", "values": {"CDU": 32}},
            {"date": "2024-08-06", "values": {"SPD": 27, "CDU": 34}},
            {"date": "2024-09-06", "values": {"CDU": 33}},
        ]
        segments = []
        original_line = ImageDraw.ImageDraw.line

        def record_line(draw, points, fill=None, width=0, joint=None):
            if joint == "curve":
                segments.append(list(points))
            return original_line(draw, points, fill=fill, width=width, joint=joint)

        draw = ImageDraw.Draw(Image.new("RGB", (640, 640), "white"))
        start, end = date(2024, 1, 1), date(2024, 9, 6)
        with patch.object(ImageDraw.ImageDraw, "line", record_line):
            draw_trend(draw, frames, 610, start, end, [], [], LAYOUT,
                       lambda value: value, lambda value: value, lambda value: value, font)

        self.assertEqual([len(segment) for segment in segments], [3, 5])


if __name__ == "__main__":
    unittest.main()
