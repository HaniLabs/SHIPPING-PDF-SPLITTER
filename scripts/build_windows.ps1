$ErrorActionPreference = "Stop"

$tesseractCommand = Get-Command tesseract -ErrorAction SilentlyContinue
if (-not $tesseractCommand) {
    throw "Tesseract was not found on PATH. Install it before building the app."
}

$tesseractExe = $tesseractCommand.Source
$tesseractDir = Split-Path -Parent $tesseractExe
$tessdataDir = Join-Path $tesseractDir "tessdata"
if (-not (Test-Path $tessdataDir)) {
    throw "Tesseract tessdata folder was not found at $tessdataDir"
}

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

$pyinstallerArgs = @(
    "--noconfirm",
    "--windowed",
    "--onefile",
    "--name", "Shipping PDF Splitter",
    "--collect-all", "fitz",
    "--collect-all", "pytesseract",
    "--collect-all", "PIL",
    "--collect-all", "rapidocr",
    "--collect-all", "onnxruntime",
    "--hidden-import", "onnxruntime.capi._pybind_state",
    "--hidden-import", "shipping_pdf_splitter.gui",
    "--hidden-import", "shipping_pdf_splitter.pdf_splitter",
    "--hidden-import", "shipping_pdf_splitter.ocr",
    "--hidden-import", "shipping_pdf_splitter.models",
    "--add-binary", "$tesseractExe;tesseract",
    "--add-data", "$tessdataDir;tesseract/tessdata"
)

Get-ChildItem $tesseractDir -Filter "*.dll" | ForEach-Object {
    $pyinstallerArgs += @("--add-binary", "$($_.FullName);tesseract")
}

$pyinstallerArgs += "src/shipping_pdf_splitter_launcher.py"

pyinstaller @pyinstallerArgs

Write-Host "Build complete: dist/Shipping PDF Splitter.exe"
