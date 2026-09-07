# Copyright (c) 2026, TVS and contributors
# For license information, please see license.txt

"""
F.9, F.10 and F.11 (audit A.5) — the ICP listing returns zero rows for every input.

The defect is a contradiction inside one file. `Country Code` is derived in SQL
as `LEFT(tax_id, 2)`, which requires the country prefix to be PRESENT in
`tax_id`; `validate_eu_vat_number` then matches patterns written for the number
WITHOUT it. Both cannot be true of one string, so measured, 0 of 10 well-formed
EU VAT numbers survive validation — and the rejection reaches only
`frappe.log_error`, so the caller receives a complete-looking report with a
filing that is quietly short.

It matters more the moment the zero-rate gate opens. Rubriek `3b` of the VAT
return is driven from `tvs_tax_regime` and has no such validator. Once invoices
reach `EU_B2B_INTRA`, `3b` fills while this listing stays at zero, and the two
filings the Belastingdienst cross-checks disagree by the whole amount.

Three things this file pins:

  * F.9 — the prefix is stripped before matching, so a real `tax_id` validates;
  * F.10 — a row that fails validation is REPORTED, never dropped, because an
    empty listing is indistinguishable from a month with no intra-community
    sales;
  * F.11 — the file exists at all. `test_vat_declaration.py` did; this did not.
"""

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from erpnext.accounts.report.icp_declaration.icp_declaration import (
	get_columns,
	is_eu_country,
	validate_eu_vat_number,
	validate_icp_data,
)


# The ten well-formed numbers audit.md A.5 measured, all ten of which failed.
WELL_FORMED_EU_VAT_NUMBERS = (
	("DE123456789", "DE"),
	("ATU12345678", "AT"),
	("BE0123456789", "BE"),
	("FR12123456789", "FR"),
	("ESA12345674", "ES"),
	("IT12345678901", "IT"),
	("PL1234567890", "PL"),
	("EL123456789", "EL"),
	("GR123456789", "GR"),
	("BE 0123.456.789", "BE"),
)


class TestValidateEuVatNumber(FrappeTestCase):
	"""F.9 — the prefix the SQL requires must not be what the pattern rejects."""

	def test_the_ten_numbers_the_audit_measured_all_validate(self):
		"""
		This is A.5 as one assertion. Production storage carries the prefix —
		the site's own values read `NL853871334B01`, `FR…` — so every one of
		these is the shape a real `tax_id` has.
		"""
		for vat_number, country_code in WELL_FORMED_EU_VAT_NUMBERS:
			with self.subTest(vat_number=vat_number):
				self.assertTrue(
					validate_eu_vat_number(vat_number, country_code),
					"%s should validate for %s" % (vat_number, country_code),
				)

	def test_a_number_stored_without_its_prefix_still_validates(self):
		"""
		The prefix is stripped only when it equals the expected country code, so
		a number that never carried one is matched as it stands. A Belgian
		number is ten digits and `BE` is not two of them.
		"""
		self.assertTrue(validate_eu_vat_number("0123456789", "BE"))
		self.assertTrue(validate_eu_vat_number("123456789", "DE"))

	def test_a_number_of_the_wrong_length_is_still_refused(self):
		"""
		Stripping must not turn the validator into something that accepts
		anything. Eight digits is not a German VAT number.
		"""
		self.assertFalse(validate_eu_vat_number("DE12345678", "DE"))
		self.assertFalse(validate_eu_vat_number("DE1234567890", "DE"))

	def test_separators_are_ignored_but_the_prefix_is_not_guessed(self):
		"""Spaces and dots are formatting; the two letters are data."""
		self.assertTrue(validate_eu_vat_number("BE 0123.456.789", "BE"))
		self.assertFalse(validate_eu_vat_number("FR123456789", "DE"))

	def test_greece_validates_under_both_its_codes(self):
		"""
		`EL` is the VAT prefix and `GR` is the ISO code, and both reach this
		function: the SQL derives the code from the stored `tax_id`, so whichever
		one TVS typed is the one that arrives. `resolve-tax-treatment.ts` uses
		`GR`; the Belastingdienst uses `EL`. Refusing either files nothing.
		"""
		self.assertTrue(validate_eu_vat_number("EL123456789", "EL"))
		self.assertTrue(validate_eu_vat_number("GR123456789", "GR"))
		self.assertTrue(validate_eu_vat_number("EL123456789", "GR"))
		self.assertTrue(validate_eu_vat_number("GR123456789", "EL"))

	def test_the_lithuanian_pattern_is_anchored_on_both_alternatives(self):
		"""
		`r'^[0-9]{9}|[0-9]{12}$'` binds the alternation across the anchors, so
		`^[0-9]{9}` matches ANY string opening with nine digits. Ten digits is
		not a Lithuanian VAT number and must not pass.
		"""
		self.assertTrue(validate_eu_vat_number("LT123456789", "LT"))
		self.assertTrue(validate_eu_vat_number("LT123456789012", "LT"))
		self.assertFalse(validate_eu_vat_number("LT1234567890", "LT"))
		self.assertFalse(validate_eu_vat_number("LT12345678901", "LT"))

	def test_an_empty_or_unknown_input_is_refused_rather_than_crashing(self):
		self.assertFalse(validate_eu_vat_number("", "DE"))
		self.assertFalse(validate_eu_vat_number("DE123456789", ""))
		self.assertFalse(validate_eu_vat_number(None, "DE"))
		self.assertFalse(validate_eu_vat_number("XX123456789", "XX"))


