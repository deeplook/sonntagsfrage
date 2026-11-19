"""Generate per-parliament share pages and OG preview images for social media."""

from datetime import date
from io import BytesIO
from pathlib import Path
import shutil
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
import typer

from .animation import (
    COLORS, FONT_BOLD, FONT_REGULAR, FONT_SERIF, GOVERNMENT_BAND_COLORS, MONTHS,
    frame_date, load_state_coat, party_color,
)
from .cli import create_app, fail
from .race import load_dawum_frames, load_elections, load_frames, load_governments

PREVIEW_WIDTH = 1200
PREVIEW_HEIGHT = 630

PARLIAMENTS = {
    "bundestag": {
        "slug": "bundestag",
        "label": "Bundestag",
        "title": "Bundestagsumfragen",
        "og_title": "Bundestagsumfragen · Bar Chart Race",
        "description": "Aktuelle Wahlumfragen zum Bundestag als animiertes Balkendiagramm. Parteistärken im Zeitverlauf.",
    },
    "baden-wuerttemberg": {
        "slug": "baden-wuerttemberg",
        "label": "Baden-Württemberg",
        "title": "Landtagsumfragen Baden-Württemberg",
        "og_title": "Baden-Württemberg · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Landtag Baden-Württemberg als animiertes Balkendiagramm.",
    },
    "bayern": {
        "slug": "bayern",
        "label": "Bayern",
        "title": "Landtagsumfragen Bayern",
        "og_title": "Bayern · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Bayerischen Landtag als animiertes Balkendiagramm.",
    },
    "berlin": {
        "slug": "berlin",
        "label": "Berlin",
        "title": "Abgeordnetenhausumfragen Berlin",
        "og_title": "Berlin · Abgeordnetenhausumfragen",
        "description": "Aktuelle Wahlumfragen zum Abgeordnetenhaus von Berlin als animiertes Balkendiagramm.",
    },
    "brandenburg": {
        "slug": "brandenburg",
        "label": "Brandenburg",
        "title": "Landtagsumfragen Brandenburg",
        "og_title": "Brandenburg · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Landtag Brandenburg als animiertes Balkendiagramm.",
    },
    "bremen": {
        "slug": "bremen",
        "label": "Bremen",
        "title": "Bürgerschaftsumfragen Bremen",
        "og_title": "Bremen · Bürgerschaftsumfragen",
        "description": "Aktuelle Wahlumfragen zur Bremischen Bürgerschaft als animiertes Balkendiagramm.",
    },
    "hamburg": {
        "slug": "hamburg",
        "label": "Hamburg",
        "title": "Bürgerschaftsumfragen Hamburg",
        "og_title": "Hamburg · Bürgerschaftsumfragen",
        "description": "Aktuelle Wahlumfragen zur Hamburgischen Bürgerschaft als animiertes Balkendiagramm.",
    },
    "hessen": {
        "slug": "hessen",
        "label": "Hessen",
        "title": "Landtagsumfragen Hessen",
        "og_title": "Hessen · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Hessischen Landtag als animiertes Balkendiagramm.",
    },
    "mecklenburg-vorpommern": {
        "slug": "mecklenburg-vorpommern",
        "label": "Mecklenburg-Vorpommern",
        "title": "Landtagsumfragen Mecklenburg-Vorpommern",
        "og_title": "Mecklenburg-Vorpommern · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Landtag Mecklenburg-Vorpommern als animiertes Balkendiagramm.",
    },
    "niedersachsen": {
        "slug": "niedersachsen",
        "label": "Niedersachsen",
        "title": "Landtagsumfragen Niedersachsen",
        "og_title": "Niedersachsen · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Niedersächsischen Landtag als animiertes Balkendiagramm.",
    },
    "nordrhein-westfalen": {
        "slug": "nordrhein-westfalen",
        "label": "Nordrhein-Westfalen",
        "title": "Landtagsumfragen Nordrhein-Westfalen",
        "og_title": "Nordrhein-Westfalen · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Landtag Nordrhein-Westfalen als animiertes Balkendiagramm.",
    },
    "rheinland-pfalz": {
        "slug": "rheinland-pfalz",
        "label": "Rheinland-Pfalz",
        "title": "Landtagsumfragen Rheinland-Pfalz",
        "og_title": "Rheinland-Pfalz · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Landtag Rheinland-Pfalz als animiertes Balkendiagramm.",
    },
    "saarland": {
        "slug": "saarland",
        "label": "Saarland",
        "title": "Landtagsumfragen Saarland",
        "og_title": "Saarland · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Landtag des Saarlandes als animiertes Balkendiagramm.",
    },
    "sachsen": {
        "slug": "sachsen",
        "label": "Sachsen",
        "title": "Landtagsumfragen Sachsen",
        "og_title": "Sachsen · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Sächsischen Landtag als animiertes Balkendiagramm.",
    },
    "sachsen-anhalt": {
        "slug": "sachsen-anhalt",
        "label": "Sachsen-Anhalt",
        "title": "Landtagsumfragen Sachsen-Anhalt",
        "og_title": "Sachsen-Anhalt · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Landtag Sachsen-Anhalt als animiertes Balkendiagramm.",
    },
    "schleswig-holstein": {
        "slug": "schleswig-holstein",
        "label": "Schleswig-Holstein",
        "title": "Landtagsumfragen Schleswig-Holstein",
        "og_title": "Schleswig-Holstein · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Schleswig-Holsteinischen Landtag als animiertes Balkendiagramm.",
    },
    "thueringen": {
        "slug": "thueringen",
        "label": "Thüringen",
        "title": "Landtagsumfragen Thüringen",
        "og_title": "Thüringen · Landtagsumfragen",
        "description": "Aktuelle Wahlumfragen zum Thüringer Landtag als animiertes Balkendiagramm.",
    },
}

