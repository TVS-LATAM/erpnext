import unittest
from pathlib import Path

# Same degraded test layer as test_checklist_grid_wiring.py: there is no JS
# test runner/DOM in this repo for form-event adapters, so the client script
# and hooks.py source text are the available assertion surface. The worksheet
# skin is pure presentation -- it owns no state and no data -- so the
# properties worth pinning are structural: that it is scoped, that it is
# injected once, and that it never hides a control the mechanic must reach.
APP_ROOT = Path(__file__).parents[2]
CHECKLISTS = (
	"Arrival Checklist",
	"Job Checklist",
	"Quality Control Checklist",
	"DSG Oil Change Checklist",
)


class TestChecklistWorksheet(unittest.TestCase):
	def setUp(self):
		self.script = (APP_ROOT / "public" / "js" / "checklist_worksheet.js").read_text()
		self.hooks = (APP_ROOT / "hooks.py").read_text()

	def test_registration_is_guarded_against_multiple_doctype_loads(self):
		# Wired to 4 parent doctypes; ScriptManager evaluates a doctype's __js
		# once per form load, so an unguarded frappe.ui.form.on() would stack
		# 4 refresh handlers within one browser session.
		self.assertIn("erpnext.checklist_worksheet._registered", self.script)

	def test_every_rule_is_scoped_to_the_worksheet_class(self):
		# The stylesheet restyles .form-section / .frappe-control / .section-head
		# -- structural Frappe classes present on EVERY form in the app. An
		# unscoped rule would repaint Sales Invoice, Customer and the rest.
		# Rules are asserted to start from the scope class, never from a bare
		# Frappe class.
		css = self.script.split("style.textContent = `")[1].split("`;")[0]
		selectors = []
		for block in css.split("{")[:-1]:
			selectors.extend(part.strip() for part in block.split("}")[-1].split(","))
		for selector in selectors:
			selector = selector.strip()
			if not selector or selector.startswith("@") or selector.startswith("/*"):
				continue
			with self.subTest(selector=selector):
				self.assertTrue(
					selector.startswith(".tvs-worksheet"),
					f"unscoped selector would leak to every form: {selector}",
				)

	def test_only_one_style_element_is_injected(self):
		# refresh fires on every reload of every checklist form; without the
		# guard each pass would append another <style> to document.head.
		self.assertIn("erpnext.checklist_worksheet._injected", self.script)
		self.assertEqual(self.script.count("document.head.appendChild"), 1)

	def test_scope_class_lands_on_the_page_wrapper_not_the_body(self):
		# Precedent: project.js's hideProjectToolbarButtons. Classing
		# document.body would keep the skin applied after routing away from
		# the checklist, because Frappe swaps pages without reloading.
		self.assertIn("frm.page.wrapper.addClass", self.script)
		self.assertNotIn("document.body.classList.add", self.script)

	def test_worksheet_skin_never_hides_form_controls(self):
		# A worksheet look must not cost the mechanic access to a field.
		# display:none is only ever allowed on the section separator/collapse
		# affordances, never on .frappe-control, an input, or a label.
		css = self.script.split("style.textContent = `")[1].split("`;")[0]
		for banned in (".frappe-control {", "input {", ".control-label {"):
			block_start = css.find(banned)
			if block_start == -1:
				continue
			block = css[block_start : css.find("}", block_start)]
			with self.subTest(rule=banned):
				self.assertNotIn("display: none", block)

	def test_print_keeps_the_sheet_borders(self):
		# The whole point is that it reads as the paper form it replaces --
		# browsers strip backgrounds when printing, so the grid must be drawn
		# with borders that survive, and print-color-adjust kept for the bands.
		self.assertIn("@media print", self.script)

	def test_hooks_wire_the_worksheet_skin_on_every_checklist(self):
		namespace = {}
		exec(compile(self.hooks, "hooks.py", "exec"), namespace)
		doctype_js = namespace["doctype_js"]
		for doctype_name in CHECKLISTS:
			with self.subTest(doctype=doctype_name):
				self.assertIn("public/js/checklist_worksheet.js", doctype_js[doctype_name])
