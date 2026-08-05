from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PageMatch:
    source_pdf: Path | None = None
    page_index: int = 0
    page_number: int = 0
    text: str = ""
    shipping_list: str | None = None
    customer_no: str | None = None
    sales_order: str | None = None
    ship_date: str | None = None
    ship_to_address: str | None = None
    references: list[str] = field(default_factory=list)
    is_front_page: bool = False
    is_bill_of_lading: bool = False


@dataclass
class PageGroup:
    shipping_list: str
    customer_no: str | None = None
    sales_order: str | None = None
    ship_date: str | None = None
    ship_to_address: str | None = None
    pages: list[PageMatch] = field(default_factory=list)


@dataclass(frozen=True)
class SplitResult:
    input_pdf: Path
    copied_pdf: Path
    output_dir: Path
    output_files: list[Path]
    unmatched_pdf: Path | None
    unmatched_pages: list[PageMatch]
