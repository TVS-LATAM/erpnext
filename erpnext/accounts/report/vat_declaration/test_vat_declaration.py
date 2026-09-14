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


def _neutral_purchase_row():
	"""
	One purchase row that lands in no rubriek at all.

	It carries an empty tax category and no tax line, so it adds nothing to 4a,
	4b or 5b. Its only job is to make the period count as sourced, which is what
	the P1.5 and P1.6 assertions need: a period with no purchase invoice at all
	blanks 5c and Totaal (P2.3 option A), and a blank total cannot demonstrate
	anything about rounding.
	"""
	return frappe._dict({
		"name": "PINV-NEUTRAL-0001",
		"supplier": "_Test Supplier",
		"category": "",
		"base_net_total": 0.0,
		"supplier_address": None,
		"supplier_country": None,
		"rate": 0.0,
		"base_tax_amount": 0.0,
		"account_head": None,
		"account_type": None,
		"account_name": None,
		"supplier_type": "domestic",
	})


def _only_purchase_query(purchase_rows):
	"""
	Patch `frappe.db.sql` so ONLY the purchase query is faked.

	Replacing `frappe.db.sql` wholesale also intercepts the lookups Frappe makes
	for its own bookkeeping. `flt(value, 2)` resolves the system rounding method
	through the database, so a blanket mock answers that lookup with a list of
	purchase rows and rounding then returns 0.0 — every rubriek in the report
	silently collapses to zero, and which tests it hits depends on class name
	order, because the resolved method is cached per process.

	Faking one query and delegating the rest keeps the assertion about the
	report instead of about the mock.
	"""
	real_sql = frappe.db.sql

	def fake(query, *args, **kwargs):
		if "tabPurchase Invoice" in str(query):
			return purchase_rows
		return real_sql(query, *args, **kwargs)

	return patch("frappe.db.sql", side_effect=fake)


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
		), _only_purchase_query([_neutral_purchase_row()]):
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
		), _only_purchase_query([_neutral_purchase_row()]):
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
		), _only_purchase_query([_neutral_purchase_row()]):
			rows = fetch_vat_data(_UNPOPULATED_WINDOW)

		row_1a = next(row for row in rows if row["rubric"] == "1a")
		self.assertEqual(row_1a["amount"], 1000.00)
		self.assertEqual(row_1a["vat_amount"], 150.00)

	def test_a_rubriek_with_no_invoices_reports_zero_vat_not_a_missing_key(self):
		fake_invoices = [_fake_sales_invoice(net_total=1000.0, vat_amount=150.0, rubric="1a")]

		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=(fake_invoices, set(), 0.0),
		), _only_purchase_query([_neutral_purchase_row()]):
			rows = fetch_vat_data(_UNPOPULATED_WINDOW)

		row_1b = next(row for row in rows if row["rubric"] == "1b")
		self.assertEqual(row_1b["vat_amount"], 0.0)


# =====================================================================
# P2.2 — a verlegd tax line routes an otherwise-unmapped domestic sale to 1e
# =====================================================================
#
# `classify_period_sales` already computed a per-invoice reverse-charge signal
# from the tax line's account_head/description ("verlegd" or "reverse"), but
# `classify_sales_rubric` never read it again when it decided the rubriek: an
# invoice with a genuine "BTW Verlegd" tax line and an unmapped (or empty)
# tax_category silently filed as 1c — "Overige tarieven" — instead of the
# rubriek the seller of a domestic reverse-charge supply actually owes.
#
# P2.4 corrected the destination. Rubriek 2a "Verleggingsregelingen
# binnenland" belongs to the BUYER (Belastingdienst: "Bent u de afnemer? Dan
# moet u de btw die naar u is verlegd, zelf uitrekenen... U vult dit bedrag in
# bij rubriek 2a"). The SELLER who applies the domestic reverse charge reports
# the turnover in rubriek 1e ("Leveringen/diensten belast met 0% of niet bij u
# belast"), because this report only ever sees Sales Invoices — i.e. the
# seller's side of the transaction.
#
# The heuristic only ever fires when nothing stronger already decided: a
# stored tvs_tax_regime and an explicit TAX_CATEGORY_MAPPING hit both still
# outrank it. And it is scoped to customer_type == "domestic": an EU or
# export customer whose invoice happens to carry a verlegd-looking tax line
# belongs in 3b or 3a via the existing coherence rewrite, not in 1e.

from erpnext.accounts.report.vat_declaration.vat_declaration import classify_sales_rubric


