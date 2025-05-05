# vat.py – Declaración de IVA compatible con Belastingdienst (con soporte de Incoterm)

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
            LOWER(tax_category) AS category,
            UPPER(incoterm) AS incoterm,
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
            LOWER(tax_category) AS category,
            SUM(base_net_total) AS base_total,
            SUM(base_total_taxes_and_charges) AS tax_total
        FROM `tabPurchase Invoice`
        WHERE posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND docstatus = 1 AND company = %(company)s
        GROUP BY category
    """

    reverse_charge_query = """
        SELECT SUM(base_tax_amount) AS reverse_charge
        FROM `tabSales Taxes and Charges`
        WHERE (description LIKE '%%verlegd%%' OR account_head LIKE '%%verlegd%%')
            AND parenttype = 'Sales Invoice'
            AND docstatus = 1
    """

    sales_rows = frappe.db.sql(sales_query, filters, as_dict=True)
    purchase_rows = frappe.db.sql(purchase_query, filters, as_dict=True)
    reverse_charge = frappe.db.sql(reverse_charge_query, filters, as_dict=True)[0].reverse_charge or 0.0

    sales = {
        "domestic_high_rate": 0.0,
        "domestic_low_rate": 0.0,
        "domestic_zero_rate": 0.0,
        "domestic_other_rates": 0.0,
        "private_use": 0.0,
        "exempt_sales": 0.0,
        "export_outside_EU": 0.0,
        "intra_EU_sales": 0.0,
        "distance_sales_EU": 0.0,
        "output_tax_due": 0.0
    }

    for row in sales_rows:
        cat = row.category or ""
        incoterm = row.incoterm or ""
        amt = row.base_total or 0.0
        tax = row.tax_total or 0.0

        if incoterm in export_incoterms:
            sales["export_outside_EU"] += amt
        elif "21" in cat:
            sales["domestic_high_rate"] += amt
        elif "9" in cat:
            sales["domestic_low_rate"] += amt
        elif "0" in cat:
            sales["domestic_zero_rate"] += amt
        elif "tarief" in cat:
            sales["domestic_other_rates"] += amt
        elif "priv" in cat:
            sales["private_use"] += amt
        elif "vrijgesteld" in cat:
            sales["exempt_sales"] += amt
        elif "eu" in cat:
            sales["intra_EU_sales"] += amt
        elif "afstand" in cat or "installatie" in cat:
            sales["distance_sales_EU"] += amt

        sales["output_tax_due"] += tax

    purchases = {
        "services_outside_EU": 0.0,
        "services_EU": 0.0,
        "input_tax": 0.0
    }

    for row in purchase_rows:
        cat = row.category or ""
        amt = row.base_total or 0.0
        tax = row.tax_total or 0.0

        if "diensten" in cat and "buiten" in cat:
            purchases["services_outside_EU"] += amt
        elif "diensten" in cat and "eu" in cat:
            purchases["services_EU"] += amt

        purchases["input_tax"] += tax

    output_tax = sales["output_tax_due"]
    input_tax = purchases["input_tax"]
    net_total = output_tax - input_tax

    return [
        {"rubric": "1a", "description": _("1a. Leveringen binnenland hoog tarief"), "amount": sales["domestic_high_rate"]},
        {"rubric": "1b", "description": _("1b. Leveringen binnenland laag tarief"), "amount": sales["domestic_low_rate"]},
        {"rubric": "1c", "description": _("1c. Overige tarieven"), "amount": sales["domestic_other_rates"]},
        {"rubric": "1d", "description": _("1d. Privégebruik"), "amount": sales["private_use"]},
        {"rubric": "1e", "description": _("1e. Leveringen tegen 0% of vrijgesteld"), "amount": sales["exempt_sales"]},
        {"rubric": "2a", "description": _("2a. Verleggingsregeling binnenland"), "amount": reverse_charge},
        {"rubric": "3a", "description": _("3a. Export buiten de EU"), "amount": sales["export_outside_EU"]},
        {"rubric": "3b", "description": _("3b. Leveringen binnen de EU"), "amount": sales["intra_EU_sales"]},
        {"rubric": "3c", "description": _("3c. Afstandsverkopen binnen de EU"), "amount": sales["distance_sales_EU"]},
        {"rubric": "4a", "description": _("4a. Diensten uit landen buiten de EU"), "amount": purchases["services_outside_EU"]},
        {"rubric": "4b", "description": _("4b. Diensten uit EU-landen"), "amount": purchases["services_EU"]},
        {"rubric": "5a", "description": _("5a. Verschuldigde omzetbelasting"), "amount": output_tax},
        {"rubric": "5b", "description": _("5b. Voorbelasting"), "amount": input_tax},
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
