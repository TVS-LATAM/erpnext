# vat_declaration.py – Declaración de IVA compatible con Belastingdienst (2025)
# Correcciones clave:
# - 2a: base imponible (omzet) sin IVA
# - 1c: sin "fallback 5%"; usar IVA real por línea / impuesto
# - 4a/4b: IVA devengado por inversión a partir de impuestos/cuentas (no 21% fijo)
# - 5a: suma de IVA devengado en 1a/1b/1c/1d + 4a/4b (excluye 1e y 2a)
# - Dataset consistente con plantillas: incluye breakdown por tarifa (21/9/0) y rubrics con amount (neto) + vat

import frappe
from frappe import _
from frappe.utils import getdate, flt
from datetime import timedelta, date

# Países de la UE
EU_COUNTRIES = [
    'Austria', 'Belgium', 'Bulgaria', 'Croatia', 'Cyprus', 'Czech Republic',
    'Denmark', 'Estonia', 'Finland', 'France', 'Germany', 'Greece',
    'Hungary', 'Ireland', 'Italy', 'Latvia', 'Lithuania', 'Luxembourg',
    'Malta', 'Netherlands', 'Poland', 'Portugal', 'Romania', 'Slovakia',
    'Slovenia', 'Spain', 'Sweden'
]

# Incoterms que suelen indicar exportación
EXPORT_INCOTERMS = ['EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP']

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

    filters.update({
        "from_date": from_date,
        "to_date": to_date,
        "from_date_str": getdate(from_date).strftime('%d-%m-%Y'),
        "to_date_str": getdate(to_date).strftime('%d-%m-%Y'),
    })

    columns = get_columns()
    data = build_report_data(filters)  # devuelve lista en el orden esperado por las plantillas

    # Validaciones (no bloqueantes)
    validate_data_integrity(filters)

    return columns, data


# --------------------------------------------------------------------------------------
# Construcción del dataset consistente con plantillas
#   Orden de datos esperado por las plantillas:
#   0..5  : Breakdown por tarifa: [21_net, 21_vat, 9_net, 9_vat, 0_net, 0_vat]
#   6..10 : Rubriek 1 (1a..1e)  -> cada objeto trae amount (net) y vat
#   11    : Rubriek 2a          -> amount (net) y vat = 0.0
#   12..14: Rubriek 3 (3a..3c)  -> net; vat = 0.0
#   15..16: Rubriek 4 (4a..4b)  -> net; vat = IVA devengado por inversión
#   17..23: Rubriek 5 (5a..5f y total)  -> amounts calculados
# --------------------------------------------------------------------------------------

