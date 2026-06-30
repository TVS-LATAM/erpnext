# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

from erpnext.automotive.vehicle_sync import upsert_vehicle_from_project


def execute():
	projects = frappe.get_all(
		"Project",
		filters={"vin": ["is", "set"]},
		fields=["name"],
	)
	success = 0
	skipped = 0
	errors = []
	for p in projects:
		try:
			doc = frappe.get_doc("Project", p.name)
			result = upsert_vehicle_from_project(doc)
			if result:
				success += 1
			else:
				skipped += 1
		except Exception as e:
			errors.append(f"{p.name}: {e}")
	frappe.db.commit()
	print(
		f"Vehicles backfill: {success} synced, {skipped} skipped, "
		f"{len(errors)} errors"
	)
	for err in errors[:20]:
		print(f"  - {err}")
