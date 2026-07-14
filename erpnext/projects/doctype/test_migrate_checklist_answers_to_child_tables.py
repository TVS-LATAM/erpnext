import unittest
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.patches.v14_0.migrate_checklist_answers_to_child_tables import execute
from erpnext.projects import checklist_templates as templates_module

PATCH_MODULE = "erpnext.patches.v14_0.migrate_checklist_answers_to_child_tables"
PATCHES_TXT = Path(__file__).resolve().parents[2] / "patches.txt"


def _strip_child_rows(doctype, name):
	"""Simulate the pre-migration state of a real legacy record: zero
	Checklist Item rows, exactly like the live dev docs `ARR-CHK-00001..3`
	(see `sdd/checklist-checkbox-grid/apply-progress`)."""
	frappe.db.delete("Checklist Item", {"parent": name, "parenttype": doctype})


def _set_legacy_value(doctype, name, fieldname, value):
	"""Write directly to the orphaned flat-Select column via raw SQL -- the
	column is no longer in the DocType meta so the ORM cannot set it."""
	frappe.db.sql(f"UPDATE `tab{doctype}` SET `{fieldname}`=%s WHERE name=%s", (value, name))


def _get_legacy_value(doctype, name, fieldname):
	return frappe.db.sql(
		f"SELECT `{fieldname}` FROM `tab{doctype}` WHERE name=%s", (name,), as_dict=True
	)[0][fieldname]


def _rows_by_description(doc, table_fieldname):
	return {row.description: row for row in doc.get(table_fieldname)}


def _snapshot_tables(doc, table_fieldnames):
	"""Byte-comparable snapshot of every row across every table -- used by
	the CAM-2 idempotency checks to assert a second `execute()` run is a
	true no-op (Task 6.12)."""
	return {
		tf: [(row.description, row.yes, row.no, row.na, row.who_did_it) for row in doc.get(tf)]
		for tf in table_fieldnames
	}


