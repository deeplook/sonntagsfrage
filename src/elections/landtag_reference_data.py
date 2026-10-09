"""Download state election results and historical cabinet references."""

import argparse
import csv
from datetime import date
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
from urllib.parse import quote, unquote, urljoin

from .fetch import atomic_write, fetch, write_csv


WAHLRECHT_BASE = "https://www.wahlrecht.de/ergebnisse/"
WAHLRECHT_POLLS_BASE = "https://www.wahlrecht.de/umfragen/landtage/"
WAHLRECHT_PAGES = {
    "baden-wuerttemberg": "baden-wuerttemberg.htm",
    "bayern": "bayern.htm",
    "berlin": "berlin.htm",
    "brandenburg": "brandenburg.htm",
    "bremen": "bremen.htm",
    "hamburg": "hamburg.htm",
    "hessen": "hessen.htm",
    "mecklenburg-vorpommern": "mecklenburg.htm",
    "niedersachsen": "niedersachsen.htm",
    "nordrhein-westfalen": "nordrhein-westfalen.htm",
    "rheinland-pfalz": "rheinland-pfalz.htm",
    "saarland": "saarland.htm",
    "sachsen": "sachsen.htm",
    "sachsen-anhalt": "sachsen-anhalt.htm",
    "schleswig-holstein": "schleswig-holstein.htm",
    "thueringen": "thueringen.htm",
}
STATEPOL_VERSION_URL = "https://raw.githubusercontent.com/StatePol/Database/main/VERSION"
STATEPOL_DATA_URL = "https://raw.githubusercontent.com/StatePol/Database/main/_data/database/{name}_{version}.csv"
STATEPOL_REFERENCE_URL = "https://statepol.github.io/Database/"
WIKIPEDIA_GOVERNMENTS_URL = "https://de.wikipedia.org/wiki/Landesregierung_(Deutschland)"
STATE_CODES = {
    "baden-wuerttemberg": "bw", "bayern": "by", "berlin": "be",
    "brandenburg": "bb", "bremen": "hb", "hamburg": "hh",
    "hessen": "he", "mecklenburg-vorpommern": "mv", "niedersachsen": "ni",
    "nordrhein-westfalen": "nw", "rheinland-pfalz": "rp", "saarland": "sl",
    "sachsen": "sn", "sachsen-anhalt": "st", "schleswig-holstein": "sh",
    "thueringen": "th",
}
MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8, "september": 9,
    "oktober": 10, "november": 11, "dezember": 12,
}
YEAR_RE = re.compile(r"^(\d{4})")
ELECTION_DATE_RE = re.compile(
    r"(?:am\s+)?(\d{1,2})\.\s*([A-Za-zÄÖÜäöüß]+)\s+(\d{4})",
    re.IGNORECASE,
)
ELECTION_FIELDS = ("date", "party", "percent", "result_status", "source_url")
ELECTION_SOURCE_FIELDS = ("year", "date", "result_status", "source_url", "snapshot", "sha256")
GOVERNMENT_FIELDS = (
    "start_date", "end_date", "cabinet", "parties", "source", "source_url",
)
CURRENT_GOVERNMENT_FIELDS = ("state", "start_date", "cabinet", "parties", "source_url", "cabinet_url")
TIMELINE_FIELDS = ("start_date", "end_date_exclusive", "cabinet", "parties", "source_url")
POLL_FIELDS = (
    "source", "source_poll_id", "publication_date", "period_start", "period_end", "period_text",
    "surveyed_persons", "parliament", "institute", "tasker", "method", "source_url",
)
RESULT_FIELDS = ("source", "source_poll_id", "party", "percent", "source_url")
POLL_SOURCE_FIELDS = ("state", "source_url", "snapshot", "sha256", "supplemental_polls")


