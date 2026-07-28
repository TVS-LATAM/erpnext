import json
import unittest
from pathlib import Path

DOCTYPE_DIR = Path(__file__).parent
# Every Checklist Item table across the 4 checklists, with the note field the
# `_items` -> `_notes` convention derives from it. Pinned as a literal table
# rather than computed from the JSON so a section silently losing its note
# field is a test failure instead of a shorter loop that still passes.
EXPECTED_SECTION_NOTES = {
	"arrival_checklist": {"arrival_items": "arrival_notes"},
	"job_checklist": {
		"pre_test_drive_items": "pre_test_drive_notes",
		"test_drive_items": "test_drive_notes",
		"fault_code_items": "fault_code_notes",
		"tuning_items": "tuning_notes",
		"status_items": "status_notes",
		"final_check_items": "final_check_notes",
	},
	"quality_control_checklist": {
		"before_qc_items": "before_qc_notes",
		"during_qc_items": "during_qc_notes",
		"invoice_items": "invoice_notes",
	},
	"dsg_oil_change_checklist": {
		"before_dsg_items": "before_dsg_notes",
		"during_dsg_items": "during_dsg_notes",
		"after_dsg_items": "after_dsg_notes",
		"final_check_items": "final_check_notes",
	},
}

# A bare "Notes" appears identically on the section strip and on the
# document-level field, so on screen there was no way to tell which note you
# were reading -- in the Project modal both would print under a heading as
# "Notes". Every label now names what it belongs to.
GENERAL_NOTES_LABEL = "General Notes"
EXPECTED_NOTE_LABELS = {
	"arrival_notes": "Arrival Checks Notes",
	"pre_test_drive_notes": "Before Test Drive Notes",
	"test_drive_notes": "During Test Drive Notes",
	"fault_code_notes": "Fault Codes (DTC) Notes",
	"tuning_notes": "Tuning Checks Notes",
	"status_notes": "Vehicle Status Notes",
	"before_qc_notes": "Before Quality Control Notes",
	"during_qc_notes": "During Quality Control Notes",
	"invoice_notes": "Invoice and Delivery Notes",
	"before_dsg_notes": "Before DSG Oil Change Notes",
	"during_dsg_notes": "During DSG Oil Change Notes",
	"after_dsg_notes": "After DSG Oil Change Notes",
	"final_check_notes": "Final Check Notes",
}


