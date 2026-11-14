# TASKS

- [x] Use only "online" data for the GIF and MP4 outputs, which should reduce flickering in one text line.
- [x] Add a small (full width but small height) line-chart at the bottom, from start to the current date.
- [x] Get more data (ideally from the sources we already use), about German Bundestag elections dates and results, to integrate into the chart.
- [x] Use two alternating decent bright background colors to indicate election moments when government changes.
- [x] Add a German flag into the top-right corner.
- [x] Add an effect to make the bars "glide" vertically when the order changes. In the HTML output this can take a little more time, but in the MPEG4/GIF output this should be rather quick. Add an option to enable/disable this effect.
- [x] Use one decimal digit after the decimal point if not 0 for polls.
- [x] Close gaps in linecharts for all Landtags polls.
- [x] Rename project name from elections to sonntagsfrage.
- [x] Use typer package, incl. -h option, equivalent to --help.
- [x] Make the project installable via uv.
- [x] Add a blank between the numeric day and month in the HTML output like this: "08. Oktober 2026".
- [?] Add an image/video export button with some options like incl. linechart or not.
- [x] Add a shareable link next to each chart with all its params (shortlinks would need a server).
