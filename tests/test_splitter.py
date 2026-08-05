from pathlib import Path

from shipping_pdf_splitter import pdf_splitter
from shipping_pdf_splitter.models import PageMatch
from shipping_pdf_splitter.models import SplitResult
from shipping_pdf_splitter.pdf_splitter import build_page_groups, output_filename


def test_groups_front_pages_by_shipping_list_and_appends_repeated_pages():
    matches = [
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=0,
            page_number=1,
            text="front",
            shipping_list="150467",
            customer_no="001097",
            sales_order="089235-00",
            references=["150467"],
            is_front_page=True,
        ),
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=3,
            page_number=4,
            text="second shipping list page",
            shipping_list="150467",
            customer_no="001097",
            sales_order="089235-00",
            references=["150467"],
            is_front_page=True,
        ),
    ]

    groups, unmatched = build_page_groups(matches)

    assert unmatched == []
    assert [page.page_number for page in groups["150467"].pages] == [1, 4]
    assert groups["150467"].customer_no == "001097"
    assert groups["150467"].sales_order == "089235-00"


def test_duplicates_multi_reference_pages_into_each_matching_group():
    matches = [
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=0,
            page_number=1,
            text="front 150997",
            shipping_list="150997",
            customer_no="001171",
            sales_order="089409-00",
            references=["150997"],
            is_front_page=True,
        ),
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=1,
            page_number=2,
            text="front 150998",
            shipping_list="150998",
            customer_no="001171",
            sales_order="089410-00",
            references=["150998"],
            is_front_page=True,
        ),
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=2,
            page_number=3,
            text="bill of lading references",
            references=["150997", "150998"],
            is_front_page=False,
        ),
    ]

    groups, unmatched = build_page_groups(matches)

    assert unmatched == []
    assert [page.page_number for page in groups["150997"].pages] == [1, 3]
    assert [page.page_number for page in groups["150998"].pages] == [2, 3]


def test_bol_expands_to_all_groups_with_same_ship_date_and_address():
    common_address = "996 HWY 111 S|NC|27864"
    matches = [
        PageMatch(
            page_index=index,
            page_number=index + 1,
            text=f"shipper {shipping_list}",
            shipping_list=shipping_list,
            ship_date="2026-04-20",
            ship_to_address=common_address,
            references=[shipping_list],
            is_front_page=True,
        )
        for index, shipping_list in enumerate(
            ["151179", "151180", "151181", "151182", "151183", "151184"],
            start=1,
        )
    ]
    matches.insert(
        0,
        PageMatch(
            page_index=0,
            page_number=1,
            text="bill of lading",
            ship_date="2026-04-20",
            ship_to_address=common_address,
            references=["151179", "151184"],
            is_bill_of_lading=True,
        ),
    )

    groups, unmatched = build_page_groups(matches)

    assert unmatched == []
    for shipping_list in groups:
        assert [page.page_number for page in groups[shipping_list].pages] == [
            int(shipping_list) - 151177,
            1,
        ]


def test_bol_date_address_match_requires_both_fields():
    matches = [
        PageMatch(
            page_index=0,
            page_number=1,
            text="bill of lading",
            ship_date="2026-04-20",
            ship_to_address="996 HWY 111 S|NC|27864",
            references=[],
            is_bill_of_lading=True,
        ),
        PageMatch(
            page_index=1,
            page_number=2,
            text="same date, wrong address",
            shipping_list="151179",
            ship_date="2026-04-20",
            ship_to_address="997 HWY 111 S|NC|27864",
            references=["151179"],
            is_front_page=True,
        ),
        PageMatch(
            page_index=2,
            page_number=3,
            text="same address, wrong date",
            shipping_list="151180",
            ship_date="2026-04-21",
            ship_to_address="996 HWY 111 S|NC|27864",
            references=["151180"],
            is_front_page=True,
        ),
    ]

    groups, unmatched = build_page_groups(matches)

    assert [page.page_number for page in groups["151179"].pages] == [2]
    assert [page.page_number for page in groups["151180"].pages] == [3]
    assert [page.page_number for page in unmatched] == [1]