class TestClassifySalesRubricReverseChargeHeuristic(FrappeTestCase):
	"""classify_sales_rubric() — the verlegd tax-line heuristic. P2.2 / P2.4."""

	# --- the defect, in the exact shape production produces ----------------

	def test_domestic_verlegd_tax_line_with_unmapped_category_lands_in_1e(self):
		"""
		No stored regime, no mapped category. Today this lands in 1c. The
		seller side of a domestic reverse charge belongs in 1e, not in 2a —
		2a is the buyer's rubriek (P2.4).
		"""
		rubric, unmapped = classify_sales_rubric(
			regime="",
			category="",
			incoterm="",
			customer_type="domestic",
			reverse_charge=True,
		)

		self.assertEqual(rubric, "1e")
		self.assertIsNone(unmapped)

	# --- the precedence is the feature --------------------------------------

	def test_a_stored_regime_still_wins_over_a_verlegd_tax_line(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="NL_STANDARD",
			category="",
			incoterm="",
			customer_type="domestic",
			reverse_charge=True,
		)
		self.assertEqual(rubric, "1a")

	def test_an_explicitly_mapped_category_still_wins_over_a_verlegd_tax_line(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="",
			category="21% binnenland",
			incoterm="",
			customer_type="domestic",
			reverse_charge=True,
		)
		self.assertEqual(rubric, "1a")

	def test_an_eu_customer_with_a_verlegd_looking_line_is_not_stolen_into_1e(self):
		"""
		The heuristic is scoped to `customer_type == "domestic"`, so it never
		fires for an EU customer. The invoice falls through to the plain
		customer-type fallback that already existed, landing in 3b — the same
		outcome this test asserted before P2.4, only the rubriek it must NOT
		land in changed from 2a to 1e.
		"""
		rubric, _unmapped = classify_sales_rubric(
			regime="",
			category="",
			incoterm="",
			customer_type="eu",
			reverse_charge=True,
		)
		self.assertEqual(rubric, "3b")

	def test_an_export_customer_with_a_verlegd_looking_line_is_not_stolen_into_1e(self):
		"""Same fallback, export side."""
		rubric, _unmapped = classify_sales_rubric(
			regime="",
			category="",
			incoterm="",
			customer_type="export",
			reverse_charge=True,
		)
		self.assertEqual(rubric, "3a")

	def test_no_reverse_charge_signal_keeps_the_1c_fallback(self):
		"""Without the signal, an unmapped domestic category still falls to 1c."""
		rubric, unmapped = classify_sales_rubric(
			regime="",
			category="",
			incoterm="",
			customer_type="domestic",
			reverse_charge=False,
		)

		self.assertEqual(rubric, "1c")
		self.assertEqual(unmapped, "")


# =====================================================================
# P2.4 — an explicit verlegd tax_category maps to 1e, not 2a
# =====================================================================
#
# TAX_CATEGORY_MAPPING carried "reverse charge", "verlegd" and
# "verleggingsregeling" pointing at "2a". 2a "Verleggingsregelingen
# binnenland" belongs to the BUYER (see the P2.4 header comment in
# vat_declaration.py); this report only sees Sales Invoices, so it can only
# ever be the seller. A seller applying a domestic reverse charge reports the
# turnover in 1e ("Leveringen/diensten belast met 0% of niet bij u belast").
# The keys are repointed rather than removed, unlike the D4 keys above:
# deleting them would drop these invoices into the taxed 1c fallback, which
# overstates VAT due even more than the wrong rubriek did.
class TestVerlegdCategoryMapsToOneE(FrappeTestCase):
	"""classify_sales_rubric() / TAX_CATEGORY_MAPPING — P2.4."""

	def test_domestic_sale_with_a_verlegd_category_lands_in_1e(self):
		rubric, unmapped = classify_sales_rubric(
			regime="",
			category="verlegd",
			incoterm="",
			customer_type="domestic",
			reverse_charge=False,
		)
		self.assertEqual(rubric, "1e")
		self.assertIsNone(unmapped)

	def test_domestic_sale_with_a_reverse_charge_category_lands_in_1e(self):
		rubric, unmapped = classify_sales_rubric(
			regime="",
			category="reverse charge",
			incoterm="",
			customer_type="domestic",
			reverse_charge=False,
		)
		self.assertEqual(rubric, "1e")
		self.assertIsNone(unmapped)

	def test_domestic_sale_with_a_verleggingsregeling_category_lands_in_1e(self):
		rubric, unmapped = classify_sales_rubric(
			regime="",
			category="verleggingsregeling",
			incoterm="",
			customer_type="domestic",
			reverse_charge=False,
		)
		self.assertEqual(rubric, "1e")
		self.assertIsNone(unmapped)

	# --- the coherence rewrite now reroutes it correctly for EU/export -----

	def test_an_eu_customer_with_a_verlegd_category_is_rerouted_to_3b(self):
		"""
		P2.4. The pre-existing coherence rewrite —
		`if rubric in ["1a", "1b", "1e"] and customer_type != "domestic"` —
		now catches a verlegd category too, because it maps to 1e. An EU
		customer is rerouted to 3b: exactly what the Belastingdienst
		prescribes for an intra-EU delivery. No new code was written for
		this; it falls out of the existing rewrite once the mapping changed.
		"""
		rubric, unmapped = classify_sales_rubric(
			regime="",
			category="verlegd",
			incoterm="",
			customer_type="eu",
			reverse_charge=False,
		)
		self.assertEqual(rubric, "3b")
		self.assertIsNone(unmapped)

	def test_an_export_customer_with_a_verlegd_category_is_rerouted_to_3a(self):
		"""P2.4. Same coherence rewrite, export side."""
		rubric, unmapped = classify_sales_rubric(
			regime="",
			category="verlegd",
			incoterm="",
			customer_type="export",
			reverse_charge=False,
		)
		self.assertEqual(rubric, "3a")
		self.assertIsNone(unmapped)


# ---------------------------------------------------------------------
# P2.2 — end to end: the signal classify_period_sales already computes from
# the SQL row must be the one that reaches classify_sales_rubric.
# ---------------------------------------------------------------------

import frappe
from datetime import date

from erpnext.accounts.report.vat_declaration.vat_declaration import classify_period_sales


