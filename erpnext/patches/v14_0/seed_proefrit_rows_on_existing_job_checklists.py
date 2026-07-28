import frappe

from erpnext.projects.checklist_templates import CHECKLIST_TEMPLATES, seed_rows

DOCTYPE = "Job Checklist"


def execute():
	"""Seed the Proefrit sheet's rows onto Job Checklists created before it.

	`seed_rows` only ever runs from `before_insert`, so a Job Checklist saved
	while this doctype still carried the old generic 10-row `job_items` table
	would open with six empty sections and nothing at all to tick -- the rows
	the mechanic is supposed to answer would simply not exist.

	The obsolete `job_items` rows are deliberately NOT deleted. No field
	references them any more, so they are invisible in the UI; keeping them
	costs nothing and leaves the old answers recoverable, which mirrors how
	migrate_checklist_answers_to_child_tables treats orphaned legacy columns
	(CAM-4: never delete the old shape in the same patch that writes the new
	one).
	"""
	table_fieldnames = list(CHECKLIST_TEMPLATES[DOCTYPE])
	meta = frappe.get_meta(DOCTYPE)
	if not all(meta.has_field(tf) for tf in table_fieldnames):
		# The DocType JSON has not synced yet on this bench -- schema sync
		# runs before patches only for changed doctypes, so bail out rather
		# than half-seed. The next `bench migrate` picks this up (idempotent).
		return

	for name in frappe.get_all(DOCTYPE, pluck="name"):
		doc = frappe.get_doc(DOCTYPE, name)
		if all(doc.get(tf) for tf in table_fieldnames):
			# Already seeded (re-run, or created after the sheet landed).
			continue
		# Idempotent per table: seed_rows leaves any table that already holds
		# rows untouched, so a partially-seeded doc only gains what it lacks.
		seed_rows(doc)
		doc.save(ignore_permissions=True)
