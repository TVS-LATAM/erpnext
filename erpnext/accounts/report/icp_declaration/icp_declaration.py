# icp_declaration.py
# ICP Declaration – Belastingdienst Compliant (2025-09)
# Requisitos clave: agrupación por VAT válido, separación bienes/servicios/transferencias/ABC,
# importes NETOS en EUR, periodicidad según umbral €50.000, manejo XI (NI),
# validación VIES (opcional), conciliación opcional con casilla 3b y exportación (CSV/XBRL esqueleto).

import frappe
from frappe import _
import re
from datetime import datetime, date
from collections import defaultdict

# -----------------------------
# API PÚBLICA DEL REPORTE
# -----------------------------

def execute(filters=None):
    if not filters:
        filters = {}

    validate_filters(filters)

    # Determinar periodicidad forzada por normativa (solo para bienes)
    enforced_freq = determine_icp_frequency(filters)
    if enforced_freq and filters.get("frequency"):
        ui_freq = (filters.get("frequency") or "").strip().lower()
        if enforced_freq == "monthly" and ui_freq != "monthly":
            frappe.throw(
                _("Periodicity must be Monthly because intra-EU supplies of goods exceed €50,000 in the quarter.")
            )

    columns = get_columns()
    rows = fetch_icp_rows_line_level(filters)               # Trae nivel línea con clasificación
    data_eur = aggregate_to_icp_output(rows, filters)       # Convierte a EUR y agrega por (VAT, Tipo)
    validated_data = validate_icp_data(data_eur, filters)   # Válida formato VAT, XI, umbrales, etc.

    # Conciliación opcional con 3b (según flags disponibles)
    try_reconcile_3b(validated_data, filters)

    return columns, validated_data

# -----------------------------
# VALIDACIONES DE ENTRADA
# -----------------------------

def validate_filters(filters):
    if not filters.get("company"):
        frappe.throw(_("Company is mandatory for ICP declaration"))

    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("Date range is mandatory for ICP declaration"))

    # Solo permitir Monthly/Quarterly; Yearly solo con permiso
    freq = (filters.get("frequency") or "").strip().lower()
    if freq not in ("monthly", "quarterly", "yearly", ""):
        frappe.throw(_("Frequency must be Monthly, Quarterly, or Yearly (with permit)."))

    if freq == "yearly" and not has_icp_annual_permit(filters.get("company")):
        frappe.throw(_("Yearly ICP is only allowed with an explicit permit on the Company."))

    # Aviso si el rango supera un trimestre (el ICP normalmente es mensual/trimestral)
    from_date = datetime.strptime(filters.get("from_date"), "%Y-%m-%d")
    to_date = datetime.strptime(filters.get("to_date"), "%Y-%m-%d")
    if (to_date - from_date).days > 92 and freq != "yearly":
        frappe.msgprint(
            _("Warning: ICP declarations are typically Monthly or Quarterly. Consider using those date ranges.")
        )

def has_icp_annual_permit(company):
    # Revisa un campo custom en Company: "icp_annual_permit" (Check) -> 1/0
    try:
        return bool(frappe.db.get_value("Company", company, "icp_annual_permit") or 0)
    except Exception:
        return False

# -----------------------------
# OBTENCIÓN DE DATOS (NIVEL LÍNEA)
# -----------------------------