class TestClassifyPeriodSalesReverseChargeWiring(FrappeTestCase):
	"""
	classify_period_sales() — P2.2 / P2.4, end to end. Proves the
	reverse-charge signal computed from the tax line's account_head actually
	reaches the rubriek decision, not just `reverse_charge_total`, and that it
	lands in 1e — the seller's rubriek — not in 2a, which belongs to the buyer.
	"""

	def _sales_row(self, **overrides):
		row = frappe._dict({
			"name": "SINV-P2.2-0001",
			"customer": "_Test Customer",
			"customer_name": "_Test Customer",
			"posting_date": date(2026, 1, 15),
			"tax_id": "",
			"category": "",
			"tax_regime": "",
			"incoterm": "",
			"base_net_total": 1000.0,
			"customer_address": "Test Address-Billing",
			"customer_country": "Netherlands",
			"rate": 21.0,
			"base_tax_amount": 210.0,
			"account_head": None,
			"description": None,
			"account_type": None,
			"account_name": None,
		})
		row.update(overrides)
		return row

	def test_a_real_verlegd_tax_line_routes_an_unmapped_domestic_invoice_to_1e(self):
		"""
		A domestic invoice, empty tax_category, no tvs_tax_regime, one tax
		row whose account_head is "BTW Verlegd - T". Today this lands in 1c.
		P2.4: the seller side of a domestic reverse charge is 1e, not 2a —
		2a is the buyer's rubriek.
		"""
		rows = [self._sales_row(account_head="BTW Verlegd - T")]

		with patch("frappe.db.sql", return_value=rows):
			invoices, unknown_categories, _reverse_charge_total = classify_period_sales(
				{"from_date": "2026-01-01", "to_date": "2026-01-31", "company": ""}
			)

		self.assertEqual(len(invoices), 1)
		self.assertEqual(invoices[0]["rubric"], "1e")
		self.assertEqual(unknown_categories, set())

	def test_a_verlegd_line_carrying_no_vat_still_routes_to_1e(self):
		"""
		P2.2 / P2.4 — the realistic verlegging invoice, and the one the
		heuristic exists for.

		Under de verleggingsregeling the VAT is shifted to the buyer, so the
		seller charges nothing: the "BTW Verlegd" tax row carries a
		`base_tax_amount` of 0. Deriving the signal from the summed amount
		makes that invoice indistinguishable from one with no verlegd line at
		all, so the heuristic would miss precisely the case it was written
		for. The signal is whether such a line is PRESENT, not what it totals.
		"""
		rows = [self._sales_row(account_head="BTW Verlegd - T", base_tax_amount=0.0, rate=0.0)]

		with patch("frappe.db.sql", return_value=rows):
			invoices, _unknown_categories, _reverse_charge_total = classify_period_sales(
				{"from_date": "2026-01-01", "to_date": "2026-01-31", "company": ""}
			)

		self.assertEqual(len(invoices), 1)
		self.assertEqual(invoices[0]["rubric"], "1e")


# =====================================================================
# D4 — no sales category may file into an acquisitions rubriek (4a/4b)
# =====================================================================
#
# TAX_CATEGORY_MAPPING carried two entries that name a rubriek this report
# labels itself, on rows 4a/4b, as "Diensten uit landen buiten de EU" and
# "Diensten uit EU-landen" — services received FROM abroad. 4a and 4b are
# acquisition rubrieken: they hold purchases on which the VAT is reverse
# charged to us. A sale can never legitimately land in either.
#
# The map is read in exactly one place, `classify_sales_rubric`, which only
# ever sees Sales Invoices. The purchase side of `fetch_vat_data` never reads
# it: it compares `category` against the same two literal strings inline. So
# those two entries served no purchase-side purpose and mis-filed every sale
# that carried the category — out of 3b/3a, into an acquisitions bucket, while
# its VAT kept accumulating in 5a. That is the VD.14 self-contradiction
# reached by another road.
#
# Traced to `6373f18069` (2025-05-05), the commit that introduced the map in
# tax_declaration.py before vat_declaration.py copied it. It predates the
# regime migration (`894178abad`, 2026-09-02) by sixteen months, so this is
# not a regression from that work — it was wrong from the first draft.
#
# The fix removes the two entries rather than re-pointing them at 3b/3a,
# because `classify_sales_rubric` already decides the right rubriek from the
# customer type once nothing maps: an EU customer falls to 3b, a non-EU one to
# 3a, and a domestic one to 1c WITH the category recorded in
# `unknown_categories`, which raises the visible warning. Re-pointing the keys
# would instead hardcode a fiscal opinion about a category no Dutch sales
# invoice should carry, and would silence that warning.
#
# Measured on the dev site (see the VD.20 note above), no submitted Sales
# Invoice carries either category today, so this closes a latent misfiling
# rather than moving money in the current return.

from erpnext.accounts.report.vat_declaration.vat_declaration import TAX_CATEGORY_MAPPING

ACQUISITION_RUBRICS = ("4a", "4b")


