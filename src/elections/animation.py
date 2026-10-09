"""Export INSA online-panel polls as a one-minute square GIF and MP4."""

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

from .race import load_frames, load_governments


COLORS = {
    "CDU/CSU": "#343b4a", "SPD": "#d6444e", "GRÜNE": "#43a56b",
    "FDP": "#e6b635", "LINKE": "#ad4b8e", "AfD": "#3985c6",
    "BSW": "#8c3656", "FW": "#e48a3f", "PIRATEN": "#e99340",
}
MONTHS = ("Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez")
MAX_CONNECTED_GAP_DAYS = 21
GOVERNMENT_BAND_COLORS = ("#fff0c9", "#e1f4e8")
FONT_REGULAR = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
FONT_BOLD = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


@dataclass(frozen=True)
class Layout:
    """Frame geometry in a 640px reference coordinate system."""

    canvas_size: int = 640
    header_height: int = 112
    header_kicker: tuple[int, int] = (30, 24)
    header_title: tuple[int, int] = (30, 51)
    flag: tuple[int, int, int, int] = (564, 26, 610, 53)
    government_label: tuple[int, int] = (30, 87)
    date_label: tuple[int, int] = (30, 125)
    frame_counter: tuple[int, int] = (610, 132)
    panel_label: tuple[int, int] = (355, 132)

    bar_left: int = 164
    bar_right: int = 556
    bar_grid_top: int = 183
    bar_grid_bottom: int = 507
    bar_ticks_y: int = 170
    bar_first_y: int = 182
    bar_row_step: int = 39
    bar_height: int = 27
    party_marker: tuple[int, int, int, int] = (20, 5, 24, 23)
    party_label_x: int = 30
    value_label_max_x: int = 566
    election_marker_overhang: int = 3

    legend_party_marker: tuple[int, int, int, int] = (20, 498, 24, 510)
    legend_party_label: tuple[int, int] = (30, 495)
    polls_line: tuple[int, int, int, int] = (126, 501, 136, 501)
    polls_label: tuple[int, int] = (140, 495)
    election_circle: tuple[int, int, int, int] = (212, 497, 220, 505)
    election_legend_label: tuple[int, int] = (226, 495)
    bar_result_line: tuple[int, int, int, int] = (303, 495, 303, 505)
    bar_result_label: tuple[int, int] = (311, 495)
    government_swatches: tuple[tuple[int, int, int, int], tuple[int, int, int, int]] = (
        (417, 497, 425, 505), (428, 497, 436, 505),
    )
    government_legend_label: tuple[int, int] = (442, 495)

    trend_bounds: tuple[int, int, int, int] = (30, 532, 610, 592)
    trend_year_label_y: int = 596
    trend_year_tick_length: int = 3
    footer_rule: tuple[int, int, int, int] = (30, 615, 610, 615)
    copyright_label: tuple[int, int] = (30, 618)


