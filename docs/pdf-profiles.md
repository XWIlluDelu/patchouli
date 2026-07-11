# PDF profile reconstruction

Patchouli runs `docling-enriched` in production. The balanced and fast profiles
below retain the exact dependencies and effective parser configuration used for
comparison; they are not alternate backends in `scripts/extract.py` and are
never selected as fallbacks.

All measurements use the same 21-document, 23-page, 99-check sample after model
downloads. They compare the tested configurations, not general parser accuracy.

| Profile | Backend | Score | Time | Measured footprint |
|---|---|---:|---:|---|
| quality | Docling enriched | 66/99 | 19.6 s | 5.3 GiB environment + 1.1 GiB models; about 5 GiB peak RSS and 2.7 GiB GPU reservation |
| balanced | PyMuPDF4LLM + RapidOCR | 54/99 | 14 s | 486 MiB environment; about 1.29 GiB peak RSS |
| fast | Kreuzberg, OCR disabled | 34/99 | 0.37 s | 94 MiB environment |

## Isolated environments

`uv.lock` records every profile. The extras conflict deliberately, so one
environment contains one parser stack. To retain several local environments for
comparison, give each sync its own path:

```sh
UV_PROJECT_ENVIRONMENT=.venv-quality uv sync --extra pdf-quality
UV_PROJECT_ENVIRONMENT=.venv-balanced uv sync --extra pdf-balanced
UV_PROJECT_ENVIRONMENT=.venv-fast uv sync --extra pdf-fast
```

`.gitignore` excludes `.venv/` and `.venv-*/`. Dependency and model caches use
uv and backend defaults outside this repository. Do not force-add environments;
commit `pyproject.toml` and `uv.lock` and rebuild from those files.

## Quality: Docling enriched

This is the only production profile. Install the GPU-capable Linux stack and run
the canonical extractor:

```sh
uv sync --extra pdf-quality
python3 scripts/extract.py paper.pdf --pdf-profile docling-enriched
```

For CPU-only PyTorch wheels, use the same parser profile:

```sh
uv sync --extra pdf-quality-cpu
python3 scripts/extract.py paper.pdf --pdf-profile docling-enriched
```

The authoritative configuration is `_pdf_pipeline_options()` in
`scripts/extract.py`: Heron layout and CodeFormulaV2 at pinned model revisions,
RapidOCR through ONNX Runtime with the Chinese model that also recognizes
English, accurate table structure, formula enrichment, heading hierarchy, no
remote inference service, and at most eight CPU threads. The tracked reading
surface records `docling==2.111.0` and `docling-enriched@1`.

Docling stores downloaded models in user cache directories, not in this
repository.

## Balanced: PyMuPDF4LLM + RapidOCR

Install only after resolving the licenses for the intended use:

- `pymupdf` and `pymupdf4llm` are AGPL-3.0 or commercially licensed.
- The mandatory `pymupdf-layout` dependency is PolyForm Noncommercial or
  commercially licensed. It is the stricter constraint.

The lock entry does not grant a license. The user must determine whether the
noncommercial terms apply or obtain an Artifex commercial license.

This profile uses Python 3.11 or 3.12 because the pinned RapidOCR plugin does not
support Python 3.13:

```sh
uv sync --extra pdf-balanced
```

The benchmark configuration was:

```python
from pymupdf4llm import to_markdown, use_layout
from pymupdf4llm.ocr import rapidocr_api

use_layout(True)
markdown = to_markdown(
    "paper.pdf",
    use_ocr=True,
    force_ocr=False,
    ocr_function=rapidocr_api.exec_ocr,
    write_images=False,
    embed_images=False,
    page_chunks=False,
)
```

The explicit callback prevents OCR-engine autodetection. The profile pins
PyMuPDF, PyMuPDF Layout, and PyMuPDF4LLM to 1.28.0 and
`rapidocr-onnxruntime` to 1.4.4.

## Fast: Kreuzberg

Kreuzberg 4.10.0 scored 34/99 in 0.37 seconds, versus MarkItDown's 33/99
in 1.95 seconds and pypdf's 29/99 in 0.48 seconds. The measured configuration
deliberately disables OCR; it is for born-digital PDFs, not scans.

```sh
uv sync --extra pdf-fast
```

```python
from pathlib import Path

from kreuzberg import ExtractionConfig, extract_bytes_sync

config = ExtractionConfig(
    output_format="markdown",
    use_cache=False,
    ocr=None,
)
markdown = extract_bytes_sync(
    Path("paper.pdf").read_bytes(),
    "application/pdf",
    config=config,
).content
```

Kreuzberg is MIT-licensed. Enabling Tesseract did not improve its 34/99 score in
this corpus and increased runtime from 0.37 seconds to 41.6 seconds, so OCR is
not part of the recorded fast profile.
