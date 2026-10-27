# Copyright (c) 2026, TVS and Contributors
# License: GNU General Public License v3. See license.txt

"""Keep a Customer's phone number in step with its Contacts and Projects.

A changed Customer.phone_number is validated in Customer.validate and pushed to
the linked Contacts and Projects in Customer.on_update. Everything runs inside
the request's single DB transaction: nothing here commits, so any failure rolls
back the Customer, the Contacts and the Projects together. Webhooks queued along
the way (Contact, Project and Customer "on_update") are only flushed after that
commit, so the Lambda that syncs ERPNext to Mongo never hears about a change
that was rolled back.
"""

import re

import frappe
from frappe import _
from frappe.integrations.doctype.webhook import run_webhooks
from frappe.utils import validate_phone_number

PROJECT_PHONE_FIELD = "custom_customers_phone_number"


def digits(phone) -> str:
	"""The number as stored across the system: digits only, country code included."""
	return re.sub(r"\D", "", str(phone or ""))


def get_phone_change(doc):
	"""(old, new) digits when an existing Customer's phone_number changed, else None."""
	if doc.is_new():
		return None
	before = doc.get_doc_before_save()
	if not before or (before.phone_number or "") == (doc.phone_number or ""):
		return None
	return digits(before.phone_number), digits(doc.phone_number)


def validate_phone_change(doc):
	"""Customer.validate: check a changed phone number and store it normalised."""
	change = get_phone_change(doc)
	if not change:
		return
	old, new = change

	if not (doc.phone_number or "").strip() or not new:
		frappe.throw(_("Phone number is required."), title=_("Invalid Phone Number"))

	validate_phone_number(doc.phone_number.strip(), throw=True)

	if new == old:
		frappe.throw(
			_("The new phone number is the same as the current one."), title=_("Phone Number Unchanged")
		)

	duplicate = frappe.db.sql(
		"""
		SELECT name, customer_name FROM `tabCustomer`
		WHERE name != %(name)s
			AND phone_number IS NOT NULL AND phone_number != ''
			AND REGEXP_REPLACE(phone_number, '[^0-9]', '') = %(digits)s
		LIMIT 1
		""",
		{"name": doc.name, "digits": new},
		as_dict=True,
	)
	if duplicate:
		frappe.throw(
			_("Phone number {0} is already used by customer {1}.").format(
				frappe.bold(new), frappe.bold(duplicate[0].customer_name or duplicate[0].name)
			),
			title=_("Duplicate Phone Number"),
		)

	doc.phone_number = new
	doc.flags.phone_number_changed = (old, new)


def propagate_phone_change(doc):
	"""Customer.on_update: push the new number to linked Contacts and Projects."""
	change = doc.flags.pop("phone_number_changed", None)
	if not change:
		return
	old, new = change

	_update_contacts(doc, old, new)
	_update_projects(doc, new)


def _linked_contacts(customer):
	return frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "link_doctype": "Customer", "link_name": customer},
		pluck="parent",
		distinct=True,
	)


def _update_contacts(doc, old, new):
	"""Replace the old number with the new one on every linked Contact. Contacts
	holding other numbers (e.g. a second person at a company) are left alone. The
	primary Contact always ends up with the new number as its primary mobile."""
	primary = doc.customer_primary_contact

	for name in _linked_contacts(doc.name):
		contact = frappe.get_doc("Contact", name)
		changed = _replace_number(contact, old, new) if old else False

		if name == primary:
			changed = _make_primary_mobile(contact, new) or changed

		if changed:
			contact.flags.ignore_mandatory = True
			contact.save(ignore_permissions=True)

	if primary:
		mobile_no = frappe.db.get_value("Contact", primary, "mobile_no")
		if mobile_no != doc.mobile_no:
			doc.db_set("mobile_no", mobile_no, update_modified=False)


def _replace_number(contact, old, new) -> bool:
	changed = False
	has_new = any(digits(row.phone) == new for row in contact.phone_nos)
	for row in list(contact.phone_nos):
		if digits(row.phone) != old:
			continue
		if has_new:
			# The contact already lists the new number: drop the old row, keep its flags.
			target = next(r for r in contact.phone_nos if digits(r.phone) == new)
			target.is_primary_phone = target.is_primary_phone or row.is_primary_phone
			target.is_primary_mobile_no = target.is_primary_mobile_no or row.is_primary_mobile_no
			contact.remove(row)
		else:
			row.phone = new
			has_new = True
		changed = True
	return changed


def _make_primary_mobile(contact, new) -> bool:
	row = next((r for r in contact.phone_nos if digits(r.phone) == new), None)
	if row and row.is_primary_mobile_no:
		return False

	for other in contact.phone_nos:
		other.is_primary_mobile_no = 0
	if row:
		row.is_primary_mobile_no = 1
	else:
		contact.append("phone_nos", {"phone": new, "is_primary_mobile_no": 1})
	return True


def _update_projects(doc, new):
	"""Write the number on every Project of the Customer without running the
	Project controller (welcome emails, costing), then queue each Project's
	"on_update" webhooks so the Lambda syncs them to Mongo after commit."""
	projects = frappe.get_all("Project", filters={"customer": doc.name}, pluck="name")
	if not projects:
		return

	frappe.db.set_value("Project", {"customer": doc.name}, PROJECT_PHONE_FIELD, new)

	for name in projects:
		project = frappe.get_doc("Project", name)
		run_webhooks(project, "on_update")
		project.notify_update()
