import re
import unittest
from pathlib import Path

# No JS test runner/DOM exists in this repo for project.js's dialog-rendering
# functions (the same documented "honest gap" as test_checklist_grid_wiring.py
# and test_tvs_job_card_checklists.py's UI-wiring tests) -- this follows the
# same established pattern: assert on the client script's own source text as
# the available test layer, scoped to specific function bodies rather than a
# whole-file substring search, so a match inside an unrelated function or a
# stray comment cannot make an assertion pass vacuously.
PROJECT_JS = Path(__file__).parents[1] / "doctype" / "project" / "project.js"


def _extract_function(source, name):
	"""Returns the full source text of a top-level `function name(...) { ... }`
	declaration, matched by brace-depth counting (not a fixed line window --
	project.js is edited frequently and line numbers drift)."""
	match = re.search(rf"function {re.escape(name)}\s*\([^)]*\)\s*{{", source)
	if not match:
		raise AssertionError(f"function {name} not found in project.js")
	start = match.end() - 1  # position of the opening brace
	depth = 0
	for i in range(start, len(source)):
		if source[i] == "{":
			depth += 1
		elif source[i] == "}":
			depth -= 1
			if depth == 0:
				return source[match.start() : i + 1]
	raise AssertionError(f"unbalanced braces while extracting function {name}")