BASE_URL = "https://deeplook.github.io/sonntagsfrage"


def font(size: int, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = FONT_SERIF if serif else (FONT_BOLD if bold else FONT_REGULAR)
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def draw_preview_image(
    frame: dict,
    total_polls: int,
    elections: list[dict],
    governments: list[dict],
    header_kicker: str,
    header_title: str,
    state_coat: Image.Image | None = None,
) -> Image.Image:
    """Draw a 1200x630 preview image for social media sharing."""
    width, height = PREVIEW_WIDTH, PREVIEW_HEIGHT
    image = Image.new("RGB", (width, height), "#f3f1eb")
    draw = ImageDraw.Draw(image)
    ink = "#272923"
    quiet = "#686c62"

    draw.line((24, 90, width - 24, 90), fill="#d6d5cc", width=1)
    draw.text((24, 20), header_kicker, font=font(14, bold=True), fill=quiet)
    draw.text((24, 42), header_title, font=font(32, serif=True), fill=ink)

    flag_x = width - 70
    flag_shift = 48 if state_coat is not None else 0
    flag_x -= flag_shift
    draw.rectangle((flag_x, 20, flag_x + 46, 20 + 27), outline="#d6d5cc", width=1)
    draw.rectangle((flag_x + 1, 21, flag_x + 45, 21 + 8), fill="#000000")
    draw.rectangle((flag_x + 1, 21 + 9, flag_x + 45, 21 + 17), fill="#dd0000")
    draw.rectangle((flag_x + 1, 21 + 18, flag_x + 45, 21 + 26), fill="#ffce00")

    if state_coat is not None:
        coat_x = width - 60
        coat = state_coat.copy()
        coat.thumbnail((34, 40), Image.Resampling.LANCZOS)
        image.paste(coat, (coat_x, 14), coat)

    draw.rounded_rectangle((24, 100, width - 24, height - 20), radius=4,
                           fill="#fffefa", outline="#d6d5cc", width=1)

    government = frame["government"]
    gov_label = f"Regierung: {government['cabinet']} · {' + '.join(government['parties'])}"
    draw.text((40, 112), gov_label, font=font(12), fill="#737c68")

    published = date.fromisoformat(frame["date"])
    date_label = f"{published.day:02d}. {MONTHS[published.month - 1]} {published.year}"
    draw.text((40, 132), date_label, font=font(28, serif=True), fill=ink)

    draw.text((width - 40, 140), f"{total_polls:,} Umfragen".replace(",", "."),
              font=font(12), fill=quiet, anchor="ra")

    bar_left, bar_right = 180, width - 80
    bar_top = 180
    bar_row_height = 42
    bar_height = 28

    for tick in range(0, 51, 10):
        x = bar_left + round((bar_right - bar_left) * tick / 50)
        draw.line((x, bar_top, x, bar_top + 8 * bar_row_height), fill="#e7e6de", width=1)
        draw.text((x, bar_top - 10), str(tick), font=font(11), fill="#777a70", anchor="mb")

    ranked = sorted(frame["values"].items(), key=lambda item: (-item[1], item[0]))
    reference_date = frame_date(frame)
    latest_election = next(
        (election for election in reversed(elections) if election["date"] <= reference_date),
        None,
    )

    max_bars = min(8, len(ranked))
    for rank, (party, value) in enumerate(ranked[:max_bars]):
        y = bar_top + rank * bar_row_height

        if party in government["parties"]:
            draw.rounded_rectangle((32, y + 6, 36, y + 24), radius=2, fill="#737c68")

        draw.text((44, y + 6), party, font=font(16, bold=True), fill=ink)

        bar_end = bar_left + round((bar_right - bar_left) * min(value, 50) / 50)
        draw.rounded_rectangle((bar_left, y + 2, max(bar_left + 2, bar_end), y + bar_height),
                               radius=2, fill=party_color(party))

        if latest_election and party in latest_election["values"]:
            result_x = bar_left + round(
                (bar_right - bar_left) * min(latest_election["values"][party], 50) / 50
            )
            draw.line((result_x, y, result_x, y + bar_height + 4), fill="#777a70", width=2)

        value_label = f"{value:.1f}".replace(".", ",").removesuffix(",0") + " %"
        draw.text((min(bar_end + 8, bar_right + 20), y + 4), value_label,
                  font=font(14, bold=True), fill=ink)

    draw.line((24, height - 50, width - 24, height - 50), fill="#d6d5cc", width=1)
    draw.text((24, height - 40), "sonntagsfrage · deeplook.github.io/sonntagsfrage",
              font=font(11), fill=quiet)
    draw.text((width - 24, height - 40), "Daten: DAWUM / Wahlrecht.de",
              font=font(11), fill=quiet, anchor="ra")

    return image


def generate_share_page(parliament: str, output_dir: Path) -> None:
    """Generate an HTML share page for a parliament."""
    info = PARLIAMENTS[parliament]
    slug = info["slug"]
    redirect_url = f"{BASE_URL}/charts/election-polls.html?parliament={slug}&source=all&cadence=monthly&method=all&speed=300&last=1"
    page_url = f"{BASE_URL}/share/{slug}.html"
    image_url = f"{BASE_URL}/share/{slug}-preview.png"

    html = f'''<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{info["description"]}">
  <meta property="og:title" content="{info["og_title"]}">
  <meta property="og:description" content="{info["description"]}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:image:alt" content="Bar Chart Race: Parteienunterstützung in {info["title"]}">
  <meta property="og:url" content="{page_url}">
  <meta name="twitter:card" content="summary_large_image">
  <meta http-equiv="refresh" content="0; url={redirect_url}">
  <title>{info["og_title"]}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; padding: 40px; text-align: center; background: #f3f1eb; color: #272923; }}
    a {{ color: #4c5845; }}
  </style>
</head>
<body>
  <p>Weiterleitung zu <a href="{redirect_url}">{info["title"]}</a>…</p>
</body>
</html>
'''

    output_path = output_dir / f"{slug}.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote {output_path}")


