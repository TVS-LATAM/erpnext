import json
import re
import unittest
from pathlib import Path

# Source-text assertion layer, same as test_checklist_grid_wiring.py (no JS
# runner/DOM in this repo). The diagram is the only place in the checklists
# where a photo acquires a vehicle zone, so the invariants pinned here are the
# ones that would silently lose that attribution: the zone must reach the
# child row, every drawn shape must be a real zone, and zone keys must agree
# between the SVG and the label map.
APP_ROOT = Path(__file__).parents[2]
CHECKLISTS = (
	"Arrival Checklist",
	"Job Checklist",
	"Quality Control Checklist",
	"DSG Oil Change Checklist",
)


class TestChecklistPhotoZoneField(unittest.TestCase):
	def setUp(self):
		path = APP_ROOT / "projects" / "doctype" / "checklist_photo" / "checklist_photo.json"
		self.meta = json.loads(path.read_text())
		self.fields = {field["fieldname"]: field for field in self.meta["fields"]}

	def test_photo_rows_carry_the_vehicle_zone(self):
		self.assertIn("zone", self.fields)

	def test_zone_is_data_not_select(self):
		# The zone vocabulary is defined by the SVG in
		# checklist_vehicle_diagram.js -- the shapes ARE the options. A Select
		# would put a second copy of that list in the doctype JSON, and adding
		# a zone to the diagram would then silently fail validation on save
		# until someone remembered to patch the JSON too.
		self.assertEqual(self.fields["zone"]["fieldtype"], "Data")

	def test_zone_is_not_mandatory(self):
		# Photos uploaded through the plain "Upload photos" button carry no
		# zone (they are general shots). Making it reqd would break that path
		# and every row already in production.
		self.assertFalse(self.fields["zone"].get("reqd"))

	def test_zone_is_read_only_in_the_ui(self):
		# The zone is assigned by clicking a region of the diagram. A free
		# text input would let a mechanic type a key that matches no shape,
		# producing a photo that is filed nowhere and renders under a zone
		# heading that does not exist on the diagram.
		self.assertEqual(self.fields["zone"].get("read_only"), 1)


class TestChecklistZoneVocabulary(unittest.TestCase):
	"""The zone key -> label map is used by three callers that do NOT all load
	the diagram: the diagram itself, the checklist galleries, and the Project
	"View Checklists" dialog (project.js). It therefore lives in its own
	module, the same way checklist_pure.js was split out so the dialog could
	count answers without pulling in the grid adapter."""

	def setUp(self):
		public = APP_ROOT / "public" / "js"
		self.zones = (public / "checklist_zones.js").read_text()
		self.diagram = (public / "checklist_vehicle_diagram.js").read_text()
		self.attachments = (public / "checklist_attachments.js").read_text()
		self.project_js = (APP_ROOT / "projects" / "doctype" / "project" / "project.js").read_text()
		self.hooks = (APP_ROOT / "hooks.py").read_text()

	def test_labels_are_translated_at_call_time_not_at_module_scope(self):
		# project.js documents this hazard on PROJECT_CHECKLIST_DOCTYPES:
		# a __() evaluated while the module is still being loaded resolves
		# against whatever translation dictionary happens to be in place then.
		# So the map holds source strings and label() translates.
		labels = self.zones.split("erpnext.checklist_zones.LABELS = {")[1].split("};")[0]
		self.assertNotIn("__(", labels)
		self.assertIn("__(", self.zones.split("erpnext.checklist_zones.label = function")[1])

	def test_every_caller_reads_the_shared_vocabulary(self):
		# The failure this prevents is three drifting copies of the same
		# list -- the dialog labelling a photo "right_rear_door" while the
		# form calls it "Right Rear Door".
		for name, source in (
			("checklist_vehicle_diagram.js", self.diagram),
			("checklist_attachments.js", self.attachments),
			("project.js", self.project_js),
		):
			with self.subTest(caller=name):
				self.assertIn("erpnext.checklist_zones", source)

	def test_the_diagram_no_longer_owns_its_own_label_map(self):
		# Not "supplemented alongside" -- moved. A leftover local map is a
		# second source of truth that the set-equality test below would stop
		# covering.
		self.assertNotIn("erpnext.checklist_diagram.ZONE_LABELS", self.diagram)

	def test_hooks_load_the_vocabulary_before_every_consumer(self):
		namespace = {}
		exec(compile(self.hooks, "hooks.py", "exec"), namespace)
		doctype_js = namespace["doctype_js"]

		for doctype_name in CHECKLISTS:
			with self.subTest(doctype=doctype_name):
				scripts = doctype_js[doctype_name]
				zones_index = scripts.index("public/js/checklist_zones.js")
				self.assertLess(zones_index, scripts.index("public/js/checklist_attachments.js"))
				self.assertLess(zones_index, scripts.index("public/js/checklist_vehicle_diagram.js"))

		# project.js reads it for the "View Checklists" dialog, and Project
		# does NOT load the diagram -- which is the whole reason the
		# vocabulary is a separate file.
		self.assertIn("public/js/checklist_zones.js", doctype_js["Project"])
		self.assertNotIn("public/js/checklist_vehicle_diagram.js", doctype_js["Project"])


