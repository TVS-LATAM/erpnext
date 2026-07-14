import unittest
from pathlib import Path


# No JS test runner/DOM exists in this repo for form-event adapters (design's
# documented "honest gap": checklist_grid.js is exercised by manual QA in the
# slice-3 PR, not automated). This follows the file's own established
# degraded-layer pattern (test_tvs_job_card_checklists.py's
# test_checklist_attachments_ui_is_wired /
# test_checklist_buttons_redirect_to_existing_instead_of_duplicating): assert
# on the client script and hooks.py source text as the available test layer.
APP_ROOT = Path(__file__).parents[2]
CHECKLISTS = (
	"Arrival Checklist",
	"Job Checklist",
	"Quality Control Checklist",
	"DSG Oil Change Checklist",
)


class TestChecklistGridWiring(unittest.TestCase):
	def setUp(self):
		self.grid_script = (APP_ROOT / "public" / "js" / "checklist_grid.js").read_text()
		self.hooks = (APP_ROOT / "hooks.py").read_text()

	def test_registration_is_guarded_against_multiple_doctype_loads(self):
		# checklist_grid.js is wired to 4 parent doctypes; without a guard the
		# top-level frappe.ui.form.on() calls would register 4x and every
		# tick would fire its handler 4 times.
		self.assertIn("erpnext.checklist_grid._registered", self.grid_script)

	def test_tick_handlers_are_registered_on_the_child_doctype(self):
		self.assertIn('frappe.ui.form.on("Checklist Item"', self.grid_script)
		for field in ("yes", "no", "na"):
			with self.subTest(field=field):
				self.assertIn(f"{field}(frm, cdt, cdn)", self.grid_script)

	def test_fixed_rows_are_locked_from_onload_post_render_not_refresh(self):
		# set_df_property("cannot_add_rows"/"cannot_delete_rows") is not a
		# JSON docfield prop; onload_post_render is the verified precedent
		# (frappe/custom/doctype/doctype_layout/doctype_layout.js:9-10), not
		# refresh.
		self.assertIn("onload_post_render: erpnext.checklist_grid.lockFixedRows", self.grid_script)
		self.assertIn('"cannot_add_rows"', self.grid_script)
		self.assertIn('"cannot_delete_rows"', self.grid_script)

	def test_internal_grid_row_selection_checkboxes_are_hidden_only_for_checklist_tables(self):
		# Frappe renders a leftmost `.grid-row-check` selector column for
		# every child table. The checklist grid has fixed rows and its own
		# Yes/No/N/A answer checkboxes, so that selector column is visual
		# noise here -- but hiding it globally would break unrelated grids.
		self.assertIn("hideRowSelectionCheckboxes", self.grid_script)
		self.assertIn("tvs-checklist-grid-hide-row-selection", self.grid_script)
		self.assertIn(".row-check", self.grid_script)
		self.assertIn(".grid-row-check", self.grid_script)
		self.assertIn("grid.wrapper", self.grid_script)

	def test_new_form_seeding_has_a_catch_that_alerts_the_user(self):
		# get_template() failing silently would leave a mechanic looking at
		# an empty grid with add-row already hidden and no explanation.
		self.assertIn(".catch(", self.grid_script)
		self.assertIn("frappe.show_alert", self.grid_script)

	def test_hooks_wire_pure_module_before_adapter_for_each_checklist(self):
		for doctype_name in CHECKLISTS:
			with self.subTest(doctype=doctype_name):
				self.assertIn(doctype_name, self.hooks)
		self.assertIn("public/js/checklist_pure.js", self.hooks)
		self.assertIn("public/js/checklist_grid.js", self.hooks)

		# Ordering must be checked WITHIN EACH checklist doctype's own
		# doctype_js list value, not via a global str.index() lookup on the
		# whole hooks.py source: "Project"'s entry also contains
		# "public/js/checklist_pure.js" and sorts before every checklist
		# doctype's block, so a global index() always resolves pure_index to
		# that unrelated entry regardless of what order the 4 checklist
		# doctypes actually declare -- making the old assertion vacuous
		# (proven: swapping a checklist's real list to
		# ["checklist_attachments.js", "checklist_grid.js",
		# "checklist_pure.js"] -- a real regression, since checklist_grid.js
		# calls erpnext.checklist_pure.* at registration time -- still made
		# the old assertion pass). hooks.py has no imports and no executable
		# side effects beyond literal assignments, so exec()-ing its source
		# to read the real doctype_js dict is safe and gives the actual
		# per-doctype list, instead of slicing raw text.
		namespace = {}
		exec(compile(self.hooks, "hooks.py", "exec"), namespace)
		doctype_js = namespace["doctype_js"]

		for doctype_name in CHECKLISTS:
			with self.subTest(doctype=doctype_name):
				scripts = doctype_js[doctype_name]
				self.assertIsInstance(scripts, list)
				# checklist_pure.js MUST come before checklist_grid.js in
				# THIS doctype's own list -- checklist_grid.js calls
				# erpnext.checklist_pure.* at load time via frappe.ui.form.on
				# setup.
				pure_index = scripts.index("public/js/checklist_pure.js")
				grid_index = scripts.index("public/js/checklist_grid.js")
				self.assertLess(pure_index, grid_index)

	def test_hooks_wire_pure_module_on_project_for_the_dialog(self):
		# project.js (slice 4) will call erpnext.checklist_pure.countChecklistAnswers.
		project_section_start = self.hooks.index('"Project"')
		# the value may span multiple lines as a list; widen the window
		project_block = self.hooks[project_section_start : project_section_start + 300]
		self.assertIn("public/js/checklist_pure.js", project_block)
