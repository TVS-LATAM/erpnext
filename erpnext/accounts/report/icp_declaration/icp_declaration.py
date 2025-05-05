# icp.py
# ICP Declaration – Belastingdienst Compliant (verbeterde versie)

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
            si.customer_name AS `Customer Name`, 
            si.tax_id AS `VAT Identification Number`,
            LEFT(REPLACE(REPLACE(si.tax_id, ' ', ''), '-', ''), 2) AS `Country Code`, 
            SUM(sii.base_net_amount) AS `Net Amount`,  
            0.0 AS `Total VAT`, 
            CASE WHEN si.is_return = 1 THEN "Credit" ELSE "Normal" END AS `Invoice Type`,
            'L' AS `Transaction Code`
        FROM  
            `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE 
            si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.docstatus = 1  
            AND si.company = %(company)s
            AND LOWER(si.tax_category) = 'eu customer'
            AND si.tax_id IS NOT NULL
        GROUP BY 
            si.customer_name, si.tax_id, si.is_return
        ORDER BY     
            si.tax_id
    """

    return frappe.db.sql(query, {
        "from_date": from_date,
        "to_date": to_date,
        "company": company
    }, as_dict=True)

def get_columns():
    return [
        {"fieldname": "Customer Name", "label": _("Customer Name"), "fieldtype": "Data", "width": 200},
        {"fieldname": "VAT Identification Number", "label": _("VAT Identification Number"), "fieldtype": "Data", "width": 180},
        {"fieldname": "Country Code", "label": _("Country Code"), "fieldtype": "Data", "width": 100},
        {"fieldname": "Net Amount", "label": _("Net Amount"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "Total VAT", "label": _("Total VAT"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "Invoice Type", "label": _("Invoice Type"), "fieldtype": "Data", "width": 100},
        {"fieldname": "Transaction Code", "label": _("Transaction Code (L/D)"), "fieldtype": "Data", "width": 100}
    ]
