# vat_declaration.py – Declaración de IVA compatible con Belastingdienst (2025-09)
# Fix: parametrización de patrones LIKE para evitar ValueError por '%v' en PyMySQL

import frappe
from frappe import _
from frappe.utils import getdate, flt
from datetime import timedelta, date

EU_COUNTRIES = [
    'Austria', 'Belgium', 'Bulgaria', 'Croatia', 'Cyprus', 'Czech Republic',
    'Denmark', 'Estonia', 'Finland', 'France', 'Germany', 'Greece',
    'Hungary', 'Ireland', 'Italy', 'Latvia', 'Lithuania', 'Luxembourg',
    'Malta', 'Netherlands', 'Poland', 'Portugal', 'Romania', 'Slovakia',
    'Slovenia', 'Spain', 'Sweden'
]

EXPORT_INCOTERMS = ['EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP']

def execute(filters=None):
    if not filters:
        filters = {}

    today = date.today()
    first_day_current = date(today.year, today.month, 1)
    last_day_last_month = first_day_current - timedelta(days=1)
    first_day_last_month = date(last_day_last_month.year, last_day_last_month.month, 1)

    from_date = filters.get("from_date") or first_day_last_month.strftime('%Y-%m-%d')
    to_date = filters.get("to_date") or last_day_last_month.strftime('%Y-%m-%d')

    filters.update({
        "from_date": from_date,
        "to_date": to_date,
        "from_date_str": getdate(from_date).strftime('%d-%m-%Y'),
        "to_date_str": getdate(to_date).strftime('%d-%m-%Y'),
        "due_date": (getdate(to_date) + timedelta(days=30)).strftime('%d-%m-%Y'),
    })

    columns = get_columns()
    data = build_report_data(filters)
    validate_data_integrity(filters)

    return columns, data


