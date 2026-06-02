import streamlit as st
import pandas as pd
import re
import pdfplumber
import io
from datetime import datetime, timedelta
from dataclasses import dataclass
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers.zepter_parser import parse_zepter_rtf
from utils.clients import CLIENTS, SELLERS

st.set_page_config(page_title="FMCGOODS OÜ", page_icon="🇪🇪", layout="wide")
st.title("🇪🇪 FMCGOODS OÜ → InvoiceOcean")

# ══════════════════════════════════════════════════════════
# INLINE PARSERS (Zepter PDF + PKO Wyciag PDF)
# ══════════════════════════════════════════════════════════

@dataclass
class ZepterPDFTx:
    seq_num: str = ""; doc_num: str = ""; date: str = ""
    op_code: str = ""; bic: str = ""; account: str = ""
    debit: float = 0.0; credit: float = 0.0; amount: float = 0.0
    currency: str = "EUR"; description: str = ""; counterparty: str = ""
    is_commission: bool = False; is_conversion: bool = False

@dataclass
class PKOWyciagTx:
    date: str = ""; tx_id: str = ""; op_type: str = ""
    amount: float = 0.0; currency: str = "EUR"
    beneficiary: str = ""; title: str = ""
    is_commission: bool = False; is_fx: bool = False

def _amt(s):
    try: return float(str(s).replace('\xa0','').replace(' ','').replace(',','.'))
    except: return 0.0

def _fdate(d):
    p = str(d).strip().split('.')
    return f"{p[2]}-{p[1]}-{p[0]}" if len(p)==3 else d

def _pdf_lines(pdf_bytes):
    lines = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            lines.extend((page.extract_text() or '').split('\n'))
    return lines

def _zepter_meta(lines):
    meta = {}
    for line in lines:
        if 'Счет клиента:' in line:
            m = re.search(r'Счет клиента:\s*(\S+)\s+(EUR|RUB|USD|BYN)', line)
            if m: meta['account'] = m.group(1); meta['currency'] = m.group(2)
        m = re.search(r'с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})', line)
        if m: meta['date_from'] = _fdate(m.group(1)); meta['date_to'] = _fdate(m.group(2))
    return meta

def parse_zepter_eur_pdf(pdf_bytes):
    lines = _pdf_lines(pdf_bytes)
    meta = _zepter_meta(lines)
    currency = meta.get('currency', 'EUR')
    TX = re.compile(r'^(\d+)\s+(\S+)\s+(\d{2}\.\d{2}\.\d{4})\s+(\d)\s+(\S+)\s+([\d\s]+,\d{2})\s+([\d\s]+,\d{2})\s+([\d\s,]+)$')
    txs = []; i = 0
    while i < len(lines):
        m = TX.match(lines[i].strip())
        if m:
            seq,doc,date,op,bic = m.group(1),m.group(2),_fdate(m.group(3)),m.group(4),m.group(5)
            v1,v2 = _amt(m.group(6)),_amt(m.group(7))
            credit,debit = (v1,0.0) if op=='1' else (0.0,v1)
            amount = credit if credit>0 else -debit
            acc = ''
            if i+1<len(lines) and re.match(r'^[A-Z0-9\s]+$',lines[i+1].strip()) and len(lines[i+1].strip())<30:
                acc = lines[i+1].strip(); i+=1
            desc_lines=[]; j=i+1
            while j<len(lines):
                dl=lines[j].strip()
                if TX.match(dl) or 'Итого оборотов' in dl or 'Исходящее сальдо' in dl: break
                if dl and dl not in ('КОПИЯ',) and 'Наименование банка' not in dl and 'Подпись банка' not in dl:
                    desc_lines.append(dl)
                j+=1
            fd=' '.join(desc_lines)
            cp=''
            cm=re.search(r'(?:Бенефициар|Плательщик):\s*([^У]+?)(?:УНП:|$)',fd)
            if cm: cp=re.sub(r'\s+',' ',cm.group(1)).strip()[:120]
            is_c='комисси' in fd.lower() or 'ЦЕПТЕР БАНК' in fd or 'ком.возн' in fd.lower()
            is_v='конверсией' in fd.lower() or 'конверсия' in fd.lower()
            txs.append(ZepterPDFTx(seq,doc,date,op,bic,acc,debit,credit,amount,currency,re.sub(r'\s+',' ',fd).strip()[:300],cp,is_c,is_v))
            i=j
        else: i+=1
    return txs, meta

