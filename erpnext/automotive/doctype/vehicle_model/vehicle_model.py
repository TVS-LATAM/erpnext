# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class VehicleModel(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from erpnext.automotive.doctype.vehicle_model_dsg_code.vehicle_model_dsg_code import (
			VehicleModelDSGCode,
		)
		from erpnext.automotive.doctype.vehicle_model_engine_code.vehicle_model_engine_code import (
			VehicleModelEngineCode,
		)

		brand: DF.Data | None
		display_name: DF.Data | None
		engine_liters: DF.Data | None
		hp_kw: DF.Data | None
		model: DF.Data | None
		typical_dsg_codes: DF.Table[VehicleModelDSGCode]
		typical_engine_codes: DF.Table[VehicleModelEngineCode]
	# end: auto-generated types

	def autoname(self):
		self.display_name = _build_display_name(
			self.brand, self.model, self.engine_liters, self.hp_kw
		)
		self.name = self.display_name

	def before_save(self):
		self.display_name = _build_display_name(
			self.brand, self.model, self.engine_liters, self.hp_kw
		)


def _build_display_name(brand, model, engine_liters, hp_kw):
	parts = [
		(brand or "UNKNOWN").upper().strip(),
		(model or "UNKNOWN").upper().strip(),
		(engine_liters or "UNKNOWN").strip(),
		f"{(hp_kw or 'UNKNOWN').strip()}HP",
	]
	return " ".join(parts)
