import json
import unittest
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase


DOCTYPE_JSON = Path(__file__).parent / "job_checklist" / "job_checklist.json"
ANSWER_OPTIONS = "\nYes\nNo\nN/A"


# The "TVS Proefrit CHECKLIST" sheet's own sections, in sheet order. The
# order is asserted (not just the set) because the answer sheet paints the
# sections in `field_order` and a mechanic works the paper sheet top to
# bottom -- a reshuffle would silently change the order of work.
EXPECTED_ITEM_TABLES = [
	"pre_test_drive_items",
	"test_drive_items",
	"fault_code_items",
	"tuning_items",
	"status_items",
	"final_check_items",
]
EXPECTED_ROW_COUNT = 32


class TestJobChecklistMetadata(unittest.TestCase):
	"""Job Checklist carries the `TVS Proefrit CHECKLIST` sheet: one
	`Checklist Item` child table per section of that sheet, and no flat
	Select answer fields (CAM-1 / CIG-1)."""

	def test_no_flat_select_answer_fields_remain(self):
		metadata = self._load_metadata()
		answer_fields = [
			field
			for field in metadata["fields"]
			if field["fieldtype"] == "Select" and field.get("options") == ANSWER_OPTIONS
		]
		self.assertEqual(answer_fields, [])

	def test_one_checklist_item_table_per_proefrit_section(self):
		metadata = self._load_metadata()
		table_fields = [
			field
			for field in metadata["fields"]
			if field["fieldtype"] == "Table" and field.get("options") == "Checklist Item"
		]
		self.assertEqual([field["fieldname"] for field in table_fields], EXPECTED_ITEM_TABLES)

	def test_vehicle_header_fields_match_the_sheet(self):
		# The paper sheet's header is Auto / Kenteken / Getest door / Datum;
		# the first two were absent while this doctype held a generic
		# checklist, so a printed Proefrit had no vehicle on it.
		metadata = self._load_metadata()
		by_fieldname = {field["fieldname"]: field for field in metadata["fields"]}
		for fieldname in ("vehicle_model", "licence_plate", "checked_by", "check_date"):
			with self.subTest(field=fieldname):
				self.assertIn(fieldname, by_fieldname)
		self.assertEqual(by_fieldname["vehicle_model"]["fetch_from"], "project.model")
		self.assertEqual(by_fieldname["licence_plate"]["fetch_from"], "project.plate")

	def _load_metadata(self):
		self.assertTrue(DOCTYPE_JSON.exists(), f"Missing checklist metadata: {DOCTYPE_JSON}")
		return json.loads(DOCTYPE_JSON.read_text())


class TestJobChecklistSeeding(FrappeTestCase):
	"""CIG-1: a new Job Checklist is seeded with the Proefrit sheet's 32
	empty rows via `before_insert` -> `seed_rows` (design Decision 2's
	server-side backstop; the client `onload` seed path is DOM-bound and not
	exercised here)."""

	def test_new_doc_is_seeded_with_the_whole_proefrit_sheet(self):
		doc = frappe.get_doc({"doctype": "Job Checklist"})
		doc.insert(ignore_permissions=True)
		try:
			doc.reload()
			seeded = 0
			for table_fieldname in EXPECTED_ITEM_TABLES:
				rows = doc.get(table_fieldname)
				with self.subTest(table=table_fieldname):
					self.assertTrue(rows, f"{table_fieldname} was not seeded")
				seeded += len(rows)
				for row in rows:
					self.assertTrue(row.description)
					self.assertEqual(row.yes, 0)
					self.assertEqual(row.no, 0)
					self.assertEqual(row.na, 0)
					self.assertFalse(row.who_did_it)
			self.assertEqual(seeded, EXPECTED_ROW_COUNT)
		finally:
			frappe.delete_doc("Job Checklist", doc.name, force=True, ignore_permissions=True)
