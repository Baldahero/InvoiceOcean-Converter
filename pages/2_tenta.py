import csv
import io
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.pko_parser import parse_pko_pdf
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


TENTA_NAME = "TENTA TRADE SP. Z O.O."
TENTA_PROFILE = SELLERS.get(TENTA_NAME) or {
    "name": TENTA_NAME,
    "tax_id": "PL5423456230",
    "currency_default": "PLN",
}

INCOME_HEADERS = [
    "No.", "No.", "Kind", "Seller", "Department short name",
    "Seller's TAX ID", "Status", "Issue date", "Sale date", "Due date",
    "Buyer", "VAT ID", "Street", "Postcode", "City", "Country",
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


def build_csv_bytes(rows, headers):
    if shared_generate_csv is not None:
        try:
            return shared_generate_csv(rows, headers=headers)
        except TypeError:
            if headers == INCOME_HEADERS:
                return shared_generate_csv(rows)

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def make_due(issue_date, days):
    try:
        return (datetime.strptime(issue_date, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def detect_document_side(amount):
    if amount > 0:
