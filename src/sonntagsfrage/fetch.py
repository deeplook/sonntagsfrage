"""Fetch dawum polls and the full historical INSA Bundestag archive."""

import csv
from datetime import date, datetime
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import ssl
import sys
from tempfile import NamedTemporaryFile
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi
import typer

from .cli import create_app


DAWUM_URL = "https://api.dawum.de/"
INSA_URLS = (
    "https://www.wahlrecht.de/umfragen/insa/2013.htm",
    "https://www.wahlrecht.de/umfragen/insa/2017.htm",
    "https://www.wahlrecht.de/umfragen/insa/2021.htm",
    "https://www.wahlrecht.de/umfragen/insa/2025.htm",
    "https://www.wahlrecht.de/umfragen/insa.htm",
)
POLL_FIELDS = (
    "source", "source_poll_id", "publication_date", "period_start", "period_end", "period_text",
    "surveyed_persons", "parliament", "institute", "tasker", "method", "source_url",
)
RESULT_FIELDS = ("source", "source_poll_id", "party", "percent", "source_url")
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
PERIOD_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.")
SINGLE_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.$")


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "sonntagsfrage-poll-fetcher/0.1 (research; https://dawum.de/API/)"})
    try:
        with urlopen(request, timeout=30, context=ssl.create_default_context(cafile=certifi.where())) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not download {url}: {exc}") from exc


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(data)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, output.getvalue().encode("utf-8"))


def name_for(items: dict, key: str) -> str:
    return items.get(str(key), {}).get("Name", "")


def parse_dawum(data: bytes) -> tuple[dict, list[dict], list[dict]]:
    database = json.loads(data)
    required = {"Database", "Parliaments", "Institutes", "Taskers", "Methods", "Parties", "Surveys"}
    if not isinstance(database, dict) or not required.issubset(database):
        raise ValueError("Unexpected dawum API response: missing database sections")
    polls = []
    results = []
    for survey_id, survey in database["Surveys"].items():
        period = survey.get("Survey_Period") or {}
        polls.append({
            "source": "dawum", "source_poll_id": survey_id,
            "publication_date": survey.get("Date", ""),
            "period_start": period.get("Date_Start", ""),
            "period_end": period.get("Date_End", ""),
            "period_text": "",
            "surveyed_persons": survey.get("Surveyed_Persons", ""),
            "parliament": name_for(database["Parliaments"], survey.get("Parliament_ID")),
            "institute": name_for(database["Institutes"], survey.get("Institute_ID")),
            "tasker": name_for(database["Taskers"], survey.get("Tasker_ID")),
            "method": name_for(database["Methods"], survey.get("Method_ID")),
            "source_url": DAWUM_URL,
        })
        for party_id, percent in survey.get("Results", {}).items():
            party = database["Parties"].get(str(party_id), {})
            results.append({
                "source": "dawum", "source_poll_id": survey_id,
                "party": party.get("Shortcut") or party.get("Name") or str(party_id),
                "percent": percent, "source_url": DAWUM_URL,
            })
    return database, polls, results