class TestNoSalesCategoryFilesIntoAnAcquisitionRubric(FrappeTestCase):
	"""classify_sales_rubric() / TAX_CATEGORY_MAPPING — D4."""

	def test_the_map_names_no_acquisition_rubriek(self):
		"""
		The invariant, stated once over the whole table: this map only ever
		feeds the sales classifier, so no value of it may be 4a or 4b.
		"""
		filed_into_acquisitions = {
			category: rubric
			for category, rubric in TAX_CATEGORY_MAPPING.items()
			if rubric in ACQUISITION_RUBRICS
		}

		self.assertEqual(filed_into_acquisitions, {})

	def test_an_eu_services_sale_lands_in_3b_not_4b(self):
		"""
		Services to an EU business are an intra-community supply: rubriek 3b,
		the same bucket the ICP listing reconciles against. Before D4 this
		returned "4b" and declared the sale as an acquisition.
		"""
		rubric, _unmapped = classify_sales_rubric(
			regime="", category="diensten eu", incoterm="", customer_type="eu"
		)

		self.assertEqual(rubric, "3b")

	def test_a_non_eu_services_sale_lands_in_3a_not_4a(self):
		rubric, _unmapped = classify_sales_rubric(
			regime="", category="diensten buiten eu", incoterm="", customer_type="export"
		)

		self.assertEqual(rubric, "3a")

	def test_a_domestic_sale_carrying_a_services_category_is_flagged_not_filed_silently(self):
		"""
		"diensten eu" on an invoice to a Netherlands customer is a
		contradiction someone has to look at. It falls to the 1c fallback and
		reports the category back, which is what raises the user-facing
		unknown-category warning — 4b would have swallowed it in silence.
		"""
		rubric, unmapped = classify_sales_rubric(
			regime="", category="diensten eu", incoterm="", customer_type="domestic"
		)

		self.assertEqual(rubric, "1c")
		self.assertEqual(unmapped, "diensten eu")

	def test_a_stored_regime_still_outranks_the_services_category(self):
		rubric, unmapped = classify_sales_rubric(
			regime="NL_STANDARD", category="diensten eu", incoterm="", customer_type="domestic"
		)

		self.assertEqual(rubric, "1a")
		self.assertIsNone(unmapped)


class TestPurchaseSideStillFilesServicesIntoAcquisitionRubrics(FrappeTestCase):
	"""
	fetch_vat_data() — D4 regression guard.

	The two categories keep their meaning on the buy side, where they are
	correct. That branch compares the literal strings and never read the map,
	so removing the entries must leave it untouched. Without this test the
	fix looks like it could take 4a/4b down with it.
	"""

	def _purchase_row(self, **overrides):
		row = frappe._dict({
			"name": "PINV-D4-0001",
			"supplier": "_Test Supplier",
			"category": "diensten eu",
			"base_net_total": 1000.0,
			"supplier_address": "Test Address-Billing",
			"supplier_country": "Germany",
			"rate": 0.0,
			"base_tax_amount": 0.0,
			"account_head": None,
			"account_type": None,
			"account_name": None,
			"supplier_type": "eu",
		})
		row.update(overrides)
		return row

	def _rubric_amount(self, purchase_rows, rubric):
		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=([], set(), 0.0),
		), _only_purchase_query(purchase_rows):
			rows = fetch_vat_data(_UNPOPULATED_WINDOW)

		return next(row for row in rows if row["rubric"] == rubric)["amount"]

	def test_an_eu_services_purchase_still_lands_in_4b(self):
		amount = self._rubric_amount([self._purchase_row()], "4b")

		self.assertEqual(amount, 1000.00)

	def test_a_non_eu_services_purchase_still_lands_in_4a(self):
		purchase_rows = [
			self._purchase_row(
				category="diensten buiten eu", supplier_country="Norway", supplier_type="non_eu"
			)
		]

		amount = self._rubric_amount(purchase_rows, "4a")

		self.assertEqual(amount, 1000.00)


# =====================================================================
# P2.3 (option A) — a rubriek with no data source does not report 0.00
# =====================================================================
#
# Rubrieken 4a, 4b and 5b are the PURCHASE half of the return, and nothing
# in this stack books purchases. Verified read-only on 2026-09-14, on the
# only reachable site:
#
#   * `frappe.db.count("Purchase Invoice")` is 0 at any docstatus. The 37
#     `Purchase Taxes and Charges` rows all belong to Templates.
#   * There are no Custom Fields on Purchase Invoice at all, and
#     `tvs_tax_regime` exists only on Sales Invoice.
#   * `tvs_accountancy`'s doc_events cover Quotation, Customer and Sales
#     Invoice. There is no "Purchase Invoice" key anywhere in that app.
#   * No writer of Purchase Invoices exists in this bench or in
#     tvs-cloud-services.
#   * `Te vorderen Btw-verlegd` and `Af te dragen Btw-verlegd` exist in the
#     chart of accounts with zero GL entries.
#   * The Moneybird integration is sales-only: it pushes Customer and Sales
#     Invoice out, and its inbound webhook creates Items with
#     `is_sales_item: 1, is_purchase_item: 0`.
#
# A zero in a tax return is a MEASUREMENT. "5b Voorbelasting 0,00" asserts
# that no deductible input VAT was incurred, and `Totaal` is `5a - 5b`, so
# filing that zero overstates the VAT payable by the whole deductible
# amount. Absent is not zero — the same distinction VD.14 drew for an
# unknown country.
#
# The trigger is measured, never hardcoded: a period whose purchase query
# returns rows behaves exactly as before, byte for byte. That keeps an
# environment that DOES book purchases untouched, and makes the report heal
# itself the day purchases arrive — no constant to flip.
#
# 5c and Totaal are both `5a - 5b`, so they inherit 5b's missing source.
# 5a is left alone: it is the sales side, and it is measured.
#
# Out of scope here, tracked separately as B8: even with purchase rows
# present, the 5b accumulator matches an account name against "vat" plus
# "input"/"soportado", and the Dutch chart of accounts uses "Btw te
# vorderen ..." — so none of the site's 49 Tax accounts can ever match.

