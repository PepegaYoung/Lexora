# Third-party components and data

Lexora application code is MIT-licensed. This does not change the licences
of the following components or datasets. Retain this file and `licenses/` when redistributing.

## Dictionary (CC BY-SA 3.0 Unported)

`data/dictionary.sqlite3` is a converted version of **English-Русский FreeDict+WikDict
dictionary**, edition **2025.11.23**, maintained and published by **Karl Bartel**.
Original data: Wiktionary contributors → DBnary → WikDict → FreeDict.
The source header declares 62,181 headwords and CC BY-SA 3.0 Unported.

Source: https://download.freedict.org/generated/eng-rus/eng-rus.tei
Projects: https://freedict.org/ · https://www.wikdict.com/ · https://www.wiktionary.org/
DBnary: https://kaiko.getalp.org/about-dbnary/
Licence: https://creativecommons.org/licenses/by-sa/3.0/legalcode

Changes: TEI XML converted to SQLite by `build_dictionary.py`; headwords case-folded;
pronunciations, parts of speech and senses flattened into readable entries.
The **converted dictionary remains CC BY-SA 3.0**. No endorsement is implied.
The original TEI is included in `data/source/eng-rus.tei`.

## WordNet 3.1

`data/wordnet.sqlite3`: official WordNet 3.1 English definitions converted to SQLite
by `build_wordnet.py`. Copyright 2011 Princeton University. Permission to use, copy,
modify and distribute with retained notices. Full notice: `licenses/WordNet/LICENSE`.
Lemma underscores changed to spaces. No Princeton endorsement is implied.
Source: https://wordnetcode.princeton.edu/wn3.1.dict.tar.gz
Licence: https://wordnet.princeton.edu/license-and-commercial-use
Unmodified source archive included in source ZIP under `vendor-source/`.

## Qt / PySide6 / Shiboken 6.11.2

Used under the open-source LGPLv3 option. Qt Core, Gui and Widgets are dynamically
loaded from replaceable files in `_internal/PySide6`. The application source and
`build.ps1` are supplied so users can rebuild against a modified compatible Qt/PySide6.
No restriction on debugging changes to these components is imposed by Lexora.

Copyright: The Qt Company Ltd. and contributors; individual source files retain
their original notices. Included licence texts: `licenses/Qt/`.
Unmodified corresponding Qt and PySide6 source archives are also included in
`vendor-source/` inside the **source-with-dependencies.zip** asset of the corresponding
release, supplied alongside the portable archive. Retain access to the source archive
for the same release version when redistributing.
Upstream source:

- https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/
- https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/
- https://code.qt.io/cgit/qt/qtbase.git/?h=v6.11.2
- https://code.qt.io/cgit/pyside/pyside-setup.git/?h=v6.11.2

Upstream licensing: https://doc.qt.io/qtforpython-6/ · https://doc.qt.io/qt-6/licensing.html
The wheel's commercial-license text is retained among upstream notices; this
application selects the LGPL option declared in the wheel metadata.

## Python and other libraries

Python 3.12.14 (PSF licence); PyJWT (MIT); cryptography (Apache-2.0 or BSD-3-Clause);
Pillow (HPND and bundled-library notices); NumPy (BSD and bundled-library notices);
MSS (MIT); CTranslate2 (MIT and bundled-library notices); SentencePiece (Apache-2.0);
Requests (Apache-2.0); urllib3 (MIT); certifi (MPL-2.0); charset-normalizer (MIT);
idna (BSD-3-Clause); WinRT/PyWinRT projections (MIT).
PyInstaller bootloader: GPL with an exception permitting application distribution.
Original installed-package licence files and version inventory are in `licenses/`.
Windows OCR is provided by the operating system and is not redistributed here.
Qt's unmodified Microsoft Visual C++ runtime DLLs are retained as distributed
with the official PySide6 wheels; they are separate Microsoft redistributables.
The included OpenMP runtime is an unmodified dependency of CTranslate2.

## Optional translation model

The portable package does **not** contain model weights. The optional download
uses the Argos Translate English → Russian 1.9 package:
https://argos-net.com/v1/translate-en_ru-1_9.argosmodel
SHA-256: `591d743ae103752b88ffc38785c50421320f4eff93c8967e0d3d2e14d4e27811`.
The downloader retains the model's README and metadata next to its weights.
Training-data credits and conditions are described in that README; application
MIT licensing does not relicense the model or its training corpora.

OpenAI endpoints are external services; no OpenAI models or user credentials
are included in this distribution.

MyMemory, Yandex, DeepL and OpenAI are external services.
No service credentials or hosted models are included. Using a service is subject to its terms.

## Russian Wiktionary / Kaikki (CC BY-SA 4.0)

`data/wiktionary.sqlite3`: English entries from the Russian Wiktionary extract,
converted by `build_wiktionary.py`. Copyright Wiktionary contributors.
Russian glosses, IPA, examples, synonyms and inflected forms retained; etymology omitted.
Each entry includes an original article URL and access to contributor history.
The converted data remains CC BY-SA 4.0, separate from MIT application code.
Source, processing notes and full licence: `licenses/Wiktionary/`.
Snapshot counts and downloaded source SHA256: `data/wiktionary.json`.
No Wikimedia/Kaikki endorsement is implied.

## Repository dictionary bundle

`data/bundled-dictionaries.zip` contains the same three converted SQLite databases
and FreeDict TEI source, compressed for repository size. `scripts/prepare_data.py`
restores unchanged bytes and checks `data/manifest.json`. Compression does not
change the attribution, licence or source requirements described above.

## Additional local OCR

Lexora Game OCR v2 adapts the English PP-OCRv4 recognition weights from
PaddleOCR (Apache-2.0). Its detector uses the unmodified PP-OCRv4 detector
packaged by RapidOCR. PaddleOCR notice: licenses/PaddleOCR/LICENSE.
Model origin, changes and evaluation: assets/ocr/MODEL_CARD.json and docs/GAME_OCR.md.
RapidOCR is Apache-2.0; ONNX Runtime is MIT; OpenCV is Apache-2.0;
Shapely is BSD-3-Clause; pyclipper retains the Boost Software License.
See the corresponding licenses folders for full notices and dependency notices.
Training libraries, downloaded game screenshots and system font files are not bundled.

GPU OCR uses ONNX Runtime DirectML 1.24.4 (see licenses/onnxruntime-directml).
The RapidOCR 1.4.4 Python implementation is included with retained notices under
windowwords/_vendor/rapidocr; imports and session configuration were adapted.
No external rapidocr-onnxruntime package or second ONNX Runtime distribution is required.
