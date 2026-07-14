import frappe

from erpnext.projects.checklist_templates import CHECKLIST_TEMPLATES, iter_legacy_columns, seed_rows

# Recognized legacy flat-Select values. Anything else is drift (Refinement 1)
# and is left unset rather than silently mapped to 0/0/0.
VALUE_TO_FLAG = {"Yes": "yes", "No": "no", "N/A": "na"}


def execute():
	"""Move each doctype's legacy flat Select answer columns into their new
	`Checklist Item` child-table rows (CAM-1..4).

	Safe partial rollout: only doctypes whose Checklist Item table field(s)
	already exist in the current DocType meta are migrated. Quality Control
	/ DSG Oil Change stay on flat Select fields until a later slice converts
	their JSON, so this patch is a no-op for them today and will pick them
	up automatically (idempotent, CAM-2) the next time `bench migrate` runs
	after that conversion lands.

	Legacy columns are read via raw SQL because they are orphaned from the
	DocType meta once their field definition is removed from the JSON --
	Frappe's schema sync does not DROP COLUMN on field removal, so the data
	survives -- and they are never deleted here (CAM-4).
	"""
	drift = []

	for doctype, tables in CHECKLIST_TEMPLATES.items():
		table_fieldnames = list(tables.keys())
		meta = frappe.get_meta(doctype)
		if not all(meta.has_field(tf) for tf in table_fieldnames):
			# Not yet converted to child tables (e.g. QC/DSG before their own
			# JSON conversion lands) -- skip safely.
			continue

		db_table = f"tab{doctype}"
		# Gate1: a legacy column may already be absent (e.g. dropped by a
		# future patch) -- read what actually exists, don't assume.
		existing_columns = {
			column.Field for column in frappe.db.sql(f"SHOW COLUMNS FROM `{db_table}`", as_dict=True)
		}
		present_legacy_columns = [
			(legacy_fieldname, table_fieldname, description)
			for legacy_fieldname, table_fieldname, description in iter_legacy_columns(doctype)
			if legacy_fieldname in existing_columns
		]
		if not present_legacy_columns:
			continue

		select_columns = ["name"] + [entry[0] for entry in present_legacy_columns]
		records = frappe.db.sql(
			"SELECT {} FROM `{}`".format(", ".join(f"`{c}`" for c in select_columns), db_table),
			as_dict=True,
		)

		# Single-transaction guarantee (frappe/modules/patch_handler.py:179-201):
		# the patch runner wraps this whole `execute()` call in one
		# `frappe.db.begin()` / `frappe.db.commit()`, and rolls back the
		# ENTIRE patch on any uncaught exception. Never call
		# `frappe.db.commit()` anywhere in this function -- a commit here
		# would defeat that guarantee and leave some records migrated and
		# others not if a later record raises.
		for record in records:
			doc = frappe.get_doc(doctype, record["name"])

			# Gate2: snapshot which tables were empty BEFORE seeding. Only
			# ever migrate legacy values into rows we are seeding right now
			# on a previously-empty table -- never re-map values onto a
			# table a user (or an earlier patch run) already populated.
			was_empty = {tf: not doc.get(tf) for tf in table_fieldnames}
			# CAM-3: every migrated record must end with the FULL fixed row
			# count regardless of how many legacy columns had values, so the
			# record is "changed" (and must be saved) as soon as seed_rows
			# is about to populate any previously-empty table -- even if
			# every legacy value below turns out to be NULL/empty.
			changed = any(was_empty.values())

			seed_rows(doc)  # idempotent backstop -- no-op on already-seeded tables

			# {description: row} map per table, built AFTER seeding, so every
			# templated row is present exactly once (Refinement 3): defends
			# against silent first-match-wins if a table ever gains a
			# duplicate description.
			rows_by_table = {}
			for table_fieldname in table_fieldnames:
				rows = doc.get(table_fieldname) or []
				row_map = {row.description: row for row in rows}
				if len(row_map) != len(rows):
					frappe.throw(
						f"{doctype}.{table_fieldname} has duplicate row descriptions on {record['name']}"
					)
				rows_by_table[table_fieldname] = row_map

			for legacy_fieldname, table_fieldname, description in present_legacy_columns:
				if not was_empty[table_fieldname]:
					continue  # already-populated table -- do not touch

				value = record.get(legacy_fieldname)
				if not value:
					continue  # Gate3: NULL/"" -> already a correct unanswered row

				flag = VALUE_TO_FLAG.get(value)
				if flag is None:
					# Refinement 1: unrecognized value -- leave the row
					# unanswered rather than silently mapping to 0/0/0.
					drift.append(
						f"{doctype} {record['name']} {legacy_fieldname}={value!r} (unrecognized value, left unanswered)"
					)
					continue

				row = rows_by_table[table_fieldname].get(description)
				if row is None:
					continue
				setattr(row, flag, 1)

			# Refinement 2: only save records actually changed, mirroring
			# migrate_checklist_attachments_to_child_tables.py's `changed`
			# guard -- avoids bumping `modified` on a re-run where every
			# table was already seeded.
			if changed:
				doc.save(ignore_permissions=True)

	if drift:
		# Refinement 5: a single joined message string, not a raw list repr.
		frappe.log_error(
			title="migrate_checklist_answers_to_child_tables: value drift",
			message="\n".join(drift),
		)