def fetch_icp_rows_line_level(filters):
    """
    Trae líneas de facturas de venta con campos necesarios para:
    - distinguir bienes/servicios (via Item.is_stock_item)
    - detectar transferencias / call-off / ABC (por plantilla/impuesto/flags)
    - convertir a EUR (con base en moneda de compañía -> EUR)
    """
    company = filters.get("company")
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    # Moneda de la compañía
    company_currency = frappe.db.get_value("Company", company, "default_currency") or "EUR"

    # Nota: usamos base_* amounts (moneda de compañía). Si company_currency != EUR, luego convertimos a EUR.
    # Se selecciona por línea e incluye campos de item y plantillas para clasificar el tipo ICP.
    query = """
        SELECT
            si.name                      AS si_name,
            si.posting_date              AS posting_date,
            si.customer_name             AS customer_name,
            si.customer                  AS customer_code,
            si.tax_id                    AS vat_number,
            UPPER(LEFT(REPLACE(REPLACE(REPLACE(si.tax_id, ' ', ''), '-', ''), '.', ''), 2)) AS country_code,
            si.is_return                 AS is_return,
            si.company                   AS company,
            si.currency                  AS doc_currency,
            si.conversion_rate           AS doc_to_company_rate,
            sii.item_code                AS item_code,
            sii.item_name                AS item_name,
            sii.base_net_amount          AS base_net_amount,   -- neto sin IVA (moneda compañía)
            sii.item_tax_template        AS item_tax_template,
            si.taxes_and_charges         AS taxes_and_charges
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE
            si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.docstatus = 1
            AND si.company = %(company)s
            AND COALESCE(si.tax_id, '') != ''
            AND LENGTH(TRIM(si.tax_id)) >= 8
            -- Excluir NL en ICP
            AND UPPER(LEFT(REPLACE(REPLACE(REPLACE(si.tax_id, ' ', ''), '-', ''), '.', ''), 2)) <> 'NL'
            -- Solo clientes UE (se refina luego validando EU + XI)
            AND (
                LOWER(si.tax_category) IN ('eu customer', 'eu b2b', 'intra-eu supply')
                OR LOWER(c.tax_category) IN ('eu customer', 'eu b2b', 'intra-eu supply')
                OR 1=1  -- permitimos y validamos luego por país del VAT
            )
    """

    rows = frappe.db.sql(query, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)

    # Enriquecer con banderas de item (stock/servicio) sin romper si falta el item
    if rows:
        item_codes = list({r["item_code"] for r in rows if r.get("item_code")})
        if item_codes:
            # Cargar flags de item en un dict
            items = {
                d["name"]: d for d in frappe.get_all(
                    "Item",
                    fields=["name", "is_stock_item", "is_fixed_asset"],
                    filters={"name": ["in", item_codes]}
                )
            }
        else:
            items = {}

        for r in rows:
            it = items.get(r.get("item_code")) or {}
            r["is_stock_item"] = int(it.get("is_stock_item") or 0)
            r["is_fixed_asset"] = int(it.get("is_fixed_asset") or 0)

            # Clasificación preliminar del tipo ICP por línea
            r["icp_type"] = classify_icp_type(r)

            # Ajuste de signo si es devolución
            if int(r.get("is_return") or 0) == 1:
                r["base_net_amount"] = -1 * float(r.get("base_net_amount") or 0)

            # Añadir moneda compañía y bandera si requiere conversión a EUR
            r["company_currency"] = company_currency

    return rows or []

def classify_icp_type(row):
    """
    Determina el tipo ICP de la línea:
    - GOODS: item de stock (is_stock_item=1) no marcado como transferencia
    - SERVICES: item no stock
    - TRANSFER: detección por palabras clave en plantillas/impuestos (call-off/transfer)
    - ABC: detección por plantilla que contenga 'ABC'
    La detección de TRANSFER/ABC es heurística y puede perfeccionarse vía campos/plantillas dedicadas.
    """
    # ABC (triangular)
    for key in ("item_tax_template", "taxes_and_charges"):
        val = (row.get(key) or "").lower()
        if "abc" in val:
            return "ABC"

    # Transferencia / call-off stock (overbrengen)
    for key in ("item_tax_template", "taxes_and_charges"):
        val = (row.get(key) or "").lower()
        if "call-off" in val or "call off" in val or "transfer" in val or "overbreng" in val:
            return "TRANSFER"

    # Bienes vs servicios
    if int(row.get("is_stock_item") or 0) == 1:
        return "GOODS"
    else:
        return "SERVICES"

# -----------------------------
# CONVERSIÓN A EUR + AGREGACIÓN
# -----------------------------

def get_company_to_eur_rate(company_currency, on_date):
    """
    Devuelve tasa compañía->EUR a la fecha (usa tabCurrency Exchange).
    Si company_currency == EUR, devuelve 1.0
    """
    if (company_currency or "").upper() == "EUR":
        return 1.0

    # Buscar tasa más reciente <= on_date
    rate = frappe.db.sql(
        """
        SELECT exchange_rate
        FROM `tabCurrency Exchange`
        WHERE from_currency = %s AND to_currency = 'EUR' AND date <= %s
        ORDER BY date DESC
        LIMIT 1
        """,
        (company_currency, on_date),
    )
    if rate and rate[0][0]:
        return float(rate[0][0])

    # Intentar inversa (EUR -> company_currency)
    inv = frappe.db.sql(
        """
        SELECT exchange_rate
        FROM `tabCurrency Exchange`
        WHERE from_currency = 'EUR' AND to_currency = %s AND date <= %s
        ORDER BY date DESC
        LIMIT 1
        """,
        (company_currency, on_date),
    )
    if inv and inv[0][0]:
        inv_rate = float(inv[0][0])
        if inv_rate != 0:
            return 1.0 / inv_rate

    frappe.msgprint(
        _("No EUR exchange rate found for {0} on or before {1}. Amounts may be inaccurate.")
        .format(company_currency, on_date)
    )
    return 1.0  # fallback

