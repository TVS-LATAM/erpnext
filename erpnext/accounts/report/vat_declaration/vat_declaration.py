# vat_declaration.py – Declaración de IVA compatible con Belastingdienst (versión corregida)

import frappe
from frappe import _

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = fetch_vat_data(filters)

    return columns, data

def fetch_vat_data(filters):
    from_date = filters.get("from_date", "1900-01-01")
    to_date = filters.get("to_date", "2100-12-31")
    company = filters.get("company", "")

    export_incoterms = ['EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP']

    sales_query = """
        SELECT
            LOWER(TRIM(tax_category)) AS category,
            UPPER(TRIM(incoterm)) AS incoterm,
            SUM(base_net_total) AS base_total,
            SUM(stc.base_tax_amount) AS tax_total
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc
            ON stc.parent = si.name AND stc.parenttype = 'Sales Invoice'
        WHERE si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.docstatus = 1 AND si.company = %(company)s
        GROUP BY category, incoterm
    """

    purchase_query = """
        SELECT
            LOWER(TRIM(tax_category)) AS category,
            SUM(base_net_total) AS base_total,
            SUM(base_total_taxes_and_charges) AS tax_total
        FROM `tabPurchase Invoice`
        WHERE posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND docstatus = 1 AND company = %(company)s
        GROUP BY category
    """

    reverse_charge_query = """
        SELECT SUM(stc.base_tax_amount) AS reverse_charge
        FROM `tabSales Taxes and Charges` stc
        LEFT JOIN `tabSales Invoice` si ON stc.parent = si.name
        WHERE (stc.description LIKE '%%verlegd%%' OR stc.account_head LIKE '%%verlegd%%')
            AND stc.parenttype = 'Sales Invoice'
            AND si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.company = %(company)s
    """

    filters_sql = {"from_date": from_date, "to_date": to_date, "company": company}

    sales_rows = frappe.db.sql(sales_query, filters_sql, as_dict=True)
    purchase_rows = frappe.db.sql(purchase_query, filters_sql, as_dict=True)
    reverse_charge = frappe.db.sql(reverse_charge_query, filters_sql, as_dict=True)[0].reverse_charge or 0.0

    sales = {
        "1a": 0.0, "1b": 0.0, "1c": 0.0, "1d": 0.0, "1e": 0.0,
        "2a": reverse_charge,
        "3a": 0.0, "3b": 0.0, "3c": 0.0,
        "4a": 0.0, "4b": 0.0,
        "5a": 0.0, "5b": 0.0
    }

    unknown_categories = set()

    # === Ventas ===
    for row in sales_rows:
        cat = (row.category or "").strip().lower()
        incoterm = (row.incoterm or "").strip().upper()
        amt = row.base_total or 0.0
        tax = row.tax_total or 0.0

        if incoterm in export_incoterms:
            sales["3a"] += amt
        elif cat == "21% binnenland":
            sales["1a"] += amt
        elif cat == "9% binnenland":
            sales["1b"] += amt
        elif cat == "vrijgesteld":
            sales["1e"] += amt
        elif cat == "privégebruik":
            sales["1d"] += amt
        elif cat == "eu customer":
            sales["3b"] += amt
        elif cat == "afstandsverkopen":
            sales["3c"] += amt
        else:
            sales["1c"] += amt
            if cat:
                unknown_categories.add(cat)

        sales["5a"] += tax

    if unknown_categories:
        frappe.msgprint(_("Categorías fiscales desconocidas detectadas (sumadas a 1c):") + "<br>" + "<br>".join(sorted(unknown_categories)))

    # === Compras ===
    for row in purchase_rows:
        cat = (row.category or "").strip().lower()
        amt = row.base_total or 0.0
        tax = row.tax_total or 0.0

        if cat == "diensten buiten eu":
            sales["4a"] += amt
        elif cat == "diensten eu":
            sales["4b"] += amt

        sales["5b"] += tax

    net_total = sales["5a"] - sales["5b"]

    return [
        {"rubric": "1a", "description": _("1a. Leveringen binnenland hoog tarief"), "amount": sales["1a"]},
        {"rubric": "1b", "description": _("1b. Leveringen binnenland laag tarief"), "amount": sales["1b"]},
        {"rubric": "1c", "description": _("1c. Overige tarieven"), "amount": sales["1c"]},
        {"rubric": "1d", "description": _("1d. Privégebruik"), "amount": sales["1d"]},
        {"rubric": "1e", "description": _("1e. Leveringen tegen 0% of vrijgesteld"), "amount": sales["1e"]},
        {"rubric": "2a", "description": _("2a. Verleggingsregeling binnenland"), "amount": sales["2a"]},
        {"rubric": "3a", "description": _("3a. Export buiten de EU"), "amount": sales["3a"]},
        {"rubric": "3b", "description": _("3b. Leveringen binnen de EU"), "amount": sales["3b"]},
        {"rubric": "3c", "description": _("3c. Afstandsverkopen binnen de EU"), "amount": sales["3c"]},
        {"rubric": "4a", "description": _("4a. Diensten uit landen buiten de EU"), "amount": sales["4a"]},
        {"rubric": "4b", "description": _("4b. Diensten uit EU-landen"), "amount": sales["4b"]},
        {"rubric": "5a", "description": _("5a. Verschuldigde omzetbelasting"), "amount": sales["5a"]},
        {"rubric": "5b", "description": _("5b. Voorbelasting"), "amount": sales["5b"]},
        {"rubric": "5c", "description": _("5c. Subtotaal (5a - 5b)"), "amount": net_total},
        {"rubric": "5d", "description": _("5d. KOR vermindering"), "amount": 0.0},
        {"rubric": "5e", "description": _("5e. Correctie vorige aangifte"), "amount": 0.0},
        {"rubric": "5f", "description": _("5f. Schatting deze aangifte"), "amount": 0.0},
        {"rubric": "Totaal", "description": _("Totaal te betalen of terug te vorderen"), "amount": net_total}
    ]

def get_columns():
    return [
        {"fieldname": "rubric", "label": _("Rubriek"), "fieldtype": "Data", "width": 80},
        {"fieldname": "description", "label": _("Omschrijving"), "fieldtype": "Data", "width": 300},
        {"fieldname": "amount", "label": _("Bedrag"), "fieldtype": "Currency", "width": 150}
    ]
