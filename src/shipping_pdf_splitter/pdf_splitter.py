from __future__ import annotations

import re
import shutil
from collections import OrderedDict
from difflib import SequenceMatcher
from pathlib import Path

import fitz  # type: ignore[import-not-found]

from .models import PageGroup, PageMatch, SplitResult
from .ocr import ocr_pdf_pages


def build_page_groups(matches: list[PageMatch]) -> tuple[dict[str, PageGroup], list[PageMatch]]:
    groups: OrderedDict[str, PageGroup] = OrderedDict()
    unmatched: list[PageMatch] = []

    for match in matches:
        if match.is_front_page and match.shipping_list:
            group = groups.setdefault(match.shipping_list, PageGroup(match.shipping_list))
            _fill_group_metadata(group, match)
            group.pages.append(match)

    previous_shipping_list: str | None = None
    for match in matches:
        if match.is_front_page and match.shipping_list:
            previous_shipping_list = match.shipping_list
            continue
        targets = _resolve_reference_targets(match, groups)
        if targets:
            for reference in targets:
                groups[reference].pages.append(match)
        elif previous_shipping_list:
            groups[previous_shipping_list].pages.append(match)
        else:
            unmatched.append(match)

    return dict(groups), unmatched


def output_filename(group: PageGroup) -> str:
    parts = ["ShippingList", group.shipping_list]
    if group.customer_no:
        parts.extend(["Customer", group.customer_no])
    if group.sales_order:
        parts.extend(["SO", group.sales_order])
    return f"{'_'.join(_safe_part(part) for part in parts)}.pdf"


def split_folder(folder: Path, progress=None) -> list[SplitResult]:
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise ValueError(f"Folder does not exist: {folder}")

    copies_dir = folder / "old"
    split_dir = folder / "SplitShipper"
    copies_dir.mkdir(parents=True, exist_ok=True)
    split_dir.mkdir(parents=True, exist_ok=True)

    results: list[SplitResult] = []
    for pdf_path in sorted(folder.glob("*.pdf")):
        if progress:
            progress(f"Moving {pdf_path.name} to old")
        archived_pdf = _unique_path(copies_dir / pdf_path.name)
        shutil.move(str(pdf_path), archived_pdf)
        results.append(split_pdf(archived_pdf, split_dir, progress=progress))
    return results


def split_pdf(pdf_path: Path, output_dir: Path, progress=None) -> SplitResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    matches = ocr_pdf_pages(pdf_path, progress=progress)
    groups, unmatched = build_page_groups(matches)

    output_files: list[Path] = []
    unmatched_pdf = None
    with fitz.open(pdf_path) as source_document:
        for group in groups.values():
            if progress:
                progress(f"Writing {output_filename(group)}")
            output_path = _unique_path(output_dir / output_filename(group))
            _write_page_matches(source_document, group.pages, output_path)
            output_files.append(output_path)

        if unmatched:
            unmatched_pdf = _unique_path(output_dir / f"{pdf_path.stem}_REVIEW_UNMATCHED.pdf")
            _write_page_matches(source_document, unmatched, unmatched_pdf)

    return SplitResult(
        input_pdf=pdf_path,
        copied_pdf=pdf_path,
        output_dir=output_dir,
        output_files=output_files,
        unmatched_pdf=unmatched_pdf,
        unmatched_pages=unmatched,
    )


def _fill_group_metadata(group: PageGroup, match: PageMatch) -> None:
    if group.customer_no is None:
        group.customer_no = match.customer_no
    if group.sales_order is None:
        group.sales_order = match.sales_order
    if group.ship_date is None:
        group.ship_date = match.ship_date
    if group.ship_to_address is None:
        group.ship_to_address = match.ship_to_address


def _resolve_reference_targets(
    match: PageMatch, groups: OrderedDict[str, PageGroup]
) -> list[str]:
    exact_targets = [reference for reference in match.references if reference in groups]
    fuzzy_targets: list[str] = []
    if not exact_targets:
        for reference in match.references:
            fuzzy_target = _nearest_one_digit_match(reference, match.page_number, groups)
            if fuzzy_target:
                fuzzy_targets.append(fuzzy_target)

    date_address_targets = _matching_date_address_targets(match, groups)
    return _dedupe(exact_targets + fuzzy_targets + date_address_targets)


def _matching_date_address_targets(
    match: PageMatch, groups: OrderedDict[str, PageGroup]
) -> list[str]:
    if not (
        match.is_bill_of_lading
        and match.ship_date
        and match.ship_to_address
    ):
        return []

    return [
        reference
        for reference, group in groups.items()
        if group.ship_date == match.ship_date
        and _addresses_match(group.ship_to_address, match.ship_to_address)
    ]


def _addresses_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True

    left_parts = left.split("|")
    right_parts = right.split("|")
    if len(left_parts) != 3 or len(right_parts) != 3:
        return False
    left_street, left_state, left_postal = left_parts
    right_street, right_state, right_postal = right_parts
    if left_state != right_state or left_postal != right_postal:
        return False
    left_number, _, left_name = left_street.partition(" ")
    right_number, _, right_name = right_street.partition(" ")
    if left_number != right_number or not left_name or not right_name:
        return False
    return SequenceMatcher(None, left_name, right_name).ratio() >= 0.88


def _nearest_one_digit_match(
    reference: str, page_number: int, groups: OrderedDict[str, PageGroup]
) -> str | None:
    candidates = [
        group
        for choice, group in groups.items()
        if len(choice) == len(reference) and _digit_distance(reference, choice) == 1
    ]
    if len(candidates) == 1:
        return candidates[0].shipping_list
    if not candidates:
        return None

    closest_distance = min(_page_distance(page_number, group) for group in candidates)
    closest = [
        group
        for group in candidates
        if _page_distance(page_number, group) == closest_distance
    ]
    if len(closest) == 1:
        return closest[0].shipping_list
    return None


def _digit_distance(left: str, right: str) -> int:
    return sum(left_digit != right_digit for left_digit, right_digit in zip(left, right))


def _page_distance(page_number: int, group: PageGroup) -> int:
    if not group.pages:
        return 1_000_000
    return min(abs(page_number - page.page_number) for page in group.pages)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _safe_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "", value)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for counter in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create unique output path for {path}")


def _write_page_matches(
    source_document: fitz.Document, pages: list[PageMatch], output_path: Path
) -> None:
    with fitz.open() as output_document:
        for page in pages:
            output_document.insert_pdf(
                source_document, from_page=page.page_index, to_page=page.page_index
            )
        output_document.save(output_path)
