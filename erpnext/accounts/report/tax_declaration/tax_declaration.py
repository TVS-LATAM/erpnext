# tax.py
# TAX Declaration – Belastingdienst Compliant (with tax_category mapping)

import frappe
from frappe import _
from frappe.utils import getdate
from datetime import timedelta, date

# Explicit tax_category to rubric mapping
TAX_CATEGORY_MAPPING = {
    "hoog tarief": "1a",
    "laag tarief": "1b",
    "overig tarief": "1c",
    "privégebruik": "1d",
    "vrijgesteld": "1e",
    "verlegd": "2a",
    "export": "3a",
    "eu klant": "3b",
    "afstandsverkopen": "3c",
    "diensten buiten eu": "4a",
    "diensten eu": "4b"
}

def execute(filters=None):
    if not filters:
        filters = {}

    today = date.today()
    first_day_current = date(today.year, today.month, 1)
    last_day_last_month = first_day_current - timedelta(days=1)
    first_day_last_month = date(last_day_last_month.year, last_day_last_month.month, 1)
    from_date = filters.get("from_date") or first_day_last_month.strftime('%Y-%m-%d')
    to_date = filters.get("to_date") or last_day_last_month.strftime('%Y-%m-%d')

    filters["from_date"] = from_date
    filters["to_date"] = to_date
    filters["from_date_str"] = getdate(from_date).strftime('%d-%m-%Y')
    filters["to_date_str"] = getdate(to_date).strftime('%d-%m-%Y')
    filters["due_date"] = (getdate(to_date) + timedelta(days=30)).strftime('%d-%m-%Y')
    filters["aangiftenummer"] = "823862021B014300"
    filters["rsin"] = "823862021"
    filters["naam"] = "Fiscale Eenheid R.M. Logmans Beheer B.V. en TVS Engineering B.V. C.S."

    columns = get_columns()
    data = fetch_tax_data(filters)

    return columns, data

def fetch_tax_data(filters):
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")

    # Grouped sales by tax_category
    sales_rows = frappe.db.sql("""
        SELECT
            LOWER(tax_category) AS category,
            SUM(base_net_total) AS net_total
        FROM `tabSales Invoice`
        WHERE docstatus = 1
            AND posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND company = %(company)s
        GROUP BY LOWER(tax_category)
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)

    sales_map = {key: 0.0 for key in TAX_CATEGORY_MAPPING.values()}
    for row in sales_rows:
        rubric = TAX_CATEGORY_MAPPING.get(row.category)
        if rubric:
            sales_map[rubric] += row.net_total or 0.0

    # Additional fields: reverse charge and output tax
    tax_data = frappe.db.sql("""
        SELECT
            SUM(stc.base_tax_amount) AS output_tax_due,
            SUM(CASE WHEN stc.description LIKE '%%verlegd%%' OR stc.account_head LIKE '%%verlegd%%' THEN stc.base_tax_amount ELSE 0 END) AS reverse_charge,
            SUM(CASE WHEN si.incoterm IN ('EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP') THEN si.base_net_total ELSE 0 END) AS export_outside_EU
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name AND stc.parenttype = 'Sales Invoice'
        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.company = %(company)s
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]

    for key in tax_data:
        tax_data[key] = tax_data.get(key) or 0.0

    # Purchase input tax
    purchase_tax = frappe.db.sql("""
        SELECT
            SUM(CASE WHEN LOWER(tax_category) LIKE '%%diensten%%' AND LOWER(tax_category) LIKE '%%buiten%%' THEN base_net_total ELSE 0 END) AS services_outside_EU,
            SUM(CASE WHEN LOWER(tax_category) LIKE '%%diensten%%' AND LOWER(tax_category) LIKE '%%eu%%' THEN base_net_total ELSE 0 END) AS services_EU,
            SUM(base_total_taxes_and_charges) AS input_tax
        FROM `tabPurchase Invoice`
        WHERE docstatus = 1 AND posting_date BETWEEN %(from_date)s AND %(to_date)s AND company = %(company)s
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]

    for key in purchase_tax:
        purchase_tax[key] = purchase_tax.get(key) or 0.0

    output_tax = tax_data.output_tax_due
    input_tax = purchase_tax.input_tax
    net_tax_payable = output_tax - input_tax

    return [
        {"rubric": "1a", "description": _("Domestic sales with high tax rate (21%)"), "amount": sales_map["1a"]},
        {"rubric": "1b", "description": _("Domestic sales with low tax rate (9%)"), "amount": sales_map["1b"]},
        {"rubric": "1c", "description": _("Other tax rates"), "amount": sales_map["1c"]},
        {"rubric": "1d", "description": _("Private use (privégebruik)"), "amount": sales_map["1d"]},
        {"rubric": "1e", "description": _("Sales at 0% or exempt (vrijgesteld)"), "amount": sales_map["1e"]},
        {"rubric": "2a", "description": _("Domestic reverse charge (verlegd)"), "amount": tax_data.reverse_charge},
        {"rubric": "3a", "description": _("Exports outside the EU"), "amount": tax_data.export_outside_EU},
        {"rubric": "3b", "description": _("Intra-EU sales"), "amount": sales_map["3b"]},
        {"rubric": "3c", "description": _("Distance/installation sales within EU"), "amount": sales_map["3c"]},
        {"rubric": "4a", "description": _("Services from outside the EU"), "amount": purchase_tax.services_outside_EU},
        {"rubric": "4b", "description": _("Services from within the EU"), "amount": purchase_tax.services_EU},
        {"rubric": "5a", "description": _("Total output tax payable"), "amount": output_tax},
        {"rubric": "5b", "description": _("Input tax from purchases"), "amount": input_tax},
        {"rubric": "5c", "description": _("Subtotal (output tax - input tax)"), "amount": net_tax_payable},
        {"rubric": "5d", "description": _("Small business scheme deduction (KOR)"), "amount": 0.0},
        {"rubric": "5e", "description": _("Correction(s) from previous declarations"), "amount": 0.0},
        {"rubric": "5f", "description": _("Estimated for this declaration"), "amount": 0.0},
        {"rubric": "Total", "description": _("Tax Payable/Refundable"), "amount": net_tax_payable}
    ]

def get_columns():
    return [
        {"fieldname": "rubric", "label": _("Rubric"), "fieldtype": "Data", "width": 80},
        {"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 300},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 150}
    ]
