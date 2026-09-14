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


# =====================================================================
# VD.20 — the rubriek must follow the stored tax regime, not tax_category
# =====================================================================
#
# `fetch_vat_data` decided every sales rubriek from `tax_category`, and the
# invoicing pipeline deliberately stops posting that field (VD.4):
# `createSalesInvoice.ts` destructures it off the payload by name so the state
# machine cannot route around the omission. ERPNext fills it from the Customer
# during validate() when the Customer carries one, and measured on the dev site
# most do not.
#
# Measured 2026-09-02, `tabSales Invoice` where docstatus = 1:
#
#     (empty)                  605 invoices   630,323.82 net
#     omzet werkplaats (21%)    79 invoices    80,675.64 net
#     netherlands vat 0%         1 invoice         120.00 net
#
# None of those three strings is a key of TAX_CATEGORY_MAPPING, so every one of
# them fell through the chain to the domestic fallback `rubric = "1c"`. Running
# the report over all dates returned:
#
#     1a  Leveringen binnenland hoog tarief (21%)         0.00
#     1c  Overige tarieven                          701,074.89
#     5a  Verschuldigde omzetbelasting              148,800.84
#
# A return that declares no standard-rated domestic turnover at all while owing
# 148,800.84 of VAT on 701,074.89 of "other rates" contradicts itself on its
# face: 148,800.84 / 701,074.89 is 21.2%, and rubriek 1c is by definition not
# the standard rate. This is not a historical artefact. `(empty)` is what every
# invoice the current pipeline creates carries, so the misfiling is the steady
# state going forward.
#
# `tvs_tax_regime` did not appear in this report once. It is the field the whole
# regime effort computes — VD.1, VD.2, VD.14 and VD.18 all write or repair it —
# and the declaration that is actually filed never read it.
#
# An invoice that stores no regime keeps the old behaviour byte for byte. Those
# are the historical invoices that will never have one, and how they should be
# classified is the accounting question Q1 answered as "nothing changes for the
# past", not something this change may decide silently.

from unittest.mock import patch

from erpnext.accounts.report.vat_declaration.vat_declaration import (
	TAX_REGIME_FIELD,
	classify_sales_rubric,
	tax_regime_select,
)