# P2.4. `UNSOURCED_ALWAYS` blanks 2a for a different reason than
# `UNSOURCED_WITHOUT_PURCHASES`: 2a has no purchase-side computation at all in
# this report, with or without purchase invoices, so it never gets "cured" by
# a period that does book purchases the way 4a/4b/5b do.
from erpnext.accounts.report.vat_declaration.vat_declaration import (
	UNSOURCED_ALWAYS,
	UNSOURCED_WITHOUT_PURCHASES,
	mark_unsourced_purchase_rubrics,
)


class TestMarkUnsourcedPurchaseRubrics(FrappeTestCase):
	"""mark_unsourced_purchase_rubrics() — P2.3 option A / P2.4, in isolation."""

	def _rows(self):
		return [
			{"rubric": "1a", "description": "", "amount": 1000.0, "vat_amount": 210.0},
			{"rubric": "2a", "description": "", "amount": 0.0, "vat_amount": 0.0},
			{"rubric": "4a", "description": "", "amount": 0.0, "vat_amount": 0.0},
			{"rubric": "4b", "description": "", "amount": 0.0, "vat_amount": 0.0},
			{"rubric": "5a", "description": "", "amount": 210.0},
			{"rubric": "5b", "description": "", "amount": 0.0},
			{"rubric": "5c", "description": "", "amount": 210.0},
			{"rubric": "Totaal", "description": "", "amount": 210.0},
		]

	def test_purchase_rubrieken_report_no_amount_when_nothing_sourced_them(self):
		rows = mark_unsourced_purchase_rubrics(self._rows(), purchases_sourced=False)
		by_rubric = {row["rubric"]: row for row in rows}

		for rubric in ("4a", "4b", "5b"):
			self.assertIsNone(by_rubric[rubric]["amount"], rubric)

	def test_the_subtotal_and_the_total_inherit_the_missing_5b(self):
		"""
		Both are `5a - 5b`. Reporting 210.00 while 5b is unknown states the
		VAT payable as if the deductible were zero.
		"""
		rows = mark_unsourced_purchase_rubrics(self._rows(), purchases_sourced=False)
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertIsNone(by_rubric["5c"]["amount"])
		self.assertIsNone(by_rubric["Totaal"]["amount"])

	def test_the_vat_column_is_blanked_too_not_left_at_zero(self):
		rows = mark_unsourced_purchase_rubrics(self._rows(), purchases_sourced=False)
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertIsNone(by_rubric["4a"]["vat_amount"])
		self.assertIsNone(by_rubric["4b"]["vat_amount"])

	def test_each_blanked_row_carries_a_machine_readable_flag(self):
		"""
		The dash the print template shows must be distinguishable from a
		missing row by anything reading this data, not only by a human.
		"""
		rows = mark_unsourced_purchase_rubrics(self._rows(), purchases_sourced=False)

		flagged = {row["rubric"] for row in rows if row.get("unsourced")}
		self.assertEqual(flagged, set(UNSOURCED_WITHOUT_PURCHASES) | set(UNSOURCED_ALWAYS))

	# --- P2.4: 2a is unsourced for a different, unconditional reason --------

	def test_rubriek_2a_has_no_amount_when_purchases_are_absent(self):
		rows = mark_unsourced_purchase_rubrics(self._rows(), purchases_sourced=False)
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertIsNone(by_rubric["2a"]["amount"])
		self.assertIsNone(by_rubric["2a"]["vat_amount"])
		self.assertTrue(by_rubric["2a"]["unsourced"])

	def test_rubriek_2a_has_no_amount_even_when_purchases_are_present(self):
		"""
		Unlike 4a/4b/5b, 2a is never cured by a sourced period: this report
		has no purchase-side computation for it at all.
		"""
		rows = mark_unsourced_purchase_rubrics(self._rows(), purchases_sourced=True)
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertIsNone(by_rubric["2a"]["amount"])
		self.assertIsNone(by_rubric["2a"]["vat_amount"])
		self.assertTrue(by_rubric["2a"]["unsourced"])

	def test_the_sales_side_is_left_alone(self):
		"""1a and 5a are measured from Sales Invoices. They keep their numbers."""
		rows = mark_unsourced_purchase_rubrics(self._rows(), purchases_sourced=False)
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertEqual(by_rubric["1a"]["amount"], 1000.0)
		self.assertEqual(by_rubric["1a"]["vat_amount"], 210.0)
		self.assertEqual(by_rubric["5a"]["amount"], 210.0)
		self.assertNotIn("unsourced", by_rubric["1a"])

	def test_a_sourced_period_leaves_every_rubriek_except_2a_untouched(self):
		"""
		The guard against breaking an environment that DOES book purchases:
		one purchase row in the period blanks nothing except 2a, which P2.4
		blanks regardless because no purchase-side computation ever feeds it.
		"""
		original = self._rows()
		rows = mark_unsourced_purchase_rubrics(self._rows(), purchases_sourced=True)

		untouched = [row for row in rows if row["rubric"] != "2a"]
		untouched_original = [row for row in original if row["rubric"] != "2a"]
		self.assertEqual(untouched, untouched_original)


