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
	
	return columns, data

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
			si.name AS invoice_number,
			si.posting_date AS invoice_date,
			si.customer AS customer,
			si.customer_name AS customer_name,
			si.base_grand_total AS invoice_amount,
			si.status AS invoice_status,
			pe.name AS payment_entry,
			pe.posting_date AS payment_date,
			pe.paid_amount AS paid_amount,
			pe.reference_no AS reference_no,
			pe.reference_date AS reference_date,
			pe.mode_of_payment AS mode_of_payment,
			mop.type AS payment_type,
			IFNULL(pg.gateway_service_provider, mop.name) AS payment_gateway,
			pe.status AS payment_status
		FROM 
			`tabSales Invoice` si
		LEFT JOIN 
			`tabPayment Entry Reference` per ON per.reference_name = si.name
		LEFT JOIN 
			`tabPayment Entry` pe ON pe.name = per.parent
		LEFT JOIN 
			`tabMode of Payment` mop ON mop.name = pe.mode_of_payment
		LEFT JOIN 
			`tabPayment Gateway` pg ON pg.name = mop.payment_gateway
		WHERE 
			si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND si.company = %(company)s
	"""

	# Add optional filters
	if customer:
		query += " AND si.customer = %(customer)s"
	
	if payment_gateway:
		query += " AND (pg.gateway_service_provider = %(payment_gateway)s OR mop.name = %(payment_gateway)s)"

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

	return processed_data

def get_columns():
	"""
	Define columns for Payout Report
	"""
	return [
		{
			"fieldname": "invoice_number", 
			"label": _("Invoice Number"), 
			"fieldtype": "Link", 
			"options": "Sales Invoice",
			"width": 130
		},
		{
			"fieldname": "invoice_date", 
			"label": _("Invoice Date"), 
			"fieldtype": "Date", 
			"width": 100
		},
		{
			"fieldname": "customer", 
			"label": _("Customer"), 
			"fieldtype": "Link", 
			"options": "Customer",
			"width": 120
		},
		{
			"fieldname": "customer_name", 
			"label": _("Customer Name"), 
			"fieldtype": "Data", 
			"width": 180
		},
		{
			"fieldname": "invoice_amount", 
			"label": _("Invoice Amount"), 
			"fieldtype": "Currency", 
			"width": 120
		},
		{
			"fieldname": "invoice_status", 
			"label": _("Invoice Status"), 
			"fieldtype": "Data", 
			"width": 100
		},
		{
			"fieldname": "payment_entry", 
			"label": _("Payment Entry"), 
			"fieldtype": "Link", 
			"options": "Payment Entry",
			"width": 130
		},
		{
			"fieldname": "payment_date", 
			"label": _("Payment Date"), 
			"fieldtype": "Date", 
			"width": 100
		},
		{
			"fieldname": "paid_amount", 
			"label": _("Paid Amount"), 
			"fieldtype": "Currency", 
			"width": 120
		},
		{
			"fieldname": "reference_no", 
			"label": _("Reference No"), 
			"fieldtype": "Data", 
			"width": 120
		},
		{
			"fieldname": "payment_gateway", 
			"label": _("Payment Gateway"), 
			"fieldtype": "Data", 
			"width": 150
		},
		{
			"fieldname": "payment_type", 
			"label": _("Payment Type"), 
			"fieldtype": "Data", 
			"width": 100
		},
		{
			"fieldname": "payment_status", 
			"label": _("Payment Status"), 
			"fieldtype": "Data", 
			"width": 100
		}
	]

@frappe.whitelist()
def get_payment_gateways():
	"""
	Get list of payment gateways for filter
	"""
	# Get payment gateways from Payment Gateway table
	payment_gateways = frappe.db.sql("""
		SELECT DISTINCT gateway_service_provider 
		FROM `tabPayment Gateway` 
		WHERE gateway_service_provider IS NOT NULL
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
		gateways.append(pg.gateway_service_provider)
	
	for mop in modes_of_payment:
		if mop.name not in gateways:
			gateways.append(mop.name)
	
	return sorted(gateways)
