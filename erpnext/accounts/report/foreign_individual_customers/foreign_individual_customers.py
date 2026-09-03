# foreign_individual_customers.py — F.8 (audit A.2)
#
# A foreign customer typed `Individual` can never receive an article 138 supply.
# Article 138 is a supply to a TAXABLE PERSON in another member state, and
# `resolveTaxTreatment` rates `Individual` domestically for exactly that reason.
# So a dealer TVS ships to who is typed `Individual` in ERPNext is charged 21%
# forever, and no amount of shipping evidence or VIES work can change it. The
# audit measured Belgium 17 of 17 and Germany 7 of 7.
#
# Half of F.8 is data, and it is TVS's: correct `customer_type` on the dealers.
# This is the other half — making the mismatch findable before a filing rather
# than after one.

import frappe
from frappe import _

# ERPNext's own Country name, as the Address stores it.
DOMESTIC_COUNTRY = "Netherlands"

# The `customer_type` that closes the article 138 path.
INDIVIDUAL_CUSTOMER_TYPE = "Individual"


def foreign_individual_query():
    """
    The SELECT, returned as text rather than executed, so the rule it encodes —
    only individuals, only foreign, counted once — is testable without a
    database. Same shape `vat_review_hold` uses.

    Why the VAT number is a column and not a filter
    ------------------------------------------------
    `vat-fix-plan.md` asked for "foreign customers carrying a `tax_id` while
    typed Individual". Measured on the site, that returns ZERO rows: of 20
    foreign customers typed `Individual`, not one carries a `tax_id`. The VAT
    number was the plan's proxy for "this one is really a business", and on this
    data the proxy finds nothing because nobody ever recorded one for them —
    which is the same silence A.1 was made of.

    The population that actually cannot be zero-rated is every foreign customer
    typed `Individual`. So that is the filter, and the VAT number is shown and
    sorted on instead: carrying one is the strongest single signal that a row is
    a business and belongs at the top of the worklist.

    Why the country comes through Dynamic Link
    -------------------------------------------
    A Customer carries no country. The Address is attached through
    `Dynamic Link`, and joining it any other way returns nothing at all —
    silently, which is the failure mode this report exists to end. A customer
    with a billing AND a shipping address joins twice, hence DISTINCT: the same
    dealer listed twice reads as two, and a corrected one still appears.
    """
    return """
        SELECT DISTINCT
            c.name AS customer,
            c.customer_name,
            a.country,
            c.tax_id,
            CASE WHEN COALESCE(TRIM(c.tax_id), '') <> '' THEN 1 ELSE 0 END AS has_vat_number,
            (
                SELECT COUNT(*)
                FROM `tabSales Invoice` si
                WHERE si.customer = c.name AND si.docstatus = 1
            ) AS invoices,
            (
                SELECT COALESCE(SUM(si.base_net_total), 0)
                FROM `tabSales Invoice` si
                WHERE si.customer = c.name AND si.docstatus = 1
            ) AS net_total
        FROM `tabCustomer` c
        JOIN `tabDynamic Link` dl
            ON dl.link_name = c.name
            AND dl.link_doctype = 'Customer'
            AND dl.parenttype = 'Address'
        JOIN `tabAddress` a ON a.name = dl.parent
        WHERE c.customer_type = %(individual)s
            AND COALESCE(a.country, '') NOT IN ('', %(domestic_country)s)
        ORDER BY has_vat_number DESC, net_total DESC, a.country, c.customer_name
    """


def execute(filters=None):
    """Columns and rows. This report takes no filters; the whole list is the point."""
    return get_columns(), frappe.db.sql(
        foreign_individual_query(),
        {
            "individual": INDIVIDUAL_CUSTOMER_TYPE,
            "domestic_country": DOMESTIC_COUNTRY,
        },
        as_dict=True,
    )


def get_columns():
    return [
        {
            # The fix is one field on the Customer form, so the row links
            # straight to the record that gets corrected.
            "fieldname": "customer",
            "label": _("Customer"),
            "fieldtype": "Link",
            "options": "Customer",
            "width": 140,
        },
        {"fieldname": "customer_name", "label": _("Customer Name"), "fieldtype": "Data", "width": 220},
        {"fieldname": "country", "label": _("Country"), "fieldtype": "Data", "width": 120},
        {
            "fieldname": "tax_id",
            "label": _("VAT Number"),
            "fieldtype": "Data",
            "width": 160,
        },
        {
            # Sorted on, so the rows most likely to be businesses come first.
            "fieldname": "has_vat_number",
            "label": _("Has VAT Number"),
            "fieldtype": "Check",
            "width": 120,
        },
        {"fieldname": "invoices", "label": _("Submitted Invoices"), "fieldtype": "Int", "width": 130},
        {
            # Which relationships are worth correcting first. The plan's success
            # condition is "none for the dealers TVS ships to", and telling a
            # dealer from a private buyer means seeing who TVS actually invoices.
            "fieldname": "net_total",
            "label": _("Net Invoiced"),
            "fieldtype": "Currency",
            "width": 130,
        },
    ]