def build_report_data(filters):
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    company = filters.get("company", "")

    # Totales por rubrica (netos) y IVA (donde aplique)
    rubrics_net = {
        "1a": 0.0, "1b": 0.0, "1c": 0.0, "1d": 0.0, "1e": 0.0,
        "2a": 0.0,
        "3a": 0.0, "3b": 0.0, "3c": 0.0,
        "4a": 0.0, "4b": 0.0
    }
    rubrics_vat = {k: 0.0 for k in rubrics_net.keys()}  # IVA por rubrica (solo donde aplique)

    # Breakdown por tarifa (ventas)
    rate_breakdown_net = {"21": 0.0, "9": 0.0, "0": 0.0}
    rate_breakdown_vat = {"21": 0.0, "9": 0.0, "0": 0.0}  # IVA a 0 no suma, pero se deja por consistencia

    # ---------------------------
    # VENTAS
    # ---------------------------
    # Tomamos líneas para distinguir bienes/servicios y extraer base/impuesto por tipo
    sales_query = """
        SELECT
            si.name as inv,
            si.company,
            si.customer,
            si.customer_address,
            addr.country as customer_country,
            LOWER(TRIM(si.tax_category)) as tax_category,
            UPPER(TRIM(si.incoterm)) as incoterm,
            sii.item_code,
            it.is_stock_item,
            sii.base_net_amount as line_net,
            stc.rate as tax_rate,
            stc.base_tax_amount as line_vat,
            stc.account_head,
            stc.description,
            acc.account_type,
            acc.account_name
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name AND stc.parenttype = 'Sales Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = stc.account_head
        LEFT JOIN `tabItem` it ON it.name = sii.item_code
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

        # Clasificación base de rubricas para ventas (netas) + IVA repercutido
        # 1a: 21%, 1b: 9%, 1c: otros tipos >0, 1e: 0%/exento; 3a/3b/3c según destino/operación
        # NOTA: para simplicidad, si tax_rate es 21 o 9 y cliente no es UE/export se pone en 1a/1b
        vat_rate = flt(r.tax_rate or 0.0)
        net = flt(r.line_net or 0.0)
        vat = 0.0

        # IVA repercutido reconocido (solo si la fila de tax es VAT de venta)
        if (r.account_type == "Tax") and ("vat" in (r.account_name or "").lower()):
            vat = flt(r.line_vat or 0.0)

        rubric = None

        # Exportación por incoterms típicos o cliente "export"
        if customer_type == "export" or (r.incoterm in EXPORT_INCOTERMS):
            rubric = "3a"
        # Intracomunitarias (3b) si cliente EU (≠ NL)
        elif customer_type == "eu" and country != "Netherlands":
            # Para el reporte VAT nacional, 3b neto y generalmente SIN IVA NL (0% / verlegd)
            rubric = "3b"
        else:
            # Domésticas
            if vat_rate == 21:
                rubric = "1a"
            elif vat_rate == 9:
                rubric = "1b"
            elif vat_rate == 0:
                rubric = "1e"
            else:
                # otros tipos >0 => 1c
                if vat_rate > 0:
                    rubric = "1c"
                else:
                    # si no hay impuesto pero tampoco clasifica como EU/Export => 1e
                    rubric = "1e"

        # Acumular neto
        rubrics_net[rubric] += net

        # IVA repercutido solo cuenta en 1a/1b/1c/1d (si tuvieses privado-uso) — 1e y 2a no llevan IVA
        if rubric in ("1a", "1b", "1c"):
            rubrics_vat[rubric] += vat

        # Breakdown por tarifa (ventas)
        if vat_rate == 21:
            rate_breakdown_net["21"] += net
            rate_breakdown_vat["21"] += vat
        elif vat_rate == 9:
            rate_breakdown_net["9"] += net
            rate_breakdown_vat["9"] += vat
        elif vat_rate == 0:
            rate_breakdown_net["0"] += net
            # rate_breakdown_vat["0"] queda 0

    # ---------------------------
    # COMPRAS (para 4a/4b: IVA por inversión y bases)
    # ---------------------------
    # Objetivo: capturar adquisiciones de bienes/servicios desde fuera y dentro de la UE (no NL),
    # y calcular el IVA devengado por inversión (que se declara en 4a/4b) según el tipo (9%/21%)
    purchase_query = """
        SELECT
            pi.name as pinv,
            pi.company,
            pi.supplier,
            pi.supplier_address,
            addr.country as supplier_country,
            LOWER(TRIM(pi.tax_category)) as tax_category,
            pii.item_code,
            it.is_stock_item,
            pii.base_net_amount as line_net,
            ptc.rate as tax_rate,
            ptc.base_tax_amount as line_vat,   -- si hay VAT reflejado
            ptc.account_head,
            acc.account_type,
            acc.account_name
        FROM `tabPurchase Invoice` pi
        INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
        LEFT JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name AND ptc.parenttype = 'Purchase Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = ptc.account_head
        LEFT JOIN `tabItem` it ON it.name = pii.item_code
        LEFT JOIN `tabAddress` addr ON addr.name = pi.supplier_address
        WHERE pi.docstatus = 1
          AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND (%(company)s = '' OR pi.company = %(company)s)
    """
    purchases = frappe.db.sql(purchase_query, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)

    for r in purchases:
        scountry = (r.supplier_country or "").strip()
        supplier_type = (
            "domestic" if scountry == "Netherlands"
            else "eu" if scountry in EU_COUNTRIES
            else "non_eu"
        )

        net = flt(r.line_net or 0.0)
        vat_rate = flt(r.tax_rate or 0.0)

        # En compras desde el extranjero se puede devengar IVA por inversión:
        # 4a: desde fuera de la UE (non_eu)
        # 4b: desde países de la UE (eu)
        if supplier_type == "non_eu":
            rubrics_net["4a"] += net
            # IVA devengado según naturaleza: 21/9 u otro — si no hay "rate" en ptc,
            # deducirlo de la configuración de impuestos o deja 0 y avisa por validación.
            if vat_rate in (9.0, 21.0):
                rubrics_vat["4a"] += flt(net * (vat_rate / 100.0), 2)
        elif supplier_type == "eu":
            rubrics_net["4b"] += net
            if vat_rate in (9.0, 21.0):
                rubrics_vat["4b"] += flt(net * (vat_rate / 100.0), 2)
        else:
            # Compras domésticas: no afectan 4a/4b
            pass

        # Nota: el IVA soportado real (input VAT) se recoge para 5b con cuentas de tipo "Tax"
        # que representen IVA de compra deducible (ver más abajo).

    # ---------------------------
    # DETECCIÓN DE VERLEGD (2a) EN VENTAS NACIONALES
    # ---------------------------
    # Para 2a, debe declararse la BASE (omzet) de operaciones nacionales con IVA verlegd (sin IVA a ingresar)
    verlegd_query = """
    SELECT
        si.name as inv,
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
    GROUP BY si.name
    """
    verlegd_rows = frappe.db.sql(
        verlegd_query,
        {
            "from_date": from_date,
            "to_date": to_date,
            "company": company,
            "like_verlegd": "%verlegd%"
        },
        as_dict=True
    )
    for v in verlegd_rows:
        rubrics_net["2a"] += flt(v.net_base or 0.0)
    rubrics_vat["2a"] = 0.0  # SIEMPRE 0 en 2a

    # ---------------------------
    # INPUT VAT (5b) – IVA soportado deducible en compras nacionales/import/intra-UE
    # ---------------------------
    input_vat_query = """
    SELECT
        SUM(ptc.base_tax_amount) as input_vat
    FROM `tabPurchase Invoice` pi
    LEFT JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
    LEFT JOIN `tabAccount` acc ON acc.name = ptc.account_head
    WHERE pi.docstatus = 1
      AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
      AND (%(company)s = '' OR pi.company = %(company)s)
      AND acc.account_type = 'Tax'
      AND LOWER(acc.account_name) LIKE %(like_vat)s
    """
    input_vat = frappe.db.sql(
        input_vat_query,
        {
            "from_date": from_date,
            "to_date": to_date,
            "company": company,
            "like_vat": "%vat%"
        },
        as_dict=True
    )[0].get("input_vat") or 0.0

    input_vat = flt(input_vat, 2)

    # ---------------------------
    # 5a, 5b, 5c
    # ---------------------------
    # 5a: IVA devengado a ingresar
    vat_due_1 = rubrics_vat["1a"] + rubrics_vat["1b"] + rubrics_vat["1c"]  # 1d se omite aquí salvo que lo calcules aparte
    vat_due_4 = rubrics_vat["4a"] + rubrics_vat["4b"]
    vat_due_total = flt(vat_due_1 + vat_due_4, 2)

    # 5b: input VAT deducible
    vat_input_total = input_vat

    # 5c: subtotal
    subtotal_5c = flt(vat_due_total - vat_input_total, 2)

    # placeholders (ajustes manuales)
    kor_reduction = 0.0   # 5d
    prev_estimate = 0.0   # 5e
    curr_estimate = 0.0   # 5f

    total_payable = flt(subtotal_5c - kor_reduction - prev_estimate - curr_estimate, 2)

    # ---------------------------
    # Preparar dataset final (orden consistente con plantillas)
    # ---------------------------

    data = []

    # 0..5 – Breakdown por tarifa (ventas)
    #   [0]=21% net, [1]=21% VAT, [2]=9% net, [3]=9% VAT, [4]=0% net, [5]=0% VAT
    data.append({"section": "rates", "rate": "21", "amount": flt(rate_breakdown_net["21"], 2), "vat": flt(rate_breakdown_vat["21"], 2)})
    data.append({"section": "rates", "rate": "21_vat", "amount": flt(rate_breakdown_vat["21"], 2), "vat": 0.0})
    data.append({"section": "rates", "rate": "9",  "amount": flt(rate_breakdown_net["9"], 2),  "vat": flt(rate_breakdown_vat["9"], 2)})
    data.append({"section": "rates", "rate": "9_vat",  "amount": flt(rate_breakdown_vat["9"], 2),  "vat": 0.0})
    data.append({"section": "rates", "rate": "0",  "amount": flt(rate_breakdown_net["0"], 2),  "vat": 0.0})
    data.append({"section": "rates", "rate": "0_vat",  "amount": 0.0,  "vat": 0.0})

    # 6..10 – Rubriek 1 (omzet + IVA) (1a..1e)
    data.append({"rubric": "1a", "description": _("1a. Leveringen/diensten belast met hoog tarief"), "amount": flt(rubrics_net["1a"], 2), "vat": flt(rubrics_vat["1a"], 2)})
    data.append({"rubric": "1b", "description": _("1b. Leveringen/diensten belast met laag tarief"), "amount": flt(rubrics_net["1b"], 2), "vat": flt(rubrics_vat["1b"], 2)})
    data.append({"rubric": "1c", "description": _("1c. Leveringen/diensten belast met overige tarieven, behalve 0%"), "amount": flt(rubrics_net["1c"], 2), "vat": flt(rubrics_vat["1c"], 2)})
    data.append({"rubric": "1d", "description": _("1d. Privégebruik"), "amount": flt(rubrics_net["1d"], 2), "vat": flt(rubrics_vat["1d"], 2)})
    data.append({"rubric": "1e", "description": _("1e. Leveringen/diensten belast met 0% of niet bij u belast"), "amount": flt(rubrics_net["1e"], 2), "vat": 0.0})

    # 11 – Rubriek 2a (base sin IVA)
    data.append({"rubric": "2a", "description": _("2a. Leveringen waarop de verleggingsregeling van toepassing is"), "amount": flt(rubrics_net["2a"], 2), "vat": 0.0})

    # 12..14 – Rubriek 3 (sin IVA)
    data.append({"rubric": "3a", "description": _("3a. Leveringen naar landen buiten de EU (uitvoer)"), "amount": flt(rubrics_net["3a"], 2), "vat": 0.0})
    data.append({"rubric": "3b", "description": _("3b. Leveringen naar of diensten in landen binnen de EU"), "amount": flt(rubrics_net["3b"], 2), "vat": 0.0})
    data.append({"rubric": "3c", "description": _("3c. Installatie/afstandsverkopen binnen de EU"), "amount": flt(rubrics_net["3c"], 2), "vat": 0.0})

    # 15..16 – Rubriek 4 (IVA por inversión incluido en "vat")
    data.append({"rubric": "4a", "description": _("4a. Leveringen/diensten uit landen buiten de EU"), "amount": flt(rubrics_net["4a"], 2), "vat": flt(rubrics_vat["4a"], 2)})
    data.append({"rubric": "4b", "description": _("4b. Leveringen/diensten uit landen binnen de EU"), "amount": flt(rubrics_net["4b"], 2), "vat": flt(rubrics_vat["4b"], 2)})

    # 17..23 – Rubriek 5 (solo IVA en columnas)
    data.append({"rubric": "5a", "description": _("5a. Verschuldigde omzetbelasting (rubriek 1 t/m 4)"), "amount": flt(vat_due_total, 2), "vat": 0.0})
    data.append({"rubric": "5b", "description": _("5b. Voorbelasting"), "amount": flt(vat_input_total, 2), "vat": 0.0})
    data.append({"rubric": "5c", "description": _("5c. Subtotaal (rubriek 5a min 5b)"), "amount": flt(subtotal_5c, 2), "vat": 0.0})
    data.append({"rubric": "5d", "description": _("5d. Vermindering volgens de kleineondernemersregeling (KOR)"), "amount": flt(kor_reduction, 2), "vat": 0.0})
    data.append({"rubric": "5e", "description": _("5e. Schatting vorige aangifte(n)"), "amount": flt(prev_estimate, 2), "vat": 0.0})
    data.append({"rubric": "5f", "description": _("5f. Schatting deze aangifte"), "amount": flt(curr_estimate, 2), "vat": 0.0})
    data.append({"rubric": "Totaal", "description": _("Totaal te betalen of terug te ontvangen"), "amount": flt(total_payable, 2), "vat": 0.0})

    return data


def validate_data_integrity(filters):
    """Verificaciones no bloqueantes de integridad de datos."""
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")

    issues = []

    # Facturas de venta sin dirección (país desconocido)
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

    # Facturas de venta sin categoría fiscal
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

    # Incoterms de exportación sin país de destino
    export_without_country = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabSales Invoice` si
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND (%(company)s = '' OR si.company = %(company)s)
          AND si.incoterm IN ('EXW','FCA','FAS','FOB','CFR','CIF','CPT','CIP')
          AND (addr.country IS NULL OR addr.country = '')
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]
    if (export_without_country.get("count") or 0) > 0:
        issues.append(_("{0} facturas con Incoterms de exportación pero sin país de destino").format(export_without_country.get("count")))

    if issues:
        frappe.msgprint("<br>".join(issues), title=_("Advertencias de validación"), indicator="orange")


def get_columns():
    # Para la vista de tabla de ERPNext (el PDF/HTML usa la plantilla)
    return [
        {"fieldname": "rubric", "label": _("Rubriek / Breakdown"), "fieldtype": "Data", "width": 250},
        {"fieldname": "description", "label": _("Omschrijving"), "fieldtype": "Data", "width": 400},
        {"fieldname": "amount", "label": _("Bedrag (EUR)"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "vat", "label": _("Btw (EUR)"), "fieldtype": "Currency", "width": 150}
    ]