class TestClassifySalesRubricByRegime(FrappeTestCase):
	"""classify_sales_rubric() — the regime path. VD.20."""

	# --- the defect, in the exact shape production produces ----------------

	def test_domestic_standard_rate_lands_in_1a_not_1c(self):
		"""
		The measured production shape: no tax category at all, a Netherlands
		customer, and a regime that says standard rate. Before VD.20 this
		returned "1c" and took 630,323.82 of turnover with it.
		"""
		rubric, unmapped = classify_sales_rubric(
			regime="NL_STANDARD", category="", incoterm="", customer_type="domestic"
		)

		self.assertEqual(rubric, "1a")
		self.assertIsNone(unmapped)

	def test_the_workshop_category_no_longer_decides_the_rubriek(self):
		"""
		`omzet werkplaats (21%)` is a revenue-account name, not a Belastingdienst
		category, and it is absent from TAX_CATEGORY_MAPPING. It must not pull a
		standard-rated sale into 1c now that the regime is stored.
		"""
		rubric, unmapped = classify_sales_rubric(
			regime="NL_STANDARD",
			category="omzet werkplaats (21%)",
			incoterm="",
			customer_type="domestic",
		)

		self.assertEqual(rubric, "1a")
		self.assertIsNone(unmapped)

	# --- the four regimes the report can decide ----------------------------

	def test_reduced_rate_lands_in_1b(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="NL_REDUCED", category="", incoterm="", customer_type="domestic"
		)
		self.assertEqual(rubric, "1b")

	def test_intra_community_supply_lands_in_3b(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="EU_B2B_INTRA", category="", incoterm="", customer_type="eu"
		)
		self.assertEqual(rubric, "3b")

	def test_export_lands_in_3a(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="EXPORT_NON_EU", category="", incoterm="", customer_type="export"
		)
		self.assertEqual(rubric, "3a")

	# --- the regime outranks the address heuristics ------------------------

	def test_the_regime_wins_over_a_missing_customer_country(self):
		"""
		VD.14 made an absent country `unknown` so no rewrite acts on it. The
		regime is stronger still: it was decided at invoice time from a VIES
		answer, and an address nobody filled in cannot overturn it.
		"""
		rubric, _unmapped = classify_sales_rubric(
			regime="NL_STANDARD", category="", incoterm="", customer_type="unknown"
		)
		self.assertEqual(rubric, "1a")

	def test_the_regime_wins_over_a_contradicting_address_country(self):
		"""
		A stored NL_STANDARD says 21% was charged as a domestic supply. If the
		linked address says Germany the two disagree, and the field the pipeline
		decided and wrote is the one that governs — rewriting it to 3b would
		declare a zero-rated intra-community supply while 5a still carries the
		21% actually collected, which is the VD.14 contradiction rebuilt.
		"""
		rubric, _unmapped = classify_sales_rubric(
			regime="NL_STANDARD", category="", incoterm="", customer_type="eu"
		)
		self.assertEqual(rubric, "1a")

	def test_the_regime_wins_over_an_export_incoterm(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="NL_STANDARD", category="", incoterm="FOB", customer_type="domestic"
		)
		self.assertEqual(rubric, "1a")

	def test_a_padded_regime_is_still_the_regime(self):
		"""Consistent with resolve_credit_note_regime, which strips before use."""
		rubric, _unmapped = classify_sales_rubric(
			regime="  NL_STANDARD  ", category="", incoterm="", customer_type="domestic"
		)
		self.assertEqual(rubric, "1a")

	# --- REVIEW_HOLD is declared as what was actually charged (F.1) ---------

	def test_review_hold_lands_in_1a(self):
		"""
		F.1, audit A.4. REVIEW_HOLD was left out of the mapping on the reasoning
		that filing it under any rubriek would be the guess the regime exists to
		prevent. Omission does not mean *no rubriek*, it means the legacy
		country-guessing path — and that path files an EU customer in 3b and a
		non-EU customer in 3a, both zero-rated, while 5a still carries the 21%
		REVIEW_HOLD charges by definition. That is the VD.14 contradiction
		rebuilt by the one regime that means the system refused to rate the
		document.

		1a is not a guess. It is the only thing this report knows for certain
		about the document: 21% was charged and TVS owes it.
		"""
		rubric, unmapped = classify_sales_rubric(
			regime="REVIEW_HOLD", category="", incoterm="", customer_type="domestic"
		)

		self.assertEqual(rubric, "1a")
		self.assertIsNone(unmapped)

	def test_a_held_eu_customer_is_not_declared_as_an_intra_community_supply(self):
		"""The measured defect: 3b is exempt turnover for VAT that was collected."""
		rubric, _unmapped = classify_sales_rubric(
			regime="REVIEW_HOLD", category="", incoterm="", customer_type="eu"
		)
		self.assertEqual(rubric, "1a")

	def test_a_held_non_eu_customer_is_not_declared_as_an_export(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="REVIEW_HOLD", category="", incoterm="", customer_type="export"
		)
		self.assertEqual(rubric, "1a")

	def test_a_held_invoice_with_no_customer_country_still_lands_in_1a(self):
		"""
		The commonest hold there is: `resolveTaxTreatment` returns REVIEW_HOLD
		precisely because the country could not be resolved, and 433 of 2,363
		customers have no address at all.
		"""
		rubric, _unmapped = classify_sales_rubric(
			regime="REVIEW_HOLD", category="", incoterm="", customer_type="unknown"
		)
		self.assertEqual(rubric, "1a")

	def test_a_held_invoice_is_not_rewritten_by_an_export_incoterm(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="REVIEW_HOLD", category="", incoterm="FOB", customer_type="export"
		)
		self.assertEqual(rubric, "1a")

	def test_a_padded_review_hold_is_still_the_regime(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="  REVIEW_HOLD  ", category="", incoterm="", customer_type="eu"
		)
		self.assertEqual(rubric, "1a")

	def test_a_held_invoice_raises_no_unknown_category_warning(self):
		"""
		The hold is not a mapping failure, and the unknown-category warning is
		about categories this report cannot map. Reporting it there would put a
		decided document on a list of undecidable ones. F.2 alerts on the hold
		and F.3 lists it; this report files it.
		"""
		_rubric, unmapped = classify_sales_rubric(
			regime="REVIEW_HOLD", category="omzet werkplaats (21%)", incoterm="", customer_type="eu"
		)
		self.assertIsNone(unmapped)

	def test_an_unrecognised_regime_string_is_not_guessed(self):
		"""
		A value from a future release must not be mapped by accident. This is
		the distinction F.1 turns on: REVIEW_HOLD is a *known* value whose money
		is known, and an unknown string is neither.
		"""
		rubric, unmapped = classify_sales_rubric(
			regime="SOMETHING_NEW", category="", incoterm="", customer_type="domestic"
		)

		self.assertEqual(rubric, "1c")
		self.assertEqual(unmapped, "")


