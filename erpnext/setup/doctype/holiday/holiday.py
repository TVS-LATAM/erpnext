# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe.model.document import Document
from datetime import date


class Holiday(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		description: DF.TextEditor
		holiday_date: DF.Date
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		weekly_off: DF.Check
	# end: auto-generated types

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