class TestMigrateChecklistAnswersToChildTables(FrappeTestCase):
	def _make_legacy_doc(self, doctype="Arrival Checklist", table_fieldnames=("arrival_items",)):
		"""A fresh doc, stripped of its `before_insert`-seeded rows so it looks
		exactly like a pre-existing (pre-conversion) record: zero rows, legacy
		columns still present and settable."""
		doc = frappe.get_doc({"doctype": doctype})
		doc.insert(ignore_permissions=True)
		_strip_child_rows(doctype, doc.name)
		doc.reload()
		for table_fieldname in table_fieldnames:
			self.assertEqual(doc.get(table_fieldname), [])
		return doc

	def test_migrates_yes_no_na_and_null_and_preserves_legacy_columns(self):
		"""CAM-1/CAM-3/CAM-4: the #1 hazard scenario -- a doc with NO child
		rows and legacy flat values must end up with the FULL fixed row
		count, correct per-row mapping, empty who_did_it on migrated rows,
		and untouched legacy columns."""
		doc = self._make_legacy_doc()
		_set_legacy_value("Arrival Checklist", doc.name, "appointment_confirmed", "Yes")
		_set_legacy_value("Arrival Checklist", doc.name, "vehicle_identity_verified", "No")
		_set_legacy_value("Arrival Checklist", doc.name, "customer_concerns_recorded", "N/A")
		# visible_damage_recorded and the rest stay NULL (Gate3).

		execute()

		doc.reload()
		rows = doc.get("arrival_items")
		self.assertEqual(len(rows), 8)  # CAM-3: full count regardless of NULLs

		by_description = _rows_by_description(doc, "arrival_items")

		confirmed = by_description["Appointment Confirmed"]
		self.assertEqual((confirmed.yes, confirmed.no, confirmed.na), (1, 0, 0))
		self.assertFalse(confirmed.who_did_it)

		identity = by_description["Vehicle Identity Verified"]
		self.assertEqual((identity.yes, identity.no, identity.na), (0, 1, 0))

		concerns = by_description["Customer Concerns Recorded"]
		self.assertEqual((concerns.yes, concerns.no, concerns.na), (0, 0, 1))

		damage = by_description["Visible Damage Recorded"]
		self.assertEqual((damage.yes, damage.no, damage.na), (0, 0, 0))  # NULL -> unanswered
		self.assertFalse(damage.who_did_it)

		# CAM-4: legacy columns are never dropped or blanked.
		self.assertEqual(_get_legacy_value("Arrival Checklist", doc.name, "appointment_confirmed"), "Yes")
		self.assertEqual(
			_get_legacy_value("Arrival Checklist", doc.name, "vehicle_identity_verified"), "No"
		)

	def test_drift_value_left_unset_and_logged_as_joined_string(self):
		"""Refinement 1 (5.12) + Refinement 5 (5.16): a non-conforming value
		is never silently mapped to 0/0/0 -- it is left unset and logged via
		a single joined string, not a raw list repr."""
		doc = self._make_legacy_doc()
		_set_legacy_value("Arrival Checklist", doc.name, "appointment_confirmed", "MAYBE")
		_set_legacy_value("Arrival Checklist", doc.name, "vehicle_identity_verified", " Yes")  # stray whitespace, not an exact match

		with patch(f"{PATCH_MODULE}.frappe.log_error") as mock_log_error:
			execute()

		doc.reload()
		by_description = _rows_by_description(doc, "arrival_items")

		confirmed = by_description["Appointment Confirmed"]
		self.assertEqual((confirmed.yes, confirmed.no, confirmed.na), (0, 0, 0))

		identity = by_description["Vehicle Identity Verified"]
		self.assertEqual((identity.yes, identity.no, identity.na), (0, 0, 0))

		mock_log_error.assert_called_once()
		message = mock_log_error.call_args.kwargs["message"]
		self.assertIsInstance(message, str)
		self.assertIn("MAYBE", message)
		self.assertIn(" Yes", message)
		self.assertIn(doc.name, message)

	def test_second_run_does_not_change_modified_timestamp(self):
		"""Refinement 2 (5.13): doc.save() is gated on a `changed` flag --
		re-running the patch on an already-migrated record must not touch
		`modified`."""
		doc = self._make_legacy_doc()
		_set_legacy_value("Arrival Checklist", doc.name, "appointment_confirmed", "Yes")

		execute()
		doc.reload()
		modified_after_first_run = doc.modified

		execute()
		doc.reload()
		self.assertEqual(doc.modified, modified_after_first_run)

	def test_second_run_is_byte_identical_idempotent(self):
		"""CAM-2 (5.17): re-running `execute()` twice produces byte-identical
		rows/values -- no duplicate rows, no altered values."""
		doc = self._make_legacy_doc()
		_set_legacy_value("Arrival Checklist", doc.name, "appointment_confirmed", "Yes")
		_set_legacy_value("Arrival Checklist", doc.name, "vehicle_identity_verified", "No")

		execute()
		doc.reload()
		snapshot_1 = [
			(row.description, row.yes, row.no, row.na, row.who_did_it) for row in doc.get("arrival_items")
		]

		execute()
		doc.reload()
		snapshot_2 = [
			(row.description, row.yes, row.no, row.na, row.who_did_it) for row in doc.get("arrival_items")
		]

		self.assertEqual(len(snapshot_2), 8)
		self.assertEqual(snapshot_1, snapshot_2)

	def test_duplicate_description_within_a_table_raises(self):
		"""Refinement 3 (5.14): defends against silent first-match-wins if a
		table ever gains two rows sharing the same description."""
		doc = self._make_legacy_doc()
		_set_legacy_value("Arrival Checklist", doc.name, "appointment_confirmed", "Yes")

		original_rows = templates_module.CHECKLIST_TEMPLATES["Arrival Checklist"]["arrival_items"]
		duplicated_rows = original_rows + [("appointment_confirmed", "Appointment Confirmed")]
		templates_module.CHECKLIST_TEMPLATES["Arrival Checklist"]["arrival_items"] = duplicated_rows
		try:
			with self.assertRaises(Exception):
				execute()
		finally:
			templates_module.CHECKLIST_TEMPLATES["Arrival Checklist"]["arrival_items"] = original_rows

	def test_doctype_with_no_legacy_columns_present_is_skipped_safely(self):
		"""CAM-2: a doctype whose legacy flat columns are already absent is
		skipped without error (Gate1). Intercepts only Arrival Checklist's own
		`SHOW COLUMNS` call (forwarding every other query untouched) to avoid
		mutating real schema via `ALTER TABLE ... DROP COLUMN`."""
		original_sql = frappe.db.sql

		def fake_sql(query, *args, **kwargs):
			if "SHOW COLUMNS" in query and "tabArrival Checklist" in query:
				return []
			return original_sql(query, *args, **kwargs)

		with patch.object(frappe.db, "sql", side_effect=fake_sql):
			execute()  # must not raise even though Arrival's columns look "absent"

	def test_patch_registered_in_patches_txt_post_model_sync(self):
		"""Task 5.11: registered under [post_model_sync], after the last
		custom entry (house precedent: migrate_checklist_attachments_to_child_tables)."""
		content = PATCHES_TXT.read_text()
		post_model_sync_section = content.split("[post_model_sync]", 1)[1]
		self.assertIn(
			"erpnext.patches.v14_0.migrate_checklist_answers_to_child_tables",
			post_model_sync_section,
		)

	def test_quality_control_migration_splits_10_14_6_no_cross_section_misrouting(self):
		"""Task 6.9/6.10 -- CAM-1/CAM-3: Quality Control's 30 legacy flat Select
		columns must route into the correct one of its 3 section tables, split
		10/14/6 (NEVER 11/13/6). Zero patch code changes were needed for this --
		the `meta.has_field` guard (5.10) auto-admits QC the moment its JSON
		conversion (6.1-6.4) lands; this test exercises that admission plus the
		first-ever multi-table iteration inside a single record (Arrival/Job
		only ever exercised a single table)."""
		doc = self._make_legacy_doc(
			"Quality Control Checklist",
			table_fieldnames=("before_qc_items", "during_qc_items", "invoice_items"),
		)
		for legacy_fieldname, _table_fieldname, _description in templates_module.iter_legacy_columns(
			"Quality Control Checklist"
		):
			_set_legacy_value("Quality Control Checklist", doc.name, legacy_fieldname, "Yes")

		execute()

		doc.reload()
		before_rows = doc.get("before_qc_items")
		during_rows = doc.get("during_qc_items")
		invoice_rows = doc.get("invoice_items")
		self.assertEqual(len(before_rows), 10)
		self.assertEqual(len(during_rows), 14)
		self.assertEqual(len(invoice_rows), 6)

		# No cross-section misrouting: every row's description must belong to
		# THAT table's own template list, not another section's.
		expected_descriptions_by_table = {
			table_fieldname: {description for _legacy, description in rows}
			for table_fieldname, rows in templates_module.CHECKLIST_TEMPLATES[
				"Quality Control Checklist"
			].items()
		}
		for table_fieldname, rows in (
			("before_qc_items", before_rows),
			("during_qc_items", during_rows),
			("invoice_items", invoice_rows),
		):
			for row in rows:
				self.assertIn(row.description, expected_descriptions_by_table[table_fieldname])
				self.assertEqual((row.yes, row.no, row.na), (1, 0, 0))
				self.assertFalse(row.who_did_it)

	def test_dsg_oil_change_migration_splits_7_4_4_5_no_cross_section_misrouting(self):
		"""Task 6.9/6.11 -- CAM-1/CAM-3: DSG Oil Change's 20 legacy flat Select
		columns must route into the correct one of its 4 section tables, split
		7/4/4/5."""
		doc = self._make_legacy_doc(
			"DSG Oil Change Checklist",
			table_fieldnames=("before_dsg_items", "during_dsg_items", "after_dsg_items", "final_check_items"),
		)
		for legacy_fieldname, _table_fieldname, _description in templates_module.iter_legacy_columns(
			"DSG Oil Change Checklist"
		):
			_set_legacy_value("DSG Oil Change Checklist", doc.name, legacy_fieldname, "No")

		execute()

		doc.reload()
		before_rows = doc.get("before_dsg_items")
		during_rows = doc.get("during_dsg_items")
		after_rows = doc.get("after_dsg_items")
		final_rows = doc.get("final_check_items")
		self.assertEqual(len(before_rows), 7)
		self.assertEqual(len(during_rows), 4)
		self.assertEqual(len(after_rows), 4)
		self.assertEqual(len(final_rows), 5)

		expected_descriptions_by_table = {
			table_fieldname: {description for _legacy, description in rows}
			for table_fieldname, rows in templates_module.CHECKLIST_TEMPLATES[
				"DSG Oil Change Checklist"
			].items()
		}
		for table_fieldname, rows in (
			("before_dsg_items", before_rows),
			("during_dsg_items", during_rows),
			("after_dsg_items", after_rows),
			("final_check_items", final_rows),
		):
			for row in rows:
				self.assertIn(row.description, expected_descriptions_by_table[table_fieldname])
				self.assertEqual((row.yes, row.no, row.na), (0, 1, 0))
				self.assertFalse(row.who_did_it)

	def test_quality_control_misrouted_template_is_caught_by_this_test(self):
		"""Sensitivity proof for the two tests above (a test that cannot fail is
		worthless): temporarily swap one row's section assignment in
		CHECKLIST_TEMPLATES (before_qc_items <-> during_qc_items) and confirm
		the split-count assertion actually catches the misrouting, exactly the
		class of bug 6.10 exists to guard against."""
		before_items = templates_module.CHECKLIST_TEMPLATES["Quality Control Checklist"]["before_qc_items"]
		during_items = templates_module.CHECKLIST_TEMPLATES["Quality Control Checklist"]["during_qc_items"]
		moved_row = before_items[0]
		corrupted_before = before_items[1:]  # now 9
		corrupted_during = during_items + [moved_row]  # now 15
		templates_module.CHECKLIST_TEMPLATES["Quality Control Checklist"]["before_qc_items"] = corrupted_before
		templates_module.CHECKLIST_TEMPLATES["Quality Control Checklist"]["during_qc_items"] = corrupted_during
		try:
			doc = self._make_legacy_doc(
				"Quality Control Checklist",
				table_fieldnames=("before_qc_items", "during_qc_items", "invoice_items"),
			)
			execute()
			doc.reload()
			with self.assertRaises(AssertionError):
				self.assertEqual(len(doc.get("before_qc_items")), 10)
				self.assertEqual(len(doc.get("during_qc_items")), 14)
		finally:
			templates_module.CHECKLIST_TEMPLATES["Quality Control Checklist"]["before_qc_items"] = before_items
			templates_module.CHECKLIST_TEMPLATES["Quality Control Checklist"]["during_qc_items"] = during_items

	def test_quality_control_and_dsg_second_run_byte_identical(self):
		"""Task 6.12 -- CAM-2: re-running `execute()` on already-migrated QC and
		DSG records must be a true no-op -- byte-identical rows and unchanged
		`modified` on both."""
		qc = self._make_legacy_doc(
			"Quality Control Checklist",
			table_fieldnames=("before_qc_items", "during_qc_items", "invoice_items"),
		)
		_set_legacy_value("Quality Control Checklist", qc.name, "customer_complaints_resolved", "Yes")
		_set_legacy_value("Quality Control Checklist", qc.name, "invoice_paid", "N/A")

		dsg = self._make_legacy_doc(
			"DSG Oil Change Checklist",
			table_fieldnames=("before_dsg_items", "during_dsg_items", "after_dsg_items", "final_check_items"),
		)
		_set_legacy_value("DSG Oil Change Checklist", dsg.name, "appointment_scheduled_in_erp", "No")
		_set_legacy_value("DSG Oil Change Checklist", dsg.name, "vehicle_ready_for_delivery", "Yes")

		qc_tables = ("before_qc_items", "during_qc_items", "invoice_items")
		dsg_tables = ("before_dsg_items", "during_dsg_items", "after_dsg_items", "final_check_items")

		execute()
		qc.reload()
		dsg.reload()
		qc_modified_1, dsg_modified_1 = qc.modified, dsg.modified
		qc_snapshot_1 = _snapshot_tables(qc, qc_tables)
		dsg_snapshot_1 = _snapshot_tables(dsg, dsg_tables)

		execute()
		qc.reload()
		dsg.reload()

		self.assertEqual(qc.modified, qc_modified_1)
		self.assertEqual(dsg.modified, dsg_modified_1)
		self.assertEqual(_snapshot_tables(qc, qc_tables), qc_snapshot_1)
		self.assertEqual(_snapshot_tables(dsg, dsg_tables), dsg_snapshot_1)


if __name__ == "__main__":
	unittest.main()