class TableParser(HTMLParser):
    """Collect HTML tables, retaining header links and column spans."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict]]] = []
        self.stack: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            self.stack.append({"table": [], "row": None, "cell": None})
        elif self.stack and tag == "tr":
            self.stack[-1]["row"] = []
        elif self.stack and tag in ("th", "td") and self.stack[-1]["row"] is not None:
            self.stack[-1]["cell"] = {
                "text": "", "href": "", "colspan": int(attributes.get("colspan") or 1),
            }
        elif self.stack and tag == "a" and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"]["href"] = attributes.get("href") or ""

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"]["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if self.stack and tag in ("th", "td"):
            current = self.stack[-1]
            if current["cell"] is not None and current["row"] is not None:
                current["cell"]["text"] = " ".join(current["cell"]["text"].split())
                current["row"].append(current["cell"])
                current["cell"] = None
        elif self.stack and tag == "tr":
            current = self.stack[-1]
            if current["row"] is not None:
                current["table"].append(current["row"])
            current["row"] = None
        elif tag == "table":
            if self.stack:
                table = self.stack.pop()["table"]
                self.tables.append(table)


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def parse_percent(raw: str) -> str | None:
    value = raw.replace("\xad", "").strip()
    match = re.search(r"-?\d{1,3}(?:[.,]\d+)?", value)
    if not match:
        return None
    try:
        return f"{float(match.group().replace(',', '.')):.1f}"
    except ValueError:
        return None


def numeric_date(raw: str) -> date | None:
    match = re.fullmatch(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*", raw)
    if not match:
        return None
    day, month, year = (int(value) for value in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_wahlrecht_poll_page(data: bytes, page_url: str, state: str,
                              after: date) -> tuple[list[dict], list[dict]]:
    """Read polls newer than a state's DAWUM snapshot from Wahlrecht's table."""
    parser = TableParser()
    parser.feed(data.decode("utf-8-sig", errors="replace"))
    table = next((table for table in parser.tables if table and
                  len(table[0]) >= 8 and table[0][0]["text"].casefold() == "institut" and
                  any(cell["text"].casefold() == "datum" for cell in table[0])), None)
    if table is None:
        raise ValueError(f"Could not find the poll table on {page_url}")
    header = table[0]
    party_columns = [(index, cell["text"].strip()) for index, cell in enumerate(header)
                     if index >= 5 and cell["text"].strip()]
    method_names = {
        "O": "Online", "T": "Telefonisch", "F": "Persönlich",
        "S": "SMS", "TOM": "Telefon & Online", "TSM": "Telefon & SMS",
    }
    poll_rows, result_rows = [], []
    for row in table[1:]:
        if len(row) <= 5 or len(row) < len(header):
            continue
        published = numeric_date(row[3]["text"])
        if not published or published <= after:
            continue
        institute = row[0]["text"].strip()
        tasker = row[1]["text"].strip()
        sample_period = row[2]["text"].replace("\xad", "").replace("–", "–").strip()
        sample_match = re.search(
            r"(?:^|•\s*)([A-Z?]+)\s*•\s*(~?\d{1,3}(?:\.\d{3})*)(\d{1,2}\.\d{1,2}\.\s*[–-]\s*\d{1,2}\.\d{1,2}\.)",
            sample_period,
        )
        sample = ""
        method = "Unbekannt"
        period_text = ""
        period_start = period_end = ""
        if sample_match:
            method_code, sample_text, period_text = sample_match.groups()
            sample = str(int(re.sub(r"\D", "", sample_text))) if re.search(r"\d", sample_text) else ""
            method = method_names.get(method_code, "Unbekannt")
            dates = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.\s*[–-]\s*(\d{1,2})\.(\d{1,2})\.", period_text)
            if dates:
                start_day, start_month, end_day, end_month = map(int, dates.groups())
                start_year = published.year - (1 if start_month > end_month else 0)
                try:
                    period_start = date(start_year, start_month, start_day).isoformat()
                    period_end = date(published.year, end_month, end_day).isoformat()
                except ValueError:
                    period_start = period_end = ""
        poll_id = f"{state}:{published.isoformat()}:{institute}:{tasker}"
        poll = {
            "source": "wahlrecht-landtag", "source_poll_id": poll_id,
            "publication_date": published.isoformat(), "period_start": period_start,
            "period_end": period_end, "period_text": period_text,
            "surveyed_persons": sample, "parliament": "Landtag",
            "institute": institute, "tasker": tasker, "method": method,
            "source_url": page_url,
        }
        poll_rows.append(poll)
        for index, party in party_columns:
            percent = parse_percent(row[index]["text"])
            if percent is not None:
                result_rows.append({
                    "source": "wahlrecht-landtag", "source_poll_id": poll_id,
                    "party": party, "percent": percent, "source_url": page_url,
                })
    return poll_rows, result_rows


def election_date(data: bytes, expected_year: int) -> date:
    parser = TextParser()
    parser.feed(data.decode("utf-8-sig", errors="replace"))
    text = " ".join(" ".join(parser.parts).split())
    for match in ELECTION_DATE_RE.finditer(text):
        day, month_name, year = match.groups()
        month = MONTHS.get(month_name.casefold())
        if month and int(year) == expected_year:
            return date(expected_year, month, int(day))
    raise ValueError(f"Could not find an election date for {expected_year} in the linked Wahlrecht page")


def election_table(data: bytes, page_url: str, state: str) -> tuple[list[dict], list[tuple[int, str, str]]]:
    html = data.decode("utf-8-sig", errors="replace")
    header_cells = re.findall(
        r"<th\b(?=[^>]*\bclass=[\"'][^\"']*\bjahr\b[^\"']*[\"'])[^>]*>(.*?)</th>",
        html, re.IGNORECASE | re.DOTALL,
    )
    elections = []
    for cell in header_cells:
        text_parser = TextParser()
        text_parser.feed(cell)
        match = YEAR_RE.match(" ".join(text_parser.parts).strip())
        if not match:
            continue
        href = re.search(r"<a\b[^>]*\bhref=[\"']([^\"']+)", cell, re.IGNORECASE)
        detail_url = urljoin(page_url, href.group(1)) if href else ""
        result_status = "vorläufig" if "*" in " ".join(text_parser.parts) else "endgültig"
        elections.append((int(match.group(1)), detail_url, result_status))
    # Some current Wahlrecht result pages update the election news article
    # before their historical results table. Pick up its featured result link.
    uncommented_html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    featured_election = None
    for anchor in re.finditer(r"<a\b([^>]*)>(.*?)</a\s*>", uncommented_html, re.IGNORECASE | re.DOTALL):
        attributes = dict(re.findall(r"([\w-]+)\s*=\s*[\"']([^\"']*)[\"']", anchor.group(1)))
        title = attributes.get("title", "")
        href = attributes.get("href", "")
        year_match = re.search(r"/news/(\d{4})/", href)
        if "Wahlergebnis" not in title or not year_match:
            continue
        year = int(year_match.group(1))
        if any(existing_year == year for existing_year, _url, _status in elections):
            continue
        featured_election = (year, urljoin(page_url, href.split("#", 1)[0]), "endgültig")
        break
    if not elections:
        raise ValueError(f"No election year columns found for {state} at {page_url}")

    parser = TableParser()
    parser.feed(html)
    for table in parser.tables:
        rows = []
        for row in table:
            if len(row) < 1 + len(elections) * 2:
                continue
            party = row[0]["text"].strip()
            if not party or party.casefold().startswith("wahlbe") or party.startswith("%"):
                continue
            for index, (year, detail_url, _result_status) in enumerate(elections):
                percent = parse_percent(row[1 + index * 2]["text"])
                if percent is not None:
                    rows.append({"year": year, "party": party, "percent": percent, "source_url": detail_url or page_url})
        if rows:
            if featured_election and not any(year == featured_election[0] for year, _url, _status in elections):
                elections.append(featured_election)
                elections.sort(key=lambda item: item[0])
            return rows, elections
    raise ValueError(f"No election results table found for {state} at {page_url}")


def detail_election_results(data: bytes, year: int) -> list[dict]:
    """Extract a featured election's party percentages when the index table lags."""
    parser = TableParser()
    parser.feed(data.decode("utf-8-sig", errors="replace"))

    def expand(row: list[dict]) -> list[str]:
        expanded = []
        for cell in row:
            expanded.extend([cell["text"]] * max(1, cell["colspan"]))
        return expanded

    for table in parser.tables:
        rows = [expand(row) for row in table]
        percent_index = None
        percent_row_index = None
        for header_index, row in enumerate(rows):
            year_columns = [index for index, text in enumerate(row) if str(year) in text]
            if not year_columns:
                continue
            low, high = min(year_columns), max(year_columns)
            for following_index in range(header_index + 1, min(header_index + 5, len(rows))):
                candidates = [index for index, text in enumerate(rows[following_index])
                              if text.strip() == "%" and low <= index <= high]
                if candidates:
                    # Wahlrecht omits the party-name stub from grouped
                    # subheader rows, but it is present in result rows.
                    percent_index = candidates[0] + 1
                    percent_row_index = following_index
                    break
            if percent_index is not None:
                break
        if percent_index is None or percent_row_index is None:
            continue
        collecting = False
        results = []
        for row in rows[percent_row_index + 1:]:
            if not row:
                continue
            party = row[0].strip()
            if "Gültige Stimmen" in party:
                collecting = True
                continue
            if not collecting:
                continue
            if party.casefold() in {"gesamt", "gesamtergebnis"}:
                break
            if not party or party.casefold() == "davon":
                continue
            percent = parse_percent(row[percent_index]) if percent_index < len(row) else None
            if percent is not None:
                results.append({"year": year, "party": party, "percent": percent})
        if results:
            return results
    return []


