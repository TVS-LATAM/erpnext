# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import today


def make_model_display_name(brand, model, engine_liters, hp_kw):
	parts = [
		(brand or "UNKNOWN").upper().strip(),
		(model or "UNKNOWN").upper().strip(),
		(engine_liters or "UNKNOWN").strip(),
		f"{(hp_kw or 'UNKNOWN').strip()}HP",
	]
	return " ".join(parts)


def upsert_vehicle_model(brand, model, engine_liters, hp_kw):
	name = make_model_display_name(brand, model, engine_liters, hp_kw)
	if not frappe.db.exists("Vehicle Model", name):
		doc = frappe.new_doc("Vehicle Model")
		doc.brand = (brand or "UNKNOWN").upper()
		doc.model = (model or "UNKNOWN").upper()
		doc.engine_liters = engine_liters or "UNKNOWN"
		doc.hp_kw = hp_kw or "UNKNOWN"
		doc.insert(ignore_permissions=True)
	return name


def upsert_vehicle_from_project(project_doc):
	if not project_doc.vin:
		return None
	vin = project_doc.vin.strip().upper()
	if len(vin) != 17 or not vin.isalnum():
		return None

	model_name = upsert_vehicle_model(
		project_doc.brand,
		project_doc.model,
		project_doc.engine_liters,
		project_doc.hp_kw,
	)

	if frappe.db.exists("Vehicle", vin):
		veh = frappe.get_doc("Vehicle", vin)
		existed = True
	else:
		veh = frappe.new_doc("Vehicle")
		veh.vin = vin
		veh.first_seen_date = today()
		existed = False

	veh.vehicle_model = model_name
	veh.plate = project_doc.plate
	veh.model_year = project_doc.model_year
	veh.engine_code = project_doc.engine_code or None
	veh.dsg_code = project_doc.dsg_code or None
	veh.transmission_code = project_doc.transmission_code
	veh.dsg_model = project_doc.dsg_model
	veh.dsg_gearbox = project_doc.dsg_gearbox
	veh.ecu_number = project_doc.ecu_number
	veh.mechatronic = project_doc.mechatronic
	veh.flywheel = project_doc.flywheel
	veh.clutch = project_doc.clutch
	veh.customer = project_doc.customer
	veh.last_seen_date = today()

	if existed:
		veh.save(ignore_permissions=True)
	else:
		veh.insert(ignore_permissions=True)
	return veh.name


def sync_vehicle_on_project_save(doc, method=None):
	try:
		upsert_vehicle_from_project(doc)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Vehicle sync failed")
