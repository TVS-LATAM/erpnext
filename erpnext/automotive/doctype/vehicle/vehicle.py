# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Vehicle(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		clutch: DF.Data | None
		customer: DF.Link | None
		dsg_code: DF.Link | None
		dsg_gearbox: DF.Data | None
		dsg_model: DF.Data | None
		ecu_number: DF.Data | None
		engine_code: DF.Link | None
		first_seen_date: DF.Date | None
		flywheel: DF.Data | None
		last_seen_date: DF.Date | None
		mechatronic: DF.Data | None
		model_year: DF.Data | None
		notes: DF.SmallText | None
		plate: DF.Data | None
		transmission_code: DF.Data | None
		vehicle_model: DF.Link
		vin: DF.Data
	# end: auto-generated types

	def validate(self):
		if not self.vin:
			frappe.throw(_("VIN is required"))
		self.vin = self.vin.strip().upper()
		if len(self.vin) != 17 or not self.vin.isalnum():
			frappe.throw(_("VIN must be exactly 17 alphanumeric characters"))
