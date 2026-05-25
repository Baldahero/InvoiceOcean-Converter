import os
import re
import sys
import csv
import io
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.zepter_parser import parse_zepter_rtf
from utils.clients import CLIENTS, SELLERS, find_best_client_match, load_clients_from_export, merge_clients
try:
    from utils.csv_builder import EXPENSE_HEADERS as SHARED_EXPENSE_HEADERS
except ImportError:
    SHARED_EXPENSE_HEADERS = None

try:
    from utils.csv_builder import generate_csv as shared_generate_csv
except ImportError:
    shared_generate_csv = None

try:
    from utils.learning import find_learning_match, learning_examples_count, remember_learning_rows
except ImportError:
    def find_learning_match(*args, **kwargs):
        return {}

    def learning_examples_count():
        return 0

    def remember_learning_rows(*args, **kwargs):
        return 0


FMC_NAME = "FMCGOODS OÜ"
FMC_PROFILE = (
    SELLERS.get("FMCGOODS OÜ")
    or SELLERS.get("FMCGOODS OU")
    or SELLERS.get("FMCGOODS OГњ")
    or {
        "name": "FMCGOODS OÜ",
        "tax_id": "EE102627019",
        "currency_default": "EUR",
    }
)

EXPENSE_HEADERS = SHARED_EXPENSE_HEADERS or [
    "No.", "No.", "Kind", "Buyer", "Department short name",
    "Buyer's TAX ID", "Status", "Issue date", "Sale date", "Due date",
    "Seller", "VAT ID", "Street", "Postcode", "City", "Country",
    "Client e-mail", "Client's phone", "Mobile phone",
    "Total net price", "TAX", "Total gross price",
    "Total net price EUR", "TAX EUR", "Total gross price EUR",
    "Payment type", "Payment date", "Paid", "Currency",
    "PO number", "Addressee", "Category", "Notes",
    "Additional invoice field ", "Original document", "Reason for the correction",
    "Product / Service", "Qty", "Unit net price", "Unit gross price", "TAX",
    "VAT amount", "Total net", "Total gross",
    "Position kind", "Quantity unit", "Additional information field",
]


def build_csv_bytes(rows: list[list], headers: list[str] | None = None) -> bytes:
    if shared_generate_csv is not None:
        try:
            if headers is None:
                return shared_generate_csv(rows)
            return shared_generate_csv(rows, headers=headers)
        except TypeError:
            pass

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers or EXPENSE_HEADERS)
    for row in rows:
        writer.writerow(row)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


st.set_page_config(page_title=FMC_NAME, page_icon="🇪🇪", layout="wide")
st.title(f"🇪🇪 {FMC_NAME} -> Zepter Bank -> InvoiceOcean")


def make_due(date_value: str, days: int) -> str:
    try:
        return (datetime.strptime(date_value, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
    except ValueError:
        return date_value


def parse_slash_date(date_text: str) -> str:
    try:
        return datetime.strptime(date_text, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""