def statepol_governments(cabinet_data: bytes, state: str) -> list[dict]:
    code = STATE_CODES[state]
    rows = list(csv.DictReader(io.StringIO(cabinet_data.decode("utf-8-sig"))))
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if row.get("landtag_state_abb", "").casefold() != code:
            continue
        grouped.setdefault((row["cabinet"], row["electoralperiod"]), []).append(row)
    output = []
    for (cabinet, _period), members in grouped.items():
        starts = [row["start_date"] for row in members if row.get("start_date")]
        ends = [row["end_date"] for row in members if row.get("end_date")]
        parties = sorted({row["party"].strip() for row in members if row.get("party", "").strip()})
        if not starts or not parties:
            continue
        output.append({
            "start_date": min(starts), "end_date": max(ends) if ends else "",
            "cabinet": cabinet, "parties": ";".join(parties),
            "source": "StatePol 1.0.4", "source_url": STATEPOL_REFERENCE_URL,
        })
    return sorted(output, key=lambda row: row["start_date"])


def current_governments(data: bytes) -> dict[str, dict]:
    parser = TableParser()
    parser.feed(data.decode("utf-8-sig", errors="replace"))
    state_names = {
        "baden-württemberg": "baden-wuerttemberg", "bayern": "bayern", "berlin": "berlin",
        "brandenburg": "brandenburg", "bremen": "bremen", "hamburg": "hamburg",
        "hessen": "hessen", "mecklenburg-vorpommern": "mecklenburg-vorpommern",
        "niedersachsen": "niedersachsen", "nordrhein-westfalen": "nordrhein-westfalen",
        "rheinland-pfalz": "rheinland-pfalz", "saarland": "saarland", "sachsen": "sachsen",
        "sachsen-anhalt": "sachsen-anhalt", "schleswig-holstein": "schleswig-holstein",
        "thüringen": "thueringen",
    }
    output = {}
    for table in parser.tables:
        if not any("Beteiligte Parteien" in cell["text"] for row in table for cell in row):
            continue
        for row in table[1:]:
            if len(row) < 5:
                continue
            name = row[0]["text"].casefold()
            state = next((state_names[display] for display in sorted(state_names, key=len, reverse=True)
                          if display in name), None)
            if not state:
                continue
            date_match = ELECTION_DATE_RE.search(row[-1]["text"])
            if not date_match:
                continue
            day, month_name, year = date_match.groups()
            month = MONTHS.get(month_name.casefold())
            if not month:
                continue
            start_date = date(int(year), month, int(day)).isoformat()
            output[state] = {
                "state": state, "start_date": start_date,
                "cabinet": " ".join(row[1]["text"].split()),
                "parties": ";".join(part.strip() for part in row[-2]["text"].split(",") if part.strip()),
                "source_url": WIKIPEDIA_GOVERNMENTS_URL,
                "cabinet_url": row[1]["href"],
            }
    if set(output) != set(WAHLRECHT_PAGES):
        missing = sorted(set(WAHLRECHT_PAGES) - output.keys())
        raise ValueError(f"Could not parse current governments for: {', '.join(missing)}")
    return output


