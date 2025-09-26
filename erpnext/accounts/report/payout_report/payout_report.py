# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, flt

def execute(filters=None):
	"""
	Main execution function for Payout Report
	Returns columns and data for the report showing sales invoices with their payments and payment gateways
	"""
	if not filters:
		filters = {}

	# Validate filters
	validate_filters(filters)
	
	columns = get_columns()
	data = fetch_payout_data(filters)
	
	# Calculate totals without duplicates
	totals = get_report_totals(filters)
	
	# Add totals to the report data as a custom property
	# Format the report summary as expected by Frappe
	report_summary = [
		{
			"label": _("Total Invoices"),
			"value": totals.get("total_invoices", 0),
			"indicator": "Blue"
		},
		{
			"label": _("Total Payments"),
			"value": totals.get("total_payments", 0),
			"indicator": "Green"
		},
		{
			"label": _("Pending Amount"),
			"value": totals.get("total_invoices", 0) - totals.get("total_payments", 0),
			"indicator": "Red" if totals.get("total_invoices", 0) > totals.get("total_payments", 0) else "Green"
		}
	]
	
	return columns, data, None, None, report_summary

def validate_filters(filters):
	"""
	Validate input filters
	"""
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Date range is mandatory for Payout Report"))

	if filters.get("company") is None:
		filters["company"] = frappe.defaults.get_user_default("Company")

def fetch_payout_data(filters):
	"""
	Fetch payout data from ERPNext database
	"""
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	company = filters.get("company")
	customer = filters.get("customer")
	payment_gateway = filters.get("payment_gateway")

	# Query to get sales invoices with their payments and payment gateways
	query = """
		SELECT 
			-- Invoice Information
			si.name AS invoice_number,
			si.posting_date AS invoice_date,
			si.base_grand_total AS invoice_amount,
			si.status AS invoice_status,
			
			-- Customer Information (customer ID field is kept for filtering but not displayed)
			si.customer AS customer,
			si.customer_name AS customer_name,
			
			-- Payment Information
			pe.name AS payment_entry,
			pe.posting_date AS payment_date,
			pe.paid_amount AS paid_amount,
			CASE 
				WHEN pe.status IS NULL THEN 'Unpaid'
				ELSE pe.status 
			END AS payment_status,
			
			-- Payment Gateway Information (payment_type is kept for reference but not displayed)
			IFNULL(si.payment_gateway, mop.name) AS payment_gateway,
			mop.type AS payment_type,
			
			-- Reference Information (kept for reference but not displayed)
			pe.reference_no AS reference_no,
			pe.reference_date AS reference_date,
			pe.mode_of_payment AS mode_of_payment
		FROM 
			`tabSales Invoice` si
		LEFT JOIN 
			`tabPayment Entry Reference` per ON per.reference_name = si.name
		LEFT JOIN 
			`tabPayment Entry` pe ON pe.name = per.parent
		LEFT JOIN 
			`tabMode of Payment` mop ON mop.name = pe.mode_of_payment
		WHERE 
			si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND si.company = %(company)s
	"""

	# Add optional filters
	if customer:
		query += " AND si.customer = %(customer)s"
	
	if payment_gateway:
		query += " AND (si.payment_gateway = %(payment_gateway)s OR mop.name = %(payment_gateway)s)"

	# Order by invoice date and then payment date
	query += " ORDER BY si.posting_date, pe.posting_date"

	# Execute the query
	result = frappe.db.sql(query, {
		"from_date": from_date,
		"to_date": to_date,
		"company": company,
		"customer": customer,
		"payment_gateway": payment_gateway
	}, as_dict=True)

	# Process the data to handle invoices without payments
	processed_data = []
	for row in result:
		# If no payment entry exists, still show the invoice
		if not row.payment_entry:
			row.paid_amount = 0
			row.payment_date = None
			row.payment_gateway = None
			row.payment_status = "Unpaid"
		
		processed_data.append(row)

	# Calculate totals for table footer
	totals = get_report_totals(filters)
	
	# Add a custom property to the first row to pass totals to frontend
	if processed_data:
		processed_data[0].total_invoices_amount = totals.get("total_invoices", 0)
		processed_data[0].total_payments_amount = totals.get("total_payments", 0)

	return processed_data

