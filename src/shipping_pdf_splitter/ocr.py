from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

import fitz  # type: ignore[import-not-found]
import pytesseract  # type: ignore[import-not-found]
from PIL import Image

from .models import PageMatch


FRONT_PAGE_RE = re.compile(
    r"Shipping\s+List\s+(?P<shipping_list>\d{5,}).{0,160}?"
    r"Cust\w+\s+No\s+(?P<customer_no>\d{3,}).{0,160}?"
    r"S\w+\W+[OC]rder\s+(?P<sales_order>\d{5,}-\d{2})",
    re.IGNORECASE,
)
SHIPPING_LIST_RE = re.compile(r"Shipping\s+List\s+(?P<shipping_list>\d{5,})", re.IGNORECASE)
SALES_ORDER_RE = re.compile(
    r"S\w+\W+[OC]rder\s+(?P<sales_order>\d{5,}-\d{2})",
    re.IGNORECASE,
)
REFERENCE_BLOCK_RE = re.compile(
    r"Reference\s+Numbers?[:\s]*(?P<refs>.*?)(?:Consignee|Shipper|Street|Name|$)",
    re.IGNORECASE,
)
SIX_DIGIT_RE = re.compile(r"\b\d{6}\b")
_TESSERACT_CONFIGURED = False


def normalize_ocr_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_page_match(
    page_number: int,
    text: str,
    source_pdf: Path | None = None,
    page_index: int | None = None,
) -> PageMatch:
    normalized = normalize_ocr_text(text)
    front = FRONT_PAGE_RE.search(normalized)
    if front:
        shipping_list = front.group("shipping_list")
        return PageMatch(
            source_pdf=source_pdf,
            page_index=page_number - 1 if page_index is None else page_index,
            page_number=page_number,
            text=normalized,
            shipping_list=shipping_list,
            customer_no=front.group("customer_no"),
            sales_order=front.group("sales_order"),
            references=[shipping_list],
            is_front_page=True,
        )

    shipper = SHIPPING_LIST_RE.search(normalized)
    if shipper and "shipper" in normalized.lower():
        shipping_list = shipper.group("shipping_list")
        sales_order = SALES_ORDER_RE.search(normalized)
        return PageMatch(
            source_pdf=source_pdf,
            page_index=page_number - 1 if page_index is None else page_index,
            page_number=page_number,
            text=normalized,
            shipping_list=shipping_list,
            sales_order=sales_order.group("sales_order") if sales_order else None,
            references=[shipping_list],
            is_front_page=True,
        )

    return PageMatch(
        source_pdf=source_pdf,
        page_index=page_number - 1 if page_index is None else page_index,
        page_number=page_number,
        text=normalized,
        references=extract_shipping_list_references(normalized),
        is_front_page=False,
    )


def extract_shipping_list_references(text: str) -> list[str]:
    normalized = normalize_ocr_text(text)
    references: list[str] = []

    for match in SHIPPING_LIST_RE.finditer(normalized):
        references.append(match.group("shipping_list"))

    for block in REFERENCE_BLOCK_RE.finditer(normalized):
        references.extend(SIX_DIGIT_RE.findall(block.group("refs")))

    if not references and "bill of lading" in normalized.lower():
        references.extend(SIX_DIGIT_RE.findall(normalized))

    return _dedupe_shipping_lists(references)


def _dedupe_shipping_lists(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not _looks_like_shipping_list(value):
            continue
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _looks_like_shipping_list(value: str) -> bool:
    try:
        number = int(value)
    except ValueError:
        return False
    return 100000 <= number <= 199999


def ocr_pdf_pages(pdf_path: Path, progress=None) -> list[PageMatch]:
    configure_tesseract()
    matches: list[PageMatch] = []
    with fitz.open(pdf_path) as document:
        total_pages = len(document)
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            if progress:
                progress(f"OCR {pdf_path.name}: page {page_number}/{total_pages}")
            text = ocr_page(page)
            matches.append(
                extract_page_match(
                    page_number=page_number,
                    text=text,
                    source_pdf=pdf_path,
                    page_index=page_index,
                )
            )
    return matches


def configure_tesseract() -> None:
    global _TESSERACT_CONFIGURED
    if _TESSERACT_CONFIGURED:
        return

    bundled_dir = bundled_tesseract_dir()
    if bundled_dir:
        pytesseract.pytesseract.tesseract_cmd = str(bundled_dir / "tesseract.exe")
        tessdata_dir = bundled_dir / "tessdata"
        if tessdata_dir.is_dir():
            os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)
        os.environ["PATH"] = f"{bundled_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    _TESSERACT_CONFIGURED = True


def bundled_tesseract_dir(base_dir: Path | None = None) -> Path | None:
    bundle_root = base_dir or Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    tesseract_dir = bundle_root / "tesseract"
    tesseract_exe = tesseract_dir / "tesseract.exe"
    if tesseract_exe.exists():
        return tesseract_dir
    return None


def ocr_page(page: fitz.Page) -> str:
    pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    width, height = image.size
    top_right = image.crop((int(width * 0.45), 0, width, int(height * 0.32)))

    top_text = pytesseract.image_to_string(top_right, config="--psm 6")
    if FRONT_PAGE_RE.search(normalize_ocr_text(top_text)):
        return top_text

    full_text = pytesseract.image_to_string(image, config="--psm 6")
    return f"{top_text}\n{full_text}"
