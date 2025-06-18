# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class SalesInvoiceRefunds(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Data | None
		counterparty_name: DF.Data | None
		created_at: DF.Data | None
		expiry_date: DF.Data | None
		naming_series: DF.Data | None
		reference: DF.Data | None
		state: DF.Data | None
		trx_id: DF.Data | None
	# end: auto-generated types
	pass
