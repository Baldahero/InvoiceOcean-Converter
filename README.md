# Bank Statement → InvoiceOcean CSV Converter

Streamlit-приложение для конвертации банковских выписок в CSV формат InvoiceOcean.

## Поддерживаемые компании и банки

| Компания | Банк | Формат файла |
|---|---|---|
| FMCGOODS OÜ | ЗАО «Цептер Банк» (Минск) | `.rtf` (EUR / RUB) |
| TENTA TRADE SP. Z O.O. | PKO Bank Polski | `.pdf` (PLN / EUR) |

## Установка и запуск

```bash
# 1. Клонировать репозиторий
git clone https://github.com/YOUR_USERNAME/bank-converter.git
cd bank-converter

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Запустить
streamlit run app.py
```

Приложение откроется на http://localhost:8501

## Структура проекта

```
bank-converter/
├── app.py                    # Главная страница
├── requirements.txt
├── pages/
│   ├── 1_fmcgoods.py        # Страница FMCGOODS OÜ
│   └── 2_tenta.py           # Страница TENTA TRADE
├── parsers/
│   ├── zepter_parser.py     # Парсер RTF (Цептер Банк)
│   └── pko_parser.py        # Парсер PDF (PKO Bank)
└── utils/
    ├── clients.py           # База клиентов и продавцов
    └── csv_builder.py       # Генератор CSV для InvoiceOcean
```

## Добавление нового клиента

Откройте `utils/clients.py` и добавьте в словарь `CLIENTS`:

```python
"Название компании": {
    "vat_id": "123456789",
    "street": "Улица, дом",
    "postcode": "000000",
    "city": "Город",
    "country": "XX",   # ISO код страны
    "email": "",
    "phone": "",
},
```

## Как загрузить CSV в InvoiceOcean

1. Settings → Import → **New Import**
2. Выбрать файл `.csv`
3. Тип: **Invoices**
4. Сопоставить колонки (они уже совпадают с шаблоном InvoiceOcean)
5. Нажать **Import**

## Формат выходного CSV

Выходной файл полностью совместим с форматом импорта InvoiceOcean и содержит все обязательные поля:
`No., Kind, Seller, Seller's TAX ID, Status, Issue date, Due date, Buyer, VAT ID, Total gross price, Currency, Paid, Payment date, Product / Service, ...`

## Развёртывание на Streamlit Cloud (бесплатно)

1. Запушить репозиторий на GitHub
2. Зайти на [share.streamlit.io](https://share.streamlit.io)
3. Подключить репозиторий
4. Main file: `app.py`
5. Deploy — приложение будет доступно по публичной ссылке
