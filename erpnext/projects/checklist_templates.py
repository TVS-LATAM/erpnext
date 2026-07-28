# Single source of truth for the checklist answer grid (CIG-1). Every
# consumer -- the `before_insert` controllers (slice 5/6), the client
# `onload` seeder (checklist_grid.js), and the flat-column -> child-table
# migration patch (slice 5/6) -- reads from CHECKLIST_TEMPLATES via the
# helpers below, instead of each keeping its own copy of the 68 mappings.
#
# Structure: {parent_doctype: {table_fieldname: [(legacy_select_fieldname, description), ...]}}
# `legacy_select_fieldname` is the join key the migration patch uses to read
# the pre-conversion flat Select column via raw SQL; list order is the row
# `idx` seeded into the child table.
#
# Tradeoff (accepted, see design Decision 1): the patch imports this module
# directly, so editing a doctype's legacy keys after deploy would retroactively
# change patch semantics. Never edit an existing entry's legacy fieldname
# after this ships -- add new templates instead.
import frappe
from frappe import _

CHECKLIST_TEMPLATES = {
	"Arrival Checklist": {
		"arrival_items": [
			("appointment_confirmed", "Appointment Confirmed"),
			("vehicle_identity_verified", "Vehicle Identity Verified"),
			("customer_concerns_recorded", "Customer Concerns Recorded"),
			("visible_damage_recorded", "Visible Damage Recorded"),
			("warning_lights_checked", "Warning Lights Checked"),
			("personal_items_noted", "Personal Items Noted"),
			("pre_work_test_drive_completed", "Pre-work Test Drive Completed"),
			("vehicle_safe_to_work_on", "Vehicle Safe to Work On"),
		],
	},
	# Carries the workshop's "TVS Proefrit CHECKLIST" sheet: 32 rows over the
	# sheet's own 6 sections, in sheet order. This REPLACED an earlier
	# 10-row generic "work execution" list that was not derived from any
	# customer sheet -- the workshop confirmed those rows can be discarded,
	# so their legacy fieldnames (work_instructions_reviewed, ...) are gone
	# from this table and the answer migration patch no longer carries them.
	# That is the one sanctioned exception to the "never edit an existing
	# entry's legacy fieldname" rule in this module's header.
	#
	# The legacy fieldnames below never existed as flat Select columns (this
	# doctype was already on child tables when the sheet landed), so the
	# patch's `existing_columns` gate skips every one of them. They are kept
	# only to hold the template's (legacy_fieldname, description) shape.
	"Job Checklist": {
		"pre_test_drive_items": [
			("basic_adjustment_completed", "Basic Adjustment Completed"),
			("test_drive_reason_known", "Reason for Test Drive Known"),
		],
		"test_drive_items": [
			("clutch_adapted_while_driving", "Clutch Adapted While Driving"),
			("clutch_adaptation_within_tolerance", "Clutch Adaptation Within Tolerance"),
			("clutch_full_throttle_within_tolerance", "Clutch Full Throttle Within Tolerance"),
			("clutch_free_of_vibration", "Clutch Free of Vibration While Driving"),
			("pulling_away_forwards_smooth", "Pulling Away Forwards Is Smooth"),
			("pulling_away_reverse_smooth", "Pulling Away in Reverse Is Smooth"),
			("gearbox_play_noticeable", "Gearbox Play Noticeable"),
			("gearbox_noises_audible", "Gearbox Noises Audible"),
			("shift_flares_observed", "Shift Flares Observed"),
			("oil_smell_detected", "Oil Smell Detected"),
			("oil_leakage_on_driveway", "Oil Leakage Observed on the Driveway"),
		],
		"fault_code_items": [
			("vehicle_free_of_faults", "Vehicle Free of Faults"),
			("engine_free_of_faults", "Engine Free of Faults"),
			("dsg_free_of_faults", "DSG Free of Faults"),
		],
		"tuning_items": [
			("flywheel_holds_torque", "Flywheel Holds the Torque"),
			("clutch_holds_torque", "Clutch Holds the Torque"),
			("lambda_correction_within_tolerance", "Lambda Correction Within Tolerance (+/- 10%)"),
			("boost_pressure_follows_spec", "Boost Pressure Follows Specified Value (+/- 0.1 bar)"),
			("knocking_within_tolerance", "Knocking Within Tolerance (4.5 max)"),
		],
		"status_items": [
			("vehicle_drives_well", "Vehicle Drives Well"),
			("engine_runs_well", "Engine Runs Well"),
			("tuning_clearly_noticeable", "Tuning Clearly Noticeable"),
			("no_remarks", "No Remarks"),
		],
		"final_check_items": [
			("full_vehicle_fault_scan_saved", "Full Vehicle Fault Code Scan Saved"),
			("adaptation_values_saved", "Adaptation Values Saved"),
			("vehicle_reassembled", "Vehicle Reassembled"),
			("steering_wheel_straight", "Steering Wheel Straight"),
			("interior_clean", "Interior Clean"),
			("exterior_clean", "Exterior Clean"),
			("ready_for_delivery", "Ready for Delivery"),
		],
	},
	"Quality Control Checklist": {
		"before_qc_items": [
			("customer_complaints_resolved", "Customer Complaints Resolved"),
			("vehicle_drives_well", "Vehicle Drives Well"),
			("engine_runs_well", "Engine Runs Well"),
			("tuning_difference_noticeable", "Tuning / Software Difference Noticeable"),
			("faults_or_defects_noticed", "Faults or Defects Noticed"),
			("adaptation_values_saved", "Adaptation Values Saved"),
			("delivery_system_scan_completed", "Delivery System Scan Completed"),
			("vehicle_fault_codes_cleared_before_qc", "Vehicle Fault Codes Cleared Before Quality Control"),
			("vehicle_aligned", "Vehicle Aligned"),
			("steering_wheel_straight", "Steering Wheel Straight"),
		],
		"during_qc_items": [
			("lift_leak_inspection_completed", "Vehicle Checked on Lift for Faults and Leaks"),
			("undertray_installed", "Undertray Installed"),
			("wheels_torqued", "Wheels Tightened with Torque Wrench"),
			("engine_bay_covers_cleaned", "Covers Under Hood Cleaned"),
			("coolant_and_engine_oil_checked", "Coolant and Engine Oil Level Checked"),
			("vehicle_fault_codes_cleared_after_qc", "Vehicle Fault Codes Cleared After Quality Control"),
			("trip_meter_reset", "Trip Meter Reset"),
			("dashboard_clock_set", "Dashboard Clock Set"),
			("windows_initialized", "Windows Initialized"),
			("maintenance_notification_present", "Maintenance Service Notification Present"),
			("defective_lamp_notification_present", "Defective Lamp Notification Present"),
			("washer_fluid_notification_present", "Windshield Washer Fluid Notification Present"),
			("vehicle_vacuumed", "Vehicle Vacuumed"),
			("vehicle_washed", "Vehicle Washed"),
		],
		"invoice_items": [
			("transport_costs_on_quote", "Transport Costs Included on Quote"),
			("pickup_delivery_costs_on_quote", "Pickup / Delivery Service Costs Included on Quote"),
			("loan_car_costs_on_quote", "Loan Car Costs Included on Quote"),
			("fuel_costs_on_quote", "Fuel Costs Included on Quote"),
			("extra_work_on_quote", "All Extra Work Included on Quote"),
			("invoice_paid", "Invoice Paid"),
		],
	},
	# Section table fieldnames below are DERIVED (not specified by design):
	# the source JSON's Section Break fieldnames are
	# before/during/after_dsg_oil_change_section + final_check_section; these
	# mirror the same abbreviation the QC template already uses
	# (before_quality_control_section -> before_qc_items), dropping
	# "oil_change" the same way QC drops "quality_control" -> "qc".
	"DSG Oil Change Checklist": {
		"before_dsg_items": [
			("appointment_scheduled_in_erp", "Appointment Scheduled in ERP"),
			("oil_change_quote_submitted", "Oil Change Quote Prepared and Submitted"),
			("vehicle_modification_confirmed", "Customer Asked Whether Vehicle Is Modified / Tuned"),
			("tvs_software_offered", "TVS Software Offered to Customer"),
			("existing_complaints_confirmed", "Customer Asked About Existing Complaints / Defects"),
			("pre_check_test_drive_completed", "Pre-check / Test Drive Completed"),
			("vehicle_shifts_correctly", "Vehicle Shifts Correctly and Oil Change Can Be Performed"),
		],
		"during_dsg_items": [
			("dsg_oil_change_completed", "DSG Oil Change Completed"),
			("used_dsg_oil_sample_collected", "Used DSG Oil Sample Collected with Brake Cleaner Container"),
			("dsg_oil_filter_replaced", "DSG Oil Filter Replaced"),
			("fill_drain_plug_seal_replaced", "Fill / Drain Plug Seal Replaced"),
		],
		"after_dsg_items": [
			("post_service_test_drive_completed", "DSG Post-service Test Drive Completed"),
			("dashboard_clock_set", "Dashboard Clock Set"),
			("windows_initialized", "Door Windows Initialized"),
			("vehicle_fault_codes_cleared", "Fault Codes Cleared for Entire Vehicle"),
		],
		"final_check_items": [
			(
				"interior_exterior_cleanliness_checked",
				"Steering Wheel, Gear Lever, Hood and Screens Checked for Dirty Marks",
			),
			("service_record_completed", "Maintenance Booklet / Digital Service Plan Completed"),
			("invoice_submitted_in_erp", "Invoice Submitted in ERP"),
			("invoice_paid_in_erp", "Invoice Paid in ERP"),
			("vehicle_ready_for_delivery", "All Steps Completed and Vehicle Ready for Delivery"),
		],
	},
}