def parse_cabinet(data: bytes, page_url: str) -> dict:
    """Read a cabinet's start date, parties, and predecessor from its infobox."""
    parser = TableParser()
    parser.feed(data.decode("utf-8-sig", errors="replace"))
    fields = {}
    for table in parser.tables:
        for row in table:
            if len(row) >= 2 and row[0]["text"].casefold() in {"beginn", "vorgänger", "partei(en)"}:
                fields[row[0]["text"].casefold()] = row[1]
    start_match = ELECTION_DATE_RE.search(fields.get("beginn", {}).get("text", ""))
    parties_text = fields.get("partei(en)", {}).get("text", "")
    if not start_match or not parties_text:
        raise ValueError(f"Could not parse cabinet start date and parties from {page_url}")
    day, month_name, year = start_match.groups()
    month = MONTHS.get(month_name.casefold())
    if not month:
        raise ValueError(f"Unknown cabinet start month in {page_url}")
    parties = [p.strip() for p in re.split(r",|\bund\b", parties_text) if p.strip()]
    predecessor = fields.get("vorgänger", {})
    return {
        "start_date": date(int(year), month, int(day)).isoformat(),
        "cabinet": unquote(page_url.rstrip("/").rsplit("/", 1)[-1]).replace("_", " "),
        "parties": "|".join(parties), "source_url": page_url,
        "predecessor_url": predecessor.get("href", ""),
    }


