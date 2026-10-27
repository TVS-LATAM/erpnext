# Copyright (c) 2026, TVS and Contributors
# License: GNU General Public License v3. See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.selling.doctype.customer import customer_phone_sync

# Self-contained: no ERPNext test records are needed or created.
test_dependencies = []


class TestCustomerPhoneSync(FrappeTestCase):
	def setUp(self):
		# ERPNext's Contact after_insert hook commits; keep every test inside one
		# transaction so tearDown can roll it all back.
		self._commit = patch.object(frappe.db, "commit", lambda *a, **k: None)
		self._commit.start()
		frappe.local._webhook_queue = []
		self.company = frappe.db.get_value("Company", {}, "name")

	def tearDown(self):
		self._commit.stop()
		frappe.db.rollback()
		frappe.local._webhook_queue = []

	# helpers

	def make_customer(self, name, phone, customer_type="Individual", with_contact=True):
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": customer_type,
				"phone_number": phone,
				"mobile_no": phone if with_contact else None,
			}
		).insert(ignore_permissions=True)
		customer.reload()
		return customer

	def make_contact(self, customer, first_name, phone):
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": first_name,
				"links": [{"link_doctype": "Customer", "link_name": customer}],
			}
		)
		contact.add_phone(phone, is_primary_mobile_no=1)
		return contact.insert(ignore_permissions=True)

	def make_project(self, customer, suffix):
		return frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Phone sync test {customer} {suffix}",
				"customer": customer,
				"company": self.company,
				"plate": f"PS{suffix}",
			}
		).insert(ignore_permissions=True)

	def change_phone(self, customer, phone):
		customer = frappe.get_doc("Customer", customer.name)
		customer.phone_number = phone
		customer.save(ignore_permissions=True)
		return customer

	def queued_webhooks(self, doctype):
		return [
			(q.webhook.name, q.doc.name)
			for q in getattr(frappe.local, "_webhook_queue", None) or []
			if q.doc.doctype == doctype
		]

	# tests

	def test_propagates_to_contacts_and_projects(self):
		customer = self.make_customer("_PS Propagate", "31600000001")
		p1 = self.make_project(customer.name, "A1")
		p2 = self.make_project(customer.name, "A2")

		customer = self.change_phone(customer, "+31 6 0000 0002")

		self.assertEqual(frappe.db.get_value("Customer", customer.name, "phone_number"), "31600000002")
		self.assertEqual(frappe.db.get_value("Customer", customer.name, "mobile_no"), "31600000002")
		contact = frappe.get_doc("Contact", customer.customer_primary_contact)
		self.assertEqual(contact.mobile_no, "31600000002")
		self.assertEqual([r.phone for r in contact.phone_nos], ["31600000002"])
		for p in (p1, p2):
			self.assertEqual(
				frappe.db.get_value("Project", p.name, "custom_customers_phone_number"), "31600000002"
			)

	def test_queues_project_and_contact_webhooks(self):
		customer = self.make_customer("_PS Webhooks", "31600000011")
		project = self.make_project(customer.name, "W1")
		frappe.local._webhook_queue = []

		customer = self.change_phone(customer, "31600000012")

		project_hooks = frappe.get_all(
			"Webhook",
			filters={"webhook_doctype": "Project", "webhook_docevent": "on_update", "enabled": 1},
			pluck="name",
		)
		queued = self.queued_webhooks("Project")
		for hook in project_hooks:
			# A hook with a condition only fires when the project satisfies it,
			# the same rule a normal project save follows.
			cond = frappe.db.get_value("Webhook", hook, "condition")
			if not (cond or "").strip():
				self.assertIn((hook, project.name), queued)
		with patch.object(customer_phone_sync, "run_webhooks") as run:
			customer = self.change_phone(customer, "31600000013")
		run.assert_called_once()
		self.assertEqual(run.call_args.args[0].name, project.name)
		self.assertEqual(run.call_args.args[0].custom_customers_phone_number, "31600000013")
		self.assertEqual(run.call_args.args[1], "on_update")

	def test_other_contacts_keep_their_own_number(self):
		customer = self.make_customer("_PS Company", "31600000021", customer_type="Company")
		assistant = self.make_contact(customer.name, "Assistant", "31600000029")

		customer = self.change_phone(customer, "31600000022")

		self.assertEqual(frappe.db.get_value("Contact", assistant.name, "mobile_no"), "31600000029")
		self.assertEqual(
			frappe.db.get_value("Contact", customer.customer_primary_contact, "mobile_no"), "31600000022"
		)

	def test_rejects_duplicate_number(self):
		self.make_customer("_PS Owner", "31600000031")
		customer = self.make_customer("_PS Other", "31600000032")

		with self.assertRaises(frappe.ValidationError):
			self.change_phone(customer, "+31 6 0000 0031")

	def test_rejects_invalid_empty_and_unchanged(self):
		customer = self.make_customer("_PS Invalid", "31600000041")

		for bad in ("abc-not-a-number", "316000000419abc", "   ", "31 6 0000 0041"):
			with self.assertRaises(frappe.ValidationError, msg=bad):
				self.change_phone(customer, bad)

	def test_customer_without_contact_or_project(self):
		customer = self.make_customer("_PS Bare", "31600000051", with_contact=False)
		self.assertFalse(customer.customer_primary_contact)

		self.change_phone(customer, "31600000052")

		self.assertEqual(frappe.db.get_value("Customer", customer.name, "phone_number"), "31600000052")

	def test_verification_flag_is_kept(self):
		customer = self.make_customer("_PS Verified", "31600000061")
		frappe.db.set_value("Customer", customer.name, "is_phone_number_verified", 1)

		self.change_phone(customer, "31600000062")

		self.assertEqual(frappe.db.get_value("Customer", customer.name, "is_phone_number_verified"), 1)

	def test_failure_leaves_nothing_updated(self):
		customer = self.make_customer("_PS Rollback", "31600000071")
		project = self.make_project(customer.name, "R1")
		contact = customer.customer_primary_contact
		frappe.db.savepoint("before_phone_change")

		def fail(*args, **kwargs):
			raise frappe.ValidationError("project sync failed")

		with patch.object(customer_phone_sync, "run_webhooks", side_effect=fail):
			with self.assertRaises(frappe.ValidationError):
				self.change_phone(customer, "31600000072")

		# What the request handler does on an exception.
		frappe.db.rollback(save_point="before_phone_change")

		self.assertEqual(frappe.db.get_value("Customer", customer.name, "phone_number"), "31600000071")
		self.assertEqual(frappe.db.get_value("Contact", contact, "mobile_no"), "31600000071")
		self.assertEqual(
			frappe.db.get_value("Project", project.name, "custom_customers_phone_number"), "31600000071"
		)

	def test_other_field_save_does_not_touch_contacts(self):
		customer = self.make_customer("_PS Untouched", "31600000081")
		customer = frappe.get_doc("Customer", customer.name)
		customer.website = "https://example.com"
		with patch.object(customer_phone_sync, "_update_contacts") as update:
			customer.save(ignore_permissions=True)
		update.assert_not_called()
