# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe.model.document import Document
from datetime import date


class Holiday(Document):
	pass

@frappe.whitelist()
def get_holiday_list() -> list[dict]:

	holiday_lists = frappe.get_list(
		"Holiday",
		fields=["holiday_date"],
		ignore_permissions=True,
		filters=[['holiday_date', ">", date.today()]],
		pluck="holiday_date"
	)

	return holiday_lists