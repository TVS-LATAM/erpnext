# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class StandardLabourHours(Document):
	def validate(self):
		if not self.applicable:
			self.hours = 0

		duplicate = frappe.db.exists(
			"Standard Labour Hours",
			{
				"year": self.year,
				"dsg_code": self.dsg_code,
				"job": self.job,
				"vehicle_variant": self.vehicle_variant,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("Standard Labour Hours already exists for {0} / {1} / {2} / {3} ({4}).").format(
					self.year, self.dsg_code, self.job, self.vehicle_variant, duplicate
				)
			)


@frappe.whitelist()
def get_standard_labour_hours(dsg_code, job, vehicle_variant=None, year=None):
	"""Return standard labour hours for a gearbox/job, for the quotation builder.

	If `vehicle_variant` is given, returns that single combination. Otherwise returns
	all variants for the `(dsg_code, job)` so the template UI can present the options
	for the user to pick. `year` defaults to the most recent year on record.
	"""
	if not dsg_code or not job:
		frappe.throw(_("dsg_code and job are required"))

	if not year:
		year = frappe.db.get_value(
			"Standard Labour Hours",
			{"dsg_code": dsg_code, "job": job},
			"max(year)",
		)
	if not year:
		return [] if not vehicle_variant else None

	filters = {"dsg_code": dsg_code, "job": job, "year": year}
	if vehicle_variant:
		filters["vehicle_variant"] = vehicle_variant

	rows = frappe.get_all(
		"Standard Labour Hours",
		filters=filters,
		fields=["name", "year", "dsg_code", "job", "vehicle_variant", "applicable", "hours"],
		order_by="vehicle_variant asc",
	)

	if vehicle_variant:
		return rows[0] if rows else None
	return rows