class TestChecklistPhotoEntryPoint(unittest.TestCase):
	"""Photos have exactly ONE entry point: the vehicle diagram. A second,
	plain "Upload photos" button next to it uploads without a zone, which is
	the unsorted pile the diagram exists to replace -- and two buttons for the
	same table is also how a mechanic ends up not knowing where a photo went.
	"""

	def setUp(self):
		public = APP_ROOT / "public" / "js"
		self.attachments = (public / "checklist_attachments.js").read_text()
		self.diagram = (public / "checklist_vehicle_diagram.js").read_text()

	def test_zoned_tables_render_no_standalone_upload_button(self):
		body = self.attachments.split("erpnext.checklists.renderTable = function")[1].split("\n};")[0]
		# The button is built only when the table has no diagram in front of
		# it -- file attachments still need theirs.
		self.assertIn("cfg.zoned", body)
		self.assertIn("showUploadButton", body)

	def test_unzoned_photos_keep_a_way_in(self):
		# Removing the button must not remove the CASE. A shot of the whole
		# car belongs to no panel, and Checklist Photo.zone is deliberately
		# optional -- so the diagram carries its own "General" target, which
		# calls the uploader with NO zone argument.
		self.assertIn("tvs-vd-general", self.diagram)
		self.assertIn("openUploader(frm, cfg)", self.diagram)

	def test_the_file_attachment_table_has_no_upload_button_either(self):
		# Workshop decision: nothing is attached at the checklist level any
		# more -- everything the mechanic documents goes in through the
		# vehicle diagram.
		self.assertIn("noUploads", self.attachments)

	def test_files_attached_before_that_decision_are_still_reachable(self):
		# Taking away the entry point must not take away the rows. Production
		# checklists already carry attachments, and hiding a stored file
		# behind a UI that no longer renders it is silent data loss -- the
		# file stays in the table, billable and undeletable, with no way to
		# open it. So the gallery keeps rendering (and keeps its delete
		# control); only the way IN is gone.
		gallery = self.attachments.split("erpnext.checklists.renderGallery = function")[1].split("\n};")[0]
		self.assertNotIn("noUploads", gallery)
		self.assertIn("renderTile", gallery)

	def test_a_table_with_nothing_to_show_collapses_entirely(self):
		# With no button and no rows, the attachments control would otherwise
		# render as an empty bordered strip -- on a worksheet that reads as a
		# broken row, not as absence.
		body = self.attachments.split("erpnext.checklists.renderTable = function")[1].split("\n};")[0]
		self.assertIn("ckl-blank", body)

	def test_the_photo_table_is_never_collapsed(self):
		# REGRESSION GUARD. A zoned table also has no upload button and starts
		# with no rows, so a collapse rule written as
		# `!showUploadButton && !hasRows` hides the photos control on EVERY
		# fresh checklist -- and the vehicle diagram is painted inside that
		# control, so the whole feature disappears on exactly the forms that
		# need it most. The diagram IS a zoned table's content, so it can
		# never be blank.
		body = self.attachments.split("erpnext.checklists.renderTable = function")[1].split("\n};")[0]
		blank = re.search(r"const blank = (.+);", body)
		self.assertIsNotNone(blank, "blank computation not found")
		self.assertIn("!cfg.zoned", blank.group(1))

	def test_no_empty_state_text_is_printed(self):
		# "Nothing uploaded yet" under an empty gallery is dead space that
		# reads as broken layout on a worksheet: the button (or the diagram)
		# already says what to do, and an empty diagram already shows every
		# panel grey with no counter.
		self.assertNotIn("Nothing uploaded yet", self.attachments)


