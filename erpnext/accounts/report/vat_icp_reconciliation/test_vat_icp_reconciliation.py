# Copyright (c) 2026, TVS and contributors
# For license information, please see license.txt

"""
F.12 — the two filings the Belastingdienst cross-checks must agree.

Rubriek `3b` of the VAT return and the ICP listing report the same supplies, and
they are computed by different code from different columns:

  * `3b` comes from `tvs_tax_regime` through `classify_sales_rubric`, with no
    validator, no VAT-number requirement and no threshold;
  * the ICP listing comes from `si.tax_id` through a query that requires the
    number to be present, at least eight characters, not Dutch, and worth at
    least one euro.

So they can disagree while neither looks wrong on its own. Measured on the site
2026-09-03: 82 submitted invoices carry no `si.tax_id` while their Customer
does. Each one of those, the day it rates `EU_B2B_INTRA`, lands in `3b` and is
absent from the listing — silently, because an ICP listing that is short looks
exactly like a listing that is complete.

The load-bearing assertion of this file is `test_the_itemisation_is_complete`:
the reported rows must account for the WHOLE gap between the two totals. A
reconciliation that reports a difference it cannot itemise is worse than none,
because it is read as if it were the whole story.
"""

from frappe.tests.utils import FrappeTestCase

from erpnext.accounts.report.vat_icp_reconciliation.vat_icp_reconciliation import (
	get_columns,
	icp_exclusion_reason,
	icp_invoice_names,
	reconcile,
)


def declared(invoice, net, rubric="3b", tax_id="DE123456789", customer="CUST-DE"):
	"""One submitted invoice as `classify_period_sales` reports it."""
	return {
		"invoice": invoice,
		"customer": customer,
		"customer_name": customer,
		"period": "2026-01",
		"net": net,
		"rubric": rubric,
		"tax_id": tax_id,
	}


def listed(net, invoices, tax_id="DE123456789", customer="CUST-DE"):
	"""One row of the ICP listing, in the shape `icp_declaration` returns."""
	return {
		"Period": "2026-01",
		"Customer Name": customer,
		"Customer Code": customer,
		"VAT Identification Number": tax_id,
		"Net Amount": net,
		"Invoice Numbers": ",".join(invoices),
		"Validation": "",
	}


class TestReconcileAgreement(FrappeTestCase):
	"""The quiet case: the two filings say the same thing."""

	def test_both_totals_are_reported_even_when_they_agree(self):
		"""
		The number is the point. "No differences" is not a filing check — an
		accountant needs to see the two figures that matched.
		"""
		result = reconcile([declared("SI-1", 100.0)], [listed(100.0, ["SI-1"])])

		self.assertEqual(result["rubric_3b_total"], 100.0)
		self.assertEqual(result["icp_total"], 100.0)
		self.assertEqual(result["difference"], 0.0)

	def test_an_agreeing_period_itemises_nothing(self):
		result = reconcile([declared("SI-1", 100.0)], [listed(100.0, ["SI-1"])])

		self.assertEqual(result["rows"], [])

	def test_an_invoice_outside_3b_is_not_counted_on_either_side(self):
		"""
		A domestic invoice belongs to neither filing. It must not appear as a
		difference simply for existing in the period.
		"""
		rows = [declared("SI-1", 100.0), declared("SI-2", 500.0, rubric="1a", tax_id="")]

		result = reconcile(rows, [listed(100.0, ["SI-1"])])

		self.assertEqual(result["rubric_3b_total"], 100.0)
		self.assertEqual(result["rows"], [])

	def test_a_period_with_no_intra_community_supply_at_all_reconciles(self):
		"""
		Both totals are zero and that is a true reconciliation, not a missing
		one. This is the state the site is in until reception records a
		shipped channel, and it must not read as a clean bill of health for
		code that has never been exercised.
		"""
		result = reconcile([declared("SI-1", 900.0, rubric="1a")], [])

		self.assertEqual(result["rubric_3b_total"], 0.0)
		self.assertEqual(result["icp_total"], 0.0)
		self.assertEqual(result["difference"], 0.0)
		self.assertTrue(result["both_totals_are_zero"])

	def test_a_reconciled_period_that_filed_something_is_not_flagged_as_empty(self):
		result = reconcile([declared("SI-1", 100.0)], [listed(100.0, ["SI-1"])])

		self.assertFalse(result["both_totals_are_zero"])


