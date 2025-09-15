# tax_declaration.py
# TAX Declaration – Belastingdienst Compliant (2025)
# Correcciones clave:
# - 2a: base imponible (omzet) sin IVA
# - 4a/4b: IVA devengado por inversión a partir de impuestos reales (no fijo)
# - 5a: suma de IVA devengado en 1a/1b/1c/1d + 4a/4b (excluye 1e y 2a)
# - Dataset consistente con plantillas: amount = neto, vat = IVA (donde aplique)
# - Fecha límite recomendada: mes siguiente (cálculo final en HTML/JS)

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

def execute(filters=None):
    if not filters:
        filters = {}

    # Rango por defecto = mes anterior
    today = date.today()
    first_day_current = date(today.year, today.month, 1)
    last_day_last_month = first_day_current - timedelta(days=1)
    first_day_last_month = date(last_day_last_month.year, last_day_last_month.month, 1)

    from_date = filters.get("from_date") or first_day_last_month.strftime('%Y-%m-%d')
    to_date = filters.get("to_date") or last_day_last_month.strftime('%Y-%m-%d')

    # La due_date la mostramos en HTML como "mes siguiente"; aquí dejamos +30 como fallback UI
    filters.update({
        "from_date": from_date,
        "to_date": to_date,
        "from_date_str": getdate(from_date).strftime('%d-%m-%Y'),
        "to_date_str": getdate(to_date).strftime('%d-%m-%Y'),
        "due_date": (getdate(to_date) + timedelta(days=30)).strftime('%d-%m-%Y'),
        "aangiftenummer": filters.get("aangiftenummer") or "823862021B014300",
        "rsin": filters.get("rsin") or "823862021",
        "naam": filters.get("naam") or "Fiscale Eenheid R.M. Logmans Beheer B.V. en TVS Engineering B.V. C.S."
    })

    columns = get_columns()
    data = build_report_data(filters)

    validate_data_integrity(filters)

    return columns, data