LAYOUT = Layout()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_BOLD if bold else FONT_REGULAR:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def load_elections(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_date: dict[date, dict[str, float]] = {}
    for row in rows:
        election_date = date.fromisoformat(row["date"])
        party = row["party"].strip()
        percent = float(row["percent"])
        if not party or not 0 <= percent <= 100:
            raise ValueError(f"Invalid election result in {path}: {row}")
        by_date.setdefault(election_date, {})[party] = percent
    return [{"date": election_date, "values": values}
            for election_date, values in sorted(by_date.items())]


def frame_date(frame: dict) -> date:
    return date.fromisoformat(frame.get("reference_date") or frame["date"])


def draw_trend(draw: ImageDraw.ImageDraw, frames: list[dict], right: int,
               timeline_start: date, timeline_end: date, elections: list[dict],
               governments: list[dict], layout: Layout, px, px_x, px_y, face) -> None:
    left, top, chart_right, bottom = (px_x(layout.trend_bounds[0]), px_y(layout.trend_bounds[1]),
                                      px_x(layout.trend_bounds[2]), px_y(layout.trend_bounds[3]))
    last_date = frame_date(frames[-1])
    span = max((timeline_end - timeline_start).days, 1)

    for index, government in enumerate(governments):
        start = max(government["start"], timeline_start)
        end = min(government["end"] - timedelta(days=1), last_date)
        if start > end:
            continue
        x_start = left + round((chart_right - left) * (start - timeline_start).days / span)
        x_end = left + round((chart_right - left) * (end - timeline_start).days / span)
        draw.rectangle((x_start, top, min(x_end, right), bottom),
                       fill=GOVERNMENT_BAND_COLORS[index % len(GOVERNMENT_BAND_COLORS)])

    for tick in (0, 25, 50):
        y = bottom - round((bottom - top) * tick / 50)
        draw.line((left, y, right, y), fill="#e2e6ee", width=max(1, px(1)))

    visible_elections = [election for election in elections
                         if timeline_start <= election["date"] <= last_date]
    election_positions = []
    for election in visible_elections:
        x = left + round((chart_right - left) *
                         (election["date"] - timeline_start).days / span)
        draw.line((x, top, x, bottom), fill="#c6ccd6", width=max(1, px(1)))
        election_positions.append((election, x))

    history: dict[str, list[tuple[int, float]]] = {}
    for item in frames:
        day = (frame_date(item) - timeline_start).days
        for party, value in item["values"].items():
            history.setdefault(party, []).append((day, value))

    for party, points in history.items():
        dated_coordinates = [
            (day,
             (left + round((chart_right - left) * day / span),
              bottom - round((bottom - top) * min(value, 50) / 50)))
            for day, value in points
        ]
        segments: list[list[tuple[int, int]]] = []
        segment = []
        previous_day = None
        for day, coordinate in dated_coordinates:
            if previous_day is not None and day - previous_day > MAX_CONNECTED_GAP_DAYS:
                if segment:
                    segments.append(segment)
                segment = []
            segment.append(coordinate)
            previous_day = day
        if segment:
            segments.append(segment)

        for segment in segments:
            color = COLORS.get(party, "#8895a7")
            if len(segment) > 1:
                draw.line(segment, fill=color, width=max(1, px(2)), joint="curve")
            else:
                x, y = segment[0]
                radius = max(1, px(1))
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    for election, x in election_positions:
        for party, percent in election["values"].items():
            y = bottom - round((bottom - top) * min(percent, 50) / 50)
            radius = max(2, px(3))
            color = COLORS.get(party, "#8895a7")
            draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                         fill="#f7f8fc", outline=color, width=max(1, px(2)))
    draw.rectangle((left, top, chart_right, bottom),
                   outline="#aeb6c2", width=max(1, px(1)))
    first_year, last_year = timeline_start.year, timeline_end.year
    for year in range(first_year, last_year + 1):
        year_start = timeline_start if year == first_year else date(year, 1, 1)
        if year_start > timeline_end:
            continue
        x = left + round((chart_right - left) * (year_start - timeline_start).days / span)
        draw.line((x, bottom, x, bottom + px(layout.trend_year_tick_length)),
                  fill="#65718a", width=max(1, px(1)))
        if year % 2 == 0:
            anchor = "la" if year == first_year else "ma"
            draw.text((x, px_y(layout.trend_year_label_y)), str(year), font=face(9),
                      fill="#65718a", anchor=anchor)


