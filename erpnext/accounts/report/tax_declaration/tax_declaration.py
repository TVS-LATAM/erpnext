# tax.py
# TAX Declaration – Belastingdienst Compliant (Corrected)

import frappe
from frappe import _
from frappe.utils import getdate
from datetime import timedelta, date

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

    # Purchase input tax
    purchase_tax = frappe.db.sql("""
        SELECT
            SUM(CASE WHEN tax_category LIKE '%%diensten%%' AND tax_category LIKE '%%buiten%%' THEN base_net_total ELSE 0 END) AS services_outside_EU,
            SUM(CASE WHEN tax_category LIKE '%%diensten%%' AND tax_category LIKE '%%EU%%' THEN base_net_total ELSE 0 END) AS services_EU,
            SUM(base_total_taxes_and_charges) AS input_tax
        FROM `tabPurchase Invoice`
        WHERE docstatus = 1 AND posting_date BETWEEN %(from_date)s AND %(to_date)s AND company = %(company)s
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]

    # Sales output
    result = frappe.db.sql("""
        SELECT
            SUM(CASE WHEN si.tax_category LIKE '%%21%%' THEN si.base_net_total ELSE 0 END) AS domestic_high_rate,
            SUM(CASE WHEN si.tax_category LIKE '%%9%%' THEN si.base_net_total ELSE 0 END) AS domestic_low_rate,
            SUM(CASE WHEN si.tax_category LIKE '%%tarief%%' AND si.tax_category NOT LIKE '%%0%%' AND si.tax_category NOT LIKE '%%21%%' AND si.tax_category NOT LIKE '%%9%%' THEN si.base_net_total ELSE 0 END) AS domestic_other_rates,
            SUM(CASE WHEN si.tax_category LIKE '%%priv%%' OR si.remarks LIKE '%%priv%%' THEN si.base_net_total ELSE 0 END) AS private_use,
            SUM(CASE WHEN si.tax_category LIKE '%%vrijgesteld%%' THEN si.base_net_total ELSE 0 END) AS exempt_sales,
            SUM(CASE WHEN si.tax_category LIKE '%%EU%%' THEN si.base_net_total ELSE 0 END) AS intra_EU_sales,
            SUM(CASE WHEN si.tax_category LIKE '%%afstand%%' OR si.remarks LIKE '%%installatie%%' THEN si.base_net_total ELSE 0 END) AS distance_sales_EU,
            SUM(CASE WHEN si.incoterm LIKE '%%export%%' THEN si.base_net_total ELSE 0 END) AS export_outside_EU,
            SUM(stc.base_tax_amount) AS output_tax_due,
            SUM(CASE WHEN stc.description LIKE '%%verlegd%%' OR stc.account_head LIKE '%%verlegd%%' THEN stc.base_tax_amount ELSE 0 END) AS reverse_charge
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name AND stc.parenttype = 'Sales Invoice'
        WHERE si.docstatus = 1 AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s AND si.company = %(company)s
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]

    # Default nulls to 0.0
    for key in result:
        result[key] = result.get(key) or 0.0
    for key in purchase_tax:
        purchase_tax[key] = purchase_tax.get(key) or 0.0

    output_tax = result.output_tax_due
    input_tax = purchase_tax.input_tax
    net_tax_payable = output_tax - input_tax

    return [
        {"rubric": "1a", "description": _("Domestic sales with high tax rate (21%)"), "amount": result.domestic_high_rate},
        {"rubric": "1b", "description": _("Domestic sales with low tax rate (9%)"), "amount": result.domestic_low_rate},
        {"rubric": "1c", "description": _("Other tax rates"), "amount": result.domestic_other_rates},
        {"rubric": "1d", "description": _("Private use (privégebruik)"), "amount": result.private_use},
        {"rubric": "1e", "description": _("Sales at 0% or exempt (vrijgesteld)"), "amount": result.exempt_sales},
        {"rubric": "2a", "description": _("Domestic reverse charge (verlegd)"), "amount": result.reverse_charge},
        {"rubric": "3a", "description": _("Exports outside the EU"), "amount": result.export_outside_EU},
        {"rubric": "3b", "description": _("Intra-EU sales"), "amount": result.intra_EU_sales},
        {"rubric": "3c", "description": _("Distance/installation sales within EU"), "amount": result.distance_sales_EU},
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