class TestInvoicesTheListingNeverSaw(FrappeTestCase):
	"""`3b` fills, the listing does not. This is the shape of the defect."""

	def test_an_invoice_with_no_vat_number_is_itemised(self):
		"""The 82 invoices measured on the site are exactly this row."""
		result = reconcile([declared("SI-1", 250.0, tax_id="")], [])

		self.assertEqual(result["difference"], 250.0)
		self.assertEqual(len(result["rows"]), 1)
		self.assertEqual(result["rows"][0]["invoice"], "SI-1")
		self.assertEqual(result["rows"][0]["rubric_3b"], 250.0)
		self.assertEqual(result["rows"][0]["icp"], 0.0)
		self.assertEqual(result["rows"][0]["difference"], 250.0)

	def test_the_row_names_the_customer_so_it_can_be_corrected(self):
		result = reconcile([declared("SI-1", 250.0, tax_id="", customer="CUST-BE")], [])

		self.assertEqual(result["rows"][0]["customer"], "CUST-BE")

	def test_several_missing_invoices_are_each_itemised(self):
		rows = [declared("SI-1", 250.0, tax_id=""), declared("SI-2", 75.0, tax_id="")]

		result = reconcile(rows, [])

		self.assertEqual([row["invoice"] for row in result["rows"]], ["SI-1", "SI-2"])
		self.assertEqual(result["difference"], 325.0)


class TestIcpExclusionReason(FrappeTestCase):
	"""
	Why the listing left it out, named in the words of the filter that did it.

	These mirror the WHERE clause of `fetch_icp_data` and the threshold of
	`validate_icp_data`. They are an explanation, never the membership
	decision: what is on the listing is decided by the listing itself.
	"""

	def test_a_missing_vat_number_says_so(self):
		self.assertIn("VAT number", icp_exclusion_reason("", 250.0))

	def test_a_none_vat_number_is_the_same_as_an_empty_one(self):
		self.assertEqual(icp_exclusion_reason(None, 250.0), icp_exclusion_reason("", 250.0))

	def test_a_whitespace_vat_number_is_the_same_as_an_empty_one(self):
		self.assertEqual(icp_exclusion_reason("   ", 250.0), icp_exclusion_reason("", 250.0))

	def test_a_short_vat_number_names_the_length_the_filter_requires(self):
		reason = icp_exclusion_reason("DE12345", 250.0)

		self.assertIn("8", reason)

	def test_a_dutch_vat_number_names_the_domestic_exclusion(self):
		"""
		`NOT (LEFT(tax_id, 2) = 'NL')`. A Dutch number on an invoice declared
		as an intra-community supply is a contradiction worth reading, not a
		row to drop.
		"""
		reason = icp_exclusion_reason("NL853871334B01", 250.0)

		self.assertIn("NL", reason)

	def test_the_dutch_check_ignores_the_separators_the_sql_strips(self):
		"""The SQL removes spaces, dashes and dots before taking the prefix."""
		self.assertEqual(
			icp_exclusion_reason("NL 853.871-334B01", 250.0),
			icp_exclusion_reason("NL853871334B01", 250.0),
		)

	def test_a_separator_inside_the_prefix_is_still_a_dutch_number(self):
		"""
		The SQL takes the first two characters AFTER removing spaces, dashes and
		dots, so `N.L…` is `NL` to the filter that actually excluded the row.
		Reading the raw first two characters would name a different reason than
		the one that fired.
		"""
		self.assertEqual(
			icp_exclusion_reason("N.L 853871334B01", 250.0),
			icp_exclusion_reason("NL853871334B01", 250.0),
		)

	def test_a_missing_vat_number_outranks_the_threshold(self):
		"""
		Both exclude the invoice, and the order decides which one an accountant
		is sent to fix. A missing number is a data error a human corrects; forty
		cents below the threshold is a filing rule working as intended. The
		listing drops the number in its `WHERE`, and only rows that survived it
		ever reach the threshold.
		"""
		self.assertIn("VAT number", icp_exclusion_reason("", 0.40))

	def test_an_amount_below_one_euro_names_the_threshold(self):
		reason = icp_exclusion_reason("DE123456789", 0.40)

		self.assertIn("1", reason)

	def test_the_threshold_is_read_on_the_absolute_amount(self):
		"""A credit note of forty cents is below the threshold too."""
		self.assertEqual(
			icp_exclusion_reason("DE123456789", -0.40),
			icp_exclusion_reason("DE123456789", 0.40),
		)

	def test_a_usable_number_falls_through_to_the_selector(self):
		"""
		Nothing about the number explains the absence, so what excluded it was
		the intra-community selector — the invoice does not carry the regime
		the listing files on.
		"""
		reason = icp_exclusion_reason("DE123456789", 250.0)

		self.assertIn("intra-community", reason)

	def test_an_invalid_format_is_not_an_exclusion(self):
		"""
		F.10 — a row that fails format validation stays on the listing with the
		reason in its `Validation` column. Claiming the format excluded it
		would send an accountant to fix the wrong thing.
		"""
		self.assertNotIn("format", icp_exclusion_reason("DE12345678", 250.0))


