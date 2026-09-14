# vat_icp_reconciliation.py
# F.12 — reconcile rubriek 3b of the VAT return against the ICP listing.

"""
The two filings the Belastingdienst cross-checks, checked as a number.

Rubriek `3b` and the ICP listing report the same intra-community supplies, and
they are computed by different code from different columns:

  * `3b` comes from `tvs_tax_regime` through `classify_sales_rubric`, with no
    validator, no VAT-number requirement and no threshold;
  * the ICP listing comes from `si.tax_id` through a query that requires the
    number to be present, at least eight characters, not Dutch, and worth at
    least one euro.

Neither looks wrong on its own when they disagree. Measured on the site
2026-09-03: 82 submitted invoices carry no `si.tax_id` while their Customer
does. Each one, the day it rates `EU_B2B_INTRA`, lands in `3b` and is absent
from the listing.

Two rules this file is built on:

**Neither total is recomputed here.** `3b` is read through
`classify_period_sales`, which is the function the declaration itself sums, and
the listing is read through `fetch_icp_data` + `validate_icp_data`, which is
what the ICP report returns. A reconciliation that re-derived either side would
agree with itself and prove nothing about what gets filed.

**The itemisation accounts for the whole gap.** `unexplained` is the difference
minus the sum of the reported rows, and it is zero by construction. A report
that names a difference of 1.204,55 and itemises 900,00 of it is read as though
900,00 were the whole story.
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.icp_declaration.icp_declaration import (
    fetch_icp_data,
    validate_filters,
    validate_icp_data,
)
from erpnext.accounts.report.vat_declaration.vat_declaration import classify_period_sales

# The rubriek both filings describe. 3a (export outside the EU) has no ICP
# listing at all, and every other rubriek is out of scope by construction.
RUBRIC_3B = "3b"

# The listing's own filters, mirrored for the explanation only. Membership is
# never decided here: what is on the listing is decided by the listing.
ICP_MINIMUM_VAT_NUMBER_LENGTH = 8
ICP_MINIMUM_NET_AMOUNT = 1
ICP_DOMESTIC_PREFIX = "NL"

# Below a cent the two filings agree. The listing rounds to two decimals in
# `validate_icp_data` and the return does not, and reporting that as a
# disagreement would bury the ones that are.
MATERIAL = 0.005


def _money(amount):
    # The `+ 0.0` is not decoration: rounding a small negative residual yields
    # `-0.0`, and a reconciliation whose difference renders as "-0,00" reads as
    # a finding. It is identity for every other float.
    return round(flt(amount), 2) + 0.0


def icp_invoice_names(icp_row):
    """
    The invoices behind one filed listing row.

    The listing groups by month, customer and VAT number, and names
    its documents in a `GROUP_CONCAT`. That string is the only tie from a filed
    row back to the invoices it was built from.
    """
    concatenated = icp_row.get("Invoice Numbers") or ""

    return tuple(name.strip() for name in concatenated.split(",") if name.strip())


def icp_exclusion_reason(tax_id, net_amount):
    """
    Why the listing left an invoice out, in the words of the filter that did it.

    This mirrors the WHERE clause of `fetch_icp_data` and the threshold of
    `validate_icp_data`, in their order. It is an explanation and never a
    decision — the caller already knows the invoice is absent.

    A number that fails FORMAT validation is deliberately not a reason here.
    F.10 keeps such a row on the listing carrying its problem in the
    `Validation` column, so naming the format would send an accountant to fix
    something that is not what excluded it.
    """
    number = (tax_id or "").strip()

    if not number:
        return _(
            "The invoice carries no VAT number (si.tax_id), which the ICP listing requires."
            " The Customer may still have one — that is not the field the listing reads."
        )

    if len(number) < ICP_MINIMUM_VAT_NUMBER_LENGTH:
        return _(
            "The VAT number on the invoice is shorter than the {0} characters the ICP"
            " listing requires."
        ).format(ICP_MINIMUM_VAT_NUMBER_LENGTH)

    separatorless = number.replace(" ", "").replace("-", "").replace(".", "").upper()
    if separatorless.startswith(ICP_DOMESTIC_PREFIX):
        return _(
            "The VAT number is Dutch ({0}), which the ICP listing excludes as domestic."
            " An invoice declared as an intra-community supply to a Dutch number is a"
            " contradiction to resolve before filing."
        ).format(ICP_DOMESTIC_PREFIX)

    if abs(flt(net_amount)) < ICP_MINIMUM_NET_AMOUNT:
        return _(
            "The net amount is below the EUR {0} filing threshold the ICP listing applies."
        ).format(ICP_MINIMUM_NET_AMOUNT)

    return _(
        "The ICP listing did not select it as an intra-community supply: the invoice"
        " carries neither the EU_B2B_INTRA regime nor a legacy tax category the listing"
        " recognises."
    )


def _explain_group(icp_row, member_names, declared_by_name):
    """
    Why a filed listing row and the declared supplies behind it differ.

    Three shapes, and the row says which one it is: an invoice the declaration
    never returned, an invoice the declaration filed under another rubriek, or
    the same invoices carrying different money on the two sides.
    """
    absent = [name for name in member_names if name not in declared_by_name]
    elsewhere = [
        "%s (%s)" % (name, declared_by_name[name]["rubric"] or _("no rubriek"))
        for name in member_names
        if name in declared_by_name and declared_by_name[name]["rubric"] != RUBRIC_3B
    ]

    problems = []

    if absent:
        problems.append(
            _("on the ICP listing but not returned by the VAT declaration for this period: {0}").format(
                ", ".join(absent)
            )
        )

    if elsewhere:
        problems.append(
            _("on the ICP listing while the declaration files it under another rubriek: {0}").format(
                ", ".join(elsewhere)
            )
        )

    if problems:
        return "; ".join(problems)

    return _(
        "The same invoices carry different net amounts on the two filings. Rubriek 3b sums"
        " the invoice total (base_net_total); the listing sums the item lines"
        " (base_net_amount) with its own sign rule for credit notes."
    )


def reconcile(declaration_rows, icp_rows):
    """
    Compare the two filings and itemise every euro they disagree about.

    `declaration_rows` is `classify_period_sales` reshaped: one dict per
    submitted invoice with `invoice`, `customer`, `customer_name`, `period`,
    `tax_id`, `net` and `rubric`. `icp_rows` is what the ICP report returns.

    Two disjoint sources of difference, which is what makes the itemisation
    complete rather than merely plausible:

      * a `3b` invoice named by no listing row — it contributes its whole net;
      * a listing row whose members' declared `3b` net does not equal its own
        total — it contributes that residual.

    An invoice belongs to at most one listing row (the grouping is by month,
    customer, number and currency), so nothing is counted twice.
    """
    declared_by_name = {row["invoice"]: row for row in declaration_rows}
    filed_under_3b = [row for row in declaration_rows if row["rubric"] == RUBRIC_3B]

    listed_names = set()
    group_rows = []

    for icp_row in icp_rows:
        member_names = icp_invoice_names(icp_row)
        listed_names.update(member_names)

        icp_net = _money(icp_row.get("Net Amount"))
        matched_net = _money(
            sum(
                _money(declared_by_name[name]["net"])
                for name in member_names
                if name in declared_by_name and declared_by_name[name]["rubric"] == RUBRIC_3B
            )
        )
        residual = _money(matched_net - icp_net)

        if abs(residual) < MATERIAL:
            continue

        group_rows.append(
            {
                "period": icp_row.get("Period") or "",
                "invoice": ", ".join(member_names),
                "customer": icp_row.get("Customer Code") or "",
                "customer_name": icp_row.get("Customer Name") or "",
                "vat_number": icp_row.get("VAT Identification Number") or "",
                "rubric_3b": matched_net,
                "icp": icp_net,
                "difference": residual,
                "reason": _explain_group(icp_row, member_names, declared_by_name),
            }
        )

    missing_rows = []

    for row in filed_under_3b:
        if row["invoice"] in listed_names:
            continue

        net = _money(row["net"])

        missing_rows.append(
            {
                "period": row.get("period") or "",
                "invoice": row["invoice"],
                "customer": row.get("customer") or "",
                "customer_name": row.get("customer_name") or "",
                "vat_number": (row.get("tax_id") or "").strip(),
                "rubric_3b": net,
                "icp": 0.0,
                "difference": net,
                "reason": icp_exclusion_reason(row.get("tax_id"), net),
            }
        )

    rows = missing_rows + group_rows

    rubric_3b_total = _money(sum(_money(row["net"]) for row in filed_under_3b))
    icp_total = _money(sum(_money(row.get("Net Amount")) for row in icp_rows))
    difference = _money(rubric_3b_total - icp_total)

    return {
        "rubric_3b_total": rubric_3b_total,
        "icp_total": icp_total,
        "difference": difference,
        "rows": rows,
        "unexplained": _money(difference - sum(row["difference"] for row in rows)),
        "both_totals_are_zero": rubric_3b_total == 0.0 and icp_total == 0.0,
    }


def fetch_reconciliation(filters):
    """Both filings for the period, read from the code that files each of them."""
    sales_invoices, _unknown_categories, _reverse_charge = classify_period_sales(filters)

    declaration_rows = [
        {
            "invoice": invoice["invoice"],
            "customer": invoice["customer"],
            "customer_name": invoice["customer_name"],
            "period": invoice["period"],
            "tax_id": invoice["tax_id"],
            "net": flt(invoice["net_total"]),
            "rubric": invoice["rubric"],
        }
        for invoice in sales_invoices
    ]

    return reconcile(declaration_rows, validate_icp_data(fetch_icp_data(filters)))


def summary_rows(result):
    """The two totals and their difference, which is the point of the report."""
    rows = [
        {"invoice": "", "reason": "", "rubric_3b": None, "icp": None, "difference": None},
        {
            "invoice": _("Rubriek 3b — Leveringen binnen de EU"),
            "rubric_3b": result["rubric_3b_total"],
            "icp": None,
            "difference": None,
            "reason": _("As the VAT declaration files it, from tvs_tax_regime."),
        },
        {
            "invoice": _("ICP listing total"),
            "rubric_3b": None,
            "icp": result["icp_total"],
            "difference": None,
            "reason": _("As the ICP declaration files it, from si.tax_id."),
        },
        {
            "invoice": _("Difference"),
            "rubric_3b": None,
            "icp": None,
            "difference": result["difference"],
            "reason": _("{0} invoice line(s) above account for it.").format(len(result["rows"])),
        },
    ]

    if result["both_totals_are_zero"]:
        rows.append(
            {
                "invoice": _("No intra-community supply this period"),
                "rubric_3b": None,
                "icp": None,
                "difference": None,
                "reason": _(
                    "Both filings are zero, so they agree trivially. This is not evidence that"
                    " the two agree on a period that has intra-community turnover in it."
                ),
            }
        )

    # By construction this is zero. If it is ever not, the report says so rather
    # than presenting an itemisation that does not add up.
    if abs(result["unexplained"]) >= MATERIAL:
        rows.append(
            {
                "invoice": _("UNEXPLAINED"),
                "rubric_3b": None,
                "icp": None,
                "difference": result["unexplained"],
                "reason": _(
                    "The rows above do not account for the whole difference. Do not file on this"
                    " reconciliation."
                ),
            }
        )

    return rows


def get_columns():
    return [
        {"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 80},
        {"fieldname": "invoice", "label": _("Invoice"), "fieldtype": "Data", "width": 220},
        {
            "fieldname": "customer",
            "label": _("Customer"),
            "fieldtype": "Link",
            "options": "Customer",
            "width": 120,
        },
        {"fieldname": "customer_name", "label": _("Customer Name"), "fieldtype": "Data", "width": 180},
        {"fieldname": "vat_number", "label": _("VAT Number"), "fieldtype": "Data", "width": 150},
        {"fieldname": "rubric_3b", "label": _("Rubriek 3b (EUR)"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "icp", "label": _("ICP Listing (EUR)"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "difference", "label": _("Difference (EUR)"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "reason", "label": _("Reason"), "fieldtype": "Data", "width": 460},
    ]


def execute(filters=None):
    if not filters:
        filters = {}

    # The ICP listing's own filter contract: a filing check without a company
    # and a period is not a filing check.
    validate_filters(filters)

    result = fetch_reconciliation(filters)

    if result["rows"]:
        frappe.msgprint(
            _(
                "Rubriek 3b and the ICP listing differ by {0} for this period, itemised over"
                " {1} row(s). Both filings are cross-checked by the Belastingdienst."
            ).format(result["difference"], len(result["rows"])),
            title=_("VAT / ICP Reconciliation"),
            indicator="red",
        )

    return get_columns(), result["rows"] + summary_rows(result)