def get_columns():
	"""
	Define columns for Payout Report
	"""
	return [
		# Invoice Information
		{
			"fieldname": "invoice_number", 
			"label": _("Invoice\nNumber"), 
			"fieldtype": "Link", 
			"options": "Sales Invoice",
			"width": 140
		},
		{
			"fieldname": "invoice_date", 
			"label": _("Invoice\nDate"), 
			"fieldtype": "Date", 
			"width": 110
		},
		{
			"fieldname": "invoice_amount", 
			"label": _("Invoice\nAmount"), 
			"fieldtype": "Currency", 
			"width": 130
		},
		{
			"fieldname": "invoice_status", 
			"label": _("Invoice\nStatus"), 
			"fieldtype": "Data", 
			"width": 110
		},
		# Payment Information
		{
			"fieldname": "payment_entry", 
			"label": _("Payment\nEntry"), 
			"fieldtype": "Link", 
			"options": "Payment Entry",
			"width": 150
		},
		{
			"fieldname": "paid_amount", 
			"label": _("Paid\nAmount"), 
			"fieldtype": "Currency", 
			"width": 130
		},
		# Customer Information
		{
			"fieldname": "customer_name", 
			"label": _("Customer\nName"), 
			"fieldtype": "Data", 
			"width": 180
		},
		# Payment Gateway Information
		{
			"fieldname": "payment_gateway", 
			"label": _("Payment\nGateway"), 
			"fieldtype": "Data", 
			"width": 150
		}
	]

def get_report_totals(filters):
	"""
	Calculate report totals without duplicates
	- Total Invoices: Sum of grand_total from distinct invoices
	- Total Payments: Sum of paid_amount from payment entries
	"""
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	company = filters.get("company")
	customer = filters.get("customer")
	payment_gateway = filters.get("payment_gateway")
	
	# Query to get total invoice amount (grand_total) without duplicates
	invoice_query = """
		SELECT 
			SUM(base_grand_total) as total_invoices
		FROM 
			`tabSales Invoice` si
		WHERE 
			si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND si.company = %(company)s
	"""
	
	# Query to get total payments
	payment_query = """
		SELECT 
			SUM(pe.paid_amount) as total_payments
		FROM 
			`tabSales Invoice` si
		LEFT JOIN 
			`tabPayment Entry Reference` per ON per.reference_name = si.name
		LEFT JOIN 
			`tabPayment Entry` pe ON pe.name = per.parent
		LEFT JOIN 
			`tabMode of Payment` mop ON mop.name = pe.mode_of_payment
		WHERE 
			si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND si.company = %(company)s
			AND pe.name IS NOT NULL
	"""
	
	# Add optional filters
	if customer:
		invoice_query += " AND si.customer = %(customer)s"
		payment_query += " AND si.customer = %(customer)s"
	
	if payment_gateway:
		invoice_query += " AND (si.payment_gateway = %(payment_gateway)s)"
		payment_query += " AND (si.payment_gateway = %(payment_gateway)s OR mop.name = %(payment_gateway)s)"
	
	# Execute queries
	params = {
		"from_date": from_date,
		"to_date": to_date,
		"company": company,
		"customer": customer,
		"payment_gateway": payment_gateway
	}
	
	total_invoices = frappe.db.sql(invoice_query, params, as_dict=True)
	total_payments = frappe.db.sql(payment_query, params, as_dict=True)
	
	return {
		"total_invoices": flt(total_invoices[0].total_invoices if total_invoices else 0),
		"total_payments": flt(total_payments[0].total_payments if total_payments else 0)
	}

@frappe.whitelist()
def get_payment_gateways():
	"""
	Get list of payment gateways for filter
	"""
	# Get payment gateways from Sales Invoice table
	payment_gateways = frappe.db.sql("""
		SELECT DISTINCT payment_gateway 
		FROM `tabSales Invoice` 
		WHERE payment_gateway IS NOT NULL
	""", as_dict=True)
	
	# Get modes of payment that might be used as gateways
	modes_of_payment = frappe.db.sql("""
		SELECT DISTINCT name 
		FROM `tabMode of Payment` 
		WHERE type = 'Electronic' OR type = 'Bank'
	""", as_dict=True)
	
	# Combine both lists
	gateways = []
	for pg in payment_gateways:
		gateways.append(pg.payment_gateway)
	
	for mop in modes_of_payment:
		if mop.name not in gateways:
			gateways.append(mop.name)
	
	return sorted(gateways)