class TestIsEuCountry(FrappeTestCase):
	"""A Greek row must not be dropped for wearing the other of its two codes."""

	def test_greece_is_in_the_union_under_both_codes(self):
		self.assertTrue(is_eu_country("EL"))
		self.assertTrue(is_eu_country("GR"))

	def test_a_non_member_is_still_outside(self):
		self.assertFalse(is_eu_country("GB"))
		self.assertFalse(is_eu_country("NO"))
		self.assertFalse(is_eu_country(""))


def _row(vat_number, country_code, net_amount=100.0, total_vat=0.0, customer="CUST-001"):
	return {
		"Period": "2026-01",
		"Customer Name": "Test Customer",
		"Customer Code": customer,
		"VAT Identification Number": vat_number,
		"Country Code": country_code,
		"Net Amount": net_amount,
		"Total VAT": total_vat,
		"Invoice Type": "Invoice",
		"Transaction Code": "L",
		"Transaction Count": 1,
		"Currency": "EUR",
		"Exchange Rate": 1.0,
	}


class TestValidateIcpData(FrappeTestCase):
	"""F.10 — a row that fails validation is reported, not dropped."""

	def setUp(self):
		super().setUp()
		log_error = patch("frappe.log_error")
		msgprint = patch("frappe.msgprint")
		self.addCleanup(log_error.stop)
		self.addCleanup(msgprint.stop)
		self.log_error = log_error.start()
		self.msgprint = msgprint.start()

	def test_a_bad_row_and_a_good_row_both_survive_and_the_bad_one_is_named(self):
		"""
		The verify cell of F.10, as one test. An unusable VAT number is a data
		error a human fixes — it is not turnover the filing may forget.
		"""
		data = validate_icp_data([_row("DE123456789", "DE"), _row("DE12345678", "DE", customer="CUST-002")])

		self.assertEqual(len(data), 2)

		good = next(row for row in data if row["Customer Code"] == "CUST-001")
		bad = next(row for row in data if row["Customer Code"] == "CUST-002")

		self.assertFalse(good["Validation"])
		self.assertTrue(bad["Validation"])
		self.assertIn("DE12345678", bad["Validation"])

	def test_the_good_rows_amount_is_untouched_by_the_bad_one(self):
		"""A neighbour's data error may not move a figure that will be filed."""
		data = validate_icp_data([_row("DE123456789", "DE", net_amount=334.56, total_vat=0.0)])

		self.assertEqual(data[0]["Net Amount"], 334.56)
		self.assertEqual(data[0]["Total VAT"], 0.0)

	def test_a_non_eu_country_is_reported_rather_than_dropped(self):
		"""
		An intra-community listing carrying a British row is wrong, and so is a
		listing that silently forgot one. Report it and let a human decide.
		"""
		data = validate_icp_data([_row("GB123456789", "GB")])

		self.assertEqual(len(data), 1)
		self.assertIn("GB", data[0]["Validation"])

	def test_a_greek_supply_reaches_the_listing_under_either_code(self):
		data = validate_icp_data([_row("EL123456789", "EL"), _row("GR123456789", "GR", customer="CUST-002")])

		self.assertEqual(len(data), 2)
		self.assertFalse(data[0]["Validation"])
		self.assertFalse(data[1]["Validation"])

	def test_a_row_below_the_one_euro_threshold_is_not_filed(self):
		"""
		The >= €1 rule is a filing rule, not a data error: it is enforced in the
		HAVING clause too, and a row under it is genuinely not declarable.
		"""
		data = validate_icp_data([_row("DE123456789", "DE", net_amount=0.4)])

		self.assertEqual(data, [])

	def test_a_credit_note_below_minus_one_euro_is_still_filed(self):
		"""The threshold is on the absolute value; a refund is declarable."""
		data = validate_icp_data([_row("DE123456789", "DE", net_amount=-334.56)])

		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["Net Amount"], -334.56)

	def test_amounts_are_rounded_to_cents(self):
		data = validate_icp_data([_row("DE123456789", "DE", net_amount=100.005, total_vat=21.004)])

		self.assertEqual(data[0]["Net Amount"], 100.0)
		self.assertEqual(data[0]["Total VAT"], 21.0)

	def test_an_empty_period_returns_no_rows_and_raises_nothing(self):
		self.assertEqual(validate_icp_data([]), [])
		self.msgprint.assert_not_called()

	def test_the_failures_still_reach_the_error_log(self):
		"""
		F.10 adds a channel; it does not remove one. The report is what an
		accountant reads, the log is what a developer reads.
		"""
		validate_icp_data([_row("DE12345678", "DE")])

		self.log_error.assert_called_once()
		self.msgprint.assert_called_once()


class TestGetColumns(FrappeTestCase):
	"""A reported failure that has no column to appear in is still dropped."""

	def test_the_validation_column_exists(self):
		fieldnames = [column["fieldname"] for column in get_columns()]

		self.assertIn("Validation", fieldnames)

	def test_the_columns_the_filing_needs_are_all_present(self):
		"""
		Jantine's requirement, verbatim: country, VAT nr of the customer, total
		amount of that customer of that month.
		"""
		fieldnames = [column["fieldname"] for column in get_columns()]

		for fieldname in ("Period", "Country Code", "VAT Identification Number", "Net Amount"):
			self.assertIn(fieldname, fieldnames)
