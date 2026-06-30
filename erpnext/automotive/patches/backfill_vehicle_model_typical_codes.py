# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe


def execute():
	valid_engine_codes = set(frappe.get_all("Engine Code", pluck="name"))
	valid_dsg_codes = set(frappe.get_all("DSG Code", pluck="name"))

	rows = frappe.db.sql(
		"""
		SELECT v.vehicle_model, p.engine_code, p.dsg_code
		FROM `tabVehicle` v
		INNER JOIN `tabProject` p ON p.vin = v.vin
		WHERE v.vehicle_model IS NOT NULL AND v.vehicle_model != ''
		  AND (
		    (p.engine_code IS NOT NULL AND p.engine_code != '')
		    OR (p.dsg_code IS NOT NULL AND p.dsg_code != '')
		  )
		""",
		as_dict=True,
	)

	models = {}
	skipped_engine = 0
	skipped_dsg = 0
	for r in rows:
		bucket = models.setdefault(
			r.vehicle_model, {"engine": set(), "dsg": set()}
		)
		if r.engine_code:
			ec = r.engine_code.strip()
			if ec in valid_engine_codes:
				bucket["engine"].add(ec)
			else:
				skipped_engine += 1
		if r.dsg_code:
			dc = r.dsg_code.strip()
			if dc in valid_dsg_codes:
				bucket["dsg"].add(dc)
			else:
				skipped_dsg += 1

	success = 0
	errors = []
	for model_name, codes in models.items():
		try:
			doc = frappe.get_doc("Vehicle Model", model_name)
			doc.set(
				"typical_engine_codes",
				[{"engine_code": ec} for ec in sorted(codes["engine"])],
			)
			doc.set(
				"typical_dsg_codes",
				[{"dsg_code": dc} for dc in sorted(codes["dsg"])],
			)
			doc.save(ignore_permissions=True)
			success += 1
		except Exception as e:
			errors.append(f"{model_name}: {e}")

	frappe.db.commit()
	print(
		f"Typical codes backfill: {success} models updated, "
		f"{len(errors)} errors, "
		f"{skipped_engine} unknown engine codes filtered, "
		f"{skipped_dsg} unknown dsg codes filtered"
	)
	for err in errors[:20]:
		print(f"  - {err}")
