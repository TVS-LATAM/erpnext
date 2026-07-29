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

	def test_answers_take_one_click_instead_of_activating_the_row_first(self):
		# The reason the stock grid was replaced at all: grid_row.js:1029-1031
		# calls toggle_editable_row() on the FIRST click of any cell, and only
		# that call swaps the painted static_area for the real control -- so
		# the checkbox does not exist yet when the first click lands, and
		# answering costs two clicks per row, 8-14 times per checklist.
		# The sheet binds one delegated handler that answers on click 1.
		self.assertIn('$table.on("click", ".tvs-ckl-ans"', self.grid_script)
		self.assertIn("event.preventDefault()", self.grid_script)

	def test_tick_flips_the_field_before_delegating_to_the_pure_cascade(self):
		# computeTickResult reads row[field] AFTER the flip
		# (checklist_pure.js:16-18) -- it only decides the OTHER two answers.
		# The stock grid got that flip from Frappe's change trigger; the sheet
		# binds no control to the field, so it must flip first or every tick
		# would be read as an untick and clear the row.
		self.assertIn("row[field] = row[field] ? 0 : 1;", self.grid_script)
		self.assertIn('erpnext.checklist_grid.onTick(frm, "Checklist Item", cdn, field)', self.grid_script)

	def test_tick_dirties_the_form_independently_of_the_cascade(self):
		# onTick only calls frm.dirty() when the cascade itself changed
		# something. Re-ticking an already-answered row is a cascade no-op,
		# but the flip above it is still a real edit -- without an unguarded
		# frm.dirty() that answer would be lost on navigate-away.
		click_handler = self.grid_script.split('$table.on("click", ".tvs-ckl-ans"')[1]
		self.assertIn("frm.dirty();", click_handler.split("erpnext.checklist_grid.onTick")[0])

	def test_sheet_container_survives_wrapper_being_the_grid_field_itself(self):
		# REGRESSION. grid.js:119 is `this.wrapper = $(template).appendTo(...)`
		# and that template's ROOT node is <div class="grid-field">, so
		# grid.wrapper IS .grid-field. jQuery find() searches descendants only,
		# so `grid.wrapper.find(".grid-field")` matches nothing and returns an
		# empty set -- the first cut of the sheet hit its own guard clause and
		# never rendered once, silently degrading to the stock grid.
		# hasClass first, find() only as the fallback for a future Frappe that
		# does nest it -- and renderSheet must go through that helper rather
		# than resolving the container itself.
		self.assertIn(
			'return grid.wrapper.hasClass("grid-field") ? grid.wrapper : grid.wrapper.find(".grid-field");',
			self.grid_script,
		)
		render_sheet = self.grid_script.split("erpnext.checklist_grid.renderSheet = function")[1]
		self.assertIn("erpnext.checklist_grid.gridFieldOf(grid)", render_sheet)
		self.assertNotIn('.find(".grid-field")', render_sheet)

	def test_wrapper_scoped_css_does_not_expect_a_nested_grid_field(self):
		# Same root cause on the CSS side: the class is applied to
		# grid.wrapper, which IS .grid-field, so any selector of the form
		# `.tvs-ckl-sheet-active .grid-field ...` needs a nested .grid-field
		# that does not exist.
		self.assertIn(".tvs-ckl-sheet-active > .control-label", self.grid_script)
		self.assertNotIn(".tvs-ckl-sheet-active .grid-field", self.grid_script)

	def test_native_grid_is_hidden_only_after_the_sheet_is_in_the_dom(self):
		# Degraded path: if building the sheet throws, the stock grid must
		# still be usable rather than leaving a section with no way to answer.
		# So the hiding class is added after the append, never before.
		body = self.grid_script.split("erpnext.checklist_grid.renderSheet = function")[1]
		append_at = body.index("$gridField.append($wrap)")
		activate_at = body.index('grid.wrapper.addClass("tvs-ckl-sheet-active")')
		self.assertLess(append_at, activate_at)

	def test_sheet_rebuilds_on_refresh_because_saving_replaces_child_docnames(self):
		# Rows are addressed by data-ckl-cdn. Saving replaces every child doc
		# and its docname, so handles cached in the DOM would point at docs
		# that no longer exist in locals.
		self.assertIn("refresh: erpnext.checklist_grid.renderSheets", self.grid_script)
		self.assertIn('$gridField.find(".tvs-ckl-sheet-wrap").remove()', self.grid_script)

	def test_row_data_is_never_interpolated_into_markup_or_selectors(self):
		# description and who_did_it are rendered with .text()/.val(), and
		# rows are located by filtering on the attribute rather than building
		# a selector string, so neither can inject markup or break the query.
		self.assertIn('$(\'<td class="tvs-ckl-desc"></td>\').text(description)', self.grid_script)
		self.assertIn(".val(row.who_did_it", self.grid_script)
		self.assertIn('return this.getAttribute("data-ckl-cdn") === cdn;', self.grid_script)

	def test_category_band_reads_the_docfield_label_instead_of_a_hardcoded_map(self):
		# The Excel sheets print the category vertically down the left edge
		# (`PRE`, `TIJDENS TESTRIT`, ...). That text already exists as data --
		# it is each Table docfield's own label -- so a hardcoded
		# doctype -> band map would be a second source of truth that silently
		# drifts the moment a section is renamed in the JSON.
		self.assertIn("df.label", self.grid_script)
		self.assertNotIn('"Before Quality Control"', self.grid_script)
		self.assertNotIn('"During DSG Oil Change"', self.grid_script)

	def test_hidden_table_label_stays_reachable_for_screen_readers(self):
		# The band cell replaces the visible .control-label, but a <td> is not
		# a heading and carries no accessible name for the region, so the real
		# label must be clipped rather than display:none'd.
		self.assertIn("clip: rect(0, 0, 0, 0)", self.grid_script)
		self.assertNotIn(".grid-field > .control-label {\n\t\t\tdisplay: none", self.grid_script)

	def test_only_one_style_element_is_injected_for_all_presentational_rules(self):
		# The presentational helpers run once per Checklist Item table (up to
		# 4 tables on the DSG checklist) on every form load; without a shared
		# guard each pass would append another <style> to document.head.
		self.assertIn("erpnext.checklist_grid._stylesInjected", self.grid_script)
		self.assertEqual(self.grid_script.count("document.head.appendChild"), 1)

	def test_new_form_seeding_has_a_catch_that_alerts_the_user(self):
		# get_template() failing silently would leave a mechanic looking at
		# an empty grid with add-row already hidden and no explanation.
		self.assertIn(".catch(", self.grid_script)
		self.assertIn("frappe.show_alert", self.grid_script)

	def test_section_note_field_is_derived_by_convention_not_a_hardcoded_map(self):
		# Same reasoning as the category band reading df.label: a
		# doctype -> note-fieldname map here would be a second source of truth
		# that drifts the moment a section is added or renamed in the JSON.
		# The table fieldname already encodes it (`before_dsg_items` ->
		# `before_dsg_notes`), and the derived name is validated against the
		# doctype's own meta so a table without a sibling note simply renders
		# no strip instead of binding to a field that does not exist.
		self.assertIn("erpnext.checklist_grid.noteFieldFor", self.grid_script)
		self.assertIn('"_items"', self.grid_script)
		self.assertIn('"_notes"', self.grid_script)
		self.assertNotIn('"before_dsg_notes"', self.grid_script)
		self.assertNotIn('"arrival_notes"', self.grid_script)

	def test_note_strip_lives_inside_the_wrap_that_rebuild_removes(self):
		# renderSheet rebuilds by removing .tvs-ckl-sheet-wrap and building a
		# fresh one. A note strip appended to $gridField instead would survive
		# that removal, so every refresh (each save fires one) would stack
		# another textarea under the sheet, all bound to the same field.
		body = self.grid_script.split("erpnext.checklist_grid.renderSheet = function")[1]
		append_note_at = body.index("erpnext.checklist_grid.renderNote(")
		append_wrap_at = body.index("$gridField.append($wrap)")
		self.assertLess(append_note_at, append_wrap_at)
		self.assertIn("$wrap", body[append_note_at : append_note_at + 200])

	def test_note_starts_collapsed_but_opens_when_it_already_has_content(self):
		# The whole point of the collapse is that an empty note costs one row
		# of height. But a note saved earlier must not be hidden behind a
		# closed toggle -- that is data the mechanic wrote, invisible until
		# someone happens to click. So: collapsed when empty, open when filled.
		note = self.grid_script.split("erpnext.checklist_grid.renderNote = function")[1]
		self.assertIn("Boolean(value)", note.split("expanded")[1][:200])
		self.assertIn("aria-expanded", note)

	def test_note_toggle_is_an_explicit_button_type(self):
		# A <button> with no type defaults to type="submit". These sheets are
		# rendered inside Frappe's form markup, so opening a note must not be
		# able to submit anything.
		self.assertIn('<button type="button"', self.grid_script)

	def test_note_writes_straight_to_the_parent_doc_and_dirties_the_form(self):
		# The note is a parent-doc field with no Control bound to it (the
		# docfield is hidden precisely so the sheet owns it), so nothing else
		# marks the form dirty -- without this the note is lost on
		# navigate-away exactly like an unguarded answer tick would be.
		#
		# "input" and not just "change": change fires on blur, so typing a note
		# and hitting Ctrl+S without leaving the textarea would save the
		# document without it.
		note = self.grid_script.split("erpnext.checklist_grid.renderNote = function")[1]
		change_handler = note.split('.on("input change"')[1]
		self.assertIn("frm.doc[noteField.fieldname] = ", change_handler)
		self.assertIn("frm.dirty();", change_handler)

	def test_note_is_read_only_when_the_grid_is(self):
		# Submitted/cancelled checklists and users without write permission get
		# a disabled textarea, the same way the answer checkboxes and the
		# who_did_it inputs already do.
		note = self.grid_script.split("erpnext.checklist_grid.renderNote = function")[1]
		self.assertIn('.prop("disabled", !editable)', note)

	def test_note_value_is_never_interpolated_into_markup(self):
		# Stored note text is arbitrary free text typed by a mechanic. It goes
		# in through .val()/.text(), never through an HTML string.
		note = self.grid_script.split("erpnext.checklist_grid.renderNote = function")[1]
		self.assertIn(".val(value)", note)
		self.assertNotIn("+ value +", note)

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

	def test_a_written_section_note_is_flagged_in_red_on_the_collapsed_strip(self):
		# The note strip collapses, so a note written on an earlier visit can
		# sit behind a closed toggle with nothing on screen saying it is there.
		# The old marker was a 6px grey dot -- at the bottom of a 32-row sheet
		# that reads as punctuation. It is now a red badge.
		self.assertIn("tvs-ckl-note-alert", self.grid_script)
		self.assertNotIn("tvs-ckl-note-dot", self.grid_script)
		self.assertIn("var(--red-500)", self.grid_script)

	def test_the_note_flag_is_not_carried_by_colour_alone(self):
		# Red on its own fails a red/green colour deficiency and a greyscale
		# print of the sheet. The badge carries a glyph and the filled strip
		# gains a left edge, so the flag survives both.
		self.assertIn("border-left: 3px solid var(--red-500)", self.grid_script)
		self.assertIn('.text("!")', self.grid_script)

	def test_the_note_flag_is_announced_to_screen_readers(self):
		# The caret is aria-hidden because aria-expanded already carries that
		# state. "There is a note in here" is available from nowhere else
		# while the strip is collapsed, so the badge must not be hidden too.
		alert_markup = self.grid_script.split("tvs-ckl-note-alert")[-1]
		self.assertIn('role="img"', self.grid_script)
		self.assertIn("This section has a note", alert_markup)

	def test_the_flag_only_appears_once_the_note_has_content(self):
		# An empty note must stay silent -- a red badge on all 6 sections of an
		# untouched checklist is noise that trains the mechanic to ignore it.
		self.assertIn(".tvs-ckl-note:not(.tvs-ckl-note-filled) .tvs-ckl-note-alert", self.grid_script)
		# and the class must be re-evaluated as the mechanic types, not only
		# at render time.
		self.assertIn('$note.toggleClass("tvs-ckl-note-filled", Boolean(next))', self.grid_script)

	def test_hooks_wire_pure_module_on_project_for_the_dialog(self):
		# project.js (slice 4) will call erpnext.checklist_pure.countChecklistAnswers.
		project_section_start = self.hooks.index('"Project"')
		# the value may span multiple lines as a list; widen the window
		project_block = self.hooks[project_section_start : project_section_start + 300]
		self.assertIn("public/js/checklist_pure.js", project_block)