def government_timeline(data_dir: Path, state: str, current: dict, earliest: date) -> list[dict]:
    """Follow cabinet predecessor links back to the earliest poll date."""
    chain = []
    url = current["cabinet_url"]
    raw_dir = Path("parliaments") / "landtag" / state / "raw" / "wikipedia-cabinets"
    seen = set()
    while url:
        url = quote(url, safe=":/?=&%#")
        if url in seen:
            raise ValueError(f"Cabinet predecessor loop for {state}: {url}")
        seen.add(url)
        data = fetch(url)
        cabinet = parse_cabinet(data, url)
        snapshot = raw_dir / f"{cabinet['start_date']}-{len(chain):02d}.html"
        atomic_write(data_dir / snapshot, data)
        cabinet["snapshot"] = snapshot.as_posix()
        cabinet["sha256"] = hashlib.sha256(data).hexdigest()
        chain.append(cabinet)
        if date.fromisoformat(cabinet["start_date"]) <= earliest:
            break
        url = cabinet["predecessor_url"]
        if not url:
            raise ValueError(f"Cabinet history for {state} ends before reaching {earliest}")
    chain.reverse()
    timeline = []
    for index, cabinet in enumerate(chain):
        next_start = chain[index + 1]["start_date"] if index + 1 < len(chain) else "9999-12-31"
        timeline.append({
            "start_date": cabinet["start_date"], "end_date_exclusive": next_start,
            "cabinet": cabinet["cabinet"], "parties": cabinet["parties"],
            "source_url": cabinet["source_url"], "snapshot": cabinet["snapshot"],
            "sha256": cabinet["sha256"],
        })
    return timeline


