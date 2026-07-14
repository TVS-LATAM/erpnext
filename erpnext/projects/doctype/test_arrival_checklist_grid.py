import json
import unittest
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase


DOCTYPE_JSON = Path(__file__).parent / "arrival_checklist" / "arrival_checklist.json"
ANSWER_OPTIONS = "\nYes\nNo\nN/A"


class TestArrivalChecklistMetadata(unittest.TestCase):
	"""CAM-1 / CIG-1: Arrival Checklist's 8 flat Select answer fields are
	replaced by a single `Checklist Item` child table (`arrival_items`)."""

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
		self.assertEqual(table_fields[0]["fieldname"], "arrival_items")

	def test_mileage_is_fetched_from_job_card(self):
		metadata = self._load_metadata()
		mileage_field = next(
			field for field in metadata["fields"] if field["fieldname"] == "mileage"
		)
		self.assertEqual(mileage_field["fieldtype"], "Data")
		self.assertEqual(mileage_field["fetch_from"], "project.client_mileage_state")
		self.assertEqual(mileage_field["read_only"], 1)

	def _load_metadata(self):
		self.assertTrue(DOCTYPE_JSON.exists(), f"Missing checklist metadata: {DOCTYPE_JSON}")
		return json.loads(DOCTYPE_JSON.read_text())


class TestArrivalChecklistSeeding(FrappeTestCase):
	"""CIG-1: a new Arrival Checklist is seeded with exactly 8 empty rows via
	`before_insert` -> `seed_rows` (design Decision 2's server-side backstop;
	the client `onload` seed path is DOM-bound and not exercised here)."""

	def test_new_doc_has_eight_empty_rows(self):
		doc = frappe.get_doc({"doctype": "Arrival Checklist"})
		doc.insert(ignore_permissions=True)
		try:
			# Reload from DB rather than asserting on the in-memory object:
			# Check-field defaults (None -> 0) are only applied by
			# `get_valid_dict()`'s cast during `db_insert`, not written back
			# onto the in-memory row -- asserting pre-reload would pass on a
			# stale `None` even if the DB column had the wrong value.
			doc.reload()
			rows = doc.get("arrival_items")
			self.assertEqual(len(rows), 8)
			for row in rows:
				self.assertTrue(row.description)
				self.assertEqual(row.yes, 0)
				self.assertEqual(row.no, 0)
				self.assertEqual(row.na, 0)
				self.assertFalse(row.who_did_it)
		finally:
			frappe.delete_doc("Arrival Checklist", doc.name, force=True, ignore_permissions=True)
