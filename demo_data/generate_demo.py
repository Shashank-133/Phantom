"""Generate the 40 demo PDFs (salary slips) for PHANTOM's hero demo.

Reads demo_data/applicants.json (40 applicants, 11 flagged is_fraud=true) and
produces 40 PDFs in demo_data/pdfs/.

Fraud ring members (the 11):
  - Identical Canva-style template (single Helvetica, decorative layout)
  - Producer metadata stamped to "Canva 2.0", creator "Canva"
  - PDF /CreationDate clustered in a 16-minute window at midnight
  - Same font_subset_hash (because they share the same font set)

Clean applications (the 29):
  - CBS-style template (tabular, bank header, multiple font weights)
  - Producer metadata stamped to varied CBS systems (Finacle / BaNCS / FLEXCUBE / Temenos)
  - /CreationDate spread across the previous 30 business days
  - Subsetted TTF fonts (when system TTFs are available)

Run:
    python demo_data/generate_demo.py
Outputs:
    demo_data/pdfs/<applicant_slug>.pdf      (40 files)
    demo_data/applications_index.json        (id-mapped record of what was generated)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from seed.cbs_pdf_factory import (  # noqa: E402
    CanvaSlipData,
    SalarySlipData,
    build_canva_pdf,
    build_cbs_pdf,
    inject_pdf_metadata,
)


# Fraud-ring timing windows — these are the timestamps the engine will detect.
_FRAUD_DOC_CREATED_FROM = datetime(2024, 1, 15, 23, 47, 0)
_FRAUD_DOC_CREATED_TO = datetime(2024, 1, 16, 0, 3, 0)

# CBS producer profiles for clean PDFs — must match values in
# schemas/origin_certificate.CORE_BANKING_PRODUCERS for tool_category to land
# on CORE_BANKING_SYSTEM.
_CBS_PROFILES = [
    ("Finacle 7.3", "Finacle Report Engine"),
    ("TCS BaNCS 9.1", "BaNCS Statement Engine"),
    ("Oracle FLEXCUBE 12.4", "FLEXCUBE Document Service"),
    ("Temenos T24", "T24 Reporter"),
    ("Infosys Finacle 7.4", "Finacle Statement Engine"),
]

_INPUT_FILE = PROJECT_ROOT / "demo_data" / "applicants.json"
_PDFS_DIR = PROJECT_ROOT / "demo_data" / "pdfs"
_INDEX_FILE = PROJECT_ROOT / "demo_data" / "applications_index.json"


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.lower()).strip("_")
    return s[:64] or "unnamed"


def _fraud_creation_time(rng: random.Random) -> datetime:
    """Return a timestamp in the 16-minute fraud window."""
    span_seconds = int((_FRAUD_DOC_CREATED_TO - _FRAUD_DOC_CREATED_FROM).total_seconds())
    return _FRAUD_DOC_CREATED_FROM + timedelta(seconds=rng.randint(0, span_seconds))


def _clean_creation_time(rng: random.Random, submission_time: datetime) -> datetime:
    """Documents typically created 5-30 days before submission, business hours."""
    days_before = rng.randint(5, 30)
    created = submission_time - timedelta(days=days_before)
    return created.replace(hour=rng.randint(10, 17), minute=rng.randint(0, 59), second=rng.randint(0, 59))


def _build_fraud_pdf(applicant: dict, rng: random.Random) -> tuple[bytes, datetime]:
    """Build a Canva-style fake salary slip + return (pdf_bytes, creation_time)."""
    # All fraud docs claim employment at the same generic-looking company.
    # This is intentional — supports the "shared template" detection.
    slip = CanvaSlipData(
        employee_name=applicant["applicant_name"],
        designation="Proprietor",
        period="December 2023",
        company_name="Self Employed Business",
        basic_pay=rng.randrange(60000, 95000, 1000),
        allowances=rng.randrange(15000, 25000, 500),
        deductions=rng.randrange(3000, 8000, 500),
        net_pay=0,  # filled in below
        account_number=applicant["bank_account"],
    )
    slip.net_pay = slip.basic_pay + slip.allowances - slip.deductions

    raw = build_canva_pdf(slip)
    creation_time = _fraud_creation_time(rng)
    final = inject_pdf_metadata(
        raw,
        producer="Canva 2.0",
        creator="Canva",
        creation_date=creation_time,
    )
    return final, creation_time


def _build_clean_pdf(applicant: dict, rng: random.Random) -> tuple[bytes, datetime, str]:
    """Build a CBS-style genuine salary slip + return (pdf_bytes, creation_time, producer)."""
    basic = rng.randrange(40000, 150000, 1000)
    hra = int(basic * rng.uniform(0.30, 0.45))
    da = int(basic * rng.uniform(0.10, 0.20))
    special = rng.randrange(5000, 20000, 500)
    gross = basic + hra + da + special
    pf = int(basic * 0.12)
    ptax = 200
    itax = int(gross * rng.uniform(0.10, 0.18))
    net = gross - pf - ptax - itax

    employer = applicant.get("employer_description", "")
    bank_name = (
        applicant.get("ifsc", "BANK0000000")[:4].upper() + " Bank"
        if applicant.get("ifsc")
        else "Bank of India"
    )
    bank_name_map = {
        "SBIN": "State Bank of India",
        "HDFC": "HDFC Bank",
        "ICIC": "ICICI Bank",
        "AXIS": "Axis Bank",
        "KKBK": "Kotak Mahindra Bank",
        "PUNB": "Punjab National Bank",
        "FDRL": "Federal Bank",
    }
    ifsc_code = applicant.get("ifsc", "SBIN0000123")
    bank_name = bank_name_map.get(ifsc_code[:4], bank_name)

    slip = SalarySlipData(
        employee_name=applicant["applicant_name"],
        employee_id=f"EMP{rng.randrange(10000, 99999)}",
        designation=employer.split(" at ")[0] if " at " in employer else "Employee",
        period="December 2023",
        branch_name=applicant.get("address_line_2") or "Main Branch",
        branch_ifsc=ifsc_code,
        bank_name=bank_name,
        basic_pay=basic,
        hra=hra,
        da=da,
        special_allowance=special,
        pf_deduction=pf,
        professional_tax=ptax,
        income_tax=itax,
        net_pay=net,
        account_number=applicant["bank_account"],
    )

    raw = build_cbs_pdf(slip)
    submission_time = datetime.fromisoformat(applicant["submission_time"])
    creation_time = _clean_creation_time(rng, submission_time)
    producer, creator = rng.choice(_CBS_PROFILES)
    final = inject_pdf_metadata(
        raw,
        producer=producer,
        creator=creator,
        creation_date=creation_time,
    )
    return final, creation_time, producer


def generate(seed: int = 1316) -> dict:
    """Generate all 40 PDFs + index. Returns the index dict that was written."""
    if not _INPUT_FILE.exists():
        raise FileNotFoundError(f"Applicants file not found: {_INPUT_FILE}")

    _PDFS_DIR.mkdir(parents=True, exist_ok=True)

    applicants: list[dict] = json.loads(_INPUT_FILE.read_text(encoding="utf-8"))
    if len(applicants) != 40:
        logger.warning("Expected 40 applicants, found {}", len(applicants))

    rng = random.Random(seed)

    fraud_count = sum(1 for a in applicants if a.get("is_fraud"))
    clean_count = len(applicants) - fraud_count
    logger.info("Generating {} PDFs ({} fraud, {} clean)", len(applicants), fraud_count, clean_count)

    index_entries: list[dict] = []

    for applicant in applicants:
        slug = _slugify(applicant["applicant_name"])
        application_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())
        out_path = _PDFS_DIR / f"{slug}.pdf"

        if applicant.get("is_fraud"):
            pdf_bytes, creation_time = _build_fraud_pdf(applicant, rng)
            producer = "Canva 2.0"
            expected_category = "consumer_design_tool"
        else:
            pdf_bytes, creation_time, producer = _build_clean_pdf(applicant, rng)
            expected_category = "core_banking_system"

        out_path.write_bytes(pdf_bytes)

        entry = {
            "application_id": application_id,
            "document_id": document_id,
            "applicant_name": applicant["applicant_name"],
            "pdf_path": str(out_path.relative_to(PROJECT_ROOT)),
            "pdf_filename": out_path.name,
            "file_size_bytes": len(pdf_bytes),
            "expected_producer": producer,
            "expected_tool_category": expected_category,
            "creation_time": creation_time.isoformat(),
            "submission_time": applicant["submission_time"],
            "is_fraud_planted": bool(applicant.get("is_fraud", False)),
            "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        }
        # Echo the applicant fields for the seeder.
        for k in (
            "pan", "phone", "email", "bank_account", "ifsc", "city",
            "loan_amount_inr", "purpose_of_loan", "employer_description",
            "address_line_2", "guarantor_name", "valuer_name",
        ):
            entry[k] = applicant.get(k)
        index_entries.append(entry)

    index = {
        "generated_at": datetime.utcnow().isoformat(),
        "seed": seed,
        "count": len(index_entries),
        "fraud_count": fraud_count,
        "clean_count": clean_count,
        "fraud_window_doc_created_from": _FRAUD_DOC_CREATED_FROM.isoformat(),
        "fraud_window_doc_created_to": _FRAUD_DOC_CREATED_TO.isoformat(),
        "entries": index_entries,
    }

    _INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")

    logger.info("Wrote {} PDFs to {}", len(index_entries), _PDFS_DIR)
    logger.info("Index: {}", _INDEX_FILE)
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PHANTOM demo PDFs")
    parser.add_argument("--seed", type=int, default=1316)
    args = parser.parse_args()
    try:
        generate(seed=args.seed)
    except Exception as e:
        logger.exception("Demo PDF generation failed: {}", e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