class TestIcpInvoiceNames(FrappeTestCase):
	"""
	The listing groups by customer, VAT number, month and currency, and names
	its invoices in a `GROUP_CONCAT`. That string is how a filed row is tied
	back to the documents behind it.
	"""

	def test_one_invoice(self):
		self.assertEqual(icp_invoice_names(listed(100.0, ["SI-1"])), ("SI-1",))

	def test_several_invoices(self):
		self.assertEqual(
			icp_invoice_names(listed(100.0, ["SI-1", "SI-2"])),
			("SI-1", "SI-2"),
		)

	def test_padding_around_the_separator_is_not_part_of_the_name(self):
		row = listed(100.0, [])
		row["Invoice Numbers"] = "SI-1, SI-2 ,SI-3"

		self.assertEqual(icp_invoice_names(row), ("SI-1", "SI-2", "SI-3"))

	def test_a_row_with_no_invoice_names_yields_none(self):
		row = listed(100.0, [])
		row["Invoice Numbers"] = None

		self.assertEqual(icp_invoice_names(row), ())


class TestListedButNotDeclaredUnder3b(FrappeTestCase):
	"""The other direction: the listing files turnover the return does not."""

	def test_an_invoice_on_the_listing_filed_under_another_rubriek_is_itemised(self):
		"""
		The listing's legacy selector still reads `tax_category`, so an invoice
		with no regime can reach the ICP while the return classifies it
		somewhere else entirely.
		"""
		rows = [declared("SI-1", 100.0, rubric="1c")]

		result = reconcile(rows, [listed(100.0, ["SI-1"])])

		self.assertEqual(result["difference"], -100.0)
		self.assertEqual(len(result["rows"]), 1)
		self.assertEqual(result["rows"][0]["difference"], -100.0)

	def test_the_row_names_the_rubriek_the_invoice_actually_filed_under(self):
		rows = [declared("SI-1", 100.0, rubric="1c")]

		result = reconcile(rows, [listed(100.0, ["SI-1"])])

		self.assertIn("1c", result["rows"][0]["reason"])

	def test_an_invoice_the_declaration_never_saw_is_named_as_such(self):
		"""
		The two reports do not take the same company filter. An invoice on the
		listing that the declaration's period never returned is a row an
		accountant has to see, not a silent zero.
		"""
		result = reconcile([], [listed(100.0, ["SI-1"])])

		self.assertEqual(result["difference"], -100.0)
		self.assertEqual(len(result["rows"]), 1)
		self.assertIn("SI-1", result["rows"][0]["invoice"])


