$ErrorActionPreference = "Stop"

if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    Write-Warning "Tesseract was not found on PATH. Install it before running the built app."
}

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

pyinstaller `
    --noconfirm `
    --windowed `
    --onefile `
    --name "Shipping PDF Splitter" `
    --collect-all fitz `
    --collect-all pytesseract `
    --collect-all PIL `
    --hidden-import shipping_pdf_splitter.gui `
    --hidden-import shipping_pdf_splitter.pdf_splitter `
    --hidden-import shipping_pdf_splitter.ocr `
    --hidden-import shipping_pdf_splitter.models `
    src/shipping_pdf_splitter_launcher.py

Write-Host "Build complete: dist/Shipping PDF Splitter.exe"
