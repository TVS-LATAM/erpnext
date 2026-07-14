import json
import unittest
from pathlib import Path


DOCTYPE_JSON = Path(__file__).parent / "checklist_item.json"


class TestChecklistItem(unittest.TestCase):
	"""Metadata contract for the `Checklist Item` child DocType (CIG-4).

	`description` is read-only in the grid -- this is the entire mechanism
	behind CIG-4 (no client JS enforces it; the docfield property does).
	"""

	def test_metadata_contract(self):
		metadata = self._load_metadata()
		fields = {field["fieldname"]: field for field in metadata["fields"]}

		self.assertEqual(metadata["name"], "Checklist Item")
		self.assertEqual(metadata["module"], "Projects")
		self.assertTrue(metadata.get("istable"))

		self.assertEqual(fields["description"]["fieldtype"], "Data")
		self.assertEqual(fields["description"]["read_only"], 1)

		self.assertEqual(fields["yes"]["fieldtype"], "Check")
		self.assertEqual(fields["no"]["fieldtype"], "Check")
		self.assertEqual(fields["na"]["fieldtype"], "Check")

		self.assertEqual(fields["who_did_it"]["fieldtype"], "Data")
		# who_did_it is hand-editable at all times (CIG-3) -- never read-only.
		self.assertFalse(fields["who_did_it"].get("read_only", 0))

		# Column budget: total colsize must stay within the grid's 11-column
		# cap (frappe/public/js/frappe/form/grid.js:959-979 -- total_colsize
		# > 11 silently drops the field from view instead of erroring).
		colsize_fields = ("description", "yes", "no", "na", "who_did_it")
		total_colsize = sum(fields[name].get("columns", 0) for name in colsize_fields)
		self.assertGreater(total_colsize, 0)
		self.assertLessEqual(total_colsize, 11)

	def _load_metadata(self):
		self.assertTrue(DOCTYPE_JSON.exists(), f"Missing checklist metadata: {DOCTYPE_JSON}")
		return json.loads(DOCTYPE_JSON.read_text())
