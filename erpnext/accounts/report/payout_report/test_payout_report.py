# Copyright (c) 2026, TVS and contributors
# For license information, please see license.txt

"""
P1.1 and P1.2 — the payment amount the report attributes to one invoice must be
that invoice's own allocated share of a payment, and only of a payment that is
still valid.

P1.1: `fetch_payout_data` selects `pe.paid_amount AS paid_amount` — the WHOLE
Payment Entry total, denominated in `paid_from_account_currency`. A single
payment allocated across several invoices then shows its full amount against
EVERY one of them. `Payment Entry Reference` has no `base_allocated_amount`;
ERPNext's own controller converts with the reference row's own exchange rate,
so the report is fixed to do the same:
`per.allocated_amount * IFNULL(per.exchange_rate, 1)`.

P1.2: `docstatus` is filtered on `si` everywhere but never on `pe`, so a
cancelled Payment Entry still counts as money collected. The fix belongs in the
JOIN CONDITION (`ON ... AND pe.docstatus = 1`), never in the WHERE clause — a
WHERE-clause `pe.docstatus = 1` would discard the NULL-extended row a LEFT JOIN
produces for a genuinely unpaid invoice (NULL = 1 is UNKNOWN, and WHERE treats
UNKNOWN like FALSE), silently deleting every unpaid invoice from the report.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from erpnext.accounts.report.payout_report.payout_report import fetch_payout_data


class PayoutReportTestBase(FrappeTestCase):
	"""
	`--skip-before-tests` is mandatory on this bench (the `hrms` before_tests
	hook dies on an unrelated import), so erpnext's `_Test Company` fixtures are
	never seeded. The accounts are taken from a document the site already
	posted instead, mirroring test_vat_declaration.py / test_icp_declaration.py.
	"""

	def setUp(self):
		super().setUp()
		self.date = nowdate()

		template_name = frappe.db.get_value(
			"Sales Invoice", {"docstatus": 1, "is_return": 0}, "name", order_by="creation desc"
		)
		if not template_name:
			self.skipTest("no submitted Sales Invoice on this site to take accounts from")
		self.template = frappe.get_doc("Sales Invoice", template_name)
		self.company = self.template.company
		self.customer = self._customer()

	def _customer(self):
		# One customer per test. `bench run-tests` rolls the whole RUN back, not
		# each test, so two tests sharing a customer would see one another's
		# invoices and payments in the same period.
		name = f"Payout Report Test Customer {self._testMethodName[:50]}"
		if not frappe.db.exists("Customer", name):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_type": "Company",
					"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
					"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
					# A TVS custom field, mandatory on this site.
					"phone_number": "+31000000000",
				}
			).insert(ignore_permissions=True)
		return name

	def _invoice(self, rate):
		item = self.template.items[0]
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": self.customer,
				"company": self.company,
				"posting_date": self.date,
				"due_date": self.date,
				"currency": self.template.currency,
				"debit_to": self.template.debit_to,
				"update_stock": 0,
				"items": [
					{
						"item_code": item.item_code,
						"qty": 1,
						"rate": rate,
						"income_account": item.income_account,
						"cost_center": item.cost_center,
						"warehouse": item.warehouse,
					}
				],
			}
		)
		invoice.insert(ignore_permissions=True)
		invoice.submit()
		return invoice

	def _paid_to_account(self):
		return frappe.db.get_value(
			"Account",
			{"company": self.company, "account_type": "Cash", "is_group": 0},
			"name",
		) or frappe.db.get_value(
			"Account",
			{"company": self.company, "account_type": "Bank", "is_group": 0},
			"name",
		)

	def _payment_entry(self, allocations):
		"""
		Build one Payment Entry against one or more (invoice, allocated_amount)
		pairs, receiving the sum of the allocations. Built by hand rather than
		with get_payment_entry() because that helper only ever targets one
		document, and P1.1 needs one payment split across two invoices.
		"""
		total = sum(amount for _invoice, amount in allocations)
		pe = frappe.get_doc(
			{
				"doctype": "Payment Entry",
				"payment_type": "Receive",
				"party_type": "Customer",
				"party": self.customer,
				"company": self.company,
				"posting_date": self.date,
				"paid_from": self.template.debit_to,
				"paid_from_account_currency": self.template.currency,
				"paid_to": self._paid_to_account(),
				"paid_to_account_currency": self.template.currency,
				"source_exchange_rate": 1,
				"target_exchange_rate": 1,
				"paid_amount": total,
				"received_amount": total,
				"references": [
					{
						"reference_doctype": "Sales Invoice",
						"reference_name": invoice.name,
						"total_amount": invoice.grand_total,
						"outstanding_amount": invoice.outstanding_amount,
						"allocated_amount": amount,
						"exchange_rate": 1,
					}
					for invoice, amount in allocations
				],
			}
		)
		pe.insert(ignore_permissions=True)
		pe.submit()
		return pe

	def _rows_for(self, invoice_name):
		return [
			row
			for row in fetch_payout_data({"from_date": self.date, "to_date": self.date, "company": self.company})
			if row["invoice_number"] == invoice_name
		]


class TestAllocatedShareOfASplitPayment(PayoutReportTestBase):
	"""P1.1 — the report must show each invoice its own allocated share."""

	def test_an_invoice_shows_only_its_own_allocated_share_not_the_whole_payment(self):
		"""
		One Payment Entry of 300 allocated 100 / 200 across two invoices. Today
		`pe.paid_amount` puts the whole 300 against BOTH invoices; the first
		invoice must show 100.
		"""
		invoice_a = self._invoice(100)
		invoice_b = self._invoice(200)
		self._payment_entry([(invoice_a, 100), (invoice_b, 200)])

		rows_a = self._rows_for(invoice_a.name)

		self.assertEqual(len(rows_a), 1)
		self.assertEqual(rows_a[0]["paid_amount"], 100)

	def test_the_second_invoice_of_the_same_split_payment_shows_its_own_share_too(self):
		invoice_a = self._invoice(100)
		invoice_b = self._invoice(200)
		self._payment_entry([(invoice_a, 100), (invoice_b, 200)])

		rows_b = self._rows_for(invoice_b.name)

		self.assertEqual(len(rows_b), 1)
		self.assertEqual(rows_b[0]["paid_amount"], 200)


class TestCancelledPaymentsAreExcludedWithoutDroppingUnpaidInvoices(PayoutReportTestBase):
	"""P1.2 — a cancelled Payment Entry must not count as collected money."""

	def test_a_cancelled_payment_leaves_one_unpaid_row_with_zero_paid_amount(self):
		"""
		An invoice of 150 is fully paid, then the Payment Entry is cancelled.
		Today the row still shows the cancelled payment's 150; it must instead
		show exactly one row, Unpaid, with paid_amount 0. This also catches the
		WHERE-clause regression: if `pe.docstatus = 1` were put in the WHERE
		clause instead of the JOIN, the invoice would disappear from the report
		entirely instead of falling back to an Unpaid row.
		"""
		invoice = self._invoice(150)
		payment = self._payment_entry([(invoice, 150)])
		payment.cancel()

		rows = self._rows_for(invoice.name)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["payment_status"], "Unpaid")
		self.assertEqual(rows[0]["paid_amount"], 0)

	def test_an_invoice_with_no_payment_at_all_still_appears_as_unpaid(self):
		"""
		The control case for the WHERE-clause trap: an invoice that was never
		paid must still produce its synthetic Unpaid row.
		"""
		invoice = self._invoice(75)

		rows = self._rows_for(invoice.name)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["payment_status"], "Unpaid")
		self.assertEqual(rows[0]["paid_amount"], 0)
