# Data layout

See [SOURCES.md](SOURCES.md) for source attribution, known licenses, and reuse
terms. The CSV manifests below preserve URLs and hashes for the retrieved
snapshots; they do not establish permission to reuse the data.

Normalized election data is grouped by parliament under `parliaments/`.

- `bundestag/` contains federal polls, party results, election results,
  government intervals, and Bundestag-specific source archives.
- `landtag/<state>/` contains one directory per state, using lowercase
  hyphenated German names such as `baden-wuerttemberg` and `thueringen`.
  Poll and result tables use the same `polls/` and `results/` layout as the
  Bundestag directory; state election and government reference tables belong
  beside them.
- Other parliaments, such as `european-parliament/`, have their own directory.

Source snapshots that span several parliaments stay under `sources/<source>/`.
For example, `sources/dawum/api.json` is the complete DAWUM snapshot; the
fetcher partitions its parsed poll and result tables into the matching
parliament directories. Parliament names from the source are mapped to stable
directory names in `src/sonntagsfrage/fetch.py`.

The default fetch command treats `--output-dir` as this data root. Updating
polls does not replace curated election or government reference tables.

Landtag DAWUM polls and poll results come from the shared snapshot at
`sources/dawum/api.json`. Refresh them with `uv run sonntagsfrage --source dawum`.
The state reference downloader is `uv run sonntagsfrage-landtag-reference-data`.
It archives each state's Wahlrecht.de poll and election result pages. Polls
published after the latest DAWUM poll for a state are written to separate
`polls/wahlrecht-landtag.csv` and `results/wahlrecht-landtag.csv` tables, and
the chart combines those with DAWUM without importing older duplicate dates.
Election reports are normalized into each state's `elections.csv`. The command downloads
StatePol's cabinet-member data and writes derived `governments-statepol.csv`
tables. StatePol currently ends in 2022. The downloader also archives the
current government overview and follows each cabinet article's predecessor
links, saving the pages under each state's `raw/wikipedia-cabinets/` directory.
Those pages provide `governments.csv` intervals that cover the DAWUM poll range;
the current overview and cabinet histories are secondary sources. Source URLs
and hashes for the overview and other shared snapshots are recorded in
`sources/landtag-reference/sources.csv`, while each timeline row records its
cabinet article URL. `governments-current.csv` retains the current overview as
a point-in-time snapshot.