class TestChecklistSectionNotes(unittest.TestCase):
	"""Each checklist section carries its own free-text note, stored in a
	sibling field of that section's Checklist Item table and rendered as a
	collapsed strip inside the answer sheet (checklist_grid.js)."""

	def _load(self, slug):
		path = DOCTYPE_DIR / slug / f"{slug}.json"
		self.assertTrue(path.exists(), f"Missing checklist metadata: {path}")
		return json.loads(path.read_text())

	def test_every_checklist_item_table_has_a_sibling_note_field(self):
		# The sheet resolves the note field by convention (table `x_items` ->
		# note `x_notes`) instead of a hardcoded doctype -> fieldname map, so
		# a table without its sibling would silently render no note at all.
		for slug, tables in EXPECTED_SECTION_NOTES.items():
			metadata = self._load(slug)
			by_fieldname = {f["fieldname"]: f for f in metadata["fields"]}
			for table_fieldname, note_fieldname in tables.items():
				with self.subTest(doctype=slug, table=table_fieldname):
					self.assertIn(table_fieldname, by_fieldname)
					self.assertIn(note_fieldname, by_fieldname)
					self.assertEqual(by_fieldname[note_fieldname]["fieldtype"], "Small Text")

	def test_note_fieldnames_follow_the_items_to_notes_convention(self):
		# checklist_grid.js derives the note fieldname by swapping the `_items`
		# suffix for `_notes`. If a table were ever named without that suffix
		# the derivation would produce a name that does not exist, and the
		# note strip would vanish with no error.
		for slug, tables in EXPECTED_SECTION_NOTES.items():
			for table_fieldname, note_fieldname in tables.items():
				with self.subTest(doctype=slug, table=table_fieldname):
					self.assertTrue(table_fieldname.endswith("_items"))
					self.assertEqual(table_fieldname[: -len("_items")] + "_notes", note_fieldname)

	def test_note_field_is_hidden_so_only_the_sheet_renders_it(self):
		# The sheet paints its own collapsible textarea for this field. Left
		# visible, Frappe would ALSO paint its standard control right under the
		# table -- two inputs bound to one value, and the space saving the
		# collapse exists for is lost. Same mechanism check_date/checked_by
		# already use on these doctypes.
		for slug, tables in EXPECTED_SECTION_NOTES.items():
			metadata = self._load(slug)
			by_fieldname = {f["fieldname"]: f for f in metadata["fields"]}
			for note_fieldname in tables.values():
				with self.subTest(doctype=slug, note=note_fieldname):
					self.assertEqual(by_fieldname[note_fieldname].get("hidden"), 1)

	def test_note_field_directly_follows_its_table_in_field_order(self):
		# field_order drives both the form layout and the Project dialog's
		# section walk (renderChecklistFields groups on Section Break), so a
		# note listed outside its own section would be attributed to the next
		# section's heading in the dialog.
		for slug, tables in EXPECTED_SECTION_NOTES.items():
			metadata = self._load(slug)
			order = metadata["field_order"]
			for table_fieldname, note_fieldname in tables.items():
				with self.subTest(doctype=slug, table=table_fieldname):
					self.assertIn(table_fieldname, order)
					self.assertEqual(order[order.index(table_fieldname) + 1], note_fieldname)

	def test_section_note_label_names_its_own_section(self):
		# The label is what the sheet's toggle prints and what the Project
		# modal prints as the row label, and it is read from the docfield
		# (checklist_grid.js's sheetLabels reasoning) rather than written in
		# JS -- so the JSON is the only place it can be made unambiguous.
		for slug, tables in EXPECTED_SECTION_NOTES.items():
			metadata = self._load(slug)
			by_fieldname = {f["fieldname"]: f for f in metadata["fields"]}
			for note_fieldname in tables.values():
				with self.subTest(doctype=slug, note=note_fieldname):
					self.assertEqual(
						by_fieldname[note_fieldname]["label"],
						EXPECTED_NOTE_LABELS[note_fieldname],
					)

	def test_section_note_label_matches_its_table_label(self):
		# The section note must be named after the section it belongs to, not
		# after an independently-written string that drifts the day the table
		# is relabelled.
		for slug, tables in EXPECTED_SECTION_NOTES.items():
			metadata = self._load(slug)
			by_fieldname = {f["fieldname"]: f for f in metadata["fields"]}
			for table_fieldname, note_fieldname in tables.items():
				with self.subTest(doctype=slug, table=table_fieldname):
					table_label = by_fieldname[table_fieldname]["label"]
					self.assertEqual(by_fieldname[note_fieldname]["label"], f"{table_label} Notes")

	def test_document_level_notes_are_labelled_general(self):
		# Both the Section Break and the field: the modal prints the field
		# label, the form prints the section heading, and either one reading a
		# bare "Notes" beside 4 section notes is the ambiguity this fixes.
		for slug in EXPECTED_SECTION_NOTES:
			metadata = self._load(slug)
			by_fieldname = {f["fieldname"]: f for f in metadata["fields"]}
			with self.subTest(doctype=slug):
				self.assertEqual(by_fieldname["notes"]["label"], GENERAL_NOTES_LABEL)
				self.assertEqual(by_fieldname["notes_section"]["label"], GENERAL_NOTES_LABEL)

	def test_general_notes_section_collapses(self):
		# The section notes collapse inside the answer sheet; the
		# document-level one is a plain Section Break of its own, so Frappe's
		# native collapsible does the job with no JS at all.
		for slug in EXPECTED_SECTION_NOTES:
			metadata = self._load(slug)
			by_fieldname = {f["fieldname"]: f for f in metadata["fields"]}
			with self.subTest(doctype=slug):
				self.assertEqual(by_fieldname["notes_section"].get("collapsible"), 1)

	def test_general_notes_section_opens_when_it_already_has_content(self):
		# `collapsible: 1` ALONE collapses unconditionally: layout.js
		# refresh_section_collapse starts at `collapse = true` and only
		# collapsible_depends_on (or a missing mandatory field) can open it --
		# Frappe does NOT auto-expand a section that holds data. Without this,
		# a General Note written earlier sits invisible behind a closed
		# section, which is the same data-burying trap the sheet's note strip
		# avoids with `expanded = Boolean(value)`.
		#
		# A bare fieldname is a valid depends_on expression: layout.js
		# evaluate_depends_on_value falls through to `out = !!doc[expression]`
		# for anything without an eval:/fn: prefix.
		for slug in EXPECTED_SECTION_NOTES:
			metadata = self._load(slug)
			by_fieldname = {f["fieldname"]: f for f in metadata["fields"]}
			with self.subTest(doctype=slug):
				self.assertEqual(by_fieldname["notes_section"].get("collapsible_depends_on"), "notes")

	def test_document_level_notes_field_is_kept(self):
		# Per-section notes are additive. The existing document-level `notes`
		# ("Explain every No answer") holds real data on every checklist saved
		# so far -- dropping it from the JSON would orphan that column.
		for slug in EXPECTED_SECTION_NOTES:
			metadata = self._load(slug)
			with self.subTest(doctype=slug):
				self.assertIn("notes", {f["fieldname"] for f in metadata["fields"]})
