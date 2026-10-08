"""Download and refresh Bundestag election references used by the chart."""

import argparse
import csv
from datetime import date
import hashlib
from html.parser import HTMLParser
import io
from pathlib import Path
import re
import sys

from .fetch import atomic_write, fetch, write_csv


BUNDESWAHLLEITER_RESULTS_URL = (
    "https://www.bundeswahlleiterin.de/en/dam/jcr/"
    "24d8e745-920d-431a-893a-12805bc7ef40/btw_ab49_datenbank_ergebnisse.csv"
)
ELECTION_PAGE_URL = "https://www.bundeswahlleiterin.de/bundestagswahlen/{year}.html"
ELECTION_FIELDS = ("date", "party", "percent")
ELECTION_PAGE_FIELDS = ("year", "date", "source_url", "snapshot", "sha256")
GOVERNMENT_SOURCE_FIELDS = ("start_date", "cabinet", "source_url", "snapshot", "sha256")
MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11,
    "dezember": 12,
}
PARTY_NAMES = {
    "cdu": "CDU", "csu": "CSU", "cdu/csu": "CDU/CSU", "spd": "SPD",
    "grüne": "GRÜNE", "fdp": "FDP",
    "die linke": "LINKE", "afd": "AfD", "bsw": "BSW",
    "freie wähler": "FW", "piraten": "PIRATEN",
}
PARTY_ORDER = ("CDU/CSU", "SPD", "GRÜNE", "FDP", "LINKE", "AfD", "BSW", "FW", "PIRATEN")
CHART_START_YEAR = 2009
ELECTION_DATE_RE = re.compile(r"(\d{1,2})\.\s*([A-Za-zÄÖÜäöüß]+)\s+(\d{4})")
SLUG_RE = re.compile(r"[^a-z0-9]+")


class ElectionHeadingParser(HTMLParser):
    """Capture the official election page's main heading."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_heading = False
        self.heading_parts: list[str] = []
        self.heading = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h1" and not self.heading:
            self.in_heading = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self.in_heading:
            self.heading = " ".join("".join(self.heading_parts).split())
            self.in_heading = False

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.heading_parts.append(data)


def election_years(data: bytes) -> list[int]:
    """Find election years that have party rows in the official results CSV."""
    text = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", newline="")
    rows = list(csv.reader(text, delimiter=";"))
    years = set()
    for row in rows:
        if len(row) < 2 or row[0].strip().casefold() not in PARTY_NAMES:
            continue
        try:
            year = int(row[1].strip())
        except ValueError:
            continue
        if year >= CHART_START_YEAR:
            years.add(year)
    if not years:
        raise ValueError("No chart election years found in the official results CSV")
    return sorted(years)


def election_date(page_data: bytes, year: int) -> date:
    """Extract the election day from an official per-election HTML page."""
    parser = ElectionHeadingParser()
    parser.feed(page_data.decode("utf-8", errors="replace"))
    for match in ELECTION_DATE_RE.finditer(parser.heading):
        day, month_name, date_year = match.groups()
        month = MONTHS.get(month_name.casefold())
        if month and int(date_year) == year:
            return date(year, month, int(day))
    raise ValueError(f"Could not find the {year} election date in official page heading: {parser.heading!r}")


def parse_results(data: bytes, dates: dict[int, date]) -> list[dict]:
    """Convert the official second-vote results to chart party names."""
    text = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", newline="")
    rows = list(csv.reader(text, delimiter=";"))
    header_index = next((index for index, row in enumerate(rows)
                         if row and row[0].strip() == "Merkmal/Partei"), None)
    if header_index is None or header_index + 2 >= len(rows):
        raise ValueError("Unexpected Bundeswahlleiter results CSV: table header not found")
    header, vote_header, measure_header = rows[header_index:header_index + 3]
    try:
        percent_column = next(
            index for index in range(3, min(len(header), len(vote_header), len(measure_header)))
            if header[index].strip() == "Deutschland"
            and vote_header[index].strip() == "Zweitstimmen"
            and measure_header[index].strip() == "%"
        )
    except StopIteration as exc:
        raise ValueError("Could not locate national second-vote percentages in results CSV") from exc

    values: dict[tuple[int, str], float] = {}
    for row in rows[header_index + 3:]:
        if len(row) <= percent_column or len(row) < 2:
            continue
        try:
            year = int(row[1].strip())
        except ValueError:
            continue
        if year < CHART_START_YEAR or year not in dates:
            continue
        party = PARTY_NAMES.get(row[0].strip().casefold())
        raw_percent = row[percent_column].strip()
        if not party or raw_percent in ("", "–", "-"):
            continue
        try:
            percent = float(raw_percent.replace(".", "").replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"Unexpected result percentage for {party} in {year}: {raw_percent!r}") from exc
        values[(year, party)] = percent

    elections: dict[int, dict[str, float]] = {}
    for (year, party), percent in values.items():
        elections.setdefault(year, {})[party] = percent
    for year, party_values in elections.items():
        if "CDU" in party_values and "CSU" in party_values:
            party_values["CDU/CSU"] = round(party_values.pop("CDU") + party_values.pop("CSU"), 1)
        elif not {"CDU/CSU"} <= party_values.keys():
            raise ValueError(f"Missing CDU/CSU results for {year}")
        required = {"CDU/CSU", "SPD", "GRÜNE", "FDP", "LINKE"}
        if not required <= party_values.keys():
            missing = ", ".join(sorted(required - party_values.keys()))
            raise ValueError(f"Missing chart results for {year}: {missing}")

    output = []
    for year in sorted(elections):
        for party in PARTY_ORDER:
            if party in elections[year]:
                output.append({
                    "date": dates[year].isoformat(),
                    "party": party,
                    "percent": f"{elections[year][party]:.1f}",
                })
    if not output:
        raise ValueError("No chart party results found in the official CSV")
    return output


def snapshot_name(start_date: str, cabinet: str) -> str:
    slug = SLUG_RE.sub("-", cabinet.casefold()).strip("-")
    return f"{start_date}-{slug}.html"


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--data-dir", type=Path, default=Path("data"))
    args = cli.parse_args()
    raw_dir = args.data_dir / "raw"

    try:
        results_data = fetch(BUNDESWAHLLEITER_RESULTS_URL)
        years = election_years(results_data)
        election_pages = []
        dates = {}
        for year in years:
            url = ELECTION_PAGE_URL.format(year=year)
            page_data = fetch(url)
            dates[year] = election_date(page_data, year)
            election_pages.append((year, url, page_data))
        election_rows = parse_results(results_data, dates)

        governments_path = args.data_dir / "governments.csv"
        with governments_path.open(newline="", encoding="utf-8") as handle:
            governments = list(csv.DictReader(handle))
        snapshots = []
        seen_urls = set()
        for government in governments:
            url = government["source_url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            snapshot = fetch(url)
            filename = snapshot_name(government["start_date"], government["cabinet"])
            snapshots.append((filename, url, government, snapshot))

        atomic_write(raw_dir / "bundeswahlleiter-bundestag-results.csv", results_data)
        write_csv(args.data_dir / "bundestag_elections.csv", ELECTION_FIELDS, election_rows)

        election_page_manifest = []
        for year, url, page_data in election_pages:
            relative_path = Path("raw") / "bundeswahlleiter-election-pages" / f"{year}.html"
            atomic_write(args.data_dir / relative_path, page_data)
            election_page_manifest.append({
                "year": year,
                "date": dates[year].isoformat(),
                "source_url": url,
                "snapshot": relative_path.as_posix(),
                "sha256": hashlib.sha256(page_data).hexdigest(),
            })
        write_csv(raw_dir / "bundeswahlleiter-election-pages.csv",
                  ELECTION_PAGE_FIELDS, election_page_manifest)

        manifest = []
        for filename, url, government, snapshot in snapshots:
            relative_path = Path("raw") / "government-sources" / filename
            atomic_write(args.data_dir / relative_path, snapshot)
            manifest.append({
                "start_date": government["start_date"],
                "cabinet": government["cabinet"],
                "source_url": url,
                "snapshot": relative_path.as_posix(),
                "sha256": hashlib.sha256(snapshot).hexdigest(),
            })
        write_csv(raw_dir / "government-sources.csv", GOVERNMENT_SOURCE_FIELDS, manifest)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    years = sorted({date.fromisoformat(row["date"]).year for row in election_rows})
    print(f"Bundestag elections: {len(election_rows)} party results across {len(years)} elections ({years[0]}–{years[-1]})")
    print(f"Government source snapshots: {len(snapshots)}; review interval edits in {governments_path}")


if __name__ == "__main__":
    main()