def parse_zepter_rub_pdf(pdf_bytes):
    lines = _pdf_lines(pdf_bytes)
    meta = _zepter_meta(lines)
    currency = meta.get('currency','RUB')
    TX = re.compile(r'^(\d+)\s+(\S+)\s+(\d{2}\.\d{2}\.\d{4})\s+(\d)\s+(?:(\S+)\s+)?([\d\s]+,\d{2})\s+([\d\s]+,\d{2})')
    txs=[]; i=0
    while i<len(lines):
        m=TX.match(lines[i].strip())
        if m:
            seq,doc,date,op=m.group(1),m.group(2),_fdate(m.group(3)),m.group(4)
            bic=m.group(5) or ''
            v1=_amt(m.group(6))
            credit,debit=(v1,0.0) if op=='1' else (0.0,v1)
            amount=credit if credit>0 else -debit
            desc_lines=[]; j=i+1
            while j<len(lines):
                dl=lines[j].strip()
                if TX.match(dl) or 'Итого оборотов' in dl or 'Исходящее сальдо' in dl: break
                if dl and dl not in ('КОПИЯ',) and 'Наименование банка' not in dl: desc_lines.append(dl)
                j+=1
            fd=' '.join(desc_lines)
            cp=''
            cm=re.search(r'(?:Плательщик|Бенефициар):\s*([^У]+?)(?:УНП:|$)',fd)
            if cm: cp=re.sub(r'\s+',' ',cm.group(1)).strip()[:120]
            if not cp:
                vm=re.search(r'OOO\s+\w+|ООО\s+\S+',fd)
                if vm: cp=vm.group(0)
            is_c='ком.вознагр' in fd.lower() or 'ком.возн' in fd.lower() or 'ЦЕПТЕР БАНК' in fd
            is_v='конверсией' in fd.lower() or 'конверсия' in fd.lower()
            txs.append(ZepterPDFTx(seq,doc,date,op,bic,'',debit,credit,amount,currency,re.sub(r'\s+',' ',fd).strip()[:300],cp,is_c,is_v))
            i=j
        else: i+=1
    return txs, meta