def test_reference_page_can_attach_to_front_page_seen_later():
    matches = [
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=0,
            page_number=1,
            text="reference before front page",
            references=["150462"],
            is_front_page=False,
        ),
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=1,
            page_number=2,
            text="front page",
            shipping_list="150462",
            customer_no="001735",
            sales_order="089034-00",
            references=["150462"],
            is_front_page=True,
        ),
    ]

    groups, unmatched = build_page_groups(matches)

    assert unmatched == []
    assert [page.page_number for page in groups["150462"].pages] == [2, 1]


def test_unmatched_support_page_falls_back_to_previous_shipper():
    matches = [
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=0,
            page_number=1,
            text="shipper page",
            shipping_list="150429",
            customer_no="000041",
            sales_order="088548-00",
            references=["150429"],
            is_front_page=True,
        ),
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=1,
            page_number=2,
            text="bill of lading without readable shipping list",
            references=[],
            is_front_page=False,
        ),
    ]

    groups, unmatched = build_page_groups(matches)

    assert unmatched == []
    assert [page.page_number for page in groups["150429"].pages] == [1, 2]


def test_one_digit_ocr_reference_match_beats_previous_shipper_fallback():
    matches = [
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=0,
            page_number=1,
            text="previous shipper",
            shipping_list="150434",
            customer_no="001729",
            sales_order="089144-00",
            references=["150434"],
            is_front_page=True,
        ),
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=1,
            page_number=2,
            text="bill of lading with OCR mistake",
            references=["150848"],
            is_front_page=False,
        ),
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=2,
            page_number=3,
            text="actual matching shipper",
            shipping_list="150348",
            customer_no="000094",
            sales_order="088785-00",
            references=["150348"],
            is_front_page=True,
        ),
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=94,
            page_number=95,
            text="farther one-digit candidate",
            shipping_list="150448",
            customer_no="001560",
            sales_order="088312-00",
            references=["150448"],
            is_front_page=True,
        ),
        PageMatch(
            source_pdf=Path("sample.pdf"),
            page_index=162,
            page_number=163,
            text="farthest one-digit candidate",
            shipping_list="150248",
            customer_no="000017",
            sales_order="088230-00",
            references=["150248"],
            is_front_page=True,
        ),
    ]

    groups, unmatched = build_page_groups(matches)

    assert unmatched == []
    assert [page.page_number for page in groups["150434"].pages] == [1]
    assert [page.page_number for page in groups["150348"].pages] == [3, 2]


def test_unmatched_pages_are_returned_for_review():
    page = PageMatch(
        source_pdf=Path("sample.pdf"),
        page_index=0,
        page_number=1,
        text="bill of lading with no shipping list match",
        references=[],
        is_front_page=False,
    )

    groups, unmatched = build_page_groups([page])

    assert groups == {}
    assert unmatched == [page]


def test_output_filename_includes_shipping_list_customer_and_sales_order():
    match = PageMatch(
        source_pdf=Path("sample.pdf"),
        page_index=0,
        page_number=1,
        text="front",
        shipping_list="150998",
        customer_no="001171",
        sales_order="089410-00",
        references=["150998"],
        is_front_page=True,
    )

    groups, _ = build_page_groups([match])

    assert output_filename(groups["150998"]) == (
        "ShippingList_150998_Customer_001171_SO_089410-00.pdf"
    )


def test_split_folder_moves_originals_to_old_and_outputs_to_splitshipper(
    tmp_path, monkeypatch
):
    source_pdf = tmp_path / "shipping.pdf"
    source_pdf.write_bytes(b"%PDF-1.4 sample")
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "previous.pdf").write_bytes(b"old")
    (tmp_path / "SplitShipper").mkdir()
    (tmp_path / "SplitShipper" / "already_split.pdf").write_bytes(b"split")

    calls = []

    def fake_split_pdf(pdf_path, output_dir, progress=None):
        calls.append((pdf_path, output_dir))
        return SplitResult(
            input_pdf=pdf_path,
            copied_pdf=pdf_path,
            output_dir=output_dir,
            output_files=[],
            unmatched_pdf=None,
            unmatched_pages=[],
        )

    monkeypatch.setattr(pdf_splitter, "split_pdf", fake_split_pdf)

    results = pdf_splitter.split_folder(tmp_path)

    assert calls == [(tmp_path / "old" / "shipping.pdf", tmp_path / "SplitShipper")]
    assert not source_pdf.exists()
    assert (tmp_path / "old" / "shipping.pdf").read_bytes() == b"%PDF-1.4 sample"
    assert len(results) == 1