class TestClassifySalesRubricLegacyPath(FrappeTestCase):
	"""
	classify_sales_rubric() with no stored regime — the pre-VD.20 behaviour,
	which must survive byte for byte. Q1 was answered "nothing changes for the
	past", so these are the historical invoices and they keep what they had.
	"""

	def test_a_mapped_category_still_decides(self):
		rubric, unmapped = classify_sales_rubric(
			regime="", category="21% binnenland", incoterm="", customer_type="domestic"
		)
		self.assertEqual(rubric, "1a")
		self.assertIsNone(unmapped)

	def test_a_none_regime_is_the_same_as_an_empty_one(self):
		rubric, _unmapped = classify_sales_rubric(
			regime=None, category="21% binnenland", incoterm="", customer_type="domestic"
		)
		self.assertEqual(rubric, "1a")

	def test_an_eu_customer_still_rewrites_a_domestic_category(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="", category="21% binnenland", incoterm="", customer_type="eu"
		)
		self.assertEqual(rubric, "3b")

	def test_an_export_customer_still_rewrites_a_domestic_category(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="", category="21% binnenland", incoterm="", customer_type="export"
		)
		self.assertEqual(rubric, "3a")

	def test_an_unknown_country_still_leaves_the_category_rubriek_alone(self):
		"""VD.14 — absent is not non-EU, and no rewrite acts on it."""
		rubric, _unmapped = classify_sales_rubric(
			regime="", category="21% binnenland", incoterm="", customer_type="unknown"
		)
		self.assertEqual(rubric, "1a")

	def test_an_export_incoterm_still_decides_when_no_category_maps(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="", category="", incoterm="FOB", customer_type="domestic"
		)
		self.assertEqual(rubric, "3a")

	def test_the_domestic_fallback_still_records_the_unmapped_category(self):
		rubric, unmapped = classify_sales_rubric(
			regime="",
			category="omzet werkplaats (21%)",
			incoterm="",
			customer_type="domestic",
		)

		self.assertEqual(rubric, "1c")
		self.assertEqual(unmapped, "omzet werkplaats (21%)")


class TestTaxRegimeSelect(FrappeTestCase):
	"""
	tax_regime_select() — the Custom Field guard. VD.20.

	`tvs_tax_regime` is installed by `tvs_accountancy`. An environment that has
	not migrated it has no such column, and naming it in SQL there would turn a
	working report into a database error, so the report must keep running on the
	legacy path instead.
	"""

	def test_names_the_field_when_the_column_exists(self):
		with patch("frappe.db.has_column", return_value=True):
			self.assertIn(TAX_REGIME_FIELD, tax_regime_select())

	def test_selects_a_constant_when_the_column_is_absent(self):
		with patch("frappe.db.has_column", return_value=False):
			select = tax_regime_select()

		self.assertNotIn(TAX_REGIME_FIELD, select)
		self.assertIn("tax_regime", select)

	def test_asks_about_the_sales_invoice_column_by_name(self):
		with patch("frappe.db.has_column", return_value=True) as has_column:
			tax_regime_select()

		has_column.assert_called_once_with("Sales Invoice", TAX_REGIME_FIELD)


# =====================================================================
# P1.5 — rubrics round once, at the reporting boundary, not per invoice
# =====================================================================
#
# There was no rounding anywhere in fetch_vat_data. Summing hundreds of
# invoice net_total/vat_amount floats accumulates the usual binary-float
# drift (0.1 + 0.2 is 0.30000000000000004, not 0.3), and rounding per
# invoice would compound that error across hundreds of rows instead of
# fixing it. The fix rounds the rubrics dict once, after every invoice has
# already been accumulated into it.
#
# classify_period_sales does its own SQL, so these tests replace it with a
# fixed list of already-processed invoices (its documented return shape) and
# never touch a real Sales Invoice. The one other DB call fetch_vat_data
# makes directly — the purchase invoice query that feeds 5b — is stubbed to
# an empty result so a real Purchase Invoice already sitting in this dev
# site cannot leak into an assertion about rounding.

from erpnext.accounts.report.vat_declaration.vat_declaration import fetch_vat_data

# A window with no realistic chance of real invoices, so the live purchase
# query fetch_vat_data still runs (unstubbed in the P1.6 tests) can't leak
# unrelated data into an assertion.
_UNPOPULATED_WINDOW = {"from_date": "1900-01-01", "to_date": "1900-01-02", "company": ""}


