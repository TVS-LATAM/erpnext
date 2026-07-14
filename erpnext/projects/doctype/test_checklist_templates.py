import json
import unittest
from pathlib import Path

from erpnext.projects.checklist_templates import (
	CHECKLIST_TEMPLATES,
	get_template,
	iter_legacy_columns,
	seed_rows,
)


DOCTYPE_ROOT = Path(__file__).parent
ANSWER_OPTIONS = "\nYes\nNo\nN/A"

# Row counts verified programmatically against the live DocType JSONs
# (design Rev 2 "Verified counts" table) -- QC is 10/14/6, never 11/13/6.
EXPECTED_SECTION_COUNTS = {
	"Arrival Checklist": {"arrival_items": 8},
	"Job Checklist": {"job_items": 10},
	"Quality Control Checklist": {
		"before_qc_items": 10,
		"during_qc_items": 14,
		"invoice_items": 6,
	},
	"DSG Oil Change Checklist": {
		"before_dsg_items": 7,
		"during_dsg_items": 4,
		"after_dsg_items": 4,
		"final_check_items": 5,
	},
}

DOCTYPE_DIRECTORIES = {
	"Arrival Checklist": "arrival_checklist",
	"Job Checklist": "job_checklist",
	"Quality Control Checklist": "quality_control_checklist",
	"DSG Oil Change Checklist": "dsg_oil_change_checklist",
}


class _FakeChildRow:
	"""Minimal stand-in for a Frappe child-table row: attribute access only."""

	def __init__(self, **kwargs):
		for key, value in kwargs.items():
			setattr(self, key, value)


class _FakeDoc:
	"""Test double for `seed_rows`/patch-style callers.

	Real checklist documents can't be used here yet: `arrival_items` etc. are
	not in the live DocType meta until slice 5/6 converts the JSONs, and
	`Document.append()` validates against meta. `seed_rows` only needs
	`.doctype`, `.get(fieldname)`, and `.append(fieldname, dict)` -- this
	double provides exactly that surface, decoupled from ORM/meta specifics.
	"""

	def __init__(self, doctype):
		self.doctype = doctype
		self._tables = {}

	def get(self, fieldname):
		return self._tables.get(fieldname, [])

	def append(self, fieldname, value):
		self._tables.setdefault(fieldname, []).append(_FakeChildRow(**value))


class TestChecklistTemplates(unittest.TestCase):
	def test_row_counts_match_verified_sections(self):
		for doctype, sections in EXPECTED_SECTION_COUNTS.items():
			with self.subTest(doctype=doctype):
				tables = CHECKLIST_TEMPLATES[doctype]
				self.assertEqual(set(tables.keys()), set(sections.keys()))
				for table_fieldname, expected_count in sections.items():
					self.assertEqual(len(tables[table_fieldname]), expected_count)
				self.assertEqual(sum(sections.values()), sum(len(rows) for rows in tables.values()))

	def test_legacy_fieldnames_match_current_json(self):
		"""For doctypes not yet converted (still carry flat Select answer
		fields in their JSON -- Quality Control / DSG until slice 6),
		CHECKLIST_TEMPLATES' legacy fieldnames must match the JSON exactly,
		same as before. For doctypes already converted (Arrival/Job, slice
		5), the flat Select fields no longer exist in the JSON by design --
		the template intentionally retains their legacy fieldnames as the
		join key the migration patch
		(erpnext.patches.v14_0.migrate_checklist_answers_to_child_tables)
		uses to read the now-orphaned DB columns via raw SQL, so this test
		only asserts they still line up while the JSON still declares them."""
		for doctype, directory in DOCTYPE_DIRECTORIES.items():
			with self.subTest(doctype=doctype):
				metadata = json.loads((DOCTYPE_ROOT / directory / f"{directory}.json").read_text())
				json_answer_fields = {
					field["fieldname"]
					for field in metadata["fields"]
					if field["fieldtype"] == "Select" and field.get("options") == ANSWER_OPTIONS
				}
				template_legacy_fields = {
					legacy_fieldname for legacy_fieldname, _table, _desc in iter_legacy_columns(doctype)
				}
				if not json_answer_fields:
					# Already converted: assert the join key still exists,
					# not that it matches a JSON shape that no longer applies.
					self.assertTrue(template_legacy_fields)
					continue
				self.assertEqual(template_legacy_fields, json_answer_fields)

	def test_no_duplicate_descriptions_within_a_table(self):
		for doctype, tables in CHECKLIST_TEMPLATES.items():
			for table_fieldname, rows in tables.items():
				with self.subTest(doctype=doctype, table=table_fieldname):
					descriptions = [description for _legacy, description in rows]
					self.assertEqual(len(descriptions), len(set(descriptions)))

	def test_seed_rows_populates_every_table_from_template(self):
		doc = _FakeDoc("Arrival Checklist")
		seed_rows(doc)
		self.assertEqual(len(doc.get("arrival_items")), 8)
		self.assertEqual(doc.get("arrival_items")[0].description, "Appointment Confirmed")

	def test_seed_rows_is_idempotent(self):
		doc = _FakeDoc("Quality Control Checklist")
		seed_rows(doc)
		seed_rows(doc)  # re-run: tables already have rows -> no-op per table
		self.assertEqual(len(doc.get("before_qc_items")), 10)
		self.assertEqual(len(doc.get("during_qc_items")), 14)
		self.assertEqual(len(doc.get("invoice_items")), 6)

	def test_seed_rows_is_a_noop_for_unmapped_doctype(self):
		doc = _FakeDoc("Task")
		seed_rows(doc)  # must not raise
		self.assertEqual(doc.get("arrival_items"), [])

	def test_get_template_returns_description_only_rows_per_table(self):
		template = get_template("Job Checklist")
		self.assertEqual(set(template.keys()), {"job_items"})
		self.assertEqual(len(template["job_items"]), 10)
		self.assertEqual(template["job_items"][0], {"description": "Work Instructions Reviewed"})
