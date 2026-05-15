$ErrorActionPreference = "Stop"

if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    Write-Warning "Tesseract was not found on PATH. Install it before running the built app."
}

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

pyinstaller `
    --noconfirm `
    --windowed `
    --name "Shipping PDF Splitter" `
    --collect-all fitz `
    --collect-all pytesseract `
    --collect-all PIL `
    src/shipping_pdf_splitter/__main__.py

Write-Host "Build complete: dist/Shipping PDF Splitter/Shipping PDF Splitter.exe"