def _fake_sales_invoice(**overrides):
	"""A minimal dict shaped like one entry of classify_period_sales()'s return list."""
	base = {
		"invoice": "SINV-TEST-0001",
		"customer": "_Test Customer",
		"customer_name": "_Test Customer",
		"period": "2026-01",
		"tax_id": "",
		"net_total": 0.0,
		"category": "21% binnenland",
		"regime": "",
		"incoterm": "",
		"customer_type": "domestic",
		"vat_amount": 0.0,
		"reverse_charge": 0,
		"rubric": "1a",
	}
	base.update(overrides)
	return base


class TestFetchVatDataRoundsAtTheReportingBoundary(FrappeTestCase):
	"""fetch_vat_data() — P1.5. Rubrics round once, after accumulation."""

	def test_rubric_amount_rounds_the_accumulated_binary_float_drift(self):
		"""
		0.1 + 0.2 is 0.30000000000000004 in raw float arithmetic. Two invoices
		landing in the same rubriek must come out as 0.3, not that drift —
		proving the rounding happens after the sum, not nowhere at all.
		"""
		fake_invoices = [
			_fake_sales_invoice(net_total=0.1, rubric="1a"),
			_fake_sales_invoice(net_total=0.2, rubric="1a"),
		]

		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=(fake_invoices, set(), 0.0),
		), patch("frappe.db.sql", return_value=[]):
			rows = fetch_vat_data(_UNPOPULATED_WINDOW)

		row_1a = next(row for row in rows if row["rubric"] == "1a")
		self.assertEqual(row_1a["amount"], 0.3)

	def test_totaal_rounds_the_5a_minus_5b_subtraction(self):
		"""
		Two invoices whose VAT is 0.1 and 0.2 give 5a the same binary-float
		drift on its subtotal. Totaal (and 5c, the same figure) must report
		0.3, not the raw float difference.
		"""
		fake_invoices = [
			_fake_sales_invoice(net_total=1.0, vat_amount=0.1, rubric="1a"),
			_fake_sales_invoice(net_total=1.0, vat_amount=0.2, rubric="1a"),
		]

		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=(fake_invoices, set(), 0.0),
		), patch("frappe.db.sql", return_value=[]):
			rows = fetch_vat_data(_UNPOPULATED_WINDOW)

		totaal = next(row for row in rows if row["rubric"] == "Totaal")
		subtotaal = next(row for row in rows if row["rubric"] == "5c")
		self.assertEqual(totaal["amount"], 0.3)
		self.assertEqual(subtotaal["amount"], 0.3)


# =====================================================================
# P1.6 — return the real per-rubriek VAT instead of a hardcoded rate
# =====================================================================
#
# The per-invoice VAT is already computed in classify_period_sales. Before
# this fix it was only ever summed into rubrics["5a"] and never retained per
# rubriek, so vat_declaration.js had no field to read and invented the VAT
# client-side as amount * 0.21 / 0.09 / 0.05 — a 5% rate that exists nowhere
# in Dutch VAT law.
class TestFetchVatDataReturnsActualPerRubriekVat(FrappeTestCase):
	"""fetch_vat_data() — P1.6. Each row carries the VAT actually charged."""

	def test_row_reports_the_charged_vat_not_a_recomputed_rate(self):
		"""
		Net 1000, VAT actually charged 150 — deliberately not 21% of the net
		(which would be 210), so a passing assertion proves the figure was
		READ off the invoice, not recomputed from a hardcoded rate.
		"""
		fake_invoices = [_fake_sales_invoice(net_total=1000.0, vat_amount=150.0, rubric="1a")]

		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=(fake_invoices, set(), 0.0),
		), patch("frappe.db.sql", return_value=[]):
			rows = fetch_vat_data(_UNPOPULATED_WINDOW)

		row_1a = next(row for row in rows if row["rubric"] == "1a")
		self.assertEqual(row_1a["amount"], 1000.00)
		self.assertEqual(row_1a["vat_amount"], 150.00)

	def test_a_rubriek_with_no_invoices_reports_zero_vat_not_a_missing_key(self):
		fake_invoices = [_fake_sales_invoice(net_total=1000.0, vat_amount=150.0, rubric="1a")]

		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=(fake_invoices, set(), 0.0),
		), patch("frappe.db.sql", return_value=[]):
			rows = fetch_vat_data(_UNPOPULATED_WINDOW)

		row_1b = next(row for row in rows if row["rubric"] == "1b")
		self.assertEqual(row_1b["vat_amount"], 0.0)