def seed_rows(doc):
	"""Populate every Checklist Item table on `doc` from its template.

	Idempotent per table: a table that already holds rows is left untouched,
	so calling this twice in a row (client `onload` seed followed by the
	`before_insert` backstop, or a migration patch re-run) never duplicates
	rows. No-op for a doctype with no template (e.g. `Task`).
	"""
	tables = CHECKLIST_TEMPLATES.get(doc.doctype)
	if not tables:
		return
	for table_fieldname, rows in tables.items():
		if doc.get(table_fieldname):
			continue
		for _legacy_fieldname, description in rows:
			doc.append(table_fieldname, {"description": description})


def iter_legacy_columns(doctype):
	"""Yield (legacy_fieldname, table_fieldname, description) for `doctype`.

	Consumed by the flat-column -> child-table migration patch to know which
	raw SQL column feeds which child row and table.
	"""
	for table_fieldname, rows in CHECKLIST_TEMPLATES.get(doctype, {}).items():
		for legacy_fieldname, description in rows:
			yield legacy_fieldname, table_fieldname, description


@frappe.whitelist()
def get_template(doctype):
	"""Return `doctype`'s fixed row template, keyed by table fieldname.

	Consumed by the client on new-form `onload` to seed the grid before the
	first save: `before_insert` never sees a brand-new document because
	`frappe.model.get_new_doc` builds it entirely client-side (design
	Decision 2 / evidence 1).
	"""
	tables = CHECKLIST_TEMPLATES.get(doctype)
	if not tables:
		frappe.throw(_("No checklist template defined for {0}").format(doctype))
	return {
		table_fieldname: [{"description": description} for _legacy_fieldname, description in rows]
		for table_fieldname, rows in tables.items()
	}
