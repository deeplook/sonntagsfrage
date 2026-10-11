from pathlib import Path

from sonntagsfrage.race import (
    load_dawum_frames,
    load_elections,
    load_governments,
    normalize_party_name,
)


LANDTAG_DIR = Path("data/parliaments/landtag")


def test_common_party_aliases_share_one_display_name():
    cases = {
        "DIE LINKE": "Die Linke",
        "Linke": "Die Linke",
        "Bündnis 90/Die Grünen": "Grüne",
        "B‘90/GRÜNE": "Grüne",
        "GRÜNE/GAL²": "Grüne",
        "CDU¹": "CDU",
        "FDP/DVP": "FDP",
        "Freie Wähler Thüringen": "Freie Wähler",
        "BVB / FREIE WÄHLER³": "BVB/FW",
        "Thüringen.Gerecht (zuvor BSW) (Minderheitsregierung)": "BSW",
        "NPD²": "NPD",
    }
    for source_name, expected in cases.items():
        assert normalize_party_name(source_name) == expected


def test_party_names_are_normalized_across_all_state_data():
    states = sorted(path for path in LANDTAG_DIR.iterdir() if path.is_dir())
    assert len(states) == 16

    for state in states:
        frames = load_dawum_frames(
            state / "polls/dawum.csv", state / "results/dawum.csv",
            state / "governments.csv", state / "polls/wahlrecht-landtag.csv",
            state / "results/wahlrecht-landtag.csv",
        )
        elections = load_elections(state / "elections.csv")
        governments = load_governments(state / "governments.csv")

        names = [name for frame in frames for name in frame["values"]]
        names += [name for election in elections for name in election["values"]]
        names += [name for government in governments for name in government["parties"]]
        assert names
        assert all(normalize_party_name(name) == name for name in names), state.name


def test_thuringia_poll_and_government_names_match():
    state = LANDTAG_DIR / "thueringen"
    frames = load_dawum_frames(
        state / "polls/dawum.csv", state / "results/dawum.csv",
        state / "governments.csv", state / "polls/wahlrecht-landtag.csv",
        state / "results/wahlrecht-landtag.csv",
    )
    frame = next(frame for frame in frames if frame["reference_date"] == "2018-02-19")

    assert set(frame["government"]["parties"]) == {"Die Linke", "SPD", "Grüne"}
    assert set(frame["government"]["parties"]).issubset(frame["values"])


def test_distinct_voter_groups_are_not_collapsed():
    assert normalize_party_name("BVB/FW") == "BVB/FW"
    assert normalize_party_name("Freie Wähler") == "Freie Wähler"
