# Copyright (c) 2026, TVS and contributors
# For license information, please see license.txt

"""
VD.14 — a customer whose invoice carries no usable address country must not be
declared as an export.

The report used to classify the customer inside the SQL itself:

    CASE
        WHEN addr.country = 'Netherlands' THEN 'domestic'
        WHEN addr.country IN (...)        THEN 'eu'
        ELSE 'export'
    END AS customer_type

`customer_address` is joined with a LEFT JOIN, so an invoice with no linked
address yields `addr.country = NULL`, no WHEN matches, and the row falls through
to `ELSE 'export'`. The classification loop then rewrites a correctly mapped
`1a` (domestic 21%) into `3a` (export outside the EU), while `rubrics["5a"]`
still accumulates the 21% that was actually charged — a return that contradicts
itself, declaring zero-rated export turnover next to the VAT collected on it.

Absent is not non-EU. The two are now distinct: a country nobody recorded
classifies as `unknown`, which no rubriek rewrite acts on, so a domestic invoice
stays in the rubriek its tax category earned.
"""

from frappe.tests.utils import FrappeTestCase

from erpnext.accounts.report.vat_declaration.vat_declaration import classify_customer_type


class TestClassifyCustomerType(FrappeTestCase):
	"""classify_customer_type() — VD.14."""

	# --- the defect: a missing country is not an export --------------------

	def test_missing_country_is_unknown_not_export(self):
		self.assertEqual(classify_customer_type(None), "unknown")

	def test_empty_country_is_unknown_not_export(self):
		"""An address exists but its country was never filled in."""
		self.assertEqual(classify_customer_type(""), "unknown")

	def test_whitespace_country_is_unknown_not_export(self):
		self.assertEqual(classify_customer_type("   "), "unknown")

	# --- the classifications that must keep working ------------------------

	def test_netherlands_is_domestic(self):
		self.assertEqual(classify_customer_type("Netherlands"), "domestic")

	def test_netherlands_wins_over_the_eu_list_that_contains_it(self):
		"""
		EU_COUNTRIES includes 'Netherlands'. Domestic must be decided first or
		every Dutch sale would classify as an intra-EU supply.
		"""
		self.assertEqual(classify_customer_type("Netherlands"), "domestic")

	def test_other_member_state_is_eu(self):
		self.assertEqual(classify_customer_type("Germany"), "eu")
		self.assertEqual(classify_customer_type("Spain"), "eu")

	def test_country_outside_the_eu_is_export(self):
		self.assertEqual(classify_customer_type("United States"), "export")
		self.assertEqual(classify_customer_type("Norway"), "export")

	# --- a padded value is the same absence, not an export -----------------

	def test_padded_country_is_still_classified_on_its_name(self):
		self.assertEqual(classify_customer_type("  Netherlands  "), "domestic")
		self.assertEqual(classify_customer_type(" Germany "), "eu")
