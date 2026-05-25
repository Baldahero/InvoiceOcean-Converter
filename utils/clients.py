"""Client helpers and seller profiles."""

from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd


CLIENTS = {
    "Tenta Trade sp z o.o.": {
        "vat_id": "PL5423456230",
        "street": "Ludwika Zamenhofa 29",
        "postcode": "15435",
        "city": "Białystok",
        "country": "Poland",
        "email": "purchase@tentatrade.com",
        "phone": "",
        "invoiceocean_id": "160865575",
        "legal_name": "Tenta Trade sp z o.o.",
    },
    "PILOT INTERNATIONAL SP. Z O.O.": {
        "vat_id": "5242950541",
        "street": "UL.STANIEWICKA 5",
        "postcode": "03-310",
        "city": "Warszawa",
        "country": "Poland",
        "email": "",
        "phone": "",
        "invoiceocean_id": "160919372",
        "legal_name": "PILOT INTERNATIONAL SP. Z O.O.",
    },
    'LLC "Interopt"': {
        "vat_id": "9718077310",
        "street": "Beregovaya pass, h. 5A, b.1",
        "postcode": "127282",
        "city": "Moscow",
        "country": "Russia",
        "email": "",
        "phone": "",
        "invoiceocean_id": "198757610",
        "legal_name": 'LLC "Interopt"',
    },
    "Brandshandel Limited Liability Company": {
        "vat_id": "193674952",
        "street": "Damashevski zavulak, 11 A, room 712",
        "postcode": "220036",
        "city": "Minsk",
        "country": "Belarus",
        "email": "",
        "phone": "",
        "invoiceocean_id": "225997324",
        "legal_name": "Brandshandel Limited Liability Company",
    },
    'ООО "Селеритас"': {
        "vat_id": "193902397",
        "street": "Пр-т Газеты Звязда, 16-29",
        "postcode": "220117",
        "city": "Minsk",
        "country": "Belarus",
        "email": "",
        "phone": "",
        "invoiceocean_id": "210698971",
        "legal_name": 'ООО "Селеритас"',
    },
}


SELLERS = {
    "FMCGOODS OÜ": {
        "name": "FMCGOODS OÜ",
        "tax_id": "EE102627019",
        "bank": "Zepter Bank",
        "account_eur": "BY13 ZEPT 3024 0025 2251 0978 0000",
        "account_rub": "BY94 ZEPT 3024 0025 2281 0643 0000",
        "currency_default": "EUR",
    },
    "FMCGOODS OU": {
        "name": "FMCGOODS OÜ",
        "tax_id": "EE102627019",
        "bank": "Zepter Bank",
        "account_eur": "BY13 ZEPT 3024 0025 2251 0978 0000",
        "account_rub": "BY94 ZEPT 3024 0025 2281 0643 0000",
        "currency_default": "EUR",
    },
    "TENTA TRADE SP. Z O.O.": {
        "name": "TENTA TRADE SP. Z O.O.",
        "tax_id": "PL5423456230",
        "bank": "PKO Bank Polski",
        "account_pln": "47 1020 1332 0000 1802 1389 3625",
        "account_eur": "52 1020 1332 0000 1602 1389 3633",
        "currency_default": "PLN",
    },
}


def _clean_string(value: Any) -> str:
    if value is None:
