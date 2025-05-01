# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate
from datetime import timedelta, date

def execute(filters=None):
    if not filters:
        filters = {}

    # Default date range to last month if not provided
    today = date.today()
    first_day_current = date(today.year, today.month, 1)
    last_day_last_month = first_day_current - timedelta(days=1)
    first_day_last_month = date(last_day_last_month.year, last_day_last_month.month, 1)
    from_date = filters.get("from_date") or first_day_last_month.strftime('%Y-%m-%d')
    to_date = filters.get("to_date") or last_day_last_month.strftime('%Y-%m-%d')
    # set filters for consistency
    filters["from_date"] = from_date
    filters["to_date"] = to_date

    filters["from_date_str"] = getdate(from_date).strftime('%d-%m-%Y')
    filters["to_date_str"] = getdate(to_date).strftime('%d-%m-%Y')
    filters["due_date"] = (getdate(to_date) + timedelta(days=30)).strftime('%d-%m-%Y')
    filters["aangiftenummer"] = "823862021B014300"
    filters["rsin"] = "823862021"
    filters["naam"] = "FISCALE EENHEID R.M. LOGMANS BEHEER B.V. EN TVS ENGINEERING B.V. C.S."

    columns = get_columns()
    data = fetch_tax_data(filters)

    return columns, data

def fetch_tax_data(filters):
    from_date = filters.get("from_date", "1900-01-01")
    to_date = filters.get("to_date", "2100-12-31")
    company = filters.get("company", "")

    # Subconsulta para compras
    purchase_tax = frappe.db.sql("""
        SELECT
            SUM(ptc.base_tax_amount) AS input_tax,
            SUM(CASE WHEN pi.tax_category LIKE '%%diensten%%buiten%%' THEN pi.base_net_total ELSE 0 END) AS services_outside_EU,
            SUM(CASE WHEN pi.tax_category LIKE '%%diensten%%EU%%' THEN pi.base_net_total ELSE 0 END) AS services_EU
        FROM `tabPurchase Invoice` pi
        LEFT JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name
        WHERE pi.docstatus = 1 AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s AND pi.company = %(company)s
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]

    # Subconsulta para ventas
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

    net_tax_payable = (result.output_tax_due or 0) - (purchase_tax.input_tax or 0)

    return [
        {"rubric": "1a", "description": _("Domestic sales with high tax rate (21%)"), "amount": result.domestic_high_rate or 0},
        {"rubric": "1b", "description": _("Domestic sales with low tax rate (9%)"), "amount": result.domestic_low_rate or 0},
        {"rubric": "1c", "description": _("Other tax rates"), "amount": result.domestic_other_rates or 0},
        {"rubric": "1d", "description": _("Private use (privégebruik)"), "amount": result.private_use or 0},
        {"rubric": "1e", "description": _("Sales at 0% or exempt (vrijgesteld)"), "amount": result.exempt_sales or 0},
        {"rubric": "2a", "description": _("Domestic reverse charge (verlegd)"), "amount": result.reverse_charge or 0},
        {"rubric": "3a", "description": _("Exports outside the EU"), "amount": result.export_outside_EU or 0},
        {"rubric": "3b", "description": _("Intra-EU sales"), "amount": result.intra_EU_sales or 0},
        {"rubric": "3c", "description": _("Distance/installation sales within EU"), "amount": result.distance_sales_EU or 0},
        {"rubric": "4a", "description": _("Services from outside the EU"), "amount": purchase_tax.services_outside_EU or 0},
        {"rubric": "4b", "description": _("Services from within the EU"), "amount": purchase_tax.services_EU or 0},
        {"rubric": "5b", "description": _("Input tax from purchases"), "amount": purchase_tax.input_tax or 0},
        {"rubric": "5a", "description": _("Total output tax payable"), "amount": result.output_tax_due or 0},
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
