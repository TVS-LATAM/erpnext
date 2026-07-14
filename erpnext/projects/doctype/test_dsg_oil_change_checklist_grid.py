import json
import unittest
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase


DOCTYPE_JSON = Path(__file__).parent / "dsg_oil_change_checklist" / "dsg_oil_change_checklist.json"
ANSWER_OPTIONS = "\nYes\nNo\nN/A"
# DSG is 7/4/4/5, verified against the live JSON's own section breaks
# (design Rev 2 "Verified counts" table). Fieldnames pinned in
# checklist_templates.py / test_checklist_templates.py -- match exactly.
EXPECTED_SECTION_COUNTS = {
	"before_dsg_items": 7,
	"during_dsg_items": 4,
	"after_dsg_items": 4,
	"final_check_items": 5,
}


class TestDSGOilChangeChecklistMetadata(unittest.TestCase):
	"""CAM-1 / CIG-1: DSG Oil Change Checklist's 20 flat Select answer fields
	(7/4/4/5 across 4 sections) are replaced by 4 `Checklist Item` child
	tables."""

	def test_no_flat_select_answer_fields_remain(self):
		metadata = self._load_metadata()
		answer_fields = [
			field
			for field in metadata["fields"]
			if field["fieldtype"] == "Select" and field.get("options") == ANSWER_OPTIONS
		]
		self.assertEqual(answer_fields, [])

	def test_exactly_four_checklist_item_tables_with_correct_fieldnames(self):
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


class TestDSGOilChangeChecklistSeeding(FrappeTestCase):
	"""CIG-1: a new DSG Oil Change Checklist is seeded with exactly 20 empty
	rows, split 7/4/4/5 across its 4 sections, via `before_insert` ->
	`seed_rows` (design Decision 2's server-side backstop; the client
	`onload` seed path is DOM-bound and not exercised here)."""

	def test_new_doc_has_twenty_empty_rows_split_7_4_4_5(self):
		doc = frappe.get_doc({"doctype": "DSG Oil Change Checklist"})
		doc.insert(ignore_permissions=True)
		try:
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
			self.assertEqual(total, 20)
		finally:
			frappe.delete_doc(
				"DSG Oil Change Checklist", doc.name, force=True, ignore_permissions=True
			)