def download(data_dir: Path) -> None:
    source_manifest = []
    state_elections: dict[str, list[dict]] = {}
    for state, filename in WAHLRECHT_PAGES.items():
        base = data_dir / "parliaments" / "landtag" / state
        page_url = urljoin(WAHLRECHT_BASE, filename)
        poll_path = base / "polls" / "dawum.csv"
        if poll_path.exists():
            with poll_path.open(newline="", encoding="utf-8") as handle:
                poll_rows = list(csv.DictReader(handle))
            poll_dates = [date.fromisoformat(row.get("period_start") or row["publication_date"])
                          for row in poll_rows]
            earliest_poll_year = min(poll_dates).year if poll_dates else None
        else:
            earliest_poll_year = None
        poll_url = urljoin(WAHLRECHT_POLLS_BASE, f"{state}.htm")
        poll_page = fetch(poll_url)
        if poll_path.exists() and poll_rows:
            latest_dawum_poll = max(date.fromisoformat(row["publication_date"]) for row in poll_rows)
        else:
            latest_dawum_poll = date.min
        supplemental_polls, supplemental_results = parse_wahlrecht_poll_page(
            poll_page, poll_url, state, latest_dawum_poll,
        )
        poll_snapshot = Path("parliaments") / "landtag" / state / "raw" / "wahlrecht" / "polls.html"
        atomic_write(data_dir / poll_snapshot, poll_page)
        write_csv(base / "polls" / "wahlrecht-landtag.csv", POLL_FIELDS, supplemental_polls)
        write_csv(base / "results" / "wahlrecht-landtag.csv", RESULT_FIELDS, supplemental_results)
        source_manifest.append({
            "state": state, "source_url": poll_url, "snapshot": poll_snapshot.as_posix(),
            "sha256": hashlib.sha256(poll_page).hexdigest(),
        })
        page_data = fetch(page_url)
        raw_page = Path("parliaments") / "landtag" / state / "raw" / "wahlrecht" / "election-results.html"
        atomic_write(data_dir / raw_page, page_data)
        parsed_rows, election_links = election_table(page_data, page_url, state)

        dates = {}
        page_manifest = []
        detail_dir = Path("parliaments") / "landtag" / state / "raw" / "wahlrecht" / "election-pages"
        baseline_years = [year for year, _url, _status in election_links
                          if earliest_poll_year is not None and year < earliest_poll_year]
        baseline_year = max(baseline_years) if baseline_years else None
        for year, detail_url, result_status in election_links:
            if year < 2015 and year != baseline_year:
                continue
            if not detail_url:
                raise ValueError(f"Missing result detail link for {state} {year}")
            detail_data = fetch(detail_url)
            date_value = election_date(detail_data, year)
            if not any(row["year"] == year for row in parsed_rows):
                for row in detail_election_results(detail_data, year):
                    parsed_rows.append({**row, "source_url": detail_url})
            snapshot = detail_dir / f"{year}.html"
            atomic_write(data_dir / snapshot, detail_data)
            date_text = date_value.isoformat()
            dates[year] = date_text
            page_manifest.append({
                "year": year, "date": date_text, "source_url": detail_url,
                "result_status": result_status, "snapshot": snapshot.as_posix(),
                "sha256": hashlib.sha256(detail_data).hexdigest(),
            })

        normalized = [
            {"date": dates[row["year"]], "party": row["party"], "percent": row["percent"],
             "result_status": next(status for year, _url, status in election_links if year == row["year"]),
             "source_url": row["source_url"]}
            for row in parsed_rows if row["year"] in dates
        ]
        if not normalized:
            raise ValueError(f"No dated election result rows found for {state}")
        write_csv(base / "elections.csv", ELECTION_FIELDS, normalized)
        write_csv(base / "raw" / "wahlrecht" / "election-pages.csv", ELECTION_SOURCE_FIELDS, page_manifest)
        state_elections[state] = normalized
        source_manifest.append({
            "state": state, "source_url": page_url, "snapshot": raw_page.as_posix(),
            "sha256": hashlib.sha256(page_data).hexdigest(),
        })
        print(f"{state}: {len({row['date'] for row in normalized})} election dates, "
              f"{len(normalized)} party results, {len(supplemental_polls)} newer Wahlrecht polls")

    source_dir = data_dir / "sources" / "statepol"
    versions = fetch(STATEPOL_VERSION_URL).decode("utf-8-sig").splitlines()
    version = next((value.strip() for value in versions if value.strip()), "")
    if not version:
        raise ValueError("StatePol version file contained no versions")
    atomic_write(source_dir / "VERSION", (version + "\n").encode("utf-8"))
    cabinet_url = STATEPOL_DATA_URL.format(name="cabinet", version=version)
    cabinet_data = fetch(cabinet_url)
    atomic_write(source_dir / f"cabinet_{version}.csv", cabinet_data)
    max_end = max(row["end_date"] for row in csv.DictReader(io.StringIO(cabinet_data.decode("utf-8-sig"))) if row.get("end_date"))
    for state in WAHLRECHT_PAGES:
        governments = statepol_governments(cabinet_data, state)
        write_csv(data_dir / "parliaments" / "landtag" / state / "governments-statepol.csv", GOVERNMENT_FIELDS, governments)
    source_manifest.append({
        "state": "all", "source_url": cabinet_url,
        "snapshot": (Path("sources") / "statepol" / f"cabinet_{version}.csv").as_posix(),
        "sha256": hashlib.sha256(cabinet_data).hexdigest(),
    })
    governments_page = fetch(WIKIPEDIA_GOVERNMENTS_URL)
    current_path = Path("sources") / "wikipedia" / "landesregierungen.html"
    atomic_write(data_dir / current_path, governments_page)
    current_data = current_governments(governments_page)
    for state, row in current_data.items():
        write_csv(data_dir / "parliaments" / "landtag" / state / "governments-current.csv",
                  CURRENT_GOVERNMENT_FIELDS, [row])
        poll_path = data_dir / "parliaments" / "landtag" / state / "polls" / "dawum.csv"
        with poll_path.open(newline="", encoding="utf-8") as handle:
            poll_rows = list(csv.DictReader(handle))
        poll_dates = [date.fromisoformat(r.get("period_start") or r["publication_date"])
                      for r in poll_rows]
        if not poll_dates:
            raise ValueError(f"No DAWUM polls found for {state}: {poll_path}")
        timeline = government_timeline(data_dir, state, row, min(poll_dates))
        write_csv(data_dir / "parliaments" / "landtag" / state / "governments.csv",
                  TIMELINE_FIELDS, timeline)
        for cabinet in timeline:
            source_manifest.append({
                "state": state, "source_url": cabinet["source_url"],
                "snapshot": cabinet["snapshot"], "sha256": cabinet["sha256"],
            })
    source_manifest.append({
        "state": "all", "source_url": WIKIPEDIA_GOVERNMENTS_URL,
        "snapshot": current_path.as_posix(), "sha256": hashlib.sha256(governments_page).hexdigest(),
    })
    write_csv(data_dir / "sources" / "landtag-reference" / "sources.csv",
              ("state", "source_url", "snapshot", "sha256"), source_manifest)
    print(f"StatePol {version}: cabinets available through {max_end}; added cabinet-history timelines from Wikipedia predecessor chains")


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--data-dir", type=Path, default=Path("data"))
    args = cli.parse_args()
    try:
        download(args.data_dir)
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        cli.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
