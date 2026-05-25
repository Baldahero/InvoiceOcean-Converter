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
) -> list:
    seller = SELLERS.get(seller_key, {})
    client = CLIENTS.get(buyer_name, {})

    return [
        row_num,           # No. (sequential)
        invoice_no,        # No. (invoice number)
        kind,              # Kind
        seller.get("name", seller_key),
        seller.get("name", seller_key),   # Department short name
        seller.get("tax_id", ""),
        status,
        issue_date,
        "",                # Sale date
        due_date,
        buyer_name,
        client.get("vat_id", ""),
        client.get("street", ""),
        client.get("postcode", ""),
        client.get("city", ""),
        client.get("country", ""),
        client.get("email", ""),
        client.get("phone", ""),
        "",                # Mobile phone
        amount,            # Total net price
        0.0,               # TAX
        amount,            # Total gross price
        amount_eur,        # Total net price EUR
        0.0,               # TAX EUR
        amount_eur,        # Total gross price EUR
        "Transfer",        # Payment type
        payment_date,
        paid,              # Paid amount
        currency,
        po_number,         # PO number
        "",                # Addressee
        "",                # Category
        "",                # Notes
        "",                # Additional invoice field
        "",                # Original document
        "",                # Reason for correction
        description,       # Product / Service
        1.0,               # Qty
        amount,            # Unit net price
        amount,            # Unit gross price
        "disabled",        # TAX (position)
        0.0,               # VAT amount
        amount,            # Total net
        amount,            # Total gross
        "",                # Position kind
        "pc",              # Quantity unit
        "",                # Additional information field
    ]


def generate_csv(rows: list[list]) -> bytes:
    """Generate CSV bytes with UTF-8 BOM for Excel compatibility."""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(INVOICEOCEAN_HEADERS)
    for row in rows:
        writer.writerow(row)
    csv_bytes = ("\ufeff" + output.getvalue()).encode("utf-8")
    return csv_bytes


def format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def add_days(date_str: str, days: int) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return format_date(dt + timedelta(days=days))
