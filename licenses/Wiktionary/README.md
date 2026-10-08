# Russian Wiktionary → English dictionary for Lexora

Copyright: contributors of https://ru.wiktionary.org/ . No endorsement is implied.

The converted dataset `data/wiktionary.sqlite3` is distributed under
Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0).
Full licence: CC-BY-SA-4.0.txt in this folder.
Underlying Wikimedia text is available under CC BY-SA and, where applicable,
the GNU Free Documentation License: https://www.gnu.org/licenses/fdl-1.3.html .
This distribution selects the CC BY-SA option.

Source extract: https://kaikki.org/dictionary/downloads/ru/ru-extract.jsonl.gz
Extraction engine: https://github.com/tatuylonen/wiktextract
Download index: https://kaikki.org/dictionary/rawdata.html
Original articles and contributor history:
`https://ru.wiktionary.org/wiki/<word>` and the History tab of each article.
Each converted entry includes its article URL. The application's article button
opens that URL in the user's browser only on an explicit click.

Changes made by `build_wiktionary.py` on 2026-10-07:
English entries selected from the Russian edition; headwords case-folded;
Russian definitions, IPA, examples and synonyms flattened to plain text;
inflected forms indexed as lookup aliases; etymology and audio omitted.
The converted dataset remains CC BY-SA 4.0. This does not change the MIT licence
of the application code or the licences of other dictionaries.

Snapshot counts and the downloaded source SHA256 are in `data/wiktionary.json`.
Rebuild: `python build_wiktionary.py source.jsonl.gz data/wiktionary.sqlite3`
(remove or choose a different temporary build target before rebuilding an interrupted extraction).

Reference: Tatu Ylonen, "Wiktextract: Wiktionary as Machine-Readable Structured
Data", LREC 2022, pp. 1317–1325. https://aclanthology.org/2022.lrec-1.140/
