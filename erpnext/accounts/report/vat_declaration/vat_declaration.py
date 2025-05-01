# vat.py
# VAT Declaration – Belastingdienst Compliant (Corrected)

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

    sales_query = """
        SELECT
            SUM(CASE WHEN si.tax_category LIKE '%%21%%' THEN si.base_net_total ELSE 0 END) AS domestic_high_rate,
            SUM(CASE WHEN si.tax_category LIKE '%%9%%' THEN si.base_net_total ELSE 0 END) AS domestic_low_rate,
            SUM(CASE WHEN si.tax_category LIKE '%%0%%' THEN si.base_net_total ELSE 0 END) AS domestic_zero_rate,
            SUM(CASE WHEN si.tax_category LIKE '%%tarief%%' AND si.tax_category NOT LIKE '%%0%%' AND si.tax_category NOT LIKE '%%21%%' AND si.tax_category NOT LIKE '%%9%%' THEN si.base_net_total ELSE 0 END) AS domestic_other_rates,
            SUM(CASE WHEN si.tax_category LIKE '%%priv%%' OR si.remarks LIKE '%%priv%%' THEN si.base_net_total ELSE 0 END) AS private_use,
            SUM(CASE WHEN si.tax_category LIKE '%%vrijgesteld%%' THEN si.base_net_total ELSE 0 END) AS exempt_sales,
            SUM(CASE WHEN si.incoterm LIKE '%%export%%' THEN si.base_net_total ELSE 0 END) AS export_outside_EU,
            SUM(CASE WHEN si.tax_category LIKE '%%EU%%' THEN si.base_net_total ELSE 0 END) AS intra_EU_sales,
            SUM(CASE WHEN si.tax_category LIKE '%%afstand%%' OR si.remarks LIKE '%%installatie%%' THEN si.base_net_total ELSE 0 END) AS distance_sales_EU,
            SUM(stc.base_tax_amount) AS output_tax_due
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name AND stc.parenttype = 'Sales Invoice'
        WHERE si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.docstatus = 1
            AND si.company = %(company)s
    """

    purchase_query = """
        SELECT
            SUM(CASE WHEN tax_category LIKE '%%diensten%%' AND tax_category LIKE '%%buiten%%' THEN base_net_total ELSE 0 END) AS services_outside_EU,
            SUM(CASE WHEN tax_category LIKE '%%diensten%%' AND tax_category LIKE '%%EU%%' THEN base_net_total ELSE 0 END) AS services_EU,
            SUM(base_total_taxes_and_charges) AS input_tax
        FROM `tabPurchase Invoice`
        WHERE posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND docstatus = 1
            AND company = %(company)s
    """

    reverse_charge_query = """
        SELECT SUM(base_tax_amount) AS reverse_charge
        FROM `tabSales Taxes and Charges`
        WHERE (description LIKE '%%verlegd%%' OR account_head LIKE '%%verlegd%%')
            AND parenttype = 'Sales Invoice'
            AND docstatus = 1
    """

    sales = frappe.db.sql(sales_query, filters, as_dict=True)[0]
    purchases = frappe.db.sql(purchase_query, filters, as_dict=True)[0]
    reverse_charge = frappe.db.sql(reverse_charge_query, filters, as_dict=True)[0].reverse_charge or 0.0

    # Replace None with 0.0
    for key in sales:
        sales[key] = sales.get(key) or 0.0
    for key in purchases:
        purchases[key] = purchases.get(key) or 0.0

    output_tax = sales.output_tax_due
    input_tax = purchases.input_tax
    net_total = output_tax - input_tax

    return [
        {"rubric": "1a", "description": _("1a. Leveringen binnenland hoog tarief"), "amount": sales.domestic_high_rate},
        {"rubric": "1b", "description": _("1b. Leveringen binnenland laag tarief"), "amount": sales.domestic_low_rate},
        {"rubric": "1c", "description": _("1c. Overige tarieven"), "amount": sales.domestic_other_rates},
        {"rubric": "1d", "description": _("1d. Privégebruik"), "amount": sales.private_use},
        {"rubric": "1e", "description": _("1e. Leveringen tegen 0% of vrijgesteld"), "amount": sales.exempt_sales},
        {"rubric": "2a", "description": _("2a. Verleggingsregeling binnenland"), "amount": reverse_charge},
        {"rubric": "3a", "description": _("3a. Export buiten de EU"), "amount": sales.export_outside_EU},
        {"rubric": "3b", "description": _("3b. Leveringen binnen de EU"), "amount": sales.intra_EU_sales},
        {"rubric": "3c", "description": _("3c. Afstandsverkopen binnen de EU"), "amount": sales.distance_sales_EU},
        {"rubric": "4a", "description": _("4a. Diensten uit landen buiten de EU"), "amount": purchases.services_outside_EU},
        {"rubric": "4b", "description": _("4b. Diensten uit EU-landen"), "amount": purchases.services_EU},
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
