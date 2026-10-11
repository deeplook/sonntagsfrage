"""Render INSA poll results as a standalone HTML bar chart race."""

import argparse
import csv
from datetime import date
from importlib.resources import files
import json
from pathlib import Path

from .fetch import atomic_write


def load_governments(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No government records in {path}")
    governments = []
    previous_end = None
    for row in rows:
        start = date.fromisoformat(row["start_date"])
        end = date.fromisoformat(row["end_date_exclusive"])
        parties = row["parties"].split("|")
        if start >= end or (previous_end is not None and start != previous_end) or not all(parties):
            raise ValueError(f"Government intervals must be contiguous and nonempty: {path}")
        governments.append({"start": start, "end": end, "cabinet": row["cabinet"],
                            "parties": parties, "source_url": row["source_url"]})
        previous_end = end
    return governments


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


def load_frames(polls_path: Path, results_path: Path,
                governments_path: Path = Path("data/parliaments/bundestag/governments.csv")) -> list[dict]:
    with polls_path.open(newline="", encoding="utf-8") as handle:
        polls = list(csv.DictReader(handle))
    with results_path.open(newline="", encoding="utf-8") as handle:
        results = list(csv.DictReader(handle))
    if not polls or not results:
        raise ValueError("INSA poll files are empty; run `uv run sonntagsfrage --source insa` first")
    governments = load_governments(governments_path)

    by_poll: dict[str, dict[str, float]] = {}
    for row in results:
        if row["source"] != "wahlrecht-INSA":
            continue
        party = row["party"].strip()
        if not party or party.casefold() == "sonstige":
            continue  # 'Others' is an aggregate, not a party.
        by_poll.setdefault(row["source_poll_id"], {})[party] = float(row["percent"])

    frames = []
    for row in polls:
        if row["source"] != "wahlrecht-INSA":
            continue
        values = by_poll.get(row["source_poll_id"])
        if not values:
            continue
        reference_date = date.fromisoformat(row["period_end"] or row["publication_date"])
        government = next((record for record in governments
                           if record["start"] <= reference_date < record["end"]), None)
        if government is None:
            raise ValueError(f"No verified government for {reference_date}; update {governments_path}")
        frames.append({
            "date": row["publication_date"],
            "reference_date": reference_date.isoformat(),
            "method": row["method"], "institute": row["institute"], "tasker": row["tasker"],
            "sample": row["surveyed_persons"],
            "period": row["period_text"],
            "values": values,
            "url": row["source_url"],
            "source_name": "Wahlrecht.de",
            "government": {"cabinet": government["cabinet"],
                           "parties": government["parties"],
                           "source_url": government["source_url"]},
        })
    if not frames:
        raise ValueError("No INSA polls with party results were found")
    frames.sort(key=lambda frame: (frame["date"], frame["method"], frame["sample"]))
    return frames


def load_dawum_frames(polls_path: Path, results_path: Path,
                      governments_path: Path,
                      supplemental_polls_path: Path | None = None,
                      supplemental_results_path: Path | None = None) -> list[dict]:
    """Load one parliament's DAWUM polls into the race renderer's frame format."""
    with polls_path.open(newline="", encoding="utf-8") as handle:
        polls = list(csv.DictReader(handle))
    with results_path.open(newline="", encoding="utf-8") as handle:
        results = list(csv.DictReader(handle))
    if supplemental_polls_path and supplemental_polls_path.exists():
        with supplemental_polls_path.open(newline="", encoding="utf-8") as handle:
            polls.extend(csv.DictReader(handle))
    if supplemental_results_path and supplemental_results_path.exists():
        with supplemental_results_path.open(newline="", encoding="utf-8") as handle:
            results.extend(csv.DictReader(handle))
    if not polls or not results:
        raise ValueError(f"DAWUM poll files are empty: {polls_path}, {results_path}")
    governments = load_governments(governments_path)
    by_poll: dict[str, dict[str, float]] = {}
    for row in results:
        party = row["party"].strip()
        if not party or party.casefold() == "sonstige":
            continue
        by_poll.setdefault(row["source_poll_id"], {})[party] = float(row["percent"])

    frames = []
    for row in polls:
        values = by_poll.get(row["source_poll_id"])
        if not values:
            continue
        reference_date = date.fromisoformat(row["period_end"] or row["publication_date"])
        government = next((record for record in governments
                           if record["start"] <= reference_date < record["end"]), None)
        if government is None:
            raise ValueError(f"No government record for {reference_date}: {governments_path}")
        frames.append({
            "date": row["publication_date"], "reference_date": reference_date.isoformat(),
            "method": row["method"], "sample": row["surveyed_persons"],
            "period": row["period_text"], "institute": row["institute"],
            "tasker": row["tasker"], "values": values, "url": row["source_url"],
            "source_name": "DAWUM" if row["source"] == "dawum" else "Wahlrecht.de",
            "government": {"cabinet": government["cabinet"],
                           "parties": government["parties"],
                           "source_url": government["source_url"]},
        })
    if not frames:
        raise ValueError(f"No DAWUM polls with party results found in {polls_path}")
    frames.sort(key=lambda frame: (frame["date"], frame["institute"], frame["method"]))
    return frames


def load_dataset(name: str, label: str, eyebrow: str, title: str, intro: str,
                 frames: list[dict], elections: list[dict], governments: list[dict],
                 poll_source_name: str, poll_source_url: str,
                 election_source_name: str, election_source_url: str) -> dict:
    return {
        "name": name, "label": label, "eyebrow": eyebrow, "title": title,
        "intro": intro, "frames": frames, "elections": elections,
        "governments": governments, "poll_source_name": poll_source_name,
        "poll_source_url": poll_source_url, "election_source_name": election_source_name,
        "election_source_url": election_source_url,
    }


def render(frames: list[dict], elections: list[dict] | None = None,
           governments: list[dict] | None = None,
           datasets: list[dict] | None = None) -> str:
    template = files("sonntagsfrage").joinpath("insa_race.html").read_text(encoding="utf-8")
    def payload(value: object) -> str:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                             default=lambda item: item.isoformat() if isinstance(item, date) else item)
        return encoded.replace("<", "\\u003c").replace("&", "\\u0026")

    return (template.replace("__POLL_DATA__", payload(frames))
            .replace("__ELECTION_DATA__", payload(elections or []))
            .replace("__GOVERNMENT_DATA__", payload(governments or []))
            .replace("__DATASET_DATA__", payload(datasets or [])))


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--polls", type=Path, default=Path("data/parliaments/bundestag/polls/wahlrecht-insa.csv"))
    cli.add_argument("--results", type=Path, default=Path("data/parliaments/bundestag/results/wahlrecht-insa.csv"))
    cli.add_argument("--governments", type=Path, default=Path("data/parliaments/bundestag/governments.csv"))
    cli.add_argument("--elections", type=Path, default=Path("data/parliaments/bundestag/elections.csv"))
    cli.add_argument("--landtag-data-dir", type=Path, default=Path("data/parliaments/landtag"),
                     help="directory containing per-state polls, results, elections, and governments")
    cli.add_argument("--output", type=Path, default=Path("charts/insa-race.html"))
    args = cli.parse_args()
    try:
        frames = load_frames(args.polls, args.results, args.governments)
        elections = load_elections(args.elections)
        governments = load_governments(args.governments)
        datasets = [load_dataset(
            "bundestag", "Bundestag", "Deutschland · Bundestagswahl",
            "INSA Sonntagsfrage im Zeitverlauf",
            "Parteianteile in veröffentlichten INSA-Umfragen. Die Balken folgen dem Rang in jeder Erhebung.",
            frames, elections, governments, "wahlrecht.de / INSA",
            "https://www.wahlrecht.de/umfragen/insa.htm", "Bundeswahlleiterin",
            "https://www.bundeswahlleiterin.de/",
        )]
        states = {
            "baden-wuerttemberg": "Baden-Württemberg", "bayern": "Bayern",
            "berlin": "Berlin", "brandenburg": "Brandenburg", "bremen": "Bremen",
            "hamburg": "Hamburg", "hessen": "Hessen",
            "mecklenburg-vorpommern": "Mecklenburg-Vorpommern", "niedersachsen": "Niedersachsen",
            "nordrhein-westfalen": "Nordrhein-Westfalen", "rheinland-pfalz": "Rheinland-Pfalz",
            "saarland": "Saarland", "sachsen": "Sachsen", "sachsen-anhalt": "Sachsen-Anhalt",
            "schleswig-holstein": "Schleswig-Holstein", "thueringen": "Thüringen",
        }
        for state, state_label in states.items():
            base = args.landtag_data_dir / state
            state_frames = load_dawum_frames(base / "polls" / "dawum.csv",
                                             base / "results" / "dawum.csv",
                                             base / "governments.csv",
                                             base / "polls" / "wahlrecht-landtag.csv",
                                             base / "results" / "wahlrecht-landtag.csv")
            state_elections = load_elections(base / "elections.csv")
            state_governments = load_governments(base / "governments.csv")
            with (base / "elections.csv").open(newline="", encoding="utf-8") as handle:
                election_source_url = next(csv.DictReader(handle))["source_url"]
            datasets.append(load_dataset(
                state, f"{state_label} · Landtag", f"{state_label} · Landtagswahl",
                f"Landtagsumfragen in {state_label} im Zeitverlauf",
                f"Parteianteile in veröffentlichten Umfragen zum Landtag {state_label}. Die Balken folgen dem Rang in jeder Erhebung.",
                state_frames, state_elections, state_governments,
                "DAWUM", "https://dawum.de/", "Wahlrecht.de",
                election_source_url,
            ))
        atomic_write(args.output, render(frames, elections, governments, datasets).encode("utf-8"))
    except (OSError, KeyError, ValueError) as exc:
        cli.exit(1, f"error: {exc}\n")
    print(f"Wrote {args.output} with {len(frames)} INSA polls ({frames[0]['date']} to {frames[-1]['date']})")


if __name__ == "__main__":
    main()