class TestFetchVatDataBlanksTheUnsourcedPurchaseHalf(FrappeTestCase):
	"""fetch_vat_data() — P2.3 option A, end to end."""

	def _purchase_row(self, **overrides):
		row = frappe._dict({
			"name": "PINV-A-0001",
			"supplier": "_Test Supplier",
			"category": "diensten eu",
			"base_net_total": 1000.0,
			"supplier_address": "Test Address-Billing",
			"supplier_country": "Germany",
			"rate": 0.0,
			"base_tax_amount": 0.0,
			"account_head": None,
			"account_type": None,
			"account_name": None,
			"supplier_type": "eu",
		})
		row.update(overrides)
		return row

	def _rows_for(self, purchase_rows):
		sales = [_fake_sales_invoice(net_total=1000.0, vat_amount=210.0, rubric="1a")]

		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=(sales, set(), 0.0),
		), _only_purchase_query(purchase_rows), patch("frappe.msgprint"):
			return fetch_vat_data(_UNPOPULATED_WINDOW)

	def test_a_period_with_no_purchase_invoice_reports_no_total(self):
		rows = self._rows_for([])
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertEqual(by_rubric["1a"]["amount"], 1000.00)
		self.assertEqual(by_rubric["5a"]["amount"], 210.00)
		self.assertIsNone(by_rubric["5b"]["amount"])
		self.assertIsNone(by_rubric["Totaal"]["amount"])

	def test_a_period_with_a_purchase_invoice_still_reports_its_numbers(self):
		rows = self._rows_for([self._purchase_row()])
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertEqual(by_rubric["4b"]["amount"], 1000.00)
		self.assertEqual(by_rubric["5b"]["amount"], 0.00)
		self.assertEqual(by_rubric["Totaal"]["amount"], 210.00)
		self.assertNotIn("unsourced", by_rubric["4b"])

	# --- P2.4: 2a has no purchase-side source, sourced or not ---------------

	def test_rubriek_2a_is_unsourced_when_purchases_are_absent(self):
		rows = self._rows_for([])
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertIsNone(by_rubric["2a"]["amount"])
		self.assertIsNone(by_rubric["2a"]["vat_amount"])
		self.assertTrue(by_rubric["2a"]["unsourced"])

	def test_rubriek_2a_is_unsourced_even_when_purchases_are_present(self):
		"""
		The case that distinguishes this from P2.3: a period that DOES source
		4a/4b/5b still has no purchase-side computation for 2a at all.
		"""
		rows = self._rows_for([self._purchase_row()])
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertIsNone(by_rubric["2a"]["amount"])
		self.assertIsNone(by_rubric["2a"]["vat_amount"])
		self.assertTrue(by_rubric["2a"]["unsourced"])

	def test_the_user_is_told_which_rubrieken_have_no_source(self):
		"""
		Blanking silently would trade one invisible wrong number for an
		invisible missing one. The warning is the point.
		"""
		sales = [_fake_sales_invoice(net_total=1000.0, vat_amount=210.0, rubric="1a")]

		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=(sales, set(), 0.0),
		), _only_purchase_query([]), patch("frappe.msgprint") as msgprint:
			fetch_vat_data(_UNPOPULATED_WINDOW)

		self.assertTrue(msgprint.called)
		warned = " ".join(str(call) for call in msgprint.call_args_list)
		for rubric in ("4a", "4b", "5b", "2a"):
			self.assertIn(rubric, warned)

	def test_only_the_2a_warning_fires_when_the_period_has_purchases(self):
		"""
		P2.4. 4a/4b/5b are sourced once a period books purchases, but 2a never
		is: no purchase-side computation feeds it in this report. A sourced
		period must still warn about 2a, and only about 2a.
		"""
		sales = [_fake_sales_invoice(net_total=1000.0, vat_amount=210.0, rubric="1a")]

		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=(sales, set(), 0.0),
		), _only_purchase_query([self._purchase_row()]), patch(
			"frappe.msgprint"
		) as msgprint:
			fetch_vat_data(_UNPOPULATED_WINDOW)

		self.assertTrue(msgprint.called)
		warned = " ".join(str(call) for call in msgprint.call_args_list)
		self.assertIn("2a", warned)
		for rubric in ("4a", "4b", "5b"):
			self.assertNotIn(rubric, warned)


# =====================================================================
# B8 — 5b could never see a Dutch input-VAT account
# =====================================================================
#
# The accumulator that feeds rubriek 5b required the account name to
# contain "vat" AND one of "input"/"soportado". The chart of accounts of
# the Dutch company is written in Dutch, and none of the 49 Tax accounts on
# the site can satisfy that:
#
#     Btw te vorderen hoog / laag / overig      input VAT
#     Btw af te dragen hoog / laag / overig     output VAT
#     Te vorderen Btw-verlegd                   input side of a reverse charge
#     Af te dragen Btw-verlegd                  output side of a reverse charge
#     Btw-afdracht, Btw oude jaren
#     VAT 21%, VAT 6%, VAT 0% - TVS             the NL purchase templates
#
# "Btw te vorderen hoog" contains neither "vat" nor "input". Neither does
# "VAT 21%" contain "input", and that is the account the one existing NL
# Purchase Taxes and Charges Template posts to. So 5b was structurally
# pinned at 0.00 and `Totaal`, which is `5a - 5b`, overstated the VAT
# payable by the whole deductible amount.
#
# Whitelisting account names was the wrong shape of rule. The document type
# already says which side of the ledger a tax line is on: on a PURCHASE
# invoice a VAT account is voorbelasting unless its own name says it is the
# remittance side or a verlegd account. That reads the same in Dutch,
# English or Spanish, and it stops depending on one deployment's naming.
#
# The verlegd pair is recognised and deliberately NOT summed into 5b. Its
# counterpart belongs in 5a, and declaring one side of a reverse charge
# without the other makes the net wrong rather than incomplete — that is
# the purchase-half scope decision of P2.3 option A. It warns instead.

