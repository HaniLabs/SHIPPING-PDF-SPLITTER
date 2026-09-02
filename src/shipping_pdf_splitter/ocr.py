from __future__ import annotations

import io
import importlib
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import fitz  # type: ignore[import-not-found]
import pytesseract  # type: ignore[import-not-found]
from PIL import Image, ImageOps

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
DATE_LABEL_RE = re.compile(r"\b(?:SHIP\s*DATE|DATE\s+SHIPPED)\b", re.IGNORECASE)
GENERIC_DATE_LABEL_RE = re.compile(r"\bDATE\b", re.IGNORECASE)
DATE_VALUE_RE = re.compile(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b")
SHIP_TO_BLOCK_RE = re.compile(
    r"\bSHIP\s+TO\s*[:;]?\s*(?P<address>.*?)(?:\bSHIP\s*DATE\b|\bCUSTOMER\s+PO\b|$)",
    re.IGNORECASE,
)
MARKED_DESTINATION_RE = re.compile(
    r"OCR\s+DESTINATION\s+START(?P<address>.*?)OCR\s+DESTINATION\s+END",
    re.IGNORECASE,
)
POSTAL_CODE_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
STATE_CODES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|"
    "MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|"
    "UT|VT|VA|WA|WV|WI|WY|DC"
)
HIGHWAY_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+(?:(?:US|STATE|COUNTY)\s+)?"
    r"(?:HIGHWAY|HWY|ROUTE|RT)\s+[A-Z0-9-]+"
    r"(?:\s+(?:NORTH|SOUTH|EAST|WEST|N|S|E|W))?\b",
    re.IGNORECASE,
)
STREET_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+(?:(?:NORTH|SOUTH|EAST|WEST|N|S|E|W)\s+)?"
    r"(?:[A-Z0-9-]+\s+){1,5}"
    r"(?:STREET|ST|ROAD|RD|DRIVE|DR|AVENUE|AVE|BOULEVARD|BLVD|LANE|LN|"
    r"COURT|CT|CIRCLE|CIR|PARKWAY|PKWY|PLACE|PL|TERRACE|TER)\b",
    re.IGNORECASE,
)
_TESSERACT_CONFIGURED = False
_NEURAL_OCR_ENGINE = None
NEURAL_OCR_MIN_CONFIDENCE = 0.75


def normalize_ocr_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_page_match(
    page_number: int,
    text: str,
    source_pdf: Path | None = None,
    page_index: int | None = None,
) -> PageMatch:
    normalized = normalize_ocr_text(text)
    has_bol_title = bool(
        re.search(r"\bBILL\s+OF\s+LADING\b", normalized, re.IGNORECASE)
    )
    is_bill_of_lading = has_bol_title and bool(
        re.search(
            r"\b(?:DATE\s+SHIPPED|STRAIGHT\s+BILL\s+OF\s+LADING|CONSIGNEE\s*\(?\s*TO)\b",
            normalized,
            re.IGNORECASE,
        )
    )
    ship_date = extract_ship_date(normalized)
    if ship_date is None and is_bill_of_lading:
        ship_date = extract_bill_of_lading_date(normalized)
    ship_to_address = extract_ship_to_address(normalized)
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
            ship_date=ship_date,
            ship_to_address=ship_to_address,
            references=[shipping_list],
            is_front_page=True,
            is_bill_of_lading=is_bill_of_lading,
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
            ship_date=ship_date,
            ship_to_address=ship_to_address,
            references=[shipping_list],
            is_front_page=True,
            is_bill_of_lading=is_bill_of_lading,
        )

    return PageMatch(
        source_pdf=source_pdf,
        page_index=page_number - 1 if page_index is None else page_index,
        page_number=page_number,
        text=normalized,
        ship_date=ship_date,
        ship_to_address=ship_to_address,
        references=extract_shipping_list_references(normalized),
        is_front_page=False,
        is_bill_of_lading=is_bill_of_lading,
    )


def extract_ship_date(text: str) -> str | None:
    normalized = normalize_ocr_text(text)
    for label in DATE_LABEL_RE.finditer(normalized):
        value = DATE_VALUE_RE.search(normalized, label.end(), label.end() + 220)
        if value:
            return _normalize_date(value.group())
    return None


def extract_bill_of_lading_date(text: str) -> str | None:
    """Extract the generic header Date used by some carrier BOL forms."""
    normalized = normalize_ocr_text(text)
    for label in GENERIC_DATE_LABEL_RE.finditer(normalized):
        value = DATE_VALUE_RE.search(normalized, label.end(), label.end() + 120)
        if value:
            return _normalize_date(value.group())
    return None


def extract_ship_to_address(text: str) -> str | None:
    normalized = normalize_ocr_text(text)
    blocks = [match.group("address") for match in MARKED_DESTINATION_RE.finditer(normalized)]
    blocks.extend(match.group("address") for match in SHIP_TO_BLOCK_RE.finditer(normalized))
    for block in blocks:
        address = _address_key(block)
        if address:
            return address
    return None


