# Copyright (c) 2026, TVS and contributors
# For license information, please see license.txt

"""
F.8 (audit A.2) — a foreign customer typed `Individual` can never be zero-rated.

Article 138 is a supply to a TAXABLE PERSON in another member state.
`resolveTaxTreatment` rates `Individual` domestically for exactly that reason,
so a dealer TVS ships to who is typed `Individual` in ERPNext is charged 21%
forever, and no amount of shipping evidence or VIES work changes it. Measured in
the audit: Belgium 17 of 17 and Germany 7 of 7 foreign customers typed
`Individual`.

Half of F.8 is data and belongs to TVS: correct `customer_type` on the dealers.
This is the other half — making the mismatch findable rather than discovered by
an accountant after a filing.

Why this is broader than the plan's wording
--------------------------------------------
`vat-fix-plan.md` asks for "foreign customers carrying a `tax_id` while typed
`Individual`", and its Verify cell expects that query to return rows. Measured
on the site, it returns **zero** — of 20 foreign customers typed `Individual`,
**none carries a `tax_id` at all**. So that filter cannot go from "rows" to
"none after TVS's correction"; it is already at none, for the wrong reason.

A VAT number was the plan's proxy for "this one is really a business", and on
this data the proxy finds nothing, because nobody ever recorded one for them.
The population that actually cannot be zero-rated is every foreign customer
typed `Individual`, so that is what this lists — with the VAT number shown
rather than required, since carrying one is the strongest single signal that a
row is a business and belongs at the top of the list.

Turnover is on the report for the same reason: the plan's own success condition
is "none for the dealers TVS ships to", and telling a dealer from a private
buyer means seeing who TVS actually invoices.
"""

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from erpnext.accounts.report.foreign_individual_customers.foreign_individual_customers import (
    DOMESTIC_COUNTRY,
    INDIVIDUAL_CUSTOMER_TYPE,
    execute,
    foreign_individual_query,
    get_columns,
)


class TestForeignIndividualQuery(FrappeTestCase):
    """What the report is allowed to select."""

    def test_it_selects_only_individuals(self):
        """
        A foreign customer typed `Company` is already on the article 138 path.
        One of those on this list and the list stops being a worklist.
        """
        # Bound, not interpolated — see the parameters case below. What the
        # query text must show is that the type is filtered at all, and
        # `execute` is where the value it binds is asserted.
        self.assertIn("c.customer_type = %(individual)s", foreign_individual_query())

    def test_it_excludes_the_domestic_country(self):
        """
        A Dutch individual is rated correctly at 21% and is not a mismatch. The
        list is only worth reading if everything on it is actionable.
        """
        self.assertIn("%(domestic_country)s", foreign_individual_query())
        self.assertEqual(DOMESTIC_COUNTRY, "Netherlands")

    def test_it_excludes_customers_with_no_country_at_all(self):
        """
        A customer with no address is not evidence of a foreign dealer, it is
        evidence of a missing address. Different problem, different list.
        """
        self.assertIn("COALESCE(a.country, '')", foreign_individual_query())

    def test_it_reaches_the_country_through_the_dynamic_link(self):
        """
        A Customer has no country. The address is attached through
        `Dynamic Link`, and joining it any other way silently returns nothing.
        """
        query = foreign_individual_query()

        self.assertIn("tabDynamic Link", query)
        self.assertIn("dl.link_doctype = 'Customer'", query)
        self.assertIn("dl.parenttype = 'Address'", query)

    def test_it_counts_a_customer_once_however_many_addresses_it_has(self):
        """
        A customer with a billing and a shipping address joins twice. Listed
        twice, the same dealer looks like two, and a corrected one still shows.
        """
        self.assertIn("DISTINCT", foreign_individual_query())

    def test_it_shows_the_vat_number_rather_than_requiring_one(self):
        """
        The plan filtered on `tax_id`; measured, 0 of 20 foreign individuals
        carry one, so that filter returns an empty report on real data. It is a
        column, and a sort key, not a WHERE clause.
        """
        query = foreign_individual_query()

        self.assertIn("c.tax_id", query)
        self.assertNotIn("TRIM(c.tax_id) <> ''", query)
        self.assertNotIn('TRIM(c.tax_id) != ""', query)

    def test_it_counts_only_submitted_invoices(self):
        """A draft is not turnover, and this list is read to prioritise real ones."""
        self.assertIn("docstatus = 1", foreign_individual_query())

    def test_it_passes_its_values_as_parameters_and_never_as_text(self):
        query = foreign_individual_query()

        self.assertIn("%(domestic_country)s", query)
        self.assertIn("%(individual)s", query)
        self.assertNotIn(".format(", query)


class TestOrdering(FrappeTestCase):
    """A list nobody can triage is a list nobody reads."""

    def test_the_strongest_evidence_sorts_first(self):
        """
        Carrying a VAT number is the single strongest signal that a row is a
        business, and turnover says which relationships are worth correcting
        first. Both sort descending, VAT number before turnover.
        """
        query = foreign_individual_query()
        ordering = query[query.index("ORDER BY"):]

        self.assertLess(ordering.index("has_vat_number"), ordering.index("net_total"))
        self.assertIn("DESC", ordering)


class TestExecute(FrappeTestCase):
    """The report contract."""

    def test_it_returns_the_columns_and_the_rows(self):
        with patch("frappe.db.sql", return_value=[{"customer": "CUST-1"}]) as sql:
            columns, data = execute({})

        self.assertEqual(columns, get_columns())
        self.assertEqual(data, [{"customer": "CUST-1"}])
        sql.assert_called_once()

    def test_it_binds_the_domestic_country_and_the_individual_type(self):
        with patch("frappe.db.sql", return_value=[]) as sql:
            execute({})

        values = sql.call_args[0][1]
        self.assertEqual(values["domestic_country"], DOMESTIC_COUNTRY)
        self.assertEqual(values["individual"], INDIVIDUAL_CUSTOMER_TYPE)

    def test_it_survives_being_called_with_no_filters(self):
        """Frappe hands `None` when a report has no filters. It must not raise."""
        with patch("frappe.db.sql", return_value=[]):
            columns, data = execute(None)

        self.assertEqual(data, [])
        self.assertTrue(columns)


class TestGetColumns(FrappeTestCase):
    """What an accountant has to see to act on a row."""

    def test_it_shows_what_the_correction_needs(self):
        fieldnames = [column["fieldname"] for column in get_columns()]

        for fieldname in ("customer", "customer_name", "country", "tax_id", "net_total"):
            self.assertIn(fieldname, fieldnames)

    def test_the_customer_column_links_to_the_record_that_gets_corrected(self):
        """
        The fix is one field on the Customer form. A list that names a customer
        without linking to it makes the reader search for what it just found.
        """
        customer = next(column for column in get_columns() if column["fieldname"] == "customer")

        self.assertEqual(customer["fieldtype"], "Link")
        self.assertEqual(customer["options"], "Customer")
