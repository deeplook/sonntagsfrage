from datetime import date

from PIL import Image

from sonntagsfrage.animation import draw_frame


def test_draw_frame_returns_rgb_image_at_requested_size() -> None:
    frame = {
        "date": "2026-10-11",
        "values": {"CDU/CSU": 28.0, "SPD": 24.0, "GRÜNE": 12.0},
        "government": {"cabinet": "Test cabinet", "parties": ["CDU/CSU", "SPD"]},
        "sample": 1000,
    }

    image = draw_frame(
        frame,
        number=0,
        total=1,
        size=(960, 640),
        history=[frame],
        timeline_start=date(2026, 10, 11),
        timeline_end=date(2026, 10, 11),
        elections=[],
        governments=[],
    )

    assert isinstance(image, Image.Image)
    assert image.mode == "RGB"
    assert image.size == (960, 640)
