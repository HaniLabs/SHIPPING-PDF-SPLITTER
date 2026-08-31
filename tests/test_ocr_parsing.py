from shipping_pdf_splitter.ocr import (
    bundled_tesseract_dir,
    extract_bill_of_lading_date,
    extract_page_match,
    extract_ship_date,
    extract_ship_to_address,
    extract_shipping_list_references,
)


def test_extracts_front_page_fields_from_shipping_list_header():
    text = (
        "Shipping List 150998 Customer No 001171 "
        "Sales Order 089410-00 Sales Order Shipper"
    )

    match = extract_page_match(page_number=1, text=text)

    assert match.is_front_page is True
    assert match.shipping_list == "150998"
    assert match.customer_no == "001171"
    assert match.sales_order == "089410-00"
    assert match.references == ["150998"]


def test_extracts_front_page_fields_with_common_ocr_noise():
    text = (
        "Shipping List 150462 Customer No 001735 "
        "“Sales Order 089034-00 Sales Order Shipper"
    )

    match = extract_page_match(page_number=1, text=text)

    assert match.is_front_page is True
    assert match.shipping_list == "150462"
    assert match.customer_no == "001735"
    assert match.sales_order == "089034-00"


def test_extracts_front_page_when_ocr_misreads_customer_or_sales():
    text = (
        "Shipping List 150360 Custorner No 000475 "
        "Sales Crder 080821-00 Sales Crder Shipper"
    )

    match = extract_page_match(page_number=152, text=text)

    assert match.is_front_page is True
    assert match.shipping_list == "150360"
    assert match.customer_no == "000475"
    assert match.sales_order == "080821-00"


def test_extracts_front_page_when_sales_order_has_punctuation():
    text = (
        "Shipping List 150502 Customer No 001691 "
        "Sales, Order 089521-00 Sales Order Shipper"
    )

    match = extract_page_match(page_number=55, text=text)

    assert match.is_front_page is True
    assert match.shipping_list == "150502"
    assert match.customer_no == "001691"
    assert match.sales_order == "089521-00"


def test_treats_miscellaneous_shipper_as_front_page_without_customer():
    text = "Shipping List 150352 Miscellaneous Shipper"

    match = extract_page_match(page_number=164, text=text)

    assert match.is_front_page is True
    assert match.shipping_list == "150352"
    assert match.customer_no is None
    assert match.sales_order is None
    assert match.references == ["150352"]


def test_extracts_miscellaneous_shipper_sales_order_when_present():
    text = "Shipping List 150351 Sales Order 088820-00 Miscellaneous Shipper"

    match = extract_page_match(page_number=165, text=text)

    assert match.is_front_page is True
    assert match.shipping_list == "150351"
    assert match.sales_order == "088820-00"
    assert match.references == ["150351"]


def test_extracts_multiple_references_from_bill_of_lading_text():
    text = (
        "DATE SHIPPED BILL OF LADING NUMBER PURCHASE ORDER NUMBER "
        "REFERENCE NUMBERS 4/8/26 C42781,C42763 150997,150998 "
        "CONSIGNEE AMERICAN TRACTION SYSTEMS"
    )

    assert extract_shipping_list_references(text) == ["150997", "150998"]


def test_extracts_slash_delimited_references_from_bill_of_lading_text():
    text = "REFERENCE NUMBERS: 451381 / 151348 //151349 CONSIGNEE ABB INC"

    assert extract_shipping_list_references(text) == ["151348", "151349"]


def test_normalizes_shipper_date_and_ship_to_address():
    text = (
        "Shipping List 151179 Customer No 001656 Sales Order 089646-00 "
        "Sales Order Shipper Ship to: ABB INC PINETOPS MV PRODUCTS "
        "996 HWY 111 SOUTH PINETOPS NC 27864 United States "
        "Ship Date Customer PO 04-20-2026 4503930603"
    )

    match = extract_page_match(page_number=2, text=text)

    assert match.ship_date == "2026-04-20"
    assert match.ship_to_address == "996 HWY 111 S|NC|27864"


def test_normalizes_bol_date_and_marked_consignee_address():
    text = (
        "STRAIGHT BILL OF LADING DATE SHIPPED BILL OF LADING NUMBER "
        "4/20/26 REFERENCE NUMBERS 151179-151184 "
        "OCR DESTINATION START CONSIGNEE TO NAME ABB INC PINETOPS MV PRODUCTS "
        "STREET 996 HIGHWAY 111 SOUTH CITY PINETOPS NC 27864 "
        "OCR DESTINATION END"
    )

    match = extract_page_match(page_number=1, text=text)

    assert match.is_bill_of_lading is True
    assert match.ship_date == "2026-04-20"
    assert match.ship_to_address == "996 HWY 111 S|NC|27864"


def test_extracts_generic_date_from_bill_of_lading_header():
    text = (
        "UNIFORM STRAIGHT BILL OF LADING Date Purchase Order # "
        "06/04/2026 4503954897 Shipper # 151720"
    )

    match = extract_page_match(page_number=1, text=text)

    assert extract_bill_of_lading_date(text) == "2026-06-04"
    assert match.is_bill_of_lading is True
    assert match.ship_date == "2026-06-04"
    assert match.references == ["151720"]


def test_ship_fields_require_labeled_date_and_complete_address():
    assert extract_ship_date("Printed 04-20-2026") is None
    assert extract_ship_to_address("Ship to: ABB INC PINETOPS NC 27864") is None


def test_detects_bundled_tesseract_directory(tmp_path):
    tesseract_dir = tmp_path / "tesseract"
    tesseract_dir.mkdir()
    (tesseract_dir / "tesseract.exe").write_bytes(b"fake exe")
    (tesseract_dir / "tessdata").mkdir()

    assert bundled_tesseract_dir(tmp_path) == tesseract_dir
