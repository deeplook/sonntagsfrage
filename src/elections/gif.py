"""Export every INSA poll as a one-minute square GIF and MP4."""

import argparse
from datetime import date
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont

from .race import load_frames


COLORS = {
    "CDU/CSU": "#343b4a", "SPD": "#d6444e", "GRÜNE": "#43a56b",
    "FDP": "#e6b635", "LINKE": "#ad4b8e", "AfD": "#3985c6",
    "BSW": "#8c3656", "FW": "#e48a3f", "PIRATEN": "#e99340",
}
MONTHS = ("Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez")
FONT_REGULAR = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
FONT_BOLD = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_BOLD if bold else FONT_REGULAR:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def draw_frame(frame: dict, number: int, total: int, size: int) -> Image.Image:
    scale = size / 640
    px = lambda value: round(value * scale)
    face = lambda value, bold=False: font(max(8, px(value)), bold)
    image = Image.new("RGB", (size, size), "#f7f8fc")
    draw = ImageDraw.Draw(image)
    ink = "#172033"
    quiet = "#65718a"

    draw.rectangle((0, 0, size, px(126)), fill="#172039")
    draw.text((px(30), px(24)), "DEUTSCHLAND  ·  BUNDESTAG", font=face(14, True), fill="#b9c1ff")
    draw.text((px(30), px(51)), "INSA SONNTAGSFRAGE", font=face(31, True), fill="#ffffff")
    government = frame["government"]
    government_label = f"Regierung: {government['cabinet']} · {' + '.join(government['parties'])}"
    draw.text((px(30), px(101)), government_label, font=face(14), fill="#d8dcff")
    published = date.fromisoformat(frame["date"])
    date_label = f"{published.day:02d}. {MONTHS[published.month - 1]} {published.year}"
    draw.text((px(30), px(139)), date_label, font=face(30, True), fill=ink)
    draw.text((px(610), px(146)), f"{number + 1:,} / {total:,}".replace(",", "."),
              font=face(14), fill=quiet, anchor="ra")

    bar_left, bar_right = px(164), px(556)
    for tick in range(0, 51, 10):
        x = bar_left + round((bar_right - bar_left) * tick / 50)
        draw.line((x, px(197), x, px(522)), fill="#e2e6ee", width=max(1, px(1)))
        draw.text((x, px(184)), str(tick), font=face(11), fill="#8a95aa", anchor="mb")

    ranked = sorted(frame["values"].items(), key=lambda item: (-item[1], item[0]))
    for rank, (party, value) in enumerate(ranked):
        y = px(208 + rank * 39)
        if party in government["parties"]:
            draw.rounded_rectangle((px(20), y + px(5), px(24), y + px(23)),
                                   radius=px(2), fill="#6c65df")
        draw.text((px(30), y + px(5)), party, font=face(18, True), fill=ink)
        bar_end = bar_left + round((bar_right - bar_left) * min(value, 50) / 50)
        draw.rounded_rectangle((bar_left, y, max(bar_left + 1, bar_end), y + px(27)),
                               radius=px(5), fill=COLORS.get(party, "#8895a7"))
        value_label = f"{value:g}".replace(".", ",") + " %"
        draw.text((min(bar_end + px(8), px(566)), y + px(3)), value_label,
                  font=face(16, True), fill=ink)

    draw.rectangle((px(30), px(538), px(610), px(544)), fill="#e2e6ee")
    progress = px(30) + round(px(580) * (number + 1) / total)
    draw.rectangle((px(30), px(538), progress, px(544)), fill="#5b56cc")
    method = "Online-Panel" if frame["method"] == "Online-Panel" else "Telefon + Online"
    draw.text((px(30), px(555)), f"{method}  ·  n={frame['sample']}", font=face(13), fill=quiet)
    draw.rectangle((px(435), px(558), px(439), px(572)), fill="#6c65df")
    draw.text((px(447), px(555)), "Regierungspartei", font=face(12), fill=quiet)
    draw.line((px(30), px(585), px(610), px(585)), fill="#dfe3ec", width=max(1, px(1)))
    draw.text((px(30), px(594)), "Daten: © wahlrecht.de / INSA", font=face(12), fill="#45516a")
    draw.text((px(30), px(613)), "Weitere Datenbank: © dawum.de · ODbL", font=face(12), fill="#45516a")
    return image


def run_ffmpeg(*arguments: str) -> None:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"ffmpeg exited with {result.returncode}")


def render_video(frames: list[dict], path: Path, size: int, frame_rate: str) -> None:
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{size}x{size}",
        "-framerate", frame_rate, "-i", "pipe:0", "-an", "-c:v", "ffv1",
        "-level", "3", "-pix_fmt", "bgr0", str(path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE)
    assert process.stdin is not None and process.stderr is not None
    try:
        for index, frame in enumerate(frames):
            process.stdin.write(draw_frame(frame, index, len(frames), size).tobytes())
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
    cli.add_argument("--output", type=Path, default=Path("charts/insa-race.gif"))
    cli.add_argument("--seconds", type=int, default=60)
    cli.add_argument("--size", type=int, default=640, help="square width and height in pixels")
    cli.add_argument("--colors", type=int, default=48, help="GIF palette colors (4–256)")
    cli.add_argument("--no-mp4", action="store_true", help="skip the smaller video companion")
    args = cli.parse_args()
    if args.seconds < 1 or args.size < 320 or not 4 <= args.colors <= 256:
        cli.error("seconds must be positive, size at least 320, and colors between 4 and 256")
    if shutil.which("ffmpeg") is None:
        cli.error("ffmpeg is required to encode GIF and MP4 files")
    try:
        frames = load_frames(args.polls, args.results, args.governments)
        frame_rate = str(Fraction(len(frames), args.seconds))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="insa-race-") as directory:
            temporary = Path(directory)
            master = temporary / "master.mkv"
            palette = temporary / "palette.png"
            gif_output = temporary / "race.gif"
            mp4_output = temporary / "race.mp4"
            render_video(frames, master, args.size, frame_rate)
            run_ffmpeg("-i", str(master), "-vf",
                       f"palettegen=max_colors={args.colors}:stats_mode=diff",
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
