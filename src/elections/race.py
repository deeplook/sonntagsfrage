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


def load_frames(polls_path: Path, results_path: Path,
                governments_path: Path = Path("data/governments.csv")) -> list[dict]:
    with polls_path.open(newline="", encoding="utf-8") as handle:
        polls = list(csv.DictReader(handle))
    with results_path.open(newline="", encoding="utf-8") as handle:
        results = list(csv.DictReader(handle))
    if not polls or not results:
        raise ValueError("INSA poll files are empty; run `uv run elections --source insa` first")
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
            "method": row["method"],
            "sample": row["surveyed_persons"],
            "period": row["period_text"],
            "values": values,
            "url": row["source_url"],
            "government": {"cabinet": government["cabinet"],
                           "parties": government["parties"],
                           "source_url": government["source_url"]},
        })
    if not frames:
        raise ValueError("No INSA polls with party results were found")
    frames.sort(key=lambda frame: (frame["date"], frame["method"], frame["sample"]))
    return frames


def render(frames: list[dict]) -> str:
    template = files("elections").joinpath("insa_race.html").read_text(encoding="utf-8")
    payload = json.dumps(frames, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace("&", "\\u0026")
    return template.replace("__POLL_DATA__", payload)


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--polls", type=Path, default=Path("data/insa_polls.csv"))
    cli.add_argument("--results", type=Path, default=Path("data/insa_results.csv"))
    cli.add_argument("--governments", type=Path, default=Path("data/governments.csv"))
    cli.add_argument("--output", type=Path, default=Path("charts/insa-race.html"))
    args = cli.parse_args()
    try:
        frames = load_frames(args.polls, args.results, args.governments)
        atomic_write(args.output, render(frames).encode("utf-8"))
    except (OSError, KeyError, ValueError) as exc:
        cli.exit(1, f"error: {exc}\n")
    print(f"Wrote {args.output} with {len(frames)} INSA polls ({frames[0]['date']} to {frames[-1]['date']})")


if __name__ == "__main__":
    main()