class TestProjectChecklistRender(unittest.TestCase):
	def setUp(self):
		self.source = PROJECT_JS.read_text()

	def test_table_fieldtype_is_no_longer_skipped_by_the_layout_set(self):
		# PCD-1: CHECKLIST_LAYOUT_FIELDTYPES previously included "Table",
		# which made renderChecklistFields silently skip every Table field --
		# including Checklist Item child tables -- producing an empty
		# summary for any converted checklist (the exact regression PCD-1
		# exists to prevent). Scoped to the const's own definition line so a
		# stray "Table" elsewhere in the file (e.g. inside a comment) cannot
		# make this assertion pass vacuously.
		match = re.search(r"const CHECKLIST_LAYOUT_FIELDTYPES = new Set\(\[(.*?)\]\);", self.source)
		self.assertIsNotNone(match, "CHECKLIST_LAYOUT_FIELDTYPES definition not found")
		layout_types = match.group(1)
		self.assertNotIn('"Table"', layout_types)
		# The layout-only fieldtypes it should still skip are untouched.
		for fieldtype in ("Section Break", "Column Break", "Tab Break", "HTML", "Button"):
			with self.subTest(fieldtype=fieldtype):
				self.assertIn(f'"{fieldtype}"', layout_types)

	def test_vehicle_detail_fields_are_not_rendered_in_project_checklist_dialog(self):
		# Vehicle details are visible on each checklist form, but they add
		# noise to the Project quick-scan modal. The modal should focus on
		# checklist answers and who_did_it only.
		match = re.search(r"const CHECKLIST_HEADER_FIELDS = new Set\(\[(.*?)\]\);", self.source, re.S)
		self.assertIsNotNone(match, "CHECKLIST_HEADER_FIELDS definition not found")
		header_fields = match.group(1)
		for fieldname in ("vehicle_model", "licence_plate", "mileage"):
			with self.subTest(fieldname=fieldname):
				self.assertIn(f'"{fieldname}"', header_fields)

	def test_render_checklist_fields_walks_checklist_item_tables(self):
		# PCD-1: a Table field whose child doctype is "Checklist Item" must
		# have its rows walked into the section render; other Table fields
		# (photos/attachments) must still be skipped, so the walk MUST be
		# gated on options === "Checklist Item", not on fieldtype alone.
		body = _extract_function(self.source, "renderChecklistFields")
		self.assertIn('field.fieldtype === "Table"', body)
		self.assertIn('field.options === "Checklist Item"', body)
		# The walk must read the actual row array off the document for this
		# field, not a hardcoded fieldname.
		self.assertIn("doc[field.fieldname]", body)

	def test_summarize_checklist_answers_delegates_to_the_pure_counter(self):
		# PCD-1 task 4.5: the dialog's summary must be rewired to call the
		# node-tested erpnext.checklist_pure.countChecklistAnswers instead of
		# project.js's own ad hoc loop (which only excluded
		# CHECKLIST_NON_ANSWER_FIELDS, not CHECKLIST_HEADER_FIELDS -- the
		# notes:"No" bug PCD-1 fixes).
		body = _extract_function(self.source, "summarizeChecklistAnswers")
		self.assertIn("erpnext.checklist_pure.countChecklistAnswers", body)
		# The old ad hoc per-key loop must be gone from this function, not
		# just supplemented -- otherwise both the old (buggy) and new logic
		# could run side by side without either test catching it.
		self.assertNotIn("CHECKLIST_NON_ANSWER_FIELDS.has(key)", body)

	def test_count_excluded_is_the_union_of_non_answer_and_header_fields(self):
		# The union itself (not a swap -- the two sets are disjoint and a
		# swap would silently regress the vehicle_model/licence_plate/mileage
		# guard, per design [FIX-6]).
		self.assertIn(
			"new Set([...CHECKLIST_NON_ANSWER_FIELDS, ...CHECKLIST_HEADER_FIELDS])",
			self.source,
		)

	def test_section_note_fields_are_excluded_from_the_answer_count(self):
		# Same class of bug as the notes:"No" one PCD-1 already fixed, now with
		# 9 more free-text fields on the parent doc: countChecklistAnswers
		# walks every top-level key and counts a value of exactly "No" as an
		# answer, so a mechanic writing just "No" in a section note would
		# inflate that checklist's ✗ chip. The per-section note fieldnames are
		# derived from meta rather than listed, so a new section is covered
		# without touching this file.
		body = _extract_function(self.source, "summarizeChecklistAnswers")
		self.assertIn("checklistNoteFieldnames(doctype)", body)
		# ...and that the union is a union, not a swap: dropping
		# CHECKLIST_COUNT_EXCLUDED here would silently regress the
		# vehicle_model/licence_plate/mileage guard [FIX-6].
		self.assertIn("...CHECKLIST_COUNT_EXCLUDED", body)
		derive = _extract_function(self.source, "checklistNoteFieldnames")
		self.assertIn("isChecklistNoteField(f.fieldname)", derive)
		self.assertIn('const CHECKLIST_NOTE_SUFFIX = "_notes";', self.source)
		self.assertNotIn('"before_dsg_notes"', self.source)

	def test_empty_section_notes_are_not_rendered_in_the_dialog(self):
		# renderChecklistFields renders every non-header scalar field as a
		# label/value row, printing "—" when empty. With a note field per
		# section that is up to 4 empty rows of pure noise per checklist in a
		# modal whose whole job is a quick scan.
		body = _extract_function(self.source, "renderChecklistFields")
		self.assertIn("isChecklistNoteField(field.fieldname)", body)

	def test_free_text_notes_do_not_render_as_a_single_nowrap_value(self):
		# renderChecklistFieldRow paints every scalar as `.ckl-val`, which the
		# dialog stylesheet gives `white-space: nowrap; text-align: right`.
		# That is right for a Yes/No pill or a date and WRONG for a note: a
		# two-line note written by a mechanic renders as one unwrapped line
		# that runs off the card, so the modal shows the data but not all of
		# it. Notes get the same pre-wrap block the document-level note has.
		self.assertIn("function renderChecklistNoteRow(", self.source)
		body = _extract_function(self.source, "renderChecklistNoteRow")
		self.assertIn("ckl-notes", body)
		rows = _extract_function(self.source, "renderChecklistSectionRows")
		self.assertIn("renderChecklistNoteRow", rows)

	def test_note_block_style_actually_wraps(self):
		# The pre-wrap rule is the point of routing notes to their own block,
		# so pin it rather than trusting the class name.
		match = re.search(r"\.ckl-notes\s*\{([^}]*)\}", self.source)
		self.assertIsNotNone(match, ".ckl-notes rule not found")
		self.assertIn("pre-wrap", match.group(1))

	def test_document_level_note_label_comes_from_meta_not_a_literal(self):
		# The card printed a hardcoded __("Notes") heading over doc.notes. With
		# a note per section now also in the card, a heading that cannot
		# follow the JSON's relabel is exactly how the modal ends up
		# contradicting the form it summarises.
		body = _extract_function(self.source, "renderChecklistCard")
		self.assertNotIn('__("Notes")', body)
		self.assertIn("checklistFieldLabel(doctype, \"notes\"", body)

	def test_failed_hydration_is_not_silently_shown_as_an_empty_checklist(self):
		# The catch resets every child table to [] and the card then renders
		# "No checklist rows" -- indistinguishable from a genuinely empty
		# checklist. A service advisor reading that modal has no way to know
		# the fetch failed and the answers do exist.
		body = _extract_function(self.source, "hydrateChecklistDocs")
		catch_block = body.split("catch (error)")[1]
		self.assertIn("console.error", catch_block)
		self.assertIn("doc.__loadFailed = true", catch_block)
		card = _extract_function(self.source, "renderChecklistCard")
		self.assertIn("__loadFailed", card)

	def test_hydrate_checklist_docs_rename(self):
		# Task 4.6: attachChecklistFiles -> hydrateChecklistDocs, renamed
		# EVERYWHERE (definition and call site) -- not just added alongside
		# the old name.
		self.assertIn("function hydrateChecklistDocs(", self.source)
		self.assertIn("hydrateChecklistDocs(doctype, docs)", self.source)
		self.assertNotIn("attachChecklistFiles", self.source)

	def test_hydrate_checklist_docs_copies_checklist_item_child_tables(self):
		# get_list(fields: ["*"]) returns scalar parent fields only; child
		# table rows arrive only from frappe.db.get_doc(). If hydrate only
		# copies photos/files, the modal's grid renderer receives empty
		# arrival_items/job_items/etc. and shows "No checklist rows" even
		# when the checklist form itself has selected values.
		body = _extract_function(self.source, "hydrateChecklistDocs")
		self.assertIn("checklistItemTableFieldnames(doctype)", body)
		self.assertIn("doc[fieldname] = full[fieldname] || []", body)

	def test_checklist_item_row_render_includes_who_did_it(self):
		# Task 4.7: who_did_it must render beside each Checklist Item row's
		# answer in the detail view. Scoped to the row-rendering function
		# reached by the Table(Checklist Item) walk, not a bare file-wide
		# substring search (who_did_it could otherwise appear only in an
		# unrelated comment and still pass).
		body = _extract_function(self.source, "renderChecklistItemRow")
		self.assertIn("who_did_it", body)
		self.assertIn("row.description", body)

	def test_checklist_item_rows_render_as_a_quick_scan_grid(self):
		# The Project "View Checklists" dialog must show converted
		# Checklist Item child rows as a compact read-only grid, not as a
		# stack of label/value pills. Mechanics need to scan Description,
		# Yes/No/N/A, and Who Did It columns quickly without opening each
		# checklist.
		body = _extract_function(self.source, "renderChecklistItemGrid")
		self.assertIn("ckl-item-grid", body)
		for label in ("Description", "Yes", "No", "N/A", "Who Did It"):
			with self.subTest(label=label):
				self.assertIn(label, body)

	def test_hydrate_keeps_the_vehicle_zone_next_to_each_photo_url(self):
		# Checklist photos are filed against a part of the car
		# (Checklist Photo.zone, set by the vehicle diagram). Flattening the
		# rows to a bare url list -- which is what hydrate used to do --
		# throws that attribution away before the dialog can render it, and
		# no later stage can recover it.
		body = _extract_function(self.source, "hydrateChecklistDocs")
		self.assertIn("zone: row.zone", body)
		self.assertIn("url: row.image", body)

	def test_photo_tiles_are_labelled_with_their_vehicle_zone(self):
		# "Photo 1 / Photo 2 / Photo 3" tells a service advisor nothing.
		# The label must be the part of the car, resolved through the shared
		# vocabulary so the dialog and the checklist form never disagree.
		body = _extract_function(self.source, "renderChecklistCard")
		self.assertIn("erpnext.checklist_zones.label", body)

	def test_photos_are_ordered_by_where_they_sit_on_the_car(self):
		# Photos arrive in upload order, so same-zone shots end up scattered
		# across the tile strip. Ordering by the vocabulary's own order (the
		# order the parts are drawn) groups them without a heading, and is
		# stable across UI languages -- an alphabetical sort is not.
		body = _extract_function(self.source, "renderChecklistCard")
		self.assertIn("erpnext.checklist_zones.rank", body)
