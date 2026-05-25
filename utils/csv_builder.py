"""InvoiceOcean CSV builders."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from utils.clients import CLIENTS, SELLERS


INVOICEOCEAN_HEADERS = [
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

EXPENSE_HEADERS = [
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


def build_row(
    row_num: int,
    invoice_no: str,
    kind: str,
    seller_key: str,
    status: str,
    issue_date: str,
    due_date: str,
    buyer_name: str,
    amount: float,
    amount_eur: float,
    currency: str,
    payment_date: str,
    paid: float,
    description: str,
    po_number: str = "",
    clients: dict | None = None,
) -> list:
    seller = SELLERS.get(seller_key, {})
    client_source = clients or CLIENTS
    client = client_source.get(buyer_name, {})

    return [
        row_num,
        invoice_no,
        kind,
        seller.get("name", seller_key),
        seller.get("name", seller_key),
        seller.get("tax_id", ""),
        status,
        issue_date,
        "",
        due_date,
        buyer_name,
        client.get("vat_id", ""),
        client.get("street", ""),
        client.get("postcode", ""),
        client.get("city", ""),
        client.get("country", ""),
        client.get("email", ""),
        client.get("phone", ""),
        "",
        amount,
        0.0,
        amount,
        amount_eur,
        0.0,
        amount_eur,
        "Transfer",
        payment_date,
        paid,
        currency,
        po_number,
        "",
        "",
        "",
        "",
        "",
        "",
        description,
        1.0,
        amount,
        amount,
        "disabled",
        0.0,
        amount,
        amount,
        "",
        "pc",
        "",
    ]


def generate_csv(rows: list[list], headers: list[str] | None = None) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers or INVOICEOCEAN_HEADERS)
    for row in rows:
        writer.writerow(row)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def format_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def add_days(date_str: str, days: int) -> str:
    value = datetime.strptime(date_str, "%Y-%m-%d")
    return format_date(value + timedelta(days=days))