from erpnext.accounts.report.vat_declaration.vat_declaration import (
	classify_purchase_tax_account,
)


class TestClassifyPurchaseTaxAccount(FrappeTestCase):
	"""classify_purchase_tax_account() — B8."""

	# --- the defect, in the shape the site actually has --------------------

	def test_the_dutch_input_vat_accounts_are_recognised(self):
		for account_name in (
			"Btw te vorderen hoog",
			"Btw te vorderen laag",
			"Btw te vorderen overig",
		):
			self.assertEqual(
				classify_purchase_tax_account("Tax", account_name), "input", account_name
			)

	def test_the_account_the_nl_purchase_template_posts_to_is_recognised(self):
		"""
		`VAT 21% - T` is the only NL purchase tax template on the site. It
		contains "vat" but not "input", so the old rule missed it too.
		"""
		self.assertEqual(classify_purchase_tax_account("Tax", "VAT 21%"), "input")
		self.assertEqual(classify_purchase_tax_account("Tax", "VAT 6%"), "input")

	# --- the side the name rules out ---------------------------------------

	def test_the_remittance_side_is_not_deductible(self):
		for account_name in ("Btw af te dragen hoog", "Btw af te dragen laag", "Btw-afdracht"):
			self.assertIsNone(
				classify_purchase_tax_account("Tax", account_name), account_name
			)

	def test_both_verlegd_accounts_are_reported_as_reverse_charge_not_as_input(self):
		"""
		`Te vorderen Btw-verlegd` names the deductible side, but summing it
		into 5b while nothing puts its counterpart in 5a would make the net
		wrong, not merely incomplete.
		"""
		for account_name in ("Te vorderen Btw-verlegd", "Af te dragen Btw-verlegd"):
			self.assertEqual(
				classify_purchase_tax_account("Tax", account_name),
				"reverse_charge",
				account_name,
			)

	# --- what must stay out ------------------------------------------------

	def test_a_tax_account_that_is_not_vat_is_ignored(self):
		for account_name in ("Duties and Taxes", "ST 4%", "GST"):
			self.assertIsNone(
				classify_purchase_tax_account("Tax", account_name), account_name
			)

	def test_an_account_that_is_not_a_tax_account_is_ignored(self):
		self.assertIsNone(classify_purchase_tax_account("Payable", "Btw te vorderen hoog"))
		self.assertIsNone(classify_purchase_tax_account(None, "Btw te vorderen hoog"))

	def test_a_missing_account_name_is_ignored_not_crashed_on(self):
		self.assertIsNone(classify_purchase_tax_account("Tax", None))
		self.assertIsNone(classify_purchase_tax_account("Tax", ""))

	# --- the names the old rule did match still match ----------------------

	def test_the_english_and_spanish_names_still_resolve(self):
		"""
		Another deployment of this fork may still name them the old way. B8
		widens the rule; it must not narrow it.
		"""
		self.assertEqual(classify_purchase_tax_account("Tax", "Input VAT 21%"), "input")
		self.assertEqual(classify_purchase_tax_account("Tax", "IVA soportado 21%"), "input")

	def test_the_match_is_case_insensitive(self):
		self.assertEqual(classify_purchase_tax_account("Tax", "BTW TE VORDEREN HOOG"), "input")
		self.assertEqual(
			classify_purchase_tax_account("Tax", "AF TE DRAGEN BTW-VERLEGD"), "reverse_charge"
		)


class TestFetchVatDataAccumulatesDutchInputVat(FrappeTestCase):
	"""fetch_vat_data() — B8, end to end."""

	def _purchase_row(self, **overrides):
		row = frappe._dict({
			"name": "PINV-B8-0001",
			"supplier": "_Test Supplier",
			"category": "",
			"base_net_total": 1000.0,
			"supplier_address": "Test Address-Billing",
			"supplier_country": "Netherlands",
			"rate": 21.0,
			"base_tax_amount": 210.0,
			"account_head": "Btw te vorderen hoog - T",
			"account_type": "Tax",
			"account_name": "Btw te vorderen hoog",
			"supplier_type": "domestic",
		})
		row.update(overrides)
		return row

	def _rows_for(self, purchase_rows):
		sales = [_fake_sales_invoice(net_total=2000.0, vat_amount=420.0, rubric="1a")]

		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=(sales, set(), 0.0),
		), _only_purchase_query(purchase_rows), patch("frappe.msgprint"):
			return fetch_vat_data(_UNPOPULATED_WINDOW)

	def test_a_dutch_input_vat_line_reaches_5b(self):
		"""Before B8 this was 0.00 and Totaal claimed the full 420.00 was owed."""
		rows = self._rows_for([self._purchase_row()])
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertEqual(by_rubric["5b"]["amount"], 210.00)
		self.assertEqual(by_rubric["5a"]["amount"], 420.00)
		self.assertEqual(by_rubric["Totaal"]["amount"], 210.00)

	def test_a_verlegd_line_stays_out_of_5b(self):
		purchase_rows = [
			self._purchase_row(
				account_head="Te vorderen Btw-verlegd - T",
				account_name="Te vorderen Btw-verlegd",
			)
		]

		rows = self._rows_for(purchase_rows)
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertEqual(by_rubric["5b"]["amount"], 0.00)

	def test_a_verlegd_line_is_reported_to_the_user_not_swallowed(self):
		purchase_rows = [
			self._purchase_row(
				account_head="Te vorderen Btw-verlegd - T",
				account_name="Te vorderen Btw-verlegd",
			)
		]
		sales = [_fake_sales_invoice(net_total=2000.0, vat_amount=420.0, rubric="1a")]

		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=(sales, set(), 0.0),
		), _only_purchase_query(purchase_rows), patch("frappe.msgprint") as msgprint:
			fetch_vat_data(_UNPOPULATED_WINDOW)

		self.assertTrue(msgprint.called)
		warned = " ".join(str(call) for call in msgprint.call_args_list)
		self.assertIn("PINV-B8-0001", warned)

	def test_a_non_vat_tax_line_does_not_reach_5b(self):
		purchase_rows = [
			self._purchase_row(
				account_head="Duties and Taxes - T", account_name="Duties and Taxes"
			)
		]

		rows = self._rows_for(purchase_rows)
		by_rubric = {row["rubric"]: row for row in rows}

		self.assertEqual(by_rubric["5b"]["amount"], 0.00)


