# Data sources, attribution, and reuse terms

This register records the sources used by the datasets and charts, what is
known about their reuse terms, and the attribution or review needed when
redistributing derived material. It is a provenance aid, not a legal opinion.
Review source terms again before publishing or redistributing a dataset or
chart, especially when a status below is marked **Unclear**.

The retrieval manifests beside the archived data record snapshot paths,
source URLs, retrieval dates where available, and SHA-256 hashes. Normalized
rows retain source URLs when the source is row-specific. The manifests establish
which source copy was used; they do not grant reuse rights.

| Source | Data used | Published terms / rights status | Attribution and reuse notes |
| --- | --- | --- | --- |
| [DAWUM](https://dawum.de/Urheberrecht/) | Federal and state polls and results from the API | DAWUM states its survey database is under the Open Database License (ODbL) 1.0. | Credit DAWUM and link the ODbL. For public redistribution of a derivative database, review and follow ODbL attribution and share-alike requirements. The charts link to DAWUM and the ODbL. |
| [Wahlrecht.de](https://www.wahlrecht.de/kontakt.htm) | INSA polls, newer Landtag polls that postdate the DAWUM snapshot, Landtag election result tables, and linked result reports | **Unclear:** the inspected imprint does not state a general reuse license for the site’s compiled material. | The project links to Wahlrecht and records page URLs. Linking and attribution do not by themselves establish permission to republish archived page content or substantial extracts. Check with the publisher before redistributing those materials or substantial derived extracts. |
| [Federal Returning Officer](https://www.bundeswahlleiterin.de/) | Bundestag election results and official election pages | The Bundestag results CSV is distributed under [Data Licence Germany – Attribution – Version 2.0](https://www.govdata.de/dl-de/by-2-0), as stated by the source. | Include the required attribution and link to the license when redistributing the results or derived material. Chart outputs include source and license attribution. |
| [StatePol Database](https://github.com/StatePol/Database) | Historical Landtag cabinet membership | **Unclear:** the inspected download and citation pages provide no explicit data license. | Cite the database paper (Koch, Kuhlen, Müller & Stecker, “StatePol – A Database on the Members of German State Cabinets and Parliaments,” *Politische Vierteljahresschrift*, 2024, [DOI](https://doi.org/10.1007/s11615-024-00528-z)) and the downloaded version. Verify reuse terms with the maintainers before republishing the cabinet-member dataset. |
| [German Wikipedia](https://de.wikipedia.org/wiki/Wikipedia:Weiternutzung) | Current government overview and cabinet predecessor pages used to build Landtag government intervals | Wikipedia text is available under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). | Provide attribution and a link to the source article and license; indicate changes. If redistributed material is an adaptation of Wikipedia text, comply with share-alike terms. The timeline uses structured cabinet facts; assess applicable obligations before external redistribution. |
| Official Bundestag government pages | Dates and descriptions supporting Bundestag government intervals | The linked official pages do not carry a single project-wide license record in this repository. | Cite the specific official source page for each interval. Check the terms on the source page before republication. |
| [Wikimedia Commons state coat-of-arms files](https://commons.wikimedia.org/wiki/Category:SVG_coats_of_arms_of_states_of_Germany) | Small SVG versions of the 16 Länder coats of arms embedded in the standalone HTML chart and raster companions used in movies | Licenses differ by file; the per-file source page, author, license, and license URL are recorded in `../src/sonntagsfrage/assets/wappen/manifest.json`. Most files are marked public domain on Commons; Bavaria and Brandenburg use CC BY-SA files. | The selected state's image is credited in the chart footer with a link to its Commons description page and, where available, the file license. Movie credits include the Commons file URL, author where listed, and license. The original SVG files are bundled unchanged; transparent PNGs in `raster/` are derived for Pillow movie rendering. A file license covers the submitted artwork; it does not necessarily settle every use of a protected state emblem. Review the relevant state's rules before uses beyond this informational chart. |

## Project attribution

For charts using multiple datasets, show the sources that contribute to the
displayed data and include applicable license links. Current chart attribution
is in the chart footer or accompanying documentation. A single short credit
line is not a substitute for any database license notice or share-alike terms
that apply to a redistributed dataset.

## Source manifests

- `sources/landtag-reference/sources.csv` lists Landtag source URLs, archived
  snapshot paths, and hashes, including the individual cabinet article pages.
- `parliaments/landtag/<state>/raw/wahlrecht/election-pages.csv` lists each
  election report page, election date/status, archived page, and hash.
- `sources/statepol/sources.csv` identifies the StatePol cabinet dataset
  snapshot and hash.
- `parliaments/bundestag/raw/bundeswahlleiter/election-pages.csv` lists
  Bundestag election pages, dates, snapshots, and hashes.
- `parliaments/bundestag/raw/government-sources.csv` records official pages
  used to verify federal government intervals.
- `../src/sonntagsfrage/assets/wappen/manifest.json` records Wikimedia Commons
  file pages and per-file author and license metadata for the bundled state
  coat-of-arms SVGs.

This register was reviewed on 2026-10-09. Recheck source terms when refreshing
the data and update this file if a provider publishes or changes its license.