def parse_zepter_pdf_auto(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = pdf.pages[0].extract_text() or ''
    return parse_zepter_rub_pdf(pdf_bytes) if 'RUB' in text else parse_zepter_eur_pdf(pdf_bytes)

OP_MAP = {
    'OBC.KWOTĄ WYSYŁ. PRZEL.ZAGRANICZNY':'Foreign transfer',
    'OBC. PROW. OD WYSYŁ. PRZEL. ZAGR':'Commission',
    'PRZELEW PRZYCHODZĄCY':'Incoming transfer',
    'PRZELEW WYCHODZĄCY':'Outgoing transfer',
    'OBCIĄŻENIE OPERACJĄ SKARBOWĄ':'FX debit',
    'UZNANIE OPERACJĄ SKARBOWĄ':'FX credit',
    'SPŁ.NIEAUT.ODS.ZAPADŁYCH NIESPŁAC.':'Interest',
    'OPŁATA MIESIĘCZNA ZA KARTĘ':'Card fee',
    'OPŁATA ZA PROWADZENIE RACHUNKU':'Account fee',
}

def parse_pko_wyciag(pdf_bytes):
    lines = _pdf_lines(pdf_bytes)
    meta = {}
    for line in lines:
        if 'WYCIĄG za okres' in line:
            m=re.search(r'(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})',line)
            if m: meta['date_from']=_fdate(m.group(1)); meta['date_to']=_fdate(m.group(2))
        if 'Waluta rachunku:' in line:
            for cur in ('EUR','PLN','USD'):
                if cur in line: meta['currency']=cur; break
        if 'Nr rachunku/karty:' in line:
            m=re.search(r'Nr rachunku/karty:\s*([\d\s]+)',line)
            if m: meta['account']=m.group(1).strip()
    currency=meta.get('currency','EUR')
    TX=re.compile(r'^(\d{2}\.\d{2}\.\d{4})\s+(\S+)\s+(.+?)\s+(-?[\d\s]+,\d{2})\s+(-?[\d\s]+,\d{2})\s*$')
    txs=[]; i=0
    while i<len(lines):
        m=TX.match(lines[i].strip())
        if m:
            date=_fdate(m.group(1)); tx_id=m.group(2); op_raw=m.group(3).strip()
            amount=_amt(m.group(4))
            op_type=op_raw
            for pl,en in OP_MAP.items():
                if pl in op_raw: op_type=en; break
            j=i+1; desc_lines=[]
            while j<len(lines):
                dl=lines[j].strip()
                if TX.match(dl) or 'Saldo do przeniesienia' in dl or 'Saldo końcowe' in dl: break
                if 'Niniejszy dokument' in dl or 'Powszechna Kasa' in dl: j+=1; continue
                if dl: desc_lines.append(dl)
                j+=1
            fd=' '.join(desc_lines)
            benef=''
            bm=re.search(r'Benef\.:\s*(.+?)(?:Rach\. benef\.|tyt\.|$)',fd)
            if bm: benef=bm.group(1).strip()
            title=''
            tm=re.search(r'tyt\.:\s*(.+?)(?:Kwota oryg|$)',fd)
            if tm: title=tm.group(1).strip()
            if not benef and desc_lines: benef=desc_lines[0][:80]
            is_c=op_type in ('Commission','Account fee','Card fee','Interest')
            is_fx=op_type in ('FX debit','FX credit') or 'FX' in tx_id
            txs.append(PKOWyciagTx(date,tx_id,op_type,amount,currency,benef[:120],title[:200],is_c,is_fx))
            i=j
        else: i+=1
    return txs, meta

# ══════════════════════════════════════════════════════════
# MAIN PAGE
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.header("⚙️ Настройки")
    due_days     = st.number_input("Срок оплаты (дней)", min_value=0, max_value=90, value=7)
    invoice_kind = st.selectbox("Вид документа", ["Invoice","Proforma Invoice","Receipt"])
    filter_type  = st.selectbox("Показать", ["Все","Только поступления (+)","Только списания (-)"])
    skip_comm    = st.checkbox("Скрыть комиссии банка", value=True)
    skip_conv    = st.checkbox("Скрыть конверсию валют", value=True)
    skip_fx      = st.checkbox("Скрыть FX-операции", value=True)
    skip_loans   = st.checkbox("Скрыть займы (LOAN)", value=False)

st.info("📂 Поддерживаемые форматы:\n- **Цептер Банк**: PDF (EUR/RUB) или RTF\n- **PKO Bank Polski**: PDF (WYCIĄG)")

uploaded = st.file_uploader("Загрузите выписки (PDF или RTF)", type=["pdf","rtf","txt"], accept_multiple_files=True)
if not uploaded:
    st.stop()

class UTx:
    def __init__(self,date,doc_num,amount,currency,counterparty,description,is_commission,is_conversion,is_fx,source):
        self.date=date; self.doc_num=doc_num; self.amount=amount; self.currency=currency
        self.counterparty=counterparty; self.description=description
        self.is_commission=is_commission; self.is_conversion=is_conversion
        self.is_fx=is_fx; self.source=source

all_txs=[]
for f in uploaded:
    raw=f.read(); name=f.name.lower()
    try:
        if name.endswith('.rtf') or name.endswith('.txt'):
            txs,meta=parse_zepter_rtf(raw)
            cur=meta.get('currency','EUR'); src=f"Zepter {cur} (RTF)"
            for t in txs:
                all_txs.append(UTx(t.date,t.doc_num,t.amount,t.currency,t.counterparty,t.description,t.is_commission,t.is_conversion,False,src))
        elif name.endswith('.pdf'):
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                first=pdf.pages[0].extract_text() or ''
            if 'ЦЕПТЕР БАНК' in first or 'ZEPTBY2X' in first:
                txs,meta=parse_zepter_pdf_auto(raw)
                cur=meta.get('currency','EUR'); src=f"Zepter {cur} (PDF)"
                for t in txs:
                    all_txs.append(UTx(t.date,t.doc_num,t.amount,t.currency,t.counterparty,t.description,t.is_commission,t.is_conversion,False,src))
            elif 'WYCIĄG' in first or 'Waluta rachunku' in first:
                txs,meta=parse_pko_wyciag(raw)
                cur=meta.get('currency','EUR'); src=f"PKO {cur} (PDF)"
                for t in txs:
                    all_txs.append(UTx(t.date,t.tx_id,t.amount,t.currency,t.beneficiary,t.title,t.is_commission,False,t.is_fx,src))
            else:
                st.warning(f"⚠️ {f.name}: не удалось определить банк"); continue
        st.success(f"✅ {f.name} → **{src}**: {len(txs)} операций · {meta.get('date_from','')} – {meta.get('date_to','')}")
    except Exception as e:
        st.error(f"❌ {f.name}: {e}")
        import traceback; st.code(traceback.format_exc())

if not all_txs:
    st.warning("Транзакции не найдены."); st.stop()

txs=all_txs
if skip_comm:  txs=[t for t in txs if not t.is_commission]
if skip_conv:  txs=[t for t in txs if not t.is_conversion]
if skip_fx:    txs=[t for t in txs if not t.is_fx]
if skip_loans: txs=[t for t in txs if 'LOAN' not in (t.description or '').upper()]
if filter_type=="Только поступления (+)": txs=[t for t in txs if t.amount>0]
elif filter_type=="Только списания (-)":  txs=[t for t in txs if t.amount<0]

if not txs:
    st.warning("После фильтрации нет транзакций."); st.stop()

def find_client(name):
    nl=(name or '').lower()
    for cname in CLIENTS:
        words=[w for w in cname.lower().split() if len(w)>3]
        if any(w in nl for w in words[:3]): return cname
    return ""

def make_due(issue,days):
    try: return (datetime.strptime(issue,"%Y-%m-%d")+timedelta(days=days)).strftime("%Y-%m-%d")
    except: return ""

seller=SELLERS["FMCGOODS OÜ"]
client_list=[""]+list(CLIENTS.keys())

def build_rows(txs,kind,days):
    rows=[]
    for i,t in enumerate(txs,1):
        buyer=find_client(t.counterparty); client=CLIENTS.get(buyer,{})
        amt=abs(t.amount); amt_eur=amt if t.currency=="EUR" else 0.0
        rows.append({
            "No.":i,"No. (invoice)":t.doc_num or f"FMC-{t.date.replace('-','')}-{i:03d}",
            "Kind":kind,"Seller":seller["name"],"Department short name":seller["name"],
            "Seller's TAX ID":seller["tax_id"],"Status":"Paid" if t.amount>0 else "Issued",
            "Issue date":t.date,"Sale date":"","Due date":make_due(t.date,days),
            "Buyer":buyer,"VAT ID":client.get("vat_id",""),"Street":client.get("street",""),
            "Postcode":client.get("postcode",""),"City":client.get("city",""),
            "Country":client.get("country",""),"Client e-mail":client.get("email",""),
            "Client's phone":client.get("phone",""),"Mobile phone":"",
            "Total net price":amt,"TAX":0.0,"Total gross price":amt,
            "Total net price EUR":amt_eur,"TAX EUR":0.0,"Total gross price EUR":amt_eur,
            "Payment type":"Transfer","Payment date":t.date if t.amount>0 else "",
            "Paid":amt if t.amount>0 else 0.0,"Currency":t.currency,
            "PO number":t.doc_num or "","Addressee":"","Category":"","Notes":"",
            "Additional invoice field":"","Original document":"","Reason for the correction":"",
            "Product / Service":(t.description or "")[:200],"Qty":1.0,
            "Unit net price":amt,"Unit gross price":amt,"TAX (position)":"disabled",
            "VAT amount":0.0,"Total net":amt,"Total gross":amt,
            "Position kind":"","Quantity unit":"pc","Additional information":"",
            "_source":t.source,
        })
    return rows

if "fmc_df" not in st.session_state or st.button("🔃 Перезагрузить из выписок", key="reload_fmc"):
    st.session_state.fmc_df=pd.DataFrame(build_rows(txs,invoice_kind,due_days))

st.subheader(f"📊 {len(txs)} операций")
c1,c2,c3,c4=st.columns(4)
c1.metric("Поступления",f"+{sum(t.amount for t in txs if t.amount>0):,.2f}")
c2.metric("Списания",f"{sum(t.amount for t in txs if t.amount<0):,.2f}")
c3.metric("Записей",len(txs))
c4.metric("Источников",len({t.source for t in txs}))

st.subheader("✏️ Редактирование")
st.caption("Выберите **Покупателя ▼** — адрес и VAT заполнятся автоматически.")

display_cols=[c for c in st.session_state.fmc_df.columns if c!="_source"]
col_cfg={
    "No.":st.column_config.NumberColumn("№",width="small",disabled=True),
    "No. (invoice)":st.column_config.TextColumn("Номер счёта",width="medium"),
    "Kind":st.column_config.SelectboxColumn("Вид",options=["Invoice","Proforma Invoice","Receipt"],width="small"),
    "Seller":st.column_config.TextColumn("Продавец",width="medium"),
    "Department short name":st.column_config.TextColumn("Отдел",width="small"),
    "Seller's TAX ID":st.column_config.TextColumn("TAX ID",width="small"),
    "Status":st.column_config.SelectboxColumn("Статус",options=["Paid","Partially paid","Issued","Rejected"],width="small"),
    "Issue date":st.column_config.TextColumn("Дата",width="small"),
    "Sale date":st.column_config.TextColumn("Дата продажи",width="small"),
    "Due date":st.column_config.TextColumn("Срок оплаты",width="small"),
    "Buyer":st.column_config.SelectboxColumn("Покупатель ▼",options=client_list,width="large"),
    "VAT ID":st.column_config.TextColumn("VAT ID",width="medium"),
    "Street":st.column_config.TextColumn("Улица",width="medium"),
    "Postcode":st.column_config.TextColumn("Индекс",width="small"),
    "City":st.column_config.TextColumn("Город",width="small"),
    "Country":st.column_config.TextColumn("Страна",width="small"),
    "Client e-mail":st.column_config.TextColumn("Email",width="medium"),
    "Client's phone":st.column_config.TextColumn("Телефон",width="small"),
    "Total net price":st.column_config.NumberColumn("Нетто",format="%.2f",width="medium"),
    "TAX":st.column_config.NumberColumn("НДС",format="%.2f",width="small"),
    "Total gross price":st.column_config.NumberColumn("Брутто",format="%.2f",width="medium"),
    "Total net price EUR":st.column_config.NumberColumn("Нетто EUR",format="%.2f",width="medium"),
    "TAX EUR":st.column_config.NumberColumn("НДС EUR",format="%.2f",width="small"),
    "Total gross price EUR":st.column_config.NumberColumn("Брутто EUR",format="%.2f",width="medium"),
    "Payment type":st.column_config.SelectboxColumn("Оплата",options=["Transfer","Cash","Card"],width="small"),
    "Payment date":st.column_config.TextColumn("Дата оплаты",width="small"),
    "Paid":st.column_config.NumberColumn("Оплачено",format="%.2f",width="medium"),
    "Currency":st.column_config.SelectboxColumn("Валюта",options=["EUR","RUB","PLN","USD"],width="small"),
    "PO number":st.column_config.TextColumn("PO",width="medium"),
    "Product / Service":st.column_config.TextColumn("Товар / Услуга",width="large"),
    "Qty":st.column_config.NumberColumn("Кол-во",format="%.2f",width="small"),
    "Unit net price":st.column_config.NumberColumn("Цена нетто",format="%.2f",width="medium"),
    "Unit gross price":st.column_config.NumberColumn("Цена брутто",format="%.2f",width="medium"),
    "TAX (position)":st.column_config.TextColumn("НДС поз.",width="small"),
    "VAT amount":st.column_config.NumberColumn("Сумма НДС",format="%.2f",width="small"),
    "Total net":st.column_config.NumberColumn("Итого нетто",format="%.2f",width="medium"),
    "Total gross":st.column_config.NumberColumn("Итого брутто",format="%.2f",width="medium"),
    "Quantity unit":st.column_config.SelectboxColumn("Ед. изм.",options=["cases","pc","kg","l","pcs"],width="small"),
    "Additional information":st.column_config.TextColumn("Доп. инфо",width="medium"),
}

edited=st.data_editor(st.session_state.fmc_df[display_cols],column_config=col_cfg,
    use_container_width=True,num_rows="dynamic",hide_index=True,key="fmc_editor")

changed=False
old_df=st.session_state.fmc_df.reset_index(drop=True)
edited=edited.reset_index(drop=True)
for idx in edited.index:
    try:
        buyer_new=str(edited.at[idx,"Buyer"] or "")
        buyer_old=str(old_df.at[idx,"Buyer"] if idx in old_df.index else "")
        if buyer_new!=buyer_old and buyer_new in CLIENTS:
            c=CLIENTS[buyer_new]
            for col,key in [("VAT ID","vat_id"),("Street","street"),("Postcode","postcode"),
                            ("City","city"),("Country","country"),("Client e-mail","email"),("Client's phone","phone")]:
                edited.at[idx,col]=c.get(key,"")
            changed=True
    except (KeyError, IndexError):
        pass

merged=edited.copy()
if "_source" in old_df.columns:
    src_vals=old_df["_source"].values
    merged["_source"]=list(src_vals[:len(merged)])+[""]*(max(0,len(merged)-len(src_vals)))

if changed:
    st.session_state.fmc_df=merged; st.rerun()
else:
    st.session_state.fmc_df=merged

st.divider()
st.subheader("📥 Экспорт")
if st.button("🔄 Сгенерировать CSV для InvoiceOcean",type="primary",use_container_width=True):
    final_cols=["No.","No.","Kind","Seller","Department short name","Seller's TAX ID","Status",
        "Issue date","Sale date","Due date","Buyer","VAT ID","Street","Postcode","City","Country",
        "Client e-mail","Client's phone","Mobile phone","Total net price","TAX","Total gross price",
        "Total net price EUR","TAX EUR","Total gross price EUR","Payment type","Payment date","Paid",
        "Currency","PO number","Addressee","Category","Notes","Additional invoice field ",
        "Original document","Reason for the correction","Product / Service","Qty",
        "Unit net price","Unit gross price","TAX","VAT amount","Total net","Total gross",
        "Position kind","Quantity unit","Additional information field"]
    import csv
    out_rows=[]
    for _,row in st.session_state.fmc_df.iterrows():
        amt=float(row.get("Total gross price",0) or 0)
        amt_eur=float(row.get("Total gross price EUR",0) or 0)
        out_rows.append([int(row.get("No.",0)),str(row.get("No. (invoice)","")),
            str(row.get("Kind","Invoice")),str(row.get("Seller","")),str(row.get("Department short name","")),
            str(row.get("Seller's TAX ID","")),str(row.get("Status","Issued")),str(row.get("Issue date","")),
            str(row.get("Sale date","")),str(row.get("Due date","")),str(row.get("Buyer","")),
            str(row.get("VAT ID","")),str(row.get("Street","")),str(row.get("Postcode","")),
            str(row.get("City","")),str(row.get("Country","")),str(row.get("Client e-mail","")),
            str(row.get("Client's phone","")),"",
            amt,0.0,amt,amt_eur,0.0,amt_eur,
            str(row.get("Payment type","Transfer")),str(row.get("Payment date","")),
            float(row.get("Paid",0) or 0),str(row.get("Currency","EUR")),str(row.get("PO number","")),
            "","","","","","",str(row.get("Product / Service","")),
            float(row.get("Qty",1) or 1),amt,amt,"disabled",0.0,amt,amt,
            "",str(row.get("Quantity unit","pc")),""])
    buf=io.StringIO(); w=csv.writer(buf); w.writerow(final_cols); w.writerows(out_rows)
    csv_bytes=("\ufeff"+buf.getvalue()).encode("utf-8")
    filename=f"InvoiceOcean_FMCGOODS_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    st.download_button(f"⬇️ Скачать {filename}",csv_bytes,filename,"text/csv",use_container_width=True)
    st.success(f"✅ {len(out_rows)} строк экспортировано.")

st.caption("📌 InvoiceOcean: Settings → Import → New Import → выбрать CSV")