def draw_frame(frame: dict, number: int, total: int, size: int | tuple[int, int],
               history: list[dict], timeline_start: date, timeline_end: date,
               elections: list[dict], governments: list[dict]) -> Image.Image:
    layout = LAYOUT
    width, height = (size, size) if isinstance(size, int) else size
    # Layout coordinates use a 640px design grid. Typography and strokes follow
    # the shorter canvas axis so wide outputs gain room without oversized text.
    scale = min(width / layout.canvas_size, height / layout.canvas_size)
    px = lambda value: round(value * scale)
    px_x = lambda value: round(value * width / layout.canvas_size)
    px_y = lambda value: round(value * height / layout.canvas_size)
    point = lambda xy: (px_x(xy[0]), px_y(xy[1]))
    box = lambda xyxy: (px_x(xyxy[0]), px_y(xyxy[1]), px_x(xyxy[2]), px_y(xyxy[3]))
    line = lambda xyxy: box(xyxy)
    face = lambda value, bold=False: font(max(8, px(value)), bold)
    image = Image.new("RGB", (width, height), "#f7f8fc")
    draw = ImageDraw.Draw(image)
    ink = "#172033"
    quiet = "#65718a"

    draw.rectangle((0, 0, width, px_y(layout.header_height)), fill="#172039")
    draw.text(point(layout.header_kicker), "DEUTSCHLAND  ·  BUNDESTAG",
              font=face(14, True), fill="#b9c1ff")
    draw.text(point(layout.header_title), "INSA SONNTAGSFRAGE",
              font=face(31, True), fill="#ffffff")
    flag_left, flag_top, flag_right, flag_bottom = box(layout.flag)
    border = max(1, px(1))
    inner_left, inner_right = flag_left + border, flag_right - border
    inner_top, inner_bottom = flag_top + border, flag_bottom - border
    stripe_height = (inner_bottom - inner_top + 1) / 3
    draw.rectangle((flag_left, flag_top, flag_right, flag_bottom),
                   fill="#d8dcff", outline="#d8dcff")
    draw.rectangle((inner_left, inner_top, inner_right,
                    round(inner_top + stripe_height - 1)), fill="#000000")
    draw.rectangle((inner_left, round(inner_top + stripe_height), inner_right,
                    round(inner_top + 2 * stripe_height - 1)), fill="#dd0000")
    draw.rectangle((inner_left, round(inner_top + 2 * stripe_height), inner_right,
                    inner_bottom), fill="#ffce00")
    government = frame["government"]
    government_label = f"Regierung: {government['cabinet']} · {' + '.join(government['parties'])}"
    draw.text(point(layout.government_label), government_label,
              font=face(14), fill="#d8dcff")
    published = date.fromisoformat(frame["date"])
    date_label = f"{published.day:02d}. {MONTHS[published.month - 1]} {published.year}"
    draw.text(point(layout.date_label), date_label, font=face(30, True), fill=ink)
    draw.text(point(layout.frame_counter), f"{number + 1:,} / {total:,}".replace(",", "."),
              font=face(12), fill=quiet, anchor="ra")
    draw.text(point(layout.panel_label), f"Online-Panel  ·  n={frame['sample']}",
              font=face(12), fill=quiet)
    reference_date = frame_date(frame)

    bar_left, bar_right = px_x(layout.bar_left), px_x(layout.bar_right)
    for tick in range(0, 51, 10):
        x = bar_left + round((bar_right - bar_left) * tick / 50)
        draw.line((x, px_y(layout.bar_grid_top), x, px_y(layout.bar_grid_bottom)),
                  fill="#e2e6ee", width=max(1, px(1)))
        draw.text((x, px_y(layout.bar_ticks_y)), str(tick), font=face(11),
                  fill="#8a95aa", anchor="mb")

    ranked = sorted(frame["values"].items(), key=lambda item: (-item[1], item[0]))
    latest_election = next(
        (election for election in reversed(elections) if election["date"] <= reference_date),
        None,
    )
    for rank, (party, value) in enumerate(ranked):
        y = px_y(layout.bar_first_y + rank * layout.bar_row_step)
        if party in government["parties"]:
            marker_left, marker_top, marker_right, marker_bottom = layout.party_marker
            draw.rounded_rectangle((px_x(marker_left), y + px(marker_top),
                                    px_x(marker_right), y + px(marker_bottom)),
                                   radius=px(2), fill="#6c65df")
        draw.text((px_x(layout.party_label_x), y + px(5)), party,
                  font=face(18, True), fill=ink)
        bar_end = bar_left + round((bar_right - bar_left) * min(value, 50) / 50)
        draw.rounded_rectangle((bar_left, y, max(bar_left + 1, bar_end),
                                y + px(layout.bar_height)),
                               radius=px(5), fill=COLORS.get(party, "#8895a7"))
        if latest_election and party in latest_election["values"]:
            result_x = bar_left + round(
                (bar_right - bar_left) * min(latest_election["values"][party], 50) / 50
            )
            marker_top = y - px(layout.election_marker_overhang)
            marker_bottom = y + px(layout.bar_height + layout.election_marker_overhang)
            draw.line((result_x, marker_top, result_x, marker_bottom),
                      fill="#8a95a2", width=max(2, px(2)))
        value_label = f"{value:g}".replace(".", ",") + " %"
        draw.text((min(bar_end + px(8), px_x(layout.value_label_max_x)), y + px(3)), value_label,
                  font=face(16, True), fill=ink)

    timeline_span = max((timeline_end - timeline_start).days, 1)
    trend_left, _, trend_right, _ = layout.trend_bounds
    progress = px_x(trend_left) + round((px_x(trend_right) - px_x(trend_left)) *
                                      (reference_date - timeline_start).days / timeline_span)
    draw.rectangle(box(layout.legend_party_marker), fill="#6c65df")
    draw.text(point(layout.legend_party_label), "Regierungspartei",
              font=face(11), fill=quiet)
    draw.line(line(layout.polls_line), fill="#65718a", width=max(1, px(2)))
    draw.text(point(layout.polls_label), "Umfragen", font=face(10), fill=quiet)
    draw.ellipse(box(layout.election_circle),
                 fill="#f7f8fc", outline="#65718a", width=max(1, px(1)))
    draw.text(point(layout.election_legend_label), "Wahlergebnis",
              font=face(10), fill=quiet)
    draw.line(line(layout.bar_result_line), fill="#8a95a2",
              width=max(2, px(2)))
    election_label = f"Balken: Wahl {latest_election['date'].year}" if latest_election else "Balken"
    draw.text(point(layout.bar_result_label), election_label,
              font=face(10), fill=quiet)
    for swatch, color in zip(layout.government_swatches, GOVERNMENT_BAND_COLORS):
        draw.rectangle(box(swatch), fill=color)
    draw.text(point(layout.government_legend_label), "Regierung",
              font=face(10), fill=quiet)
    draw_trend(draw, history, progress, timeline_start, timeline_end,
               elections, governments, layout, px, px_x, px_y, face)
    draw.line(line(layout.footer_rule), fill="#dfe3ec", width=max(1, px(1)))
    draw.text(point(layout.copyright_label),
              "Daten: © wahlrecht.de / INSA · dawum.de / ODbL · Bundeswahlleiterin (DL-DE/BY-2.0)",
              font=face(10), fill="#45516a")
    return image