def _normalize_date(value: str) -> str | None:
    cleaned = value.replace(".", "/").replace("-", "/")
    for pattern in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(cleaned, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def _address_key(block: str) -> str | None:
    cleaned = re.sub(r"[^A-Za-z0-9-]+", " ", block).upper().strip()
    postal_codes = POSTAL_CODE_RE.findall(cleaned)
    if not postal_codes:
        return None
    postal_code = postal_codes[-1]

    state_matches = list(
        re.finditer(rf"\b(?P<state>{STATE_CODES})\b\s+{re.escape(postal_code)}\b", cleaned)
    )
    if not state_matches:
        return None
    state = state_matches[-1].group("state")

    street_matches = list(HIGHWAY_ADDRESS_RE.finditer(cleaned))
    street_matches.extend(STREET_ADDRESS_RE.finditer(cleaned))
    if not street_matches:
        return None
    street = max(street_matches, key=lambda match: match.start()).group()
    street = _normalize_street(street)
    return f"{street}|{state}|{postal_code}"


def _normalize_street(street: str) -> str:
    aliases = {
        "HIGHWAY": "HWY",
        "ROUTE": "RT",
        "STREET": "ST",
        "ROAD": "RD",
        "DRIVE": "DR",
        "AVENUE": "AVE",
        "BOULEVARD": "BLVD",
        "LANE": "LN",
        "COURT": "CT",
        "CIRCLE": "CIR",
        "PARKWAY": "PKWY",
        "PLACE": "PL",
        "TERRACE": "TER",
        "NORTH": "N",
        "SOUTH": "S",
        "EAST": "E",
        "WEST": "W",
    }
    return " ".join(aliases.get(token, token) for token in street.upper().split())


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
    top_half = image.crop((0, 0, width, int(height * 0.48)))

    top_text = pytesseract.image_to_string(top_right, config="--psm 6")
    top_half_text = pytesseract.image_to_string(top_half, config="--psm 6")
    header_text = f"{top_half_text}\n{top_text}"
    normalized_header = normalize_ocr_text(header_text)
    if FRONT_PAGE_RE.search(normalized_header):
        return header_text

    full_text = pytesseract.image_to_string(image, config="--psm 6")
    destination_text = ""
    bol_header_text = ""
    neural_header_text = ""
    if re.search(r"\bBILL\s+OF\s+LADING\b", normalized_header, re.IGNORECASE):
        bol_header_text = _ocr_bill_of_lading_header(image)
        neural_header_text = _ocr_bill_of_lading_neural_header(image)
        destination = image.crop(
            (int(width * 0.45), int(height * 0.15), width, int(height * 0.42))
        )
        destination_ocr = pytesseract.image_to_string(destination, config="--psm 6")
        destination_text = (
            f"\nOCR DESTINATION START\n{destination_ocr}\nOCR DESTINATION END"
        )
    return (
        f"{header_text}{bol_header_text}{neural_header_text}"
        f"{destination_text}\n{full_text}"
    )


def _ocr_bill_of_lading_header(image: Image.Image) -> str:
    """Re-read the carrier header with thresholding to recover faint references."""
    width, height = image.size
    header = image.crop(
        (
            int(width * 0.32),
            int(height * 0.055),
            int(width * 0.96),
            int(height * 0.125),
        )
    )
    grayscale = ImageOps.grayscale(header)
    variants = [
        grayscale.point(lambda value: 0 if value < threshold else 255)
        for threshold in (130, 190)
    ]
    texts = [
        pytesseract.image_to_string(variant, config="--psm 6")
        for variant in variants
    ]
    return (
        "\nOCR BOL HEADER START\n"
        + "\n".join(texts)
        + "\nOCR BOL HEADER END"
    )


def _get_neural_ocr_engine():
    """Create the CPU-only OCR engine once, only when a BOL needs it."""
    global _NEURAL_OCR_ENGINE
    if _NEURAL_OCR_ENGINE is None:
        rapidocr = importlib.import_module("rapidocr")
        _NEURAL_OCR_ENGINE = rapidocr.RapidOCR()
    return _NEURAL_OCR_ENGINE


def _ocr_bill_of_lading_neural_header(image: Image.Image) -> str:
    """Use neural OCR on the small BOL header where key identifiers live."""
    width, height = image.size
    header = image.crop((0, 0, width, int(height * 0.18)))

    try:
        result = _get_neural_ocr_engine()(header)
    except Exception:
        # Tesseract remains the primary engine, so an unavailable neural fallback
        # must not prevent the rest of the shipment from being processed.
        return ""

    texts = getattr(result, "txts", None) or ()
    scores = getattr(result, "scores", None) or ()
    confident_text = [
        str(text)
        for text, score in zip(texts, scores)
        if float(score) >= NEURAL_OCR_MIN_CONFIDENCE
    ]
    if not confident_text:
        return ""

    return (
        "\nOCR NEURAL BOL HEADER START\n"
        + "\n".join(confident_text)
        + "\nOCR NEURAL BOL HEADER END"
    )
