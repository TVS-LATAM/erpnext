import json
import unittest
from pathlib import Path


DOCTYPE_ROOT = Path(__file__).parents[2] / "projects" / "doctype"
CHECKLISTS = {
	"Arrival Checklist": "arrival_checklist",
	"Job Checklist": "job_checklist",
	"Quality Control Checklist": "quality_control_checklist",
	"DSG Oil Change Checklist": "dsg_oil_change_checklist",
}
ANSWER_OPTIONS = "\nYes\nNo\nN/A"
# All 4 checklists are converted from flat Select answer fields to
# `Checklist Item` child tables as of slice 6 (task 6.13 rewrite -- this
# module previously bridged slice 5's partial conversion via
# CONVERTED_TO_CHECKLIST_ITEM_TABLE; that bridge is gone, every doctype is
# converted now). Row-count/seeding coverage lives in each doctype's own
# dedicated grid test module (test_arrival_checklist_grid.py,
# test_job_checklist_grid.py, test_quality_control_checklist_grid.py,
# test_dsg_oil_change_checklist_grid.py), not here -- this module asserts
# only the shared cross-doctype metadata contract.
CHECKLIST_ITEM_TABLES = {
	"Arrival Checklist": {"arrival_items"},
	"Job Checklist": {"job_items"},
	"Quality Control Checklist": {"before_qc_items", "during_qc_items", "invoice_items"},
	"DSG Oil Change Checklist": {
		"before_dsg_items",
		"during_dsg_items",
		"after_dsg_items",
		"final_check_items",
	},
}


class TestTVSJobCardChecklists(unittest.TestCase):
	def test_checklist_metadata_contract(self):
		for doctype_name, directory_name in CHECKLISTS.items():
			with self.subTest(doctype=doctype_name):
				metadata = self._load_metadata(directory_name)
				fields = {field["fieldname"]: field for field in metadata["fields"]}

				self.assertEqual(metadata["name"], doctype_name)
				self.assertEqual(metadata["module"], "Projects")
				self.assertFalse(metadata.get("is_submittable", 0))

				self.assertEqual(fields["project"]["fieldtype"], "Link")
				self.assertEqual(fields["project"]["options"], "Project")
				# No field on these checklists is mandatory: `reqd` was deliberately
				# removed from all four doctypes. Asserted so that a re-export from the
				# Desk UI cannot silently reintroduce it.
				self.assertEqual(fields["project"].get("reqd", 0), 0)

				# CAM-1/CIG-1 (slice 5+6): every flat Select answer field has been
				# replaced by one or more `Checklist Item` child tables -- no
				# doctype should carry ANY flat Select answer field anymore.
				answer_fields = [
					field
					for field in metadata["fields"]
					if field["fieldtype"] == "Select" and field.get("options") == ANSWER_OPTIONS
				]
				self.assertEqual(answer_fields, [])

				# CIG-1: exactly the expected set of Checklist Item table
				# fieldnames per doctype -- this is the count/shape assertion
				# that replaces the old exact-flat-Select-fieldname checks.
				table_fields = {
					field["fieldname"]
					for field in metadata["fields"]
					if field["fieldtype"] == "Table" and field.get("options") == "Checklist Item"
				}
				self.assertEqual(table_fields, CHECKLIST_ITEM_TABLES[doctype_name])

				self.assertEqual(fields["notes"]["fieldtype"], "Text")
				self.assertEqual(fields["photos"]["fieldtype"], "Table")
				self.assertEqual(fields["photos"]["options"], "Checklist Photo")
				self.assertEqual(fields["attachments"]["fieldtype"], "Table")
				self.assertEqual(fields["attachments"]["options"], "Checklist Attachment")
				self.assertFalse(fields["photos"].get("reqd", 0))
				self.assertFalse(fields["attachments"].get("reqd", 0))

	def test_attachment_child_tables_contract(self):
		photo = self._load_metadata("checklist_photo")
		photo_fields = {f["fieldname"]: f for f in photo["fields"]}
		self.assertEqual(photo["name"], "Checklist Photo")
		self.assertTrue(photo.get("istable"))
		self.assertEqual(photo_fields["image"]["fieldtype"], "Attach Image")

		attachment = self._load_metadata("checklist_attachment")
		attachment_fields = {f["fieldname"]: f for f in attachment["fields"]}
		self.assertEqual(attachment["name"], "Checklist Attachment")
		self.assertTrue(attachment.get("istable"))
		self.assertEqual(attachment_fields["file"]["fieldtype"], "Attach")

	def test_checklist_item_child_table_contract(self):
		"""CIG-1/CIG-4: the shared `Checklist Item` child table -- read-only
		description, exclusive yes/no/na Check flags, free-text who_did_it --
		is the single row shape every checklist doctype seeds via
		`seed_rows` (checklist_templates.py)."""
		metadata = self._load_metadata("checklist_item")
		fields = {f["fieldname"]: f for f in metadata["fields"]}
		self.assertEqual(metadata["name"], "Checklist Item")
		self.assertTrue(metadata.get("istable"))
		self.assertEqual(fields["description"]["fieldtype"], "Data")
		self.assertTrue(fields["description"].get("read_only"))
		self.assertEqual(fields["yes"]["fieldtype"], "Check")
		self.assertEqual(fields["no"]["fieldtype"], "Check")
		self.assertEqual(fields["na"]["fieldtype"], "Check")
		self.assertEqual(fields["who_did_it"]["fieldtype"], "Data")

	def test_checklist_attachments_ui_is_wired(self):
		app_root = DOCTYPE_ROOT.parents[1]
		script_path = app_root / "public" / "js" / "checklist_attachments.js"
		self.assertTrue(script_path.exists(), f"Missing shared uploader script: {script_path}")
		script = script_path.read_text()
		hooks = (app_root / "hooks.py").read_text()
		for doctype_name in CHECKLISTS:
			with self.subTest(doctype=doctype_name):
				# the shared script registers a form handler for each checklist
				self.assertIn(f'"{doctype_name}"', script)
				# and the doctype is wired to the script via the doctype_js hook
				self.assertIn(doctype_name, hooks)
		self.assertIn("public/js/checklist_attachments.js", hooks)

	def test_project_job_card_exposes_checklist_entry_points(self):
		project_directory = DOCTYPE_ROOT / "project"
		client_script = (project_directory / "project.js").read_text()
		dashboard = (project_directory / "project_dashboard.py").read_text()

		for doctype_name in CHECKLISTS:
			with self.subTest(doctype=doctype_name):
				self.assertIn(f'"{doctype_name}"', client_script)
				self.assertIn(f'"{doctype_name}"', dashboard)

	def test_checklist_buttons_redirect_to_existing_instead_of_duplicating(self):
		# No JS test runner exists in this repo (no bundler/test config in
		# package.json). This follows the file's own established pattern
		# (test_checklist_attachments_ui_is_wired, above) of asserting on the
		# client script source as the available test layer.
		project_directory = DOCTYPE_ROOT / "project"
		client_script = (project_directory / "project.js").read_text()

		# setup_checklist_buttons must delegate to a helper that checks for an
		# existing checklist before creating one -- it must NOT unconditionally
		# call frappe.new_doc on every click, which would create a duplicate
		# every time regardless of what already exists for the project.
		setup_start = client_script.index("setup_checklist_buttons: function")
		setup_end = client_script.index("set_custom_buttons: function", setup_start)
		setup_block = client_script[setup_start:setup_end]
		self.assertNotIn(
			"() => frappe.new_doc(doctype, { project: frm.doc.name })",
			setup_block,
			"setup_checklist_buttons must not unconditionally create a new checklist on every click",
		)
		self.assertIn("openOrCreateChecklist", setup_block)

		# The redirect helper must look up existing checklists for the project,
		# order by most recently modified, route to it when one exists, and
		# fall back to frappe.new_doc only when none exist.
		helper_start = client_script.index("async function openOrCreateChecklist")
		helper_end = client_script.index("\n}", helper_start)
		helper_block = client_script[helper_start:helper_end]
		self.assertIn("frappe.db.get_list(doctype", helper_block)
		self.assertIn('order_by: "modified desc"', helper_block)
		self.assertIn('frappe.set_route("Form", doctype', helper_block)
		self.assertIn("frappe.new_doc(doctype, { project: frm.doc.name })", helper_block)

	def _load_metadata(self, directory_name):
		path = DOCTYPE_ROOT / directory_name / f"{directory_name}.json"
		self.assertTrue(path.exists(), f"Missing checklist metadata: {path}")
		return json.loads(path.read_text())
