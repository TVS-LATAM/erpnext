# icp.py
# Copyright (c) 2024, Frappe Technologies Pvt. Ltd.
# ICP Declaration – Belastingdienst Compliant

import frappe
from frappe import _

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = fetch_icp_data(filters)

    return columns, data

def fetch_icp_data(filters):
    from_date = filters.get("from_date", "1900-01-01")
    to_date = filters.get("to_date", "2100-12-31")
    company = filters.get("company", "")

    query = """
        SELECT 
            customer_name AS `Customer Name`, 
            tax_id AS `VAT Identification Number`, 
            SUM(base_net_total) AS `Net Amount`,  
            0.0 AS `Total VAT`, 
            CASE WHEN is_return = 1 THEN "Credit" ELSE "Normal" END AS `Invoice Type`
        FROM  
            `tabSales Invoice`
        WHERE 
            posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND docstatus = 1  
            AND company = %(company)s
            AND tax_category = 'EU Customer'
            AND tax_id IS NOT NULL
        GROUP BY 
            customer_name, tax_id, is_return
        ORDER BY     
            tax_id
    """

    return frappe.db.sql(query, {
        "from_date": from_date,
        "to_date": to_date,
        "company": company
    }, as_dict=True)

def get_columns():
    return [
        {
            "fieldname": "Customer Name",
            "label": _("Customer Name"),
            "fieldtype": "Data",
            "width": 200
        },
        {
            "fieldname": "VAT Identification Number",
            "label": _("VAT Identification Number"),
            "fieldtype": "Data",
            "width": 180
        },
        {
            "fieldname": "Net Amount",
            "label": _("Net Amount"),
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "fieldname": "Total VAT",
            "label": _("Total VAT"),
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "fieldname": "Invoice Type",
            "label": _("Invoice Type"),
            "fieldtype": "Data",
            "width": 100
        }
    ]