class TestAmountsThatDisagree(FrappeTestCase):
	"""
	Both filings name the same invoice and disagree about the money.

	`3b` sums the invoice header's `base_net_total`; the listing sums the
	items' `base_net_amount` with its own sign rule for credit notes. A row
	here is that divergence, and it is the one nobody would find by eye.
	"""

	def test_a_matched_group_whose_money_differs_is_itemised(self):
		result = reconcile([declared("SI-1", 100.0)], [listed(60.0, ["SI-1"])])

		self.assertEqual(result["difference"], 40.0)
		self.assertEqual(len(result["rows"]), 1)
		self.assertEqual(result["rows"][0]["rubric_3b"], 100.0)
		self.assertEqual(result["rows"][0]["icp"], 60.0)
		self.assertEqual(result["rows"][0]["difference"], 40.0)

	def test_a_credit_note_the_listing_signed_the_other_way_is_itemised(self):
		"""
		A credit note reaches `3b` as a negative net. If the listing reports it
		positive, the two filings differ by twice the note while each looks
		internally consistent.
		"""
		result = reconcile([declared("SI-CN", -100.0)], [listed(100.0, ["SI-CN"])])

		self.assertEqual(result["difference"], -200.0)
		self.assertEqual(result["rows"][0]["difference"], -200.0)

	def test_a_difference_under_a_cent_is_not_reported(self):
		"""
		The listing rounds to two decimals and the return does not. Rounding is
		not a disagreement, and reporting it would bury the ones that are.
		"""
		result = reconcile([declared("SI-1", 100.004)], [listed(100.0, ["SI-1"])])

		self.assertEqual(result["rows"], [])


class TestTheItemisationIsComplete(FrappeTestCase):
	"""
	The load-bearing invariant. Every euro of the gap is on a row.

	`vat-fix-plan.md` F.12: *"The two totals are equal for the period, or the
	difference is itemised by invoice."* A report that says "the filings differ
	by 1.204,55" and itemises 900,00 of it is read as though 900,00 were the
	whole story, and the remaining 304,55 is filed wrong with a reconciliation
	on record saying it was checked.
	"""

	def test_the_itemisation_is_complete(self):
		declaration = [
			declared("SI-1", 100.0),  # agrees
			declared("SI-2", 250.0, tax_id=""),  # no VAT number: 3b only
			declared("SI-3", 0.40),  # below the threshold: 3b only
			declared("SI-4", 500.0, rubric="1c"),  # on the listing, filed as 1c
			declared("SI-5", 80.0),  # matched, but the money differs
			declared("SI-6", 900.0, rubric="1a", tax_id=""),  # neither filing
		]
		icp = [
			listed(100.0, ["SI-1"]),
			listed(500.0, ["SI-4"], customer="CUST-FR", tax_id="FR12123456789"),
			listed(60.0, ["SI-5"], customer="CUST-IT", tax_id="IT12345678901"),
			listed(42.0, ["SI-7"], customer="CUST-ES", tax_id="ESA12345674"),
		]

		result = reconcile(declaration, icp)

		self.assertEqual(
			round(sum(row["difference"] for row in result["rows"]), 2),
			result["difference"],
		)
		self.assertEqual(result["unexplained"], 0.0)

	def test_the_totals_are_the_two_filings_and_nothing_else(self):
		declaration = [
			declared("SI-1", 100.0),
			declared("SI-2", 250.0, tax_id=""),
			declared("SI-6", 900.0, rubric="1a"),
		]
		icp = [listed(100.0, ["SI-1"]), listed(42.0, ["SI-7"])]

		result = reconcile(declaration, icp)

		self.assertEqual(result["rubric_3b_total"], 350.0)
		self.assertEqual(result["icp_total"], 142.0)
		self.assertEqual(result["difference"], 208.0)

	def test_an_invoice_counted_on_both_sides_is_not_counted_twice(self):
		"""
		A filed invoice belongs to exactly one listing group — the grouping is
		by customer, number, month and currency. If the itemisation ever
		matched one invoice into two groups, the completeness check above would
		still pass while both rows double-counted it, so it is asserted here on
		its own.
		"""
		declaration = [declared("SI-1", 100.0), declared("SI-2", 100.0)]
		icp = [listed(150.0, ["SI-1", "SI-2"])]

		result = reconcile(declaration, icp)

		self.assertEqual(len(result["rows"]), 1)
		self.assertEqual(result["rows"][0]["difference"], 50.0)