def aggregate_to_icp_output(rows, filters):
    """
    Agrega por (VAT, CountryCode, ICP Type) y convierte a EUR.
    Devuelve lista de dicts ya listos para grilla/export.
    """
    out = defaultdict(lambda: {"Net Amount": 0.0, "Transaction Count": 0, "Invoice Numbers": set(), "Doc Dates": set()})
    for r in rows:
        vat = (r.get("vat_number") or "").strip()
        cc = (r.get("country_code") or "").strip()
        icp_type = r.get("icp_type") or "GOODS"
        key = (vat, cc, icp_type)

        # Convertir a EUR desde moneda de compañía
        company_currency = r.get("company_currency") or "EUR"
        rate = get_company_to_eur_rate(company_currency, r.get("posting_date"))
        amount_eur = round(float(r.get("base_net_amount") or 0) * float(rate), 2)

        out[key]["Net Amount"] += amount_eur
        out[key]["Transaction Count"] += 1
        out[key]["Invoice Numbers"].add(r.get("si_name"))
        out[key]["Doc Dates"].add(str(r.get("posting_date")))

        # Guardar metadata representativa
        out[key]["Customer Name"] = r.get("customer_name")
        out[key]["Customer Code"] = r.get("customer_code")
        out[key]["VAT Identification Number"] = vat
        out[key]["Country Code"] = cc
        out[key]["ICP Type"] = icp_type

    # construir filas
    rows_out = []
    for (vat, cc, icp_type), agg in out.items():
        rows_out.append({
            "Customer Name": agg.get("Customer Name"),
            "Customer Code": agg.get("Customer Code"),
            "VAT Identification Number": vat,
            "Country Code": cc,
            "ICP Type": icp_type,                              # Bienes/Servicios/Transfer/ABC
            "Net Amount": round(agg["Net Amount"], 2),         # EUR
            "Transaction Count": agg["Transaction Count"],
            "Invoice Numbers": ", ".join(sorted(agg["Invoice Numbers"])),
        })

    # Umbral mínimo de €1 por agregación (mantener limpieza)
    rows_out = [r for r in rows_out if abs(float(r.get("Net Amount") or 0)) >= 1.0]

    # Orden recomendado: País, VAT, Tipo
    rows_out.sort(key=lambda x: (x.get("Country Code") or "", x.get("VAT Identification Number") or "", x.get("ICP Type") or ""))
    return rows_out

# -----------------------------
# VALIDACIÓN DE SALIDA
# -----------------------------

def validate_icp_data(data, filters):
    validated_data = []
    errors = []

    for row in data:
        vat_number = row.get("VAT Identification Number", "")
        country_code = row.get("Country Code", "")
        icp_type = row.get("ICP Type", "GOODS")
        net_amount = float(row.get("Net Amount") or 0)

        # Validación de país UE (incluye XI)
        if not is_eu_country(country_code):
            errors.append(f"Non-EU/XI country code: {country_code} for VAT {vat_number}")
            continue

        # Formato VAT (incluye XI)
        if not validate_eu_vat_number(vat_number, country_code):
            errors.append(f"Invalid VAT format: {vat_number} ({country_code})")
            continue

        # Para XI (Irlanda del Norte) solo bienes (regla Brexit); si es servicio, avisar
        if country_code == "XI" and icp_type != "GOODS":
            errors.append(f"XI (Northern Ireland) is only for goods in ICP. VAT {vat_number} type {icp_type}.")
            continue

        # Redondeo final a 2 decimales
        row["Net Amount"] = round(net_amount, 2)

        validated_data.append(row)

    if errors:
        error_log = "ICP Validation Errors:\n" + "\n".join(errors)
        frappe.log_error(error_log, "ICP Declaration Validation")
        frappe.msgprint(_(f"Found {len(errors)} validation errors. Check Error Log for details."))

    return validated_data

