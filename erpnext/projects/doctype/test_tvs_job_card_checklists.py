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
ANSWER_OPTIONS = "Yes\nNo\nN/A"


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
				self.assertEqual(fields["project"]["reqd"], 1)

				answer_fields = [
					field
					for field in metadata["fields"]
					if field["fieldtype"] == "Select" and field.get("options") == ANSWER_OPTIONS
				]
				self.assertTrue(answer_fields)
				self.assertTrue(all(field.get("reqd") == 1 for field in answer_fields))

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

	def test_quality_control_matches_source_form(self):
		required_fields = {
			"customer_complaints_resolved", "vehicle_drives_well", "engine_runs_well",
			"tuning_difference_noticeable", "faults_or_defects_noticed", "adaptation_values_saved",
			"delivery_system_scan_completed", "vehicle_fault_codes_cleared_before_qc",
			"vehicle_aligned", "steering_wheel_straight", "lift_leak_inspection_completed",
			"undertray_installed", "wheels_torqued", "engine_bay_covers_cleaned",
			"coolant_and_engine_oil_checked", "vehicle_fault_codes_cleared_after_qc",
			"trip_meter_reset", "dashboard_clock_set", "windows_initialized",
			"maintenance_notification_present", "defective_lamp_notification_present",
			"washer_fluid_notification_present", "vehicle_vacuumed", "vehicle_washed",
			"transport_costs_on_quote", "pickup_delivery_costs_on_quote",
			"loan_car_costs_on_quote", "fuel_costs_on_quote", "extra_work_on_quote",
			"invoice_paid",
		}
		self._assert_exact_answer_fields("quality_control_checklist", required_fields)

	def test_dsg_oil_change_matches_source_form(self):
		required_fields = {
			"appointment_scheduled_in_erp", "oil_change_quote_submitted",
			"vehicle_modification_confirmed", "tvs_software_offered",
			"existing_complaints_confirmed", "pre_check_test_drive_completed",
			"vehicle_shifts_correctly", "dsg_oil_change_completed",
			"used_dsg_oil_sample_collected", "dsg_oil_filter_replaced",
			"fill_drain_plug_seal_replaced", "post_service_test_drive_completed",
			"dashboard_clock_set", "windows_initialized", "vehicle_fault_codes_cleared",
			"interior_exterior_cleanliness_checked", "service_record_completed",
			"invoice_submitted_in_erp", "invoice_paid_in_erp", "vehicle_ready_for_delivery",
		}
		self._assert_exact_answer_fields("dsg_oil_change_checklist", required_fields)

	def _assert_exact_answer_fields(self, directory_name, expected):
		metadata = self._load_metadata(directory_name)
		answer_fields = {
			field["fieldname"]
			for field in metadata["fields"]
			if field.get("options") == ANSWER_OPTIONS
		}
		self.assertEqual(answer_fields, expected)

	def test_project_job_card_exposes_checklist_entry_points(self):
		project_directory = DOCTYPE_ROOT / "project"
		client_script = (project_directory / "project.js").read_text()
		dashboard = (project_directory / "project_dashboard.py").read_text()

		for doctype_name in CHECKLISTS:
			with self.subTest(doctype=doctype_name):
				self.assertIn(f'"{doctype_name}"', client_script)
				self.assertIn(f'"{doctype_name}"', dashboard)

	def _load_metadata(self, directory_name):
		path = DOCTYPE_ROOT / directory_name / f"{directory_name}.json"
		self.assertTrue(path.exists(), f"Missing checklist metadata: {path}")
		return json.loads(path.read_text())