class TestValidationRowsSurviveAZeroResidual(FrappeTestCase):
	"""
	P.2.1 companion — a listing group whose residual nets to zero must still
	surface here if `validate_icp_data` flagged it.

	P.2.1 makes an invoice with no usable VAT number land on the ICP listing
	instead of being dropped by the WHERE clause. Once it lands, it forms its
	own listing group (grouped by, among other things, its own — blank —
	`tax_id`), its declared 3b net equals its ICP net exactly, the residual
	nets to zero, and `reconcile()` used to drop the group here on
	`if abs(residual) < MATERIAL: continue` — never reading `Validation` at
	all. The exact row P.2.1 exists to reveal would disappear again, one
	layer further downstream, with no reconciliation row ever mentioning it.
	"""

	def test_a_zero_residual_group_with_a_validation_flag_is_still_itemised(self):
		icp_row = listed(250.0, ["SI-1"], tax_id=None, customer="CUST-NOVAT")
		icp_row["Validation"] = "Missing VAT number: ..."

		result = reconcile([declared("SI-1", 250.0, tax_id=None, customer="CUST-NOVAT")], [icp_row])

		self.assertEqual(len(result["rows"]), 1)
		self.assertEqual(result["rows"][0]["difference"], 0.0)
		self.assertIn("Missing VAT number", result["rows"][0]["reason"])

	def test_the_zero_residual_validation_row_does_not_corrupt_unexplained(self):
		"""
		Its `difference` is 0.0 by construction (matched 3b net equals ICP
		net), so adding it to `rows` must not move `unexplained` away from
		zero for an otherwise-agreeing period.
		"""
		icp_row = listed(250.0, ["SI-1"], tax_id=None, customer="CUST-NOVAT")
		icp_row["Validation"] = "Missing VAT number: ..."

		result = reconcile([declared("SI-1", 250.0, tax_id=None, customer="CUST-NOVAT")], [icp_row])

		self.assertEqual(result["unexplained"], 0.0)

	def test_a_zero_residual_group_with_no_validation_flag_still_itemises_nothing(self):
		"""The existing behaviour for a clean, agreeing group is unchanged."""
		result = reconcile([declared("SI-1", 100.0)], [listed(100.0, ["SI-1"])])

		self.assertEqual(result["rows"], [])


class TestColumns(FrappeTestCase):
	"""F.10's lesson: a value with no column to appear in is still dropped."""

	def test_every_key_a_row_carries_has_a_column(self):
		result = reconcile([declared("SI-1", 250.0, tax_id="")], [])
		fieldnames = {column["fieldname"] for column in get_columns()}

		for key in result["rows"][0]:
			with self.subTest(key=key):
				self.assertIn(key, fieldnames)

	def test_the_reason_has_a_column_wide_enough_to_read(self):
		reason = [column for column in get_columns() if column["fieldname"] == "reason"][0]

		self.assertGreaterEqual(reason["width"], 240)