def build_report_data(filters):
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")

    # Estructuras por rúbrica: neto y IVA donde aplique
    rub_net = {k: 0.0 for k in ["1a","1b","1c","1d","1e","2a","3a","3b","3c","4a","4b"]}
    rub_vat = {k: 0.0 for k in ["1a","1b","1c","1d","1e","2a","3a","3b","3c","4a","4b"]}

    # ---------------------------
    # VENTAS (línea a línea)
    # ---------------------------
    sales_query = """
        SELECT
            si.name as inv,
            si.company,
            si.customer,
            si.customer_address,
            addr.country as customer_country,
            LOWER(TRIM(si.tax_category)) as tax_category,
            UPPER(TRIM(si.incoterm)) as incoterm,
            sii.base_net_amount as line_net,
            stc.rate as tax_rate,
            stc.base_tax_amount as line_vat,
            stc.account_head,
            acc.account_type,
            acc.account_name
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name AND stc.parenttype = 'Sales Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = stc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND (%(company)s = '' OR si.company = %(company)s)
    """
    sales = frappe.db.sql(sales_query, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)

    for r in sales:
        country = (r.customer_country or "").strip()
        customer_type = (
            "domestic" if country == "Netherlands"
            else "eu" if country in EU_COUNTRIES
            else "export"
        )

        net = flt(r.line_net or 0.0)
        vat_rate = flt(r.tax_rate or 0.0)
        vat = 0.0
        if (r.account_type == "Tax") and ("vat" in (r.account_name or "").lower()):
            vat = flt(r.line_vat or 0.0)

        # Clasificación
        rubric = None
        if customer_type == "export":
            rubric = "3a"
        elif customer_type == "eu" and country != "Netherlands":
            rubric = "3b"
        else:
            if vat_rate == 21:
                rubric = "1a"
            elif vat_rate == 9:
                rubric = "1b"
            elif vat_rate == 0:
                rubric = "1e"
            elif vat_rate > 0:
                rubric = "1c"
            else:
                rubric = "1e"

        rub_net[rubric] += net
        if rubric in ("1a","1b","1c","1d"):
            rub_vat[rubric] += vat
        # 1e, 2a y 3a/3b/3c no llevan IVA NL repercutido

    # ---------------------------
    # 2a (verlegd) – BASE sin IVA
    # ---------------------------
    verlegd_query = """
        SELECT
            SUM(sii.base_net_amount) as net_base
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
        LEFT JOIN `tabAccount` acc ON acc.name = stc.account_head
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND (%(company)s = '' OR si.company = %(company)s)
          AND (addr.country = 'Netherlands' OR addr.country IS NULL)
          AND (
                LOWER(COALESCE(stc.description,'')) LIKE %(like_verlegd)s OR
                LOWER(COALESCE(stc.account_head,'')) LIKE %(like_verlegd)s OR
                LOWER(COALESCE(si.remarks,'')) LIKE %(like_verlegd)s
              )
    """
    verlegd_rows = frappe.db.sql(
        verlegd_query,
        {"from_date": from_date, "to_date": to_date, "company": company, "like_verlegd": "%verlegd%"},
        as_dict=True
    )
    rub_net["2a"] += flt((verlegd_rows[0] or {}).get("net_base") or 0.0, 2)
    rub_vat["2a"] = 0.0

    # ---------------------------
    # COMPRAS – 4a/4b (IVA devengado por inversión) e input VAT (5b)
    # ---------------------------
    purchase_query = """
        SELECT
            pi.name as pinv,
            pi.company,
            pi.supplier,
            pi.supplier_address,
            addr.country as supplier_country,
            pii.base_net_amount as line_net,
            ptc.rate as tax_rate,
            ptc.base_tax_amount as line_vat,
            ptc.account_head,
            acc.account_type,
            acc.account_name
        FROM `tabPurchase Invoice` pi
        INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
        LEFT JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name AND ptc.parenttype = 'Purchase Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = ptc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = pi.supplier_address
        WHERE pi.docstatus = 1
          AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND (%(company)s = '' OR pi.company = %(company)s)
    """
    purchases = frappe.db.sql(purchase_query, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)

    input_vat_total = 0.0

    for r in purchases:
        scountry = (r.supplier_country or "").strip()
        supplier_type = (
            "domestic" if scountry == "Netherlands"
            else "eu" if scountry in EU_COUNTRIES
            else "non_eu"
        )
        net = flt(r.line_net or 0.0)
        rate = flt(r.tax_rate or 0.0)

        # IVA soportado deducible (5b): cuentas de tipo Tax con "vat" en nombre
        if (r.account_type == "Tax") and ("vat" in (r.account_name or "").lower()):
            input_vat_total += flt(r.line_vat or 0.0)

        # IVA por inversión (4a/4b): calcula desde la base y el rate si corresponde (9/21)
        if supplier_type == "non_eu":
            rub_net["4a"] += net
            if rate in (9.0, 21.0):
                rub_vat["4a"] += flt(net * (rate / 100.0), 2)
        elif supplier_type == "eu":
            rub_net["4b"] += net
            if rate in (9.0, 21.0):
                rub_vat["4b"] += flt(net * (rate / 100.0), 2)

    # ---------------------------
    # 5a, 5b, 5c
    # ---------------------------
    vat_due_r1 = rub_vat["1a"] + rub_vat["1b"] + rub_vat["1c"] + rub_vat["1d"]
    vat_due_r4 = rub_vat["4a"] + rub_vat["4b"]
    vat_due_total = flt(vat_due_r1 + vat_due_r4, 2)

    vat_input_total = flt(input_vat_total, 2)

    subtotal_5c = flt(vat_due_total - vat_input_total, 2)

    kor_reduction = 0.0
    prev_corrections = 0.0
    provisional_estimate = 0.0

    total_payable = flt(subtotal_5c - kor_reduction - prev_corrections - provisional_estimate, 2)

    # ---------------------------
    # Dataset final – índices para las plantillas
    # 0..4 : 1a..1e
    # 5    : 2a
    # 6..8 : 3a..3c
    # 9..10: 4a..4b
    # 11..17: 5a..5g (incluye total)
    # ---------------------------
    data = []
    data.append({"rubric": "1a", "description": _("1a. Leveringen/diensten belast met hoog tarief"), "amount": flt(rub_net["1a"],2), "vat": flt(rub_vat["1a"],2)})
    data.append({"rubric": "1b", "description": _("1b. Leveringen/diensten belast met laag tarief"), "amount": flt(rub_net["1b"],2), "vat": flt(rub_vat["1b"],2)})
    data.append({"rubric": "1c", "description": _("1c. Andere tarieven"), "amount": flt(rub_net["1c"],2), "vat": flt(rub_vat["1c"],2)})
    data.append({"rubric": "1d", "description": _("1d. Privégebruik"), "amount": flt(rub_net["1d"],2), "vat": flt(rub_vat["1d"],2)})
    data.append({"rubric": "1e", "description": _("1e. Leveringen/diensten 0% of vrijgesteld"), "amount": flt(rub_net["1e"],2), "vat": 0.0})

    data.append({"rubric": "2a", "description": _("2a. Verleggingsregeling (omzet)"), "amount": flt(rub_net["2a"],2), "vat": 0.0})

    data.append({"rubric": "3a", "description": _("3a. Leveringen buiten de EU (uitvoer)"), "amount": flt(rub_net["3a"],2), "vat": 0.0})
    data.append({"rubric": "3b", "description": _("3b. Leveringen/diensten binnen de EU"), "amount": flt(rub_net["3b"],2), "vat": 0.0})
    data.append({"rubric": "3c", "description": _("3c. Afstandsverkopen/installaties binnen de EU"), "amount": flt(rub_net["3c"],2), "vat": 0.0})

    data.append({"rubric": "4a", "description": _("4a. Prestaties uit landen buiten de EU (btw verlegd)"), "amount": flt(rub_net["4a"],2), "vat": flt(rub_vat["4a"],2)})
    data.append({"rubric": "4b", "description": _("4b. Prestaties uit EU-landen (btw verlegd)"), "amount": flt(rub_net["4b"],2), "vat": flt(rub_vat["4b"],2)})

    data.append({"rubric": "5a", "description": _("5a. Verschuldigde btw (rubriek 1 t/m 4)"), "amount": vat_due_total, "vat": 0.0})
    data.append({"rubric": "5b", "description": _("5b. Voorbelasting"), "amount": vat_input_total, "vat": 0.0})
    data.append({"rubric": "5c", "description": _("5c. Subtotaal (5a - 5b)"), "amount": subtotal_5c, "vat": 0.0})
    data.append({"rubric": "5d", "description": _("5d. KOR vermindering"), "amount": kor_reduction, "vat": 0.0})
    data.append({"rubric": "5e", "description": _("5e. Correcties uit eerdere aangiften"), "amount": prev_corrections, "vat": 0.0})
    data.append({"rubric": "5f", "description": _("5f. Voorlopige schatting"), "amount": provisional_estimate, "vat": 0.0})
    data.append({"rubric": "5g", "description": _("5g. Te betalen of terug te ontvangen"), "amount": total_payable, "vat": 0.0})

    return data