def generate_preview_image(parliament: str, output_dir: Path, landtag_data_dir: Path) -> None:
    """Generate a 1200x630 preview image for a parliament."""
    info = PARLIAMENTS[parliament]
    slug = info["slug"]

    if parliament == "bundestag":
        base = Path("data/parliaments/bundestag")
        dawum_frames = load_dawum_frames(
            base / "polls" / "dawum.csv",
            base / "results" / "dawum.csv",
            base / "governments.csv",
        )
        wahlrecht_frames = load_frames(
            base / "polls" / "wahlrecht-insa.csv",
            base / "results" / "wahlrecht-insa.csv",
            base / "governments.csv",
        )
        wahlrecht_insa = {
            (frame["date"], frame["institute"], tuple(sorted(frame["values"].items())))
            for frame in wahlrecht_frames
        }
        dawum_frames = [
            frame for frame in dawum_frames
            if frame["institute"] != "INSA" or (
                frame["date"], frame["institute"], tuple(sorted(frame["values"].items()))
            ) not in wahlrecht_insa
        ]
        frames = dawum_frames + wahlrecht_frames
        frames.sort(key=lambda frame: (
            frame["date"], frame.get("reference_date", frame["date"]), frame["institute"],
        ))
        elections = load_elections(base / "elections.csv")
        governments = load_governments(base / "governments.csv")
        header_kicker = "IM ZEITVERLAUF"
        header_title = "Bundestag"
        state_coat = None
    else:
        base = landtag_data_dir / parliament
        frames = load_dawum_frames(
            base / "polls" / "dawum.csv",
            base / "results" / "dawum.csv",
            base / "governments.csv",
            base / "polls" / "wahlrecht-landtag.csv",
            base / "results" / "wahlrecht-landtag.csv",
        )
        elections = load_elections(base / "elections.csv")
        governments = load_governments(base / "governments.csv")
        header_kicker = "IM ZEITVERLAUF"
        header_title = f"Landtag {info['label']}"
        state_coat, _ = load_state_coat(parliament)

    if not frames:
        print(f"Warning: No frames found for {parliament}, skipping preview image")
        return

    latest_frame = frames[-1]
    image = draw_preview_image(
        latest_frame, len(frames), elections, governments,
        header_kicker, header_title, state_coat
    )

    output_path = output_dir / f"{slug}-preview.png"
    image.save(output_path, "PNG", optimize=True)
    print(f"Wrote {output_path} ({image.width}x{image.height})")


app = create_app(__doc__)


@app.command()
def run(
    output_dir: Path = typer.Option(Path("share"), "--output-dir", help="output directory for share pages and images"),
    landtag_data_dir: Path = typer.Option(Path("data/parliaments/landtag"), "--landtag-data-dir"),
    parliaments: list[str] | None = typer.Option(None, "--parliament", help="specific parliaments to generate (default: all)"),
    pages_only: bool = typer.Option(False, "--pages-only", help="generate only HTML pages, skip images"),
    images_only: bool = typer.Option(False, "--images-only", help="generate only preview images, skip pages"),
) -> None:
    """Generate share pages and preview images for all parliaments."""
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = parliaments if parliaments else list(PARLIAMENTS.keys())
    for parliament in selected:
        if parliament not in PARLIAMENTS:
            fail(f"Unknown parliament: {parliament}")
        try:
            if not images_only:
                generate_share_page(parliament, output_dir)
            if not pages_only:
                generate_preview_image(parliament, output_dir, landtag_data_dir)
        except Exception as exc:
            print(f"Warning: Failed to generate for {parliament}: {exc}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
