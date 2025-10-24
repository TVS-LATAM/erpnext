# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AvailablePaymentMethods(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		bank_transfer: DF.Check
		ideal: DF.Check
		revolut: DF.Check
		stripe: DF.Check
	# end: auto-generated types
	pass
