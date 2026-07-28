import unittest
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.patches.v14_0.seed_proefrit_rows_on_existing_job_checklists import execute
from erpnext.projects.checklist_templates import CHECKLIST_TEMPLATES

PATCH_MODULE = "erpnext.patches.v14_0.seed_proefrit_rows_on_existing_job_checklists"
TABLE_FIELDNAMES = list(CHECKLIST_TEMPLATES["Job Checklist"])
EXPECTED_ROW_COUNT = 32


class TestPatchRegistration(unittest.TestCase):
	def test_patch_is_registered_after_the_answer_migration(self):
		# It seeds rows into the very tables the answer migration is allowed
		# to write into, so running it first would hand that patch an
		# already-populated table and its `was_empty` gate would skip it.
		patches = (
			(Path(__file__).parents[2] / "patches.txt").read_text().splitlines()
		)
		self.assertIn(PATCH_MODULE, patches)
		self.assertGreater(
			patches.index(PATCH_MODULE),
			patches.index("erpnext.patches.v14_0.migrate_checklist_answers_to_child_tables"),
		)


class TestSeedProefritRowsOnExistingJobChecklists(FrappeTestCase):
	"""A Job Checklist saved before the Proefrit sheet landed has none of the
	sheet's rows: `seed_rows` only runs from `before_insert`. Without this
	patch it opens as six empty sections with nothing to answer."""

	def _make_unseeded_checklist(self):
		doc = frappe.get_doc({"doctype": "Job Checklist"})
		doc.insert(ignore_permissions=True)
		# Reproduce the pre-sheet shape: `before_insert` has already seeded
		# the tables, so strip them back down to the empty state a document
		# created before the conversion actually has on disk.
		for table_fieldname in TABLE_FIELDNAMES:
			doc.set(table_fieldname, [])
		doc.save(ignore_permissions=True)
		doc.reload()
		return doc

	def test_existing_checklist_gains_the_whole_sheet(self):
		doc = self._make_unseeded_checklist()
		try:
			self.assertEqual(sum(len(doc.get(tf)) for tf in TABLE_FIELDNAMES), 0)
			execute()
			doc.reload()
			seeded = 0
			for table_fieldname, rows in CHECKLIST_TEMPLATES["Job Checklist"].items():
				with self.subTest(table=table_fieldname):
					self.assertEqual(len(doc.get(table_fieldname)), len(rows))
				seeded += len(doc.get(table_fieldname))
			self.assertEqual(seeded, EXPECTED_ROW_COUNT)
		finally:
			frappe.delete_doc("Job Checklist", doc.name, force=True, ignore_permissions=True)

	def test_rerun_does_not_duplicate_rows(self):
		doc = self._make_unseeded_checklist()
		try:
			execute()
			execute()
			doc.reload()
			self.assertEqual(
				sum(len(doc.get(tf)) for tf in TABLE_FIELDNAMES), EXPECTED_ROW_COUNT
			)
		finally:
			frappe.delete_doc("Job Checklist", doc.name, force=True, ignore_permissions=True)

	def test_existing_answers_are_not_overwritten(self):
		# Gate mirrored from migrate_checklist_answers_to_child_tables: a
		# table that already holds rows is never touched, so a mechanic's
		# ticks survive a re-run of the patch.
		doc = self._make_unseeded_checklist()
		try:
			execute()
			doc.reload()
			doc.get("status_items")[0].yes = 1
			doc.get("status_items")[0].who_did_it = "mechanic-a"
			doc.save(ignore_permissions=True)

			execute()
			doc.reload()
			self.assertEqual(doc.get("status_items")[0].yes, 1)
			self.assertEqual(doc.get("status_items")[0].who_did_it, "mechanic-a")
		finally:
			frappe.delete_doc("Job Checklist", doc.name, force=True, ignore_permissions=True)
