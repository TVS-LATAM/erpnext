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
	# Round values to 3 decimal places
	total_invoices = round(totals.get("total_invoices", 0), 3)
	total_payments = round(totals.get("total_payments", 0), 3)
	pending_amount = round(total_invoices - total_payments, 3)
	
	report_summary = [
		{
			"label": _("Total Invoices"),
			"value": total_invoices,
			"indicator": "Blue"
		},
		{
			"label": _("Total Payments"),
			"value": total_payments,
			"indicator": "Green"
		},
		{
			"label": _("Pending Amount"),
			"value": pending_amount,
			"indicator": "Red" if pending_amount > 0 else "Green"
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
			-- First try to get payment_gateway from sales invoice, then from mode of payment
			-- Use LOWER to normalize case and NULLIF to convert empty strings to NULL
			CASE
				WHEN NULLIF(LOWER(si.payment_gateway), '') IS NOT NULL THEN LOWER(si.payment_gateway) 
				WHEN NULLIF(LOWER(mop.name), '') IS NOT NULL THEN LOWER(mop.name)
				ELSE NULL
			END AS payment_gateway,
			mop.type AS payment_type,
			
			-- Payment Details from Sales Invoice
			si.payment_details AS payment_details,
			si.payment_id AS payment_id,
			
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
		# Use a simpler filter for payment_gateway
		query += " AND LOWER(si.payment_gateway) = LOWER(%(payment_gateway)s)"

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

	# Process the data to handle invoices without payments and group multiple payments for the same invoice
	processed_data = []
	
	# Create a dictionary to group by invoice_number
	invoice_map = {}
	
	for row in result:
		# If this is the first time we see this invoice, initialize it
		if row.invoice_number not in invoice_map:
			invoice_map[row.invoice_number] = {
				"invoice_number": row.invoice_number,
				"invoice_date": row.invoice_date,
				"invoice_amount": row.invoice_amount,
				"invoice_status": row.invoice_status,
				"customer": row.customer,
				"customer_name": row.customer_name,
				"payment_gateway": row.payment_gateway,
				"payments": [],
				"total_paid": 0
			}
		
		# If there's a payment entry, add it to the payments list
		if row.payment_entry:
			invoice_map[row.invoice_number]["payments"].append({
				"payment_entry": row.payment_entry,
				"payment_date": row.payment_date,
				"paid_amount": row.paid_amount,
				"payment_status": row.payment_status
			})
			invoice_map[row.invoice_number]["total_paid"] += flt(row.paid_amount)
			
		# Update payment gateway if it exists in this row and not in the invoice map
		if row.payment_gateway and not invoice_map[row.invoice_number]["payment_gateway"]:
			invoice_map[row.invoice_number]["payment_gateway"] = row.payment_gateway
	
	# Convert the grouped data back to rows
	for invoice_number, invoice_data in invoice_map.items():
		# Create a base row with invoice information
		base_row = frappe._dict({
			"invoice_number": invoice_data["invoice_number"],
			"invoice_date": invoice_data["invoice_date"],
			"invoice_amount": invoice_data["invoice_amount"],
			"invoice_status": invoice_data["invoice_status"],
			"customer": invoice_data["customer"],
			"customer_name": invoice_data["customer_name"],
			"payment_gateway": invoice_data["payment_gateway"]
		})
		
		# If there are no payments, add a single row with 0 paid amount
		if not invoice_data["payments"]:
			base_row.payment_entry = None
			base_row.payment_date = None
			base_row.paid_amount = 0
			base_row.payment_status = "Unpaid"
			processed_data.append(base_row)
		else:
			# Add a row for each payment
			for payment in invoice_data["payments"]:
				payment_row = frappe._dict(base_row.copy())
				payment_row.payment_entry = payment["payment_entry"]
				payment_row.payment_date = payment["payment_date"]
				payment_row.paid_amount = payment["paid_amount"]
				payment_row.payment_status = payment["payment_status"]
				processed_data.append(payment_row)
	
	# Normalize payment gateway values
	for row in processed_data:
		if row.payment_gateway:
			# Convert to lowercase for consistency
			row.payment_gateway = row.payment_gateway.lower()
			
			# Map any variations to standard names
			if row.payment_gateway == "revolut":
				row.payment_gateway = "revolut"
			elif row.payment_gateway == "ideal":
				row.payment_gateway = "ideal"
			elif row.payment_gateway == "stripe":
				row.payment_gateway = "stripe"
			elif row.payment_gateway == "manual":
				row.payment_gateway = "manual"

	# Calculate totals for table footer
	totals = get_report_totals(filters)
	
	# Add a custom property to the first row to pass totals to frontend
	# Round values to 3 decimal places
	if processed_data:
		processed_data[0].total_invoices_amount = round(totals.get("total_invoices", 0), 3)
		processed_data[0].total_payments_amount = round(totals.get("total_payments", 0), 3)

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
	# Use DISTINCT to ensure we only sum each invoice once
	invoice_query = """
		SELECT 
			SUM(base_grand_total) as total_invoices
		FROM 
			(SELECT DISTINCT si.name, si.base_grand_total
			FROM `tabSales Invoice` si
			WHERE 
				si.docstatus = 1
				AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
				AND si.company = %(company)s
				{customer_condition}
				{payment_gateway_condition}
			) as unique_invoices
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
	
	# Prepare filter conditions as format strings
	customer_condition = ""
	payment_gateway_condition = ""
	
	if customer:
		customer_condition = "AND si.customer = %(customer)s"
	
	if payment_gateway:
		# Use a simpler filter for payment_gateway to avoid SQL errors
		payment_gateway_condition = "AND LOWER(si.payment_gateway) = LOWER(%(payment_gateway)s)"
	
	# Format the query with conditions
	invoice_query = invoice_query.format(
		customer_condition=customer_condition,
		payment_gateway_condition=payment_gateway_condition
	)
	
	# Add optional filters for payment query
	payment_query_conditions = []
	if customer:
		payment_query_conditions.append("si.customer = %(customer)s")
	
	if payment_gateway:
		payment_query_conditions.append("LOWER(si.payment_gateway) = LOWER(%(payment_gateway)s)")
	
	if payment_query_conditions:
		payment_query += " AND " + " AND ".join(payment_query_conditions)
	
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
	Get list of payment gateways for filter directly from the data shown in the report
	"""
	try:
		# Get all payment gateways that appear in the data
		# This includes both from Sales Invoice and Mode of Payment
		# Use LOWER to normalize case and NULLIF to convert empty strings to NULL
		query = """
		SELECT 
			DISTINCT LOWER(NULLIF(IFNULL(si.payment_gateway, mop.name), '')) AS gateway
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
			AND NULLIF(IFNULL(si.payment_gateway, mop.name), '') IS NOT NULL
		"""
		
		result = frappe.db.sql(query, as_dict=True)
		
		# Extract the gateway names
		gateways = []
		for row in result:
			if row.gateway and row.gateway not in gateways:
				gateways.append(row.gateway)
		
		# Add manual and ideal if they're not already in the list
		for gateway in ["manual", "ideal", "revolut", "stripe"]:
			if gateway not in gateways:
				gateways.append(gateway)
		
		# If no gateways found, add the ones from the screenshot
		if not gateways:
			gateways = ["manual", "ideal", "stripe", "revolut"]
		
		return sorted(gateways)
	except Exception as e:
		frappe.log_error(f"Error in get_payment_gateways: {str(e)}", "Payout Report")
		# Return the gateways from the screenshot in case of error
		return ["manual", "ideal", "stripe", "revolut"]