# Patrones VAT por país, incluyendo XI (NI)
def validate_eu_vat_number(vat_number, country_code):
    if not vat_number or not country_code:
        return False
    clean_vat = re.sub(r'[^A-Z0-9]', '', vat_number.upper())

    vat_patterns = {
        'AT': r'^ATU[0-9]{8}$|^U[0-9]{8}$',
        'BE': r'^[0-9]{10}$',
        'BG': r'^[0-9]{9,10}$',
        'CY': r'^[0-9]{8}[A-Z]$',
        'CZ': r'^[0-9]{8,10}$',
        'DE': r'^[0-9]{9}$',
        'DK': r'^[0-9]{8}$',
        'EE': r'^[0-9]{9}$',
        'EL': r'^[0-9]{9}$',
        'ES': r'^[A-Z0-9][0-9]{7}[A-Z0-9]$',
        'FI': r'^[0-9]{8}$',
        'FR': r'^[A-Z0-9]{2}[0-9]{9}$',
        'HR': r'^[0-9]{11}$',
        'HU': r'^[0-9]{8}$',
        'IE': r'^[0-9][A-Z0-9\+\*][0-9]{5}[A-Z]$|^[0-9]{7}[A-Z]{1,2}$',
        'IT': r'^[0-9]{11}$',
        'LT': r'^([0-9]{9}|[0-9]{12})$',
        'LU': r'^[0-9]{8}$',
        'LV': r'^[0-9]{11}$',
        'MT': r'^[0-9]{8}$',
        'PL': r'^[0-9]{10}$',
        'PT': r'^[0-9]{9}$',
        'RO': r'^[0-9]{2,10}$',
        'SE': r'^[0-9]{12}$',
        'SI': r'^[0-9]{8}$',
        'SK': r'^[0-9]{10}$',
        # XI (Northern Ireland) – formatos tipo GB (9 ó 12 dígitos) con prefijo XI en el sistema
        'XI': r'^[0-9]{9}$|^[0-9]{12}$',
    }

    pattern = vat_patterns.get(country_code)
    if not pattern:
        return False
    return bool(re.match(pattern, clean_vat))

def is_eu_country(country_code):
    eu = {
        'AT','BE','BG','CY','CZ','DE','DK','EE','EL','ES',
        'FI','FR','HR','HU','IE','IT','LT','LU','LV','MT',
        'PL','PT','RO','SE','SI','SK','XI'  # XI incluido para bienes
    }
    return (country_code or "").upper() in eu

# -----------------------------
# PERIODICIDAD SEGÚN UMBRAL
# -----------------------------

def determine_icp_frequency(filters):
    """
    Devuelve 'monthly' si el total de bienes en el trimestre del rango excede €50.000 (EUR).
    En otro caso None (respetar selección UI).
    """
    # Identificar trimestre del from_date
    from_date = datetime.strptime(filters.get("from_date"), "%Y-%m-%d").date()
    year = from_date.year
    q_ranges = [
        (date(year,1,1),  date(year,3,31)),
        (date(year,4,1),  date(year,6,30)),
        (date(year,7,1),  date(year,9,30)),
        (date(year,10,1), date(year,12,31)),
    ]
    q_start = q_end = None
    for qs, qe in q_ranges:
        if qs <= from_date <= qe:
            q_start, q_end = qs, qe
            break
    if not q_start:
        return None

    # Traer líneas del trimestre completo (no solo del rango seleccionado)
    tmp_filters = dict(filters)
    tmp_filters["from_date"] = q_start.strftime("%Y-%m-%d")
    tmp_filters["to_date"] = q_end.strftime("%Y-%m-%d")
    rows = fetch_icp_rows_line_level(tmp_filters)

    # Sumar solo GOODS en EUR
    total_goods_eur = 0.0
    for r in rows:
        if classify_icp_type(r) != "GOODS":
            continue
        cc = r.get("company_currency") or "EUR"
        rate = get_company_to_eur_rate(cc, r.get("posting_date"))
        total_goods_eur += float(r.get("base_net_amount") or 0) * float(rate)

    if abs(total_goods_eur) > 50000.0:
        return "monthly"
    return None

# -----------------------------
# CONCILIACIÓN CON 3B (OPCIONAL, ROBUSTO)
# -----------------------------

def _is_field_present(doctype, fieldname):
    try:
        meta = frappe.get_meta(doctype)
        return any(df.fieldname == fieldname for df in meta.fields)
    except Exception:
        return False

