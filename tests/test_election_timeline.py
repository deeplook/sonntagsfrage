from pathlib import Path

from sonntagsfrage.race import load_dataset, load_dawum_frames, load_elections, load_governments


LANDTAG_DIR = Path("data/parliaments/landtag")


def test_all_state_timelines_reach_their_latest_election():
    states = sorted(path for path in LANDTAG_DIR.iterdir() if path.is_dir())
    assert len(states) == 16

    for state_dir in states:
        frames = load_dawum_frames(
            state_dir / "polls/dawum.csv",
            state_dir / "results/dawum.csv",
            state_dir / "governments.csv",
            state_dir / "polls/wahlrecht-landtag.csv",
            state_dir / "results/wahlrecht-landtag.csv",
        )
        elections = load_elections(state_dir / "elections.csv")
        dataset = load_dataset(
            state_dir.name, state_dir.name, "", "", "", frames, elections,
            load_governments(state_dir / "governments.csv"), "", "", "", "",
        )

        assert elections, f"{state_dir.name} has no election results"
        assert dataset["timeline_end_date"] >= elections[-1]["date"], state_dir.name
        assert elections[-1]["values"], f"{state_dir.name} has no latest election result values"
