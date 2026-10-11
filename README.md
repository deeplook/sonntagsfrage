# Sonntagsfrage

Download the poll data discussed in [work/BRAINSTORM.md](work/BRAINSTORM.md). The
project uses Python 3.12+ and [uv](https://docs.astral.sh/uv/) to manage its
dependencies.

Install the project and its dependencies in a local virtual environment with:

```sh
uv sync
```

Then run project commands with `uv run` as shown below. To create distributable
source and wheel packages, run `uv build`.

```sh
uv run sonntagsfrage
```

The default command downloads two sources:

- [dawum's complete JSON API](https://dawum.de/API/): all available federal and
  state polls from 2017 onward, including INSA. The shared source snapshot is
  saved at `data/sources/dawum/api.json`; parsed tables are partitioned by
  parliament under `data/parliaments/`.
- [wahlrecht's INSA Bundestag archive](https://www.wahlrecht.de/umfragen/insa.htm):
  the current page and four historical pages back to 2012. Original HTML pages
  and normalized poll/result tables are stored in the Bundestag directory.

The data tree separates scope from source: `data/parliaments/bundestag/` holds
federal polls, results, elections, governments, and source archives;
`data/parliaments/landtag/<state>/` holds each state's data; and other
parliaments, such as the European Parliament, have their own directory. Raw
DAWUM JSON stays in `data/sources/dawum/` because one snapshot contains polls
for several parliaments.

Use `uv run sonntagsfrage --source dawum` or `uv run sonntagsfrage --source insa` to
fetch one source. Use `--output-dir PATH` to change the destination. Running the
command again refreshes those files. The fetched data is tracked in this repository.

Each provider's `polls/*.csv` and `results/*.csv` files use matching
`source_poll_id` values to connect polls to party results. The two providers
overlap from 2017 onward, so their rows remain in separate files. The archive's
`period_text` preserves the website's fieldwork notation; `period_start` and
`period_end` are empty when that notation has no exact date. Election result
rows in the archive are excluded because they are not polls.

The [GESIS Politbarometer](https://www.gesis.org/wahlen/politbarometer) mentioned
in the brainstorm is a different, respondent-level research dataset. GESIS
requires a registered user and limits its use to academic research and teaching;
this public poll fetcher does not automate that authenticated download. GERDA
contains election results rather than polls and is likewise outside this
fetcher's scope.

See [`data/SOURCES.md`](data/SOURCES.md) for the project's source register,
known licenses, attribution guidance, and sources whose reuse terms still need
verification before redistribution.

## INSA bar chart race

After fetching the archive, generate a standalone interactive page:

```sh
uv run sonntagsfrage-race
```

Open `charts/insa-race.html` in a browser. Its poll data, CSS, and JavaScript
and election reference data are embedded, so the file works offline. Its
history chart grows with playback and includes election results and government
periods. Use the **Parlament** selector to switch between the Bundestag and any
of the 16 Landtage; poll series, government labels, election markers, titles,
and source credits update together. Landtag polls newer than the latest DAWUM
entry are supplemented from Wahlrecht.de's state poll tables. **Institut / Auftraggeber** filters a
Landtag view by pollster or commissioning organization; the Bundestag view
currently offers INSA only. The file embeds DAWUM, supplemental Wahlrecht poll
data, and Landtag reference tables, so no separate data files are needed in the browser.
The default playback shows the last published poll of each month;
switch to **Jede Umfrage** to step through every poll. You can filter by survey
method, scrub the timeline, and change playback speed. The values are
individual poll snapshots, not a cumulative total.

The violet stroke beside a party marks it as part of the **federal government
at the end of that poll's fieldwork**. The chart also names the cabinet and its
parties. The dated, source-linked intervals are in
[`data/parliaments/bundestag/governments.csv`](data/parliaments/bundestag/governments.csv). They distinguish the SPD–Greens
minority government after the FDP ministers left on 7 November 2024. When a
fieldwork end date is missing, the publication date is used. The current table
is verified through 11 October 2026 against the Federal Cabinet page; update
it when the cabinet changes. Both renderers accept `--governments PATH`.

Use `--polls`, `--results`, and `--output` to supply different CSV paths or an
output filename. The chart follows the horizontal ranking and animation pattern
of [davanstrien's benchmark-race](https://huggingface.co/spaces/davanstrien/benchmark-race/blob/main/index.html),
with a fixed 0–50% scale for poll comparability.

## One-minute GIF for sharing

The following command renders every fetched INSA **Online-Panel** Bundestag
poll into a square, 60-second animation. It also writes a smaller MP4 companion
next to the GIF. Phone and online-panel mixed polls are excluded by default.
Install [FFmpeg](https://ffmpeg.org/) first; uv installs Pillow from the project
dependencies.

```sh
uv run sonntagsfrage-gif
```

Default outputs are `charts/insa-race.gif` and `charts/insa-race.mp4` (640 × 640
pixels). Both include a German flag, poll source attribution, and a government
marker in every frame. The fixed 0–50% axis avoids
a changing visual scale. Each frame also includes a compact history chart of
online poll values from the first poll through that frame's date. Hollow colored
circles show Bundestag election results; thin vertical guides mark election
dates. Poll lines connect observations up to three calendar months apart and
leave a gap when the next poll is more than three months later. The election markers cover the four
federal elections in the chart's date range (2013, 2017, 2021, and 2025),
combining CDU and CSU to match the poll series. A vertical tick on each party's
poll bar shows its result in the most recent Bundestag election as of that frame,
with the election year in the legend. The 2009 results provide a baseline for
the first polls in the timeline.
Alternating pale background bands show the government period in effect for
each frame, using the same fieldwork-end date as the `Regierung` header
(publication date when the fieldwork end is unavailable).

Choose a parliament and filter its polls by source, institute, commissioner,
or method. Landtag names use their data directory slug. For example:

```sh
uv run sonntagsfrage-gif --parliament brandenburg --source all
uv run sonntagsfrage-gif --parliament bayern --source dawum --institute INSA
uv run sonntagsfrage-gif --parliament bundestag --source all --institute INSA
```

Sources are `dawum`, `wahlrecht`, or `all`. The Bundestag defaults to
Wahlrecht/INSA Online-Panel polls to preserve the original movie; Landtage
default to all available poll sources and methods. A Landtag movie defaults to
`charts/<state>-race.gif` (and an MP4 with the same name). Use `--output` to
choose another path.

Election result percentages come from the Federal Returning Officer's
[historical results CSV](https://www.bundeswahlleiterin.de/en/dam/jcr/24d8e745-920d-431a-893a-12805bc7ef40/btw_ab49_datenbank_ergebnisse.csv);
dates come from its official HTML page for each election, such as the
[2025 election page](https://www.bundeswahlleiterin.de/bundestagswahlen/2025.html).
The source CSV is preserved at
[`data/parliaments/bundestag/raw/bundeswahlleiter/results.csv`](data/parliaments/bundestag/raw/bundeswahlleiter/results.csv),
and the chart-ready values are in
[`data/parliaments/bundestag/elections.csv`](data/parliaments/bundestag/elections.csv). These results
are distributed under the [Data Licence Germany – Attribution – Version
2.0](https://www.govdata.de/dl-de/by-2-0); the video frames include the required
attribution. The 1949 election used one vote rather than separate first and
second votes; it falls outside this chart's 2012–present timeline.

Refresh the chart's election results and source material with:

```sh
uv run sonntagsfrage-bundestag-reference-data
```

This downloads the official results CSV and the per-election HTML pages for
each election year in it, rebuilds `data/parliaments/bundestag/elections.csv`
(combining CDU and CSU), and saves the CSV at
`data/parliaments/bundestag/raw/bundeswahlleiter/results.csv`. The election
pages are archived under
`data/parliaments/bundestag/raw/bundeswahlleiter/election-pages/`, with dates,
URLs, and hashes in
`data/parliaments/bundestag/raw/bundeswahlleiter/election-pages.csv`. It also
downloads snapshots of the official pages cited by
`data/parliaments/bundestag/governments.csv` into
`data/parliaments/bundestag/raw/government-sources/`, with a URL/hash manifest
at `data/parliaments/bundestag/raw/government-sources.csv`.

Government dates and party membership remain curated in
`data/parliaments/bundestag/governments.csv`: the cited official pages are narrative documents, not a
structured feed, so review them and edit the intervals when the cabinet changes.
Pass `--data-dir PATH` to refresh a separate data directory.

Use `--output PATH`, `--seconds N`, `--size N`, or `--colors N` to control the
GIF. For a non-square output, pass `--width W --height H` instead of `--size`;
for example, `--width 960 --height 640` renders a 3:2 landscape animation.
Layout positions adapt to the canvas and fonts scale with its shorter side.
Bars glide vertically between poll ranks by default; use `--no-glide` to turn
this off. The HTML chart has a matching “Rangwechsel gleiten” checkbox.
`--no-mp4` skips the video companion. Because GIF frame timing is limited
to centiseconds, the encoder alternates frame delays to make the full sequence
exactly 60 seconds.