class PollTableParser(HTMLParser):
    """Extract the header and body cells from wahlrecht's poll table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.section = ""
        self.cell: dict | None = None
        self.row: list[dict] | None = None
        self.headers: list[dict] = []
        self.rows: list[list[dict]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and "wilko" in (attributes.get("class") or "").split():
            self.in_table = True
        elif self.in_table and tag in ("thead", "tbody"):
            self.section = tag
        elif self.in_table and tag == "tr" and self.section in ("thead", "tbody"):
            self.row = []
        elif self.row is not None and tag in ("th", "td"):
            self.cell = {"text": "", "class": attributes.get("class", ""), "title": attributes.get("title", "")}

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag in ("th", "td") and self.cell is not None and self.row is not None:
            self.cell["text"] = " ".join(self.cell["text"].split())
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.section == "thead" and not self.headers:
                self.headers = self.row
            elif self.section == "tbody":
                self.rows.append(self.row)
            self.row = None
        elif tag in ("thead", "tbody") and self.in_table:
            self.section = ""
        elif tag == "table" and self.in_table:
            self.in_table = False


def iso_period(raw: str, published: date) -> tuple[str, str]:
    match = PERIOD_RE.search(raw)
    if not match:
        single = SINGLE_DATE_RE.fullmatch(raw)
        if single:
            day, month = map(int, single.groups())
            year = published.year - (month > published.month and published.month == 1)
            try:
                value = date(year, month, day).isoformat()
                return value, value
            except ValueError:
                pass
        return "", ""
    start_day, start_month, end_day, end_month = map(int, match.groups())
    end_year = published.year
    if end_month > published.month and published.month == 1:
        end_year -= 1
    start_year = end_year - (start_month > end_month)
    try:
        return date(start_year, start_month, start_day).isoformat(), date(end_year, end_month, end_day).isoformat()
    except ValueError:
        return "", ""


def parse_insa(html: bytes, url: str) -> tuple[list[dict], list[dict]]:
    parser = PollTableParser()
    parser.feed(html.decode("utf-8"))
    if not parser.headers or not parser.rows:
        raise ValueError(f"No INSA poll table found at {url}")
    labels = [cell["text"].replace(" ", "") for cell in parser.headers]
    try:
        respondents_index = labels.index("Befragte")
        period_index = labels.index("Zeitraum")
    except ValueError as exc:
        raise ValueError(f"INSA table layout changed at {url}") from exc
    polls = []
    results = []
    seen_ids = set()
    for row in parser.rows:
        if len(row) != len(labels) or not DATE_RE.fullmatch(row[0]["text"]):
            continue  # Election result rows and notes are not polls.
        if "ws" in row[0]["class"].split():
            continue
        published = datetime.strptime(row[0]["text"], "%d.%m.%Y").date()
        period_start, period_end = iso_period(row[period_index]["text"], published)
        respondents = row[respondents_index]["text"]
        count = re.search(r"[•·]\s*([\d.]+)", respondents)
        fingerprint = sha256("|".join(cell["text"] for cell in row).encode("utf-8")).hexdigest()[:12]
        poll_id = f"{published.isoformat()}:{url.rsplit('/', 1)[-1]}:{fingerprint}"
        if poll_id in seen_ids:
            continue  # The archive repeats one identical INSA row.
        seen_ids.add(poll_id)
        polls.append({
            "source": "wahlrecht-INSA", "source_poll_id": poll_id,
            "publication_date": published.isoformat(), "period_start": period_start,
            "period_end": period_end, "period_text": row[period_index]["text"],
            "surveyed_persons": count.group(1).replace(".", "") if count else "",
            "parliament": "Bundestag", "institute": "INSA", "tasker": "",
            "method": row[respondents_index]["title"] or respondents.split("•")[0].strip(),
            "source_url": url,
        })
        for index in range(2, respondents_index):
            party = labels[index]
            value = row[index]["text"].replace("%", "").replace(",", ".").strip()
            if party and value and value not in ("–", "-", "?"):
                try:
                    percent = float(value)
                except ValueError as exc:
                    raise ValueError(f"Unexpected INSA result {value!r} at {url}") from exc
                results.append({
                    "source": "wahlrecht-INSA", "source_poll_id": poll_id,
                    "party": party, "percent": percent, "source_url": url,
                })
    if not polls:
        raise ValueError(f"No INSA poll rows found at {url}")
    return polls, results


app = create_app(__doc__)


@app.command()
def run(
    output_dir: Path = typer.Option(Path("data"), "--output-dir", help="data directory (default: data)"),
    source: Literal["all", "dawum", "insa"] = typer.Option(
        "all", "--source", help="poll source to fetch (default: all)"
    ),
) -> None:
    try:
        if source in ("all", "dawum"):
            raw = fetch(DAWUM_URL)
            database, polls, results = parse_dawum(raw)
            atomic_write(output_dir / "raw" / "dawum.json", raw)
            write_csv(output_dir / "dawum_polls.csv", POLL_FIELDS, polls)
            write_csv(output_dir / "dawum_results.csv", RESULT_FIELDS, results)
            insa_count = sum(poll["institute"].upper() == "INSA" for poll in polls)
            print(f"dawum: {len(polls)} polls ({insa_count} INSA), {len(results)} party results; updated {database['Database']['Last_Update']}")
        if source in ("all", "insa"):
            polls, results = [], []
            for url in INSA_URLS:
                raw = fetch(url)
                page_polls, page_results = parse_insa(raw, url)
                polls.extend(page_polls)
                results.extend(page_results)
                atomic_write(output_dir / "raw" / f"insa-{url.rsplit('/', 1)[-1]}", raw)
            write_csv(output_dir / "insa_polls.csv", POLL_FIELDS, polls)
            write_csv(output_dir / "insa_results.csv", RESULT_FIELDS, results)
            print(f"wahlrecht INSA: {len(polls)} polls, {len(results)} party results; {min(p['publication_date'] for p in polls)} to {max(p['publication_date'] for p in polls)}")
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def main() -> None:
    app()


if __name__ == "__main__":
    main()
