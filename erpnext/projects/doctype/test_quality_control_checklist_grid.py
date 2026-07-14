import json
import unittest
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase


DOCTYPE_JSON = Path(__file__).parent / "quality_control_checklist" / "quality_control_checklist.json"
ANSWER_OPTIONS = "\nYes\nNo\nN/A"
# QC is 10/14/6, verified against the live JSON's own section breaks
# (design Rev 2 "Verified counts" table) -- NEVER 11/13/6.
EXPECTED_SECTION_COUNTS = {
	"before_qc_items": 10,
	"during_qc_items": 14,
	"invoice_items": 6,
}


class TestQualityControlChecklistMetadata(unittest.TestCase):
	"""CAM-1 / CIG-1: Quality Control Checklist's 30 flat Select answer fields
	(10/14/6 across 3 sections) are replaced by 3 `Checklist Item` child
	tables."""

	def test_no_flat_select_answer_fields_remain(self):
		metadata = self._load_metadata()
		answer_fields = [
			field
			for field in metadata["fields"]
			if field["fieldtype"] == "Select" and field.get("options") == ANSWER_OPTIONS
		]
		self.assertEqual(answer_fields, [])

	def test_exactly_three_checklist_item_tables_with_correct_fieldnames(self):
		metadata = self._load_metadata()
		table_fields = [
			field
			for field in metadata["fields"]
			if field["fieldtype"] == "Table" and field.get("options") == "Checklist Item"
		]
		self.assertEqual({f["fieldname"] for f in table_fields}, set(EXPECTED_SECTION_COUNTS))

	def _load_metadata(self):
		self.assertTrue(DOCTYPE_JSON.exists(), f"Missing checklist metadata: {DOCTYPE_JSON}")
		return json.loads(DOCTYPE_JSON.read_text())


class TestQualityControlChecklistSeeding(FrappeTestCase):
	"""CIG-1: a new Quality Control Checklist is seeded with exactly 30 empty
	rows, split 10/14/6 across its 3 sections, via `before_insert` ->
	`seed_rows` (design Decision 2's server-side backstop; the client
	`onload` seed path is DOM-bound and not exercised here)."""

	def test_new_doc_has_thirty_empty_rows_split_10_14_6(self):
		doc = frappe.get_doc({"doctype": "Quality Control Checklist"})
		doc.insert(ignore_permissions=True)
		try:
			# Reload from DB rather than asserting on the in-memory object:
			# Check-field defaults (None -> 0) are only applied by
			# `get_valid_dict()`'s cast during `db_insert`, not written back
			# onto the in-memory row -- asserting pre-reload would pass on a
			# stale `None` even if the DB column had the wrong value.
			doc.reload()
			total = 0
			for table_fieldname, expected_count in EXPECTED_SECTION_COUNTS.items():
				with self.subTest(table=table_fieldname):
					rows = doc.get(table_fieldname)
					self.assertEqual(len(rows), expected_count)
					total += len(rows)
					for row in rows:
						self.assertTrue(row.description)
						self.assertEqual(row.yes, 0)
						self.assertEqual(row.no, 0)
						self.assertEqual(row.na, 0)
						self.assertFalse(row.who_did_it)
			self.assertEqual(total, 30)
		finally:
			frappe.delete_doc("Quality Control Checklist", doc.name, force=True, ignore_permissions=True)