# =====================================================================
# P1.7 (print format) — the template must not drift from the data again
# =====================================================================
#
# `vat_declaration.html` is the template Frappe renders for the report's
# standard Print and PDF entries: `frappe/desk/query_report.py` loads it
# with `get_html_format` and hands it back as `html_format`, which
# `query_report.js` passes to `frappe.render_template`.
#
# It had rotted in three ways at once, none of them visible from the
# report page, because the report's own JS button opens its own window:
#
#   * It declared a Jinja `macro`. That engine is not Jinja — it is
#     JavaScript — so `new Function()` threw and Print and PDF failed
#     before rendering a single row.
#   * It indexed rows by POSITION, `data[0]` through `data[23]`, against a
#     layout that no longer exists. fetch_vat_data returns 19 rows, so
#     everything from `data[19]` was out of range and the indices that did
#     resolve pointed at the wrong row — `data[18]` expected 5a and is
#     Totaal. P1.7 removed exactly this implicit contract from the JS and
#     left the template behind.
#   * It recomputed VAT from hardcoded rates (`amount * 0.21`, and a 0.05
#     that exists nowhere in Dutch VAT law), which is the P1.6 defect.
#
# These assertions are structural on purpose. A Python suite cannot render
# a JavaScript template, but it can pin the contract the template broke:
# rubrieken are addressed by name, and the VAT is read rather than
# recomputed. HTML comments are stripped first so that describing the old
# defect in the file does not trip the check on it.

import os
import re


def _print_template():
	path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vat_declaration.html")
	with open(path, encoding="utf-8") as handle:
		return re.sub(r"<!--.*?-->", "", handle.read(), flags=re.DOTALL)


class TestPrintTemplateAddressesRubrieksByName(FrappeTestCase):
	"""vat_declaration.html — P1.7 applied to the print format."""

	def test_no_row_is_addressed_by_position(self):
		positional = re.findall(r"data\[\s*\d+\s*\]", _print_template())

		self.assertEqual(positional, [])

	def test_the_template_declares_no_jinja_macro(self):
		"""The engine is JavaScript. A macro makes new Function() throw."""
		template = _print_template()

		self.assertNotIn("macro", template)

	def test_no_vat_figure_is_recomputed_from_a_hardcoded_rate(self):
		rates = re.findall(r"\*\s*0\.\d+", _print_template())

		self.assertEqual(rates, [])

	def test_no_template_delimiter_hides_inside_an_html_comment(self):
		"""
		The engine rewrites its delimiters across the whole file, comments
		included, so a comment that quotes one compiles as code. Writing
		this defect up inside the file is exactly how that happens: the
		first draft of the comment above named the Jinja tag it was warning
		about, and the render died on "macro is not defined".
		"""
		path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vat_declaration.html")
		with open(path, encoding="utf-8") as handle:
			comments = re.findall(r"<!--.*?-->", handle.read(), flags=re.DOTALL)

		for comment in comments:
			for delimiter in ("{%", "%}", "{{", "}}"):
				self.assertNotIn(delimiter, comment)

	def test_every_rubriek_the_report_returns_is_named_in_the_template(self):
		"""
		The contract that replaced the positional one. A rubriek added to
		fetch_vat_data and forgotten in the print is a silently missing line
		on a tax return.
		"""
		with patch(
			"erpnext.accounts.report.vat_declaration.vat_declaration.classify_period_sales",
			return_value=([], set(), 0.0),
		), _only_purchase_query([]), patch("frappe.msgprint"):
			rows = fetch_vat_data(_UNPOPULATED_WINDOW)

		template = _print_template()
		missing = [
			row["rubric"]
			for row in rows
			if row["rubric"] and '"%s"' % row["rubric"] not in template
		]

		self.assertEqual(missing, [])

	def test_rubriek_2a_is_named_with_the_buyers_wording(self):
		"""
		P2.4. 2a "Verleggingsregelingen binnenland" belongs to the buyer:
		the official label is "Leveringen/diensten waarbij de omzetbelasting
		naar u is verlegd". The template used to carry seller-side wording
		("Leveringen waarop de verleggingsregeling van toepassing is"), which
		was itself evidence of the wrong assumption this defect fixes.
		"""
		template = _print_template()

		self.assertIn("Leveringen/diensten waarbij de omzetbelasting naar u is verlegd", template)
		self.assertNotIn("Leveringen waarop de verleggingsregeling van toepassing is", template)