def validate_data_integrity(filters):
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")

    issues = []

    # Sin dirección
    missing_address = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND (%(company)s = '' OR si.company = %(company)s)
          AND (si.customer_address IS NULL OR si.customer_address = '')
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]
    if (missing_address.get("count") or 0) > 0:
        issues.append(_("{0} facturas de venta sin dirección de cliente").format(missing_address.get("count")))

    # Sin tax_category
    missing_tax_category = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND (%(company)s = '' OR si.company = %(company)s)
          AND (si.tax_category IS NULL OR si.tax_category = '')
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]
    if (missing_tax_category.get("count") or 0) > 0:
        issues.append(_("{0} facturas de venta sin categoría fiscal").format(missing_tax_category.get("count")))

    if issues:
        frappe.msgprint("<br>".join(issues), title=_("Advertencias de validación"), indicator="orange")


def get_columns():
    # Para la vista de tabla (el PDF usa plantilla)
    return [
        {"fieldname": "rubric", "label": _("Rubriek"), "fieldtype": "Data", "width": 140},
        {"fieldname": "description", "label": _("Omschrijving"), "fieldtype": "Data", "width": 420},
        {"fieldname": "amount", "label": _("Bedrag (EUR)"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "vat", "label": _("Btw (EUR)"), "fieldtype": "Currency", "width": 150}
    ]