class TestChecklistVehicleDiagram(unittest.TestCase):
	def setUp(self):
		public = APP_ROOT / "public" / "js"
		self.script = (public / "checklist_vehicle_diagram.js").read_text()
		self.zones = (public / "checklist_zones.js").read_text()
		self.attachments = (public / "checklist_attachments.js").read_text()
		self.hooks = (APP_ROOT / "hooks.py").read_text()

	def test_registration_is_guarded_against_multiple_doctype_loads(self):
		self.assertIn("erpnext.checklist_diagram._registered", self.script)

	def test_clicking_a_zone_uploads_into_that_zone(self):
		# The whole feature: the click handler must forward the zone key it
		# read off the shape into the uploader, not just open a generic one.
		self.assertIn('data-ckl-zone', self.script)
		self.assertIn("openUploader(frm, cfg, zone)", self.script)

	def test_uploader_writes_the_zone_onto_the_child_row(self):
		# openUploader lives in checklist_attachments.js; if it drops the zone
		# argument the diagram still "works" visually but every photo lands
		# unzoned.
		upload = self.attachments.split("erpnext.checklists.openUploader = function")[1]
		self.assertIn("zone", upload.split("{")[0])
		self.assertIn("row.zone = zone", upload)

	def test_drawn_zones_and_labelled_zones_are_the_same_set(self):
		# A zone drawn without a label renders a nameless tooltip and an
		# unnamed heading in the gallery. A label with no shape is the other
		# half of the same drift: checklist_attachments.js reads the label map
		# to decide the gallery's group ORDER, so a stale key there silently
		# reorders groups around a part that no longer exists.
		drawn = set(self.iter_zone_keys())
		self.assertTrue(drawn, "no zones declared")
		self.assertEqual(drawn, set(self.iter_label_keys()))

	def test_zone_keys_are_unique_across_views(self):
		# Left and right flanks are mirrored geometry; reusing the same key on
		# both would merge damage on opposite sides of the car into one bucket.
		keys = list(self.iter_zone_keys())
		self.assertEqual(len(keys), len(set(keys)), "duplicate zone key across views")

	def test_zones_are_labelled_for_screen_readers_and_hover(self):
		self.assertIn("<title>", self.script)
		self.assertIn("aria-label", self.script)

	def test_diagram_is_inert_when_the_form_is_read_only(self):
		self.assertIn("frm.read_only", self.script)
		self.assertIn("docstatus", self.script)

	def test_diagram_repaints_when_the_photo_table_changes(self):
		# Uploading through the diagram calls erpnext.checklists.setup to
		# repaint the gallery. Without a hook back into the diagram the zone
		# counters would stay stale until a full reload.
		self.assertIn("erpnext.checklists.afterRender", self.script)
		self.assertIn("erpnext.checklists.afterRender", self.attachments)

	def test_zone_keys_are_never_interpolated_into_a_jquery_selector(self):
		# Same rule the grid follows for docnames: keys are data, matched by
		# attribute read, not by building a selector string.
		self.assertNotIn('find(\'[data-ckl-zone="\' +', self.script)
		self.assertIn('getAttribute("data-ckl-zone")', self.script)

	def test_hooks_load_the_diagram_after_the_uploader_it_calls(self):
		namespace = {}
		exec(compile(self.hooks, "hooks.py", "exec"), namespace)
		doctype_js = namespace["doctype_js"]
		for doctype_name in CHECKLISTS:
			with self.subTest(doctype=doctype_name):
				scripts = doctype_js[doctype_name]
				attachments_index = scripts.index("public/js/checklist_attachments.js")
				diagram_index = scripts.index("public/js/checklist_vehicle_diagram.js")
				# Load order is handler-run order. The diagram paints itself
				# into the `photos` field wrapper that checklist_attachments.js
				# builds, and registers into its afterRender list.
				self.assertLess(attachments_index, diagram_index)

	def iter_zone_keys(self):
		"""Every `key:` declared inside the VIEWS zone definitions.

		Views themselves are identified by `id:`, not `key:`, precisely so
		this scan cannot mistake a view name for a zone name.
		"""
		views = self.script.split("erpnext.checklist_diagram.VIEWS = [")[1].split("\n];")[0]
		return re.findall(r'key:\s*"([a-z0-9_]+)"', views)

	def iter_label_keys(self):
		"""Every key of the shared LABELS object literal."""
		labels = self.zones.split("erpnext.checklist_zones.LABELS = {")[1].split("};")[0]
		return re.findall(r"^\s*([a-z0-9_]+):", labels, re.MULTILINE)