def _get_enforce_match_flag():
    """
    Obtiene flag para forzar conciliación ICP=3b de forma robusta:
    1) Si existe el campo 'enforce_icp_matches_vat_3b' en 'Accounts Settings', lo usa.
    2) Si existe Single 'ICP Settings' con el mismo campo, lo usa.
    3) Si nada existe, retorna 0 (desactivado).
    """
    try:
        if _is_field_present("Accounts Settings", "enforce_icp_matches_vat_3b"):
            val = frappe.db.get_single_value("Accounts Settings", "enforce_icp_matches_vat_3b") or 0
            return int(val)
    except Exception:
        pass

    try:
        if frappe.db.exists("DocType", "ICP Settings"):
            val = frappe.db.get_single_value("ICP Settings", "enforce_icp_matches_vat_3b") or 0
            return int(val)
    except Exception:
        pass

    return 0

def try_reconcile_3b(data, filters):
    """
    Conciliación opcional con casilla 3b.
    Si el flag no existe en tu instancia, la función se salta sin error.
    """
    enforce = _get_enforce_match_flag()
    if not int(enforce):
        return

    total_icp = sum(float(r.get("Net Amount") or 0) for r in data)

    # Ejemplo (stub): leer un valor 3b guardado en un DocType custom "NL VAT Control"
    try:
        control = frappe.db.sql(
            """
            SELECT total_3b_eur
            FROM `tabNL VAT Control`
            WHERE company=%s AND from_date=%s AND to_date=%s
            LIMIT 1
            """,
            (filters.get("company"), filters.get("from_date"), filters.get("to_date")),
            as_dict=True,
        )
        if control:
            total_3b = float(control[0]["total_3b_eur"] or 0)
            if round(total_icp, 2) != round(total_3b, 2):
                frappe.throw(_("ICP total ({0}) does not match VAT 3b total ({1}) for the same period.")
                             .format(round(total_icp,2), round(total_3b,2)))
        # Si no hay control, no bloqueamos.
    except Exception:
        # Si no existe el DocType o hay error, no bloquee.
        pass

# -----------------------------
# COLUMNAS DEL REPORTE
# -----------------------------

def get_columns():
    return [
        {"fieldname": "Customer Name",            "label": _("Customer Name"),             "fieldtype": "Data",     "width": 200},
        {"fieldname": "Customer Code",            "label": _("Customer Code"),             "fieldtype": "Link",     "options": "Customer", "width": 120},
        {"fieldname": "VAT Identification Number","label": _("VAT Identification Number"), "fieldtype": "Data",     "width": 180},
        {"fieldname": "Country Code",             "label": _("Country Code"),              "fieldtype": "Data",     "width": 80},
        {"fieldname": "ICP Type",                 "label": _("ICP Type (Goods/Services/Transfer/ABC)"), "fieldtype": "Data", "width": 180},
        {"fieldname": "Net Amount",               "label": _("Net Amount (EUR)"),          "fieldtype": "Currency", "width": 140},
        {"fieldname": "Transaction Count",        "label": _("Transaction Count"),         "fieldtype": "Int",      "width": 90},
        {"fieldname": "Invoice Numbers",          "label": _("Invoice Numbers"),           "fieldtype": "Small Text","width": 220},
    ]

# -----------------------------
# EXPORTACIONES
# -----------------------------