def build_report_data(filters):
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")

    # Estructura por rúbrica (net y vat)
    R = {
        "1a": {"net": 0.0, "vat": 0.0},
        "1b": {"net": 0.0, "vat": 0.0},
        "1c": {"net": 0.0, "vat": 0.0},
        "1d": {"net": 0.0, "vat": 0.0},
        "1e": {"net": 0.0, "vat": 0.0},
        "2a": {"net": 0.0, "vat": 0.0},
        "3a": {"net": 0.0, "vat": 0.0},
        "3b": {"net": 0.0, "vat": 0.0},
        "3c": {"net": 0.0, "vat": 0.0},
        "4a": {"net": 0.0, "vat": 0.0},
        "4b": {"net": 0.0, "vat": 0.0},
    }

    issues = []

    # === VENTAS ===
    sales = frappe.db.sql("""
        SELECT
            si.name,
            si.posting_date,
            si.company,
            LOWER(TRIM(si.tax_category)) as tax_category,
            UPPER(TRIM(si.incoterm)) as incoterm,
            si.base_net_total as net_total,
            addr.country as country,
            SUM(CASE
                    WHEN acc.account_type='Tax'
                     AND LOWER(acc.account_name) LIKE %(vat)s
                 THEN stc.base_tax_amount ELSE 0
                END) as vat_total,
            MAX(CASE WHEN acc.account_type='Tax' THEN stc.rate ELSE NULL END) as any_rate
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc
            ON stc.parent = si.name AND stc.parenttype='Sales Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = stc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(from)s AND %(to)s
          AND (%(company)s = '' OR si.company = %(company)s)
        GROUP BY si.name
        ORDER BY si.posting_date, si.name
    """, {"from": from_date, "to": to_date, "company": company, "vat": "%vat%"}, as_dict=True)

    for row in sales:
        net = flt(row.net_total)
        vat = flt(row.vat_total)
        country = (row.country or "").strip()
        rate = flt(row.any_rate or 0)

        # Clasificación por país
        if country == "Netherlands":
            customer_type = "domestic"
        elif not country:
            customer_type = "unknown"
        elif country in EU_COUNTRIES:
            customer_type = "eu"
        else:
            customer_type = "export"

        # Determinar rúbrica en base a impuestos + país
        rubric = None
        if vat > 0:
            if 20 <= rate <= 22:
                rubric = "1a"
            elif 8 <= rate <= 10:
                rubric = "1b"
            else:
                rubric = "1c"
            if customer_type in ("eu", "export"):
                issues.append(_(f"Factura {row.name}: país {country or 'NULL'} no doméstico pero se cobró VAT NL. Revise ICP/Export."))
        else:
            if customer_type == "domestic":
                if (row.tax_category or "").find("verlegd") >= 0:
                    rubric = "2a"
                else:
                    rubric = "1e"
            elif customer_type == "eu":
                rubric = "3b"
            elif customer_type == "export":
                rubric = "3a"
            else:
                issues.append(_(f"Factura {row.name}: país NULL. Complete dirección/país; no se clasifica como 3a automáticamente."))
                rubric = "1e"

        if rubric not in R:
            rubric = "1c"

        R[rubric]["net"] += net
        if rubric in ("1a", "1b", "1c", "1d"):
            R[rubric]["vat"] += vat

    # === COMPRAS ===
    purchases = frappe.db.sql("""
        SELECT
            pi.name,
            pi.posting_date,
            pi.base_net_total as net_total,
            addr.country as country,
            SUM(CASE
                    WHEN acc.account_type='Tax'
                     AND LOWER(acc.account_name) LIKE %(vat)s
                 THEN ptc.base_tax_amount ELSE 0
                END) as input_vat,
            MAX(CASE WHEN acc.account_type='Tax' THEN ptc.rate ELSE NULL END) as any_rate
        FROM `tabPurchase Invoice` pi
        LEFT JOIN `tabPurchase Taxes and Charges` ptc
            ON ptc.parent = pi.name AND ptc.parenttype='Purchase Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = ptc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = pi.supplier_address
        WHERE pi.docstatus = 1
          AND pi.posting_date BETWEEN %(from)s AND %(to)s
          AND (%(company)s = '' OR pi.company = %(company)s)
        GROUP BY pi.name
        ORDER BY pi.posting_date, pi.name
    """, {"from": from_date, "to": to_date, "company": company, "vat": "%vat%"}, as_dict=True)

    input_vat_total = 0.0
    for row in purchases:
        net = flt(row.net_total)
        vat_in = flt(row.input_vat)
        country = (row.country or "").strip()

        if country == "Netherlands":
            supplier_type = "domestic"
        elif not country:
            supplier_type = "unknown"
        elif country in EU_COUNTRIES:
            supplier_type = "eu"
        else:
            supplier_type = "non_eu"

        if supplier_type == "non_eu":
            R["4a"]["net"] += net
        elif supplier_type == "eu":
            R["4b"]["net"] += net

        input_vat_total += vat_in

    # TOTALES
    vat_due_rubrics = R["1a"]["vat"] + R["1b"]["vat"] + R["1c"]["vat"] + R["1d"]["vat"]
    vat_due_total = vat_due_rubrics  # (añade inversión si la modelas aparte)
    vat_input_total = input_vat_total
    net_payable = vat_due_total - vat_input_total

    if issues:
        frappe.msgprint("<br>".join(issues), title=_("Advertencias de consistencia"), indicator="orange")

    data = [
        {"rubric": "1a", "description": _("1a. Leveringen/diensten belast met hoog tarief (21%)"), "net": R["1a"]["net"], "vat": R["1a"]["vat"]},
        {"rubric": "1b", "description": _("1b. Leveringen/diensten belast met laag tarief (9%/6%)"), "net": R["1b"]["net"], "vat": R["1b"]["vat"]},
        {"rubric": "1c", "description": _("1c. Leveringen/diensten belast met overige tarieven, behalve 0%"), "net": R["1c"]["net"], "vat": R["1c"]["vat"]},
        {"rubric": "1d", "description": _("1d. Privégebruik"), "net": R["1d"]["net"], "vat": R["1d"]["vat"]},
        {"rubric": "1e", "description": _("1e. Leveringen/diensten belast met 0% of niet bij u belast"), "net": R["1e"]["net"], "vat": 0.0},
        {"rubric": "2a", "description": _("2a. Leveringen waarop de verleggingsregeling van toepassing is"), "net": R["2a"]["net"], "vat": 0.0},
        {"rubric": "3a", "description": _("3a. Leveringen naar landen buiten de EU (uitvoer)"), "net": R["3a"]["net"], "vat": 0.0},
        {"rubric": "3b", "description": _("3b. Leveringen naar of diensten in landen binnen de EU"), "net": R["3b"]["net"], "vat": 0.0},
        {"rubric": "3c", "description": _("3c. Installatie/afstandsverkopen binnen de EU"), "net": R["3c"]["net"], "vat": 0.0},
        {"rubric": "4a", "description": _("4a. Leveringen/diensten uit landen buiten de EU"), "net": R["4a"]["net"], "vat": 0.0},
        {"rubric": "4b", "description": _("4b. Leveringen/diensten uit landen binnen de EU"), "net": R["4b"]["net"], "vat": 0.0},
        {"rubric": "", "description": "", "net": "", "vat": ""},  # separador
        {"rubric": "5a", "description": _("5a. Verschuldigde omzetbelasting (rubriek 1 t/m 4)"), "net": "", "vat": vat_due_total},
        {"rubric": "5b", "description": _("5b. Voorbelasting"), "net": "", "vat": vat_input_total},
        {"rubric": "5c", "description": _("5c. Subtotaal (5a - 5b)"), "net": "", "vat": net_payable},
        {"rubric": "5d", "description": _("5d. Vermindering volgens de kleineondernemersregeling (KOR)"), "net": "", "vat": 0.0},
        {"rubric": "5e", "description": _("5e. Schatting vorige aangifte(n)"), "net": "", "vat": 0.0},
        {"rubric": "5f", "description": _("5f. Schatting deze aangifte"), "net": "", "vat": 0.0},
        {"rubric": "Totaal", "description": _("Totaal te betalen of terug te ontvangen"), "net": "", "vat": net_payable},
    ]
    return data


