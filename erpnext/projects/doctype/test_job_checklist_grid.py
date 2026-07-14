import json
import unittest
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase


DOCTYPE_JSON = Path(__file__).parent / "job_checklist" / "job_checklist.json"
ANSWER_OPTIONS = "\nYes\nNo\nN/A"


class TestJobChecklistMetadata(unittest.TestCase):
	"""CAM-1 / CIG-1: Job Checklist's 10 flat Select answer fields are
	replaced by a single `Checklist Item` child table (`job_items`)."""

	def test_no_flat_select_answer_fields_remain(self):
		metadata = self._load_metadata()
		answer_fields = [
			field
			for field in metadata["fields"]
			if field["fieldtype"] == "Select" and field.get("options") == ANSWER_OPTIONS
		]
		self.assertEqual(answer_fields, [])

	def test_exactly_one_checklist_item_table(self):
		metadata = self._load_metadata()
		table_fields = [
			field
			for field in metadata["fields"]
			if field["fieldtype"] == "Table" and field.get("options") == "Checklist Item"
		]
		self.assertEqual(len(table_fields), 1)
		self.assertEqual(table_fields[0]["fieldname"], "job_items")

	def _load_metadata(self):
		self.assertTrue(DOCTYPE_JSON.exists(), f"Missing checklist metadata: {DOCTYPE_JSON}")
		return json.loads(DOCTYPE_JSON.read_text())


class TestJobChecklistSeeding(FrappeTestCase):
	"""CIG-1: a new Job Checklist is seeded with exactly 10 empty rows via
	`before_insert` -> `seed_rows` (design Decision 2's server-side backstop;
	the client `onload` seed path is DOM-bound and not exercised here)."""

	def test_new_doc_has_ten_empty_rows(self):
		doc = frappe.get_doc({"doctype": "Job Checklist"})
		doc.insert(ignore_permissions=True)
		try:
			doc.reload()
			rows = doc.get("job_items")
			self.assertEqual(len(rows), 10)
			for row in rows:
				self.assertTrue(row.description)
				self.assertEqual(row.yes, 0)
				self.assertEqual(row.no, 0)
				self.assertEqual(row.na, 0)
				self.assertFalse(row.who_did_it)
		finally:
			frappe.delete_doc("Job Checklist", doc.name, force=True, ignore_permissions=True)