@frappe.whitelist()
def export_to_belastingdienst_format(data, filters, fmt="CSV"):
    """
    Exportación a formato compatible:
    - CSV: columnas: CountryCode, VATNumber, ICPType, AmountEUR
    - XBRL: esqueleto (preparar instancia XBRL conforme a taxonomía vigente)
    Retorna dict con {file_name, file_content, mime_type}
    """
    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    if isinstance(data, str):
        data = frappe.parse_json(data)

    company = filters.get("company")
    period_label = f"{filters.get('from_date')}__{filters.get('to_date')}"

    if fmt.upper() == "CSV":
        header = ["CountryCode", "VATNumber", "ICPType", "AmountEUR"]
        lines = [",".join(header)]
        for r in data:
            cc = r.get("Country Code") or ""
            vat = re.sub(r'[^A-Z0-9]', '', (r.get("VAT Identification Number") or "").upper())
            t  = r.get("ICP Type") or "GOODS"
            amt= "{:.2f}".format(float(r.get("Net Amount") or 0))
            # Regla XI: solo bienes; si llegan servicios, ya fue validado y excluido
            lines.append(",".join([cc, vat, t, amt]))

        content = "\n".join(lines)
        return {
            "file_name": f"ICP_{company}_{period_label}.csv",
            "file_content": content,
            "mime_type": "text/csv; charset=utf-8"
        }

    elif fmt.upper() == "XBRL":
        # Esqueleto mínimo. Debe mapear a la taxonomía NL vigente (actualizar namespaces/nóminas).
        # Aquí solo devolvemos un placeholder para no romper.
        xbrl = f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance">
    <!-- TODO: construir instancia conforme a entrypoint ICP/SBR actual -->
    <context id="PERIOD">
        <entity>
            <identifier scheme="NL:KVK">{frappe.db.get_value("Company", company, "company_number") or company}</identifier>
        </entity>
        <period>
            <startDate>{filters.get('from_date')}</startDate>
            <endDate>{filters.get('to_date')}</endDate>
        </period>
    </context>
    <!-- TODO: crear items por contrapartida (VAT, tipo, importe) -->
</xbrli:xbrl>
"""
        return {
            "file_name": f"ICP_{company}_{period_label}.xbrl",
            "file_content": xbrl,
            "mime_type": "application/xml"
        }

    else:
        frappe.throw(_("Unsupported export format: {0}").format(fmt))

# -----------------------------
# ENDPOINTS / UTILIDADES
# -----------------------------

@frappe.whitelist()
def generate_icp_report(filters):
    """
    Endpoint para UI: genera data + resumen + quarter si aplica.
    """
    try:
        if isinstance(filters, str):
            filters = frappe.parse_json(filters)

        columns, data = execute(filters)
        summary = get_icp_summary(data)
        quarter = validate_quarterly_submission(filters)

        return {
            "success": True,
            "columns": columns,
            "data": data,
            "summary": summary,
            "quarter": quarter,
            "message": _(f"ICP declaration generated successfully. {len(data)} records found.")
        }
    except Exception as e:
        frappe.log_error(f"ICP Declaration Error: {str(e)}", "ICP Report Generation")
        return {
            "success": False,
            "error": str(e),
            "message": _("Error generating ICP declaration. Check error log for details.")
        }

@frappe.whitelist()
def get_icp_config(company, from_date=None, to_date=None):
    """
    Apoyo para la UI: si hay permiso anual, y si por umbral corresponde mensual.
    """
    allow_yearly = has_icp_annual_permit(company)
    freq_forced = None
    if from_date and to_date:
        freq_forced = determine_icp_frequency({"company": company, "from_date": from_date, "to_date": to_date})
    return {
        "allow_yearly": int(allow_yearly),
        "forced_frequency": freq_forced  # "monthly" o None
    }

# Sumario simple
def get_icp_summary(data):
    if not data:
        return {}
    return {
        "total_counterparties": len(set((r["VAT Identification Number"], r["ICP Type"]) for r in data)),
        "total_transactions": sum(r.get("Transaction Count", 0) for r in data),
        "total_net_amount_eur": round(sum(float(r.get("Net Amount") or 0) for r in data), 2),
        "countries_count": len(set(r["Country Code"] for r in data)),
    }

def validate_quarterly_submission(filters):
    from_date = datetime.strptime(filters.get("from_date"), "%Y-%m-%d")
    to_date = datetime.strptime(filters.get("to_date"), "%Y-%m-%d")
    year = from_date.year
    quarters = {
        1: (datetime(year, 1, 1), datetime(year, 3, 31)),
        2: (datetime(year, 4, 1), datetime(year, 6, 30)),
        3: (datetime(year, 7, 1), datetime(year, 9, 30)),
        4: (datetime(year, 10, 1), datetime(year, 12, 31))
    }
    for q, (qs, qe) in quarters.items():
        if from_date.date() == qs.date() and to_date.date() == qe.date():
            return q
    return None

# -----------------------------
# (OPCIONAL) VIES – ESQUELETO
# -----------------------------

def vies_check(vat_country_code, vat_number_no_cc):
    """
    Esqueleto de consulta VIES. En producción, implementar llamada SOAP a checkVatService
    y registrar requestIdentifier en log/auditoría.
    """
    # Aquí sólo devolvemos True como placeholder; implementar según necesidad.
    return True
