# Shipping PDF Splitter

A small desktop app for splitting scanned shipping PDFs by shipping list number.

## What It Does

- Lets you choose a folder containing PDF files.
- Moves each input PDF into an `old` folder so the selected folder is clean for the next run.
- OCRs each page to find `Shipping List`, `Customer No`, and `Sales Order`.
- Creates one split PDF per shipping list number.
- Copies bill-of-lading/reference pages into every matching shipping-list output when those pages contain multiple shipping list numbers.
- Writes pages that cannot be matched to a review PDF.

When you choose a folder, the app creates these folders inside it:

- `old`: moved original PDFs.
- `SplitShipper`: split shipping-list PDFs and any review PDFs.

## Requirements

- Python 3.10 or newer.
- Tesseract OCR installed and available on `PATH`.

Windows Tesseract install options:

```powershell
winget install UB-Mannheim.TesseractOCR
```

macOS Tesseract install option:

```bash
brew install tesseract
```

## Run From Source

```bash
python3 -m pip install -e ".[dev]"
python3 -m shipping_pdf_splitter
```

On Windows, use `python` instead of `python3` if that is how Python is installed.

## Build A Windows EXE

Run this on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

The executable is created at:

```text
dist/Shipping PDF Splitter.exe
```

## Build With GitHub Actions

After this project is pushed to GitHub, open the repository's **Actions** tab and run
the **Build Windows EXE** workflow. It runs the tests on `windows-latest`, builds the
app, and uploads an artifact named `Shipping-PDF-Splitter-Windows`.

Download that artifact and run:

```text
Shipping PDF Splitter.exe
```

## Build A macOS App

Run this on macOS:

```bash
chmod +x scripts/build_macos.sh
./scripts/build_macos.sh
```

The app bundle is created at:

```text
dist/Shipping PDF Splitter.app
```

## Notes

Build the final Windows executable on Windows and the final macOS app on macOS. Cross-compiling these desktop bundles from Linux is not reliable.

The app depends on Tesseract OCR at runtime. Keep Tesseract installed on the computer where you run the app.
