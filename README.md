# German election poll fetcher

Download the poll data discussed in [work/BRAINSTORM.md](work/BRAINSTORM.md). The
project uses Python 3.12+ and [uv](https://docs.astral.sh/uv/) to manage its
dependencies.

```sh
uv run elections
```

The default command downloads two sources:

- [dawum's complete JSON API](https://dawum.de/API/): all available federal and
  state polls from 2017 onward, including INSA. The original database is saved
  at `data/raw/dawum.json`; `data/dawum_polls.csv` has one row per poll and
  `data/dawum_results.csv` has one row per party result.
- [wahlrecht's INSA Bundestag archive](https://www.wahlrecht.de/umfragen/insa.htm):
  the current page and four historical pages back to 2012. The original HTML
  pages are saved under `data/raw/`; `data/insa_polls.csv` and
  `data/insa_results.csv` use the same two-table layout.

Use `uv run elections --source dawum` or `uv run elections --source insa` to
fetch one source. Use `--output-dir PATH` to change the destination. Running the
command again refreshes those files. The fetched data is tracked in this repository.

The `source` and `source_poll_id` columns connect each poll to its party results.
The two providers overlap from 2017 onward, so their rows remain in separate
files. The archive's `period_text` preserves the website's fieldwork notation;
`period_start` and `period_end` are empty when that notation has no exact date.
Election result rows in the archive are excluded because they are not polls.

The [GESIS Politbarometer](https://www.gesis.org/wahlen/politbarometer) mentioned
in the brainstorm is a different, respondent-level research dataset. GESIS
requires a registered user and limits its use to academic research and teaching;
this public poll fetcher does not automate that authenticated download. GERDA
contains election results rather than polls and is likewise outside this
fetcher's scope.

If you publish data derived from dawum, follow its [ODbL attribution and
database-sharing terms](https://dawum.de/API/). Check wahlrecht's terms before
redistributing its archive.

## INSA bar chart race

After fetching the archive, generate a standalone interactive page:

```sh
uv run elections-race
```

Open `charts/insa-race.html` in a browser. Its poll data, CSS, and JavaScript
are embedded, so the file works offline. The default playback shows the last
published poll of each month; switch to **Jede Umfrage** to step through every
poll. You can filter by survey method, scrub the timeline, and change playback
speed. The values are individual poll snapshots, not a cumulative total.

The violet stroke beside a party marks it as part of the **federal government
at the end of that poll's fieldwork**. The chart also names the cabinet and its
parties. The dated, source-linked intervals are in
[`data/governments.csv`](data/governments.csv). They distinguish the SPD–Greens
minority government after the FDP ministers left on 7 November 2024. When a
fieldwork end date is missing, the publication date is used. The current table
is verified through 7 October 2026; rendering a later poll requires updating
it. Both renderers accept `--governments PATH`.

Use `--polls`, `--results`, and `--output` to supply different CSV paths or an
output filename. The chart follows the horizontal ranking and animation pattern
of [davanstrien's benchmark-race](https://huggingface.co/spaces/davanstrien/benchmark-race/blob/main/index.html),
with a fixed 0–50% scale for poll comparability.

## One-minute GIF for sharing

The following command renders every fetched INSA **Online-Panel** poll into a
square, 60-second animation. It also writes a smaller MP4 companion next to the
GIF. Phone and online-panel mixed polls are excluded, keeping the method label
and sample series consistent throughout the animation.
Install [FFmpeg](https://ffmpeg.org/) first; uv installs Pillow from the project
dependencies.

```sh
uv run elections-gif
```

Default outputs are `charts/insa-race.gif` and `charts/insa-race.mp4` (640 × 640
pixels). Both include a German flag, poll source attribution, and a government
marker in every frame. The fixed 0–50% axis avoids
a changing visual scale. Each frame also includes a compact history chart of
online poll values from the first poll through that frame's date. Hollow colored
circles show Bundestag election results; thin vertical guides mark election
dates. The election markers cover the four federal elections in the chart's
date range (2013, 2017, 2021, and 2025), with CDU and CSU combined to match the
poll series. A vertical tick on each party's poll bar shows its result in the
most recent Bundestag election as of that frame, with the election year in the
legend. The 2009 results provide a baseline for the first polls in the timeline.
Alternating pale background bands show the government period in effect for
each frame, using the same fieldwork-end date as the `Regierung` header
(publication date when the fieldwork end is unavailable).

Election result percentages come from the Federal Returning Officer's
[historical results CSV](https://www.bundeswahlleiterin.de/en/dam/jcr/24d8e745-920d-431a-893a-12805bc7ef40/btw_ab49_datenbank_ergebnisse.csv);
dates come from its official HTML page for each election, such as the
[2025 election page](https://www.bundeswahlleiterin.de/bundestagswahlen/2025.html).
The source CSV is preserved at
[`data/raw/bundeswahlleiter-bundestag-results.csv`](data/raw/bundeswahlleiter-bundestag-results.csv),
and the chart-ready values are in
[`data/bundestag_elections.csv`](data/bundestag_elections.csv). These results
are distributed under the [Data Licence Germany – Attribution – Version
2.0](https://www.govdata.de/dl-de/by-2-0); the video frames include the required
attribution. The 1949 election used one vote rather than separate first and
second votes; it falls outside this chart's 2012–present timeline.

Refresh the chart's election results and source material with:

```sh
uv run elections-reference-data
```

This downloads the official results CSV and the per-election HTML pages for
each election year in it, rebuilds `data/bundestag_elections.csv` (combining
CDU and CSU), and saves the CSV at
`data/raw/bundeswahlleiter-bundestag-results.csv`. The election pages are
archived under `data/raw/bundeswahlleiter-election-pages/`, with dates, URLs,
and hashes in `data/raw/bundeswahlleiter-election-pages.csv`. It also downloads
snapshots of the official pages cited by `data/governments.csv` into
`data/raw/government-sources/`, with a URL/hash manifest at
`data/raw/government-sources.csv`.

Government dates and party membership remain curated in
`data/governments.csv`: the cited official pages are narrative documents, not a
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
