#!/usr/bin/env bash
set -euo pipefail

if ! command -v tesseract >/dev/null 2>&1; then
  echo "Warning: tesseract was not found on PATH. Install it before running the built app." >&2
fi

python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"

pyinstaller \
  --noconfirm \
  --windowed \
  --name "Shipping PDF Splitter" \
  --collect-all fitz \
  --collect-all pytesseract \
  --collect-all PIL \
  src/shipping_pdf_splitter/__main__.py

echo "Build complete: dist/Shipping PDF Splitter.app"