def run_ffmpeg(*arguments: str) -> None:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"ffmpeg exited with {result.returncode}")


def render_video(frames: list[dict], elections: list[dict], governments: list[dict], path: Path,
                 size: int | tuple[int, int], frame_rate: str) -> None:
    width, height = (size, size) if isinstance(size, int) else size
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{width}x{height}",
        "-framerate", frame_rate, "-i", "pipe:0", "-an", "-c:v", "ffv1",
        "-level", "3", "-pix_fmt", "bgr0", str(path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE)
    assert process.stdin is not None and process.stderr is not None
    try:
        history = []
        timeline_start = frame_date(frames[0])
        timeline_end = frame_date(frames[-1])
        for index, frame in enumerate(frames):
            history.append(frame)
            process.stdin.write(draw_frame(frame, index, len(frames), size, history,
                                           timeline_start, timeline_end, elections,
                                           governments).tobytes())
    except BrokenPipeError as exc:
        raise RuntimeError(f"ffmpeg stopped while receiving frames: {process.stderr.read().decode()}") from exc
    finally:
        process.stdin.close()
    error = process.stderr.read().decode().strip()
    if process.wait():
        raise RuntimeError(error or "ffmpeg could not encode the animation")


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--polls", type=Path, default=Path("data/insa_polls.csv"))
    cli.add_argument("--results", type=Path, default=Path("data/insa_results.csv"))
    cli.add_argument("--governments", type=Path, default=Path("data/governments.csv"))
    cli.add_argument("--elections", type=Path, default=Path("data/bundestag_elections.csv"))
    cli.add_argument("--output", type=Path, default=Path("charts/insa-race.gif"))
    cli.add_argument("--seconds", type=int, default=60)
    cli.add_argument("--size", type=int, default=640,
                     help="square width and height in pixels (default: 640)")
    cli.add_argument("--width", type=int, help="output width; pair with --height to set aspect ratio")
    cli.add_argument("--height", type=int, help="output height; pair with --width to set aspect ratio")
    cli.add_argument("--colors", type=int, default=48, help="GIF palette colors (4–256)")
    cli.add_argument("--no-mp4", action="store_true", help="skip the smaller video companion")
    args = cli.parse_args()
    if args.seconds < 1 or not 4 <= args.colors <= 256:
        cli.error("seconds must be positive and colors between 4 and 256")
    if (args.width is None) != (args.height is None):
        cli.error("--width and --height must be provided together")
    dimensions = (args.width, args.height) if args.width is not None else (args.size, args.size)
    if min(dimensions) < 320:
        cli.error("output width and height must each be at least 320")
    if shutil.which("ffmpeg") is None:
        cli.error("ffmpeg is required to encode GIF and MP4 files")
    try:
        frames = load_frames(args.polls, args.results, args.governments)
        frames = [frame for frame in frames if frame["method"] == "Online-Panel"]
        if not frames:
            raise ValueError("No INSA Online-Panel polls with party results were found")
        elections = load_elections(args.elections)
        governments = load_governments(args.governments)
        frame_rate = str(Fraction(len(frames), args.seconds))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="insa-race-") as directory:
            temporary = Path(directory)
            master = temporary / "master.mkv"
            palette = temporary / "palette.png"
            gif_output = temporary / "race.gif"
            mp4_output = temporary / "race.mp4"
            render_video(frames, elections, governments, master, dimensions, frame_rate)
            run_ffmpeg("-i", str(master), "-vf",
                       f"palettegen=max_colors={args.colors}:stats_mode=full",
                       "-frames:v", "1", str(palette))
            run_ffmpeg("-i", str(master), "-i", str(palette), "-lavfi",
                       "paletteuse=dither=none:diff_mode=rectangle", "-fps_mode", "passthrough",
                       "-gifflags", "+transdiff+offsetting", "-loop", "0", str(gif_output))
            gif_output.replace(args.output)
            if not args.no_mp4:
                video_path = args.output.with_suffix(".mp4")
                run_ffmpeg("-i", str(master), "-an", "-c:v", "libx264",
                           "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
                           "-movflags", "+faststart", str(mp4_output))
                mp4_output.replace(video_path)
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        cli.exit(1, f"error: {exc}\n")
    print(f"GIF: {args.output} ({args.output.stat().st_size / 1_000_000:.1f} MB, {len(frames)} polls in {args.seconds}s)")
    if not args.no_mp4:
        print(f"MP4: {video_path} ({video_path.stat().st_size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    main()
