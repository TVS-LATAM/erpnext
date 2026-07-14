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

	def test_hydrate_checklist_docs_rename(self):
		# Task 4.6: attachChecklistFiles -> hydrateChecklistDocs, renamed
		# EVERYWHERE (definition and call site) -- not just added alongside
		# the old name.
		self.assertIn("function hydrateChecklistDocs(", self.source)
		self.assertIn("hydrateChecklistDocs(doctype, docs)", self.source)
		self.assertNotIn("attachChecklistFiles", self.source)

	def test_checklist_item_row_render_includes_who_did_it(self):
		# Task 4.7: who_did_it must render beside each Checklist Item row's
		# answer in the detail view. Scoped to the row-rendering function
		# reached by the Table(Checklist Item) walk, not a bare file-wide
		# substring search (who_did_it could otherwise appear only in an
		# unrelated comment and still pass).
		body = _extract_function(self.source, "renderChecklistItemRow")
		self.assertIn("who_did_it", body)
		self.assertIn("row.description", body)