def validate_data_integrity(filters):
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")

    problems = []

    # País vacío/NULL
    missing_country = frappe.db.sql("""
        SELECT COUNT(*) as c
        FROM `tabSales Invoice` si
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(from)s AND %(to)s
          AND (%(company)s = '' OR si.company = %(company)s)
          AND (addr.country IS NULL OR addr.country = '')
    """, {"from": from_date, "to": to_date, "company": company}, as_dict=True)[0]
    if missing_country.c:
        problems.append(_(f"{missing_country.c} facturas de venta con país vacío/NULL en la dirección del cliente."))

    # UE con VAT NL
    eu_with_nl_vat = frappe.db.sql("""
        SELECT COUNT(DISTINCT si.name) as c
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
        LEFT JOIN `tabAccount` acc ON acc.name = stc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(from)s AND %(to)s
          AND (%(company)s = '' OR si.company = %(company)s)
          AND addr.country IN ({eu})
          AND addr.country <> 'Netherlands'
          AND acc.account_type='Tax'
          AND LOWER(acc.account_name) LIKE %(vat)s
          AND stc.base_tax_amount > 0
    """.format(eu="'"+"','".join(EU_COUNTRIES)+"'"),
       {"from": from_date, "to": to_date, "company": company, "vat": "%vat%"},
       as_dict=True)[0]
    if eu_with_nl_vat.c:
        problems.append(_(f"{eu_with_nl_vat.c} facturas UE con IVA NL cobrado. Revise ICP/VAT ID/plantillas de impuesto."))

    # Export con VAT
    export_with_vat = frappe.db.sql("""
        SELECT COUNT(DISTINCT si.name) as c
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
        LEFT JOIN `tabAccount` acc ON acc.name = stc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(from)s AND %(to)s
          AND (%(company)s = '' OR si.company = %(company)s)
          AND (addr.country NOT IN ({eu}) OR addr.country IS NULL OR addr.country = '')
          AND addr.country <> 'Netherlands'
          AND acc.account_type='Tax'
          AND LOWER(acc.account_name) LIKE %(vat)s
          AND stc.base_tax_amount > 0
    """.format(eu="'"+"','".join(EU_COUNTRIES)+"'"),
       {"from": from_date, "to": to_date, "company": company, "vat": "%vat%"},
       as_dict=True)[0]
    if export_with_vat.c:
        problems.append(_(f"{export_with_vat.c} facturas export con IVA NL cobrado. Revise condiciones 0% y evidencia de exportación."))

    if problems:
        frappe.msgprint("<br>".join(problems), title=_("Problemas de integridad de datos"), indicator="red")


def get_columns():
    return [
        {"fieldname": "rubric", "label": _("Rubriek"), "fieldtype": "Data", "width": 80},
        {"fieldname": "description", "label": _("Omschrijving"), "fieldtype": "Data", "width": 420},
        {"fieldname": "net", "label": _("Grondslag (EUR)"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "vat", "label": _("Btw (EUR)"), "fieldtype": "Currency", "width": 150},
    ]
