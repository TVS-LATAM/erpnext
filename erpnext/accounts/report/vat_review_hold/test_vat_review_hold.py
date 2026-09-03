# Copyright (c) 2026, TVS and contributors
# For license information, please see license.txt

"""
F.3 (audit A.4) — the held invoices must be listable before a period is filed.

`REVIEW_HOLD` is what the invoicing path writes when it refused to rate a
document. F.1 now files those invoices in rubriek 1a, which is right about the
money — 21% was charged and TVS owes it — and says nothing about the doubt. F.2
alerts on Slack the day it happens, and alerts scroll away.

This report is the list an accountant opens before pressing send: every
submitted invoice in the period that the system could not rate, with the
customer, the country, the net, the VAT and the date. Without it, the only
record that a human had to look at these documents lives in a chat channel.

It asserts three things the report cannot be allowed to get wrong:

  * it lists only held invoices, so a rated one never lands on a review list;
  * it lists only submitted ones, because a draft is not on any return yet;
  * it survives an environment where `tvs_tax_regime` was never migrated, which
    is the same guard `tax_regime_select` carries in the VAT return — naming an
    absent column in SQL turns a working report into a database error.
"""

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from erpnext.accounts.report.vat_review_hold.vat_review_hold import (
	REVIEW_HOLD_REGIME,
	TAX_REGIME_FIELD,
	execute,
	get_columns,
	held_invoice_query,
)


class TestHeldInvoiceQuery(FrappeTestCase):
	"""held_invoice_query() — what the report is allowed to select."""

	def test_selects_only_the_held_regime(self):
		"""
		The whole value of this list is that everything on it needs a human. One
		rated invoice on it and the list stops being read.
		"""
		self.assertIn(TAX_REGIME_FIELD, held_invoice_query())
		self.assertIn(REVIEW_HOLD_REGIME, held_invoice_query())

	def test_selects_only_submitted_invoices(self):
		"""A draft is not on a VAT return, so it is not what this list is for."""
		self.assertIn("si.docstatus = 1", held_invoice_query())

	def test_is_bounded_by_the_filing_period(self):
		"""An accountant files one period, and reads the holds for that period."""
		self.assertIn("si.posting_date BETWEEN %(from_date)s AND %(to_date)s", held_invoice_query())

	def test_passes_the_dates_as_parameters_and_never_as_text(self):
		self.assertNotIn("format(", held_invoice_query())
		self.assertIn("%(company)s", held_invoice_query())


class TestColumns(FrappeTestCase):
	"""get_columns() — what an accountant needs to act on a held invoice."""

	def test_carries_every_field_the_review_needs(self):
		names = [column["fieldname"] for column in get_columns()]

		for field in ("invoice", "posting_date", "customer", "country", "net_total", "vat_amount"):
			self.assertIn(field, names)

	def test_the_invoice_is_a_link_so_it_can_be_opened_from_the_list(self):
		invoice = next(column for column in get_columns() if column["fieldname"] == "invoice")

		self.assertEqual(invoice["fieldtype"], "Link")
		self.assertEqual(invoice["options"], "Sales Invoice")


class TestExecuteWithoutTheCustomField(FrappeTestCase):
	"""
	`tvs_tax_regime` is installed by `tvs_accountancy`. An environment that never
	migrated it has no such column, and naming it in SQL there would raise
	instead of reporting. The VAT return already guards this in
	`tax_regime_select`; this report cannot be the one that forgets.
	"""

	def test_returns_no_rows_instead_of_raising(self):
		with patch("frappe.db.has_column", return_value=False):
			columns, data = execute({"from_date": "2026-01-01", "to_date": "2026-01-31"})

		self.assertEqual(data, [])
		self.assertTrue(columns)

	def test_does_not_query_when_the_column_is_absent(self):
		with patch("frappe.db.has_column", return_value=False), patch("frappe.db.sql") as sql:
			execute({"from_date": "2026-01-01", "to_date": "2026-01-31"})

		sql.assert_not_called()

	def test_asks_about_the_sales_invoice_column_by_name(self):
		with patch("frappe.db.has_column", return_value=False) as has_column:
			execute({"from_date": "2026-01-01", "to_date": "2026-01-31"})

		has_column.assert_called_once_with("Sales Invoice", TAX_REGIME_FIELD)


class TestExecuteWithTheCustomField(FrappeTestCase):
	"""execute() — the rows reach the report as the query produced them."""

	def test_returns_the_rows_the_query_selected(self):
		row = {
			"invoice": "SINV-1",
			"posting_date": "2026-01-15",
			"customer": "CUST-0001",
			"country": None,
			"net_total": 100.0,
			"vat_amount": 21.0,
		}

		with patch("frappe.db.has_column", return_value=True), patch("frappe.db.sql", return_value=[row]):
			_columns, data = execute({"from_date": "2026-01-01", "to_date": "2026-01-31"})

		self.assertEqual(data, [row])

	def test_binds_the_period_and_the_company_it_was_given(self):
		with patch("frappe.db.has_column", return_value=True), patch("frappe.db.sql", return_value=[]) as sql:
			execute({"from_date": "2026-01-01", "to_date": "2026-01-31", "company": "TVS"})

		self.assertEqual(
			sql.call_args[0][1],
			{"from_date": "2026-01-01", "to_date": "2026-01-31", "company": "TVS"},
		)

	def test_an_absent_company_selects_every_company_rather_than_none(self):
		"""
		The query reads `%(company)s = '' OR si.company = %(company)s`, the same
		shape the VAT return uses. Passing None instead of '' would match no
		invoice at all and report a clean period that is not clean.
		"""
		with patch("frappe.db.has_column", return_value=True), patch("frappe.db.sql", return_value=[]) as sql:
			execute({"from_date": "2026-01-01", "to_date": "2026-01-31"})

		self.assertEqual(sql.call_args[0][1]["company"], "")
