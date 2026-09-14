# icp.py
# ICP Declaration – Belastingdienst Compliant (Improved Version)
# Complies with Dutch tax law requirements for EU sales reporting

import frappe
from frappe import _
import calendar
import re
from datetime import datetime

def execute(filters=None):
    """
    Main execution function for ICP declaration report
    Returns columns and data for the report
    """
    if not filters:
        filters = {}

    # Validate filters
    validate_filters(filters)
    
    columns = get_columns()
    data = fetch_icp_data(filters)
    
    # Validate ICP data before returning
    validated_data = validate_icp_data(data)
    
    return columns, validated_data

def validate_filters(filters):
    """
    Validate input filters for compliance
    """
    if not filters.get("company"):
        frappe.throw(_("Company is mandatory for ICP declaration"))
    
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("Date range is mandatory for ICP declaration"))
    
    # Ensure date range doesn't exceed one quarter (ICP is quarterly)
    from_date = datetime.strptime(filters.get("from_date"), "%Y-%m-%d")
    to_date = datetime.strptime(filters.get("to_date"), "%Y-%m-%d")
    
    # N.1 — "The ICP declarations need to be done every month." A range of any
    # length is still allowed, because reviewing a quarter or a year is useful;
    # what the filing needs is that its figures never merge two months, which
    # the per-month GROUP BY guarantees for every range. So this stays a
    # msgprint and not a throw, and it says what a filing period is.
    if (to_date - from_date).days > 92:
        frappe.msgprint(
            _(
                "Warning: ICP declarations are filed monthly. This range covers more than a quarter; "
                "the rows are still totalled per customer per month, one filing each."
            )
        )

# V.4 — the only field in either system that separates an article 138
# intra-community supply from an article 146 export. Both zero rates share one
# Moneybird tax rate id and ERPNext's taxes_and_charges templates differ only by
# name, so the stored key is the sole machine-readable discriminator, and
# vat-rules.md states the consequence as a rule: any ICP split must be driven
# from tvs_tax_regime.
INTRA_COMMUNITY_REGIME = "EU_B2B_INTRA"

TAX_REGIME_FIELD = "tvs_tax_regime"

# The categories this report filtered on before the regime existed. Kept for the
# invoices that predate it and nothing else — see intra_community_selector.
LEGACY_INTRA_COMMUNITY_TAX_CATEGORIES = ("eu customer", "eu b2b", "intra-eu supply")


def _legacy_tax_category_clause():
    """The pre-regime selector: the tax category on the invoice or the customer."""
    categories = ", ".join("'%s'" % category for category in LEGACY_INTRA_COMMUNITY_TAX_CATEGORIES)

    return (
        "LOWER(si.tax_category) IN ({categories})"
        " OR LOWER(c.tax_category) IN ({categories})"
    ).format(categories=categories)


def intra_community_selector():
    """
    Which invoices belong on the ICP listing.

    R.2. This report filtered on `tax_category`, and the invoicing pipeline
    deliberately stops posting that field (VD.4) — ERPNext fills it from the
    Customer during validate() instead, and the regime configuration defines no
    category at all. So every invoice the new path creates carries an empty
    category, and the listing reads it on zero lines: a report that returns
    nothing looks exactly like a quarter with no intra-community sales.

    An invoice that stores a regime is now classified by it, which is the rule
    V.4 states. An invoice that stores none keeps the old behaviour, unchanged:
    those are the 1,311 historical invoices that will never have one, and what
    they should be classified by is an open accounting question (Q1), not
    something this change may decide silently.

    The regime lives in a Custom Field installed by `tvs_accountancy`. An
    environment that has not migrated it has no such column, and naming it in
    SQL there would turn a working report into a database error. There, the
    legacy selector is the whole answer — which is what that environment does
    today.
    """
    if not frappe.db.has_column("Sales Invoice", TAX_REGIME_FIELD):
        return _legacy_tax_category_clause()

    return (
        "si.{field} = '{regime}'"
        " OR (COALESCE(si.{field}, '') = '' AND ({legacy}))"
    ).format(field=TAX_REGIME_FIELD, regime=INTRA_COMMUNITY_REGIME, legacy=_legacy_tax_category_clause())


def fetch_icp_data(filters):
    """
    Fetch ICP data from ERPNext database with proper validation
    """
    from_date = filters.get("from_date", "1900-01-01")
    to_date = filters.get("to_date", "2100-12-31")
    company = filters.get("company", "")

    # Enhanced query with proper VAT calculations and compliance checks
    query = """
        SELECT 
            DATE_FORMAT(si.posting_date, '%%Y-%%m') AS `Period`,
            si.customer_name AS `Customer Name`,
            si.customer AS `Customer Code`,
            si.tax_id AS `VAT Identification Number`,
            UPPER(LEFT(REPLACE(REPLACE(REPLACE(si.tax_id, ' ', ''), '-', ''), '.', ''), 2)) AS `Country Code`,
            -- VD.30. These sums used to negate a return's amounts, and that is a
            -- sign applied twice. `make_return_doc` negates `qty`, so ERPNext
            -- stores the credit note's item ALREADY negative: measured on the
            -- local site, an invoice of 120,00 and the credit note that
            -- reverses it store `base_net_amount` 120,00 and -120,00. Negating
            -- the second turned it back into +120,00, so a fully credited
            -- supply was filed as 240,00 of intra-community supplies instead
            -- of leaving the listing.
            --
            -- It mattered beyond one row: rubriek `3b` nets correctly, so every
            -- period holding a credit note made `VAT ICP Reconciliation`
            -- report a difference its itemisation could not explain — and
            -- credit notes are routine here, not an edge case (the deposit
            -- system for gearboxes, mechatronics and shipping boxes).
            --
            -- The stored sign is the whole answer; nothing else is needed.
            SUM(sii.base_net_amount) AS `Net Amount`,
            SUM(sii.base_amount - sii.base_net_amount) AS `Total VAT`,
            CASE 
                WHEN si.is_return = 1 THEN "Credit Note" 
                ELSE "Invoice" 
            END AS `Invoice Type`,
            CASE 
                WHEN si.is_return = 1 THEN "D"
                ELSE "L"
            END AS `Transaction Code`,
            COUNT(DISTINCT si.name) AS `Transaction Count`,
            GROUP_CONCAT(DISTINCT si.name ORDER BY si.name) AS `Invoice Numbers`,
            si.currency AS `Currency`,
            AVG(si.conversion_rate) AS `Exchange Rate`
        FROM  
            `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE 
            si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.docstatus = 1  
            AND si.company = %(company)s
            AND ({intra_community_selector})
            AND si.tax_id IS NOT NULL
            AND si.tax_id != ''
            AND LENGTH(TRIM(si.tax_id)) >= 8  -- Minimum valid EU VAT number length
            -- Exclude domestic (NL) customers from ICP
            AND NOT (UPPER(LEFT(REPLACE(REPLACE(REPLACE(si.tax_id, ' ', ''), '-', ''), '.', ''), 2)) = 'NL')
        GROUP BY 
            DATE_FORMAT(si.posting_date, '%%Y-%%m'),
            si.customer_name, 
            si.customer,
            si.tax_id,
            UPPER(LEFT(REPLACE(REPLACE(REPLACE(si.tax_id, ' ', ''), '-', ''), '.', ''), 2)),
            si.currency
        HAVING 
            -- VD.30. Same correction as `Net Amount` above, and it has to move
            -- with it: a month whose supplies are fully credited now nets to
            -- zero and is dropped here, which is the right filing — there is
            -- nothing to declare — rather than a row of twice the credit.
            ABS(SUM(sii.base_net_amount)) >= 1  -- Only include transactions >= €1
        ORDER BY     
            `Period`, `Country Code`, si.tax_id, si.customer_name
    """

    return frappe.db.sql(
        query.replace("{intra_community_selector}", intra_community_selector()),
        {
            "from_date": from_date,
            "to_date": to_date,
            "company": company,
        },
        as_dict=True,
    )

def validate_icp_data(data):
    """
    F.10 (audit A.5) — a row that fails validation is reported, never dropped.

    Before this, a failing row reached `continue` and `frappe.log_error`, so the
    caller received a complete-looking report over a filing that was quietly
    short — and an empty ICP listing is indistinguishable from a month with no
    intra-community sales at all.

    A supply that was zero-rated under article 138 belongs on the listing. If its
    VAT number is unusable, that is a data error a human fixes before filing, not
    turnover the filing may forget. So the row stays and carries the reason in
    `Validation`; a clean row carries an empty one, which is what an accountant
    scans for.

    It matters most once the zero-rate gate opens. Rubriek `3b` of the VAT return
    is driven from `tvs_tax_regime` and has no validator at all, so a row this
    function used to drop was a row on which the two filings the Belastingdienst
    cross-checks disagreed, invisibly.

    The one row still removed is one below the EUR 1 threshold: that is a filing
    rule rather than a data error, the HAVING clause enforces it too, and such a
    row is genuinely not declarable.
    """
    validated_data = []
    errors = []

    for row in data:
        vat_number = row.get("VAT Identification Number", "")
        country_code = row.get("Country Code", "")
        net_amount = float(row.get("Net Amount", 0) or 0)

        if abs(net_amount) < 1:
            continue

        problems = []

        if not validate_eu_vat_number(vat_number, country_code):
            problems.append(
                _("Invalid VAT number format: {0} for country {1}").format(vat_number, country_code)
            )

        if not is_eu_country(country_code):
            problems.append(_("Non-EU country code: {0}").format(country_code))

        row["Validation"] = " / ".join(problems)
        row["Net Amount"] = round(net_amount, 2)
        row["Total VAT"] = round(float(row.get("Total VAT", 0) or 0), 2)

        errors.extend(problems)
        validated_data.append(row)

    # The report is what an accountant reads and the log is what a developer
    # reads. F.10 adds the first channel; it does not remove the second.
    if errors:
        frappe.log_error("ICP Validation Errors:\n" + "\n".join(errors), "ICP Declaration Validation")
        frappe.msgprint(
            _(
                "{0} validation problem(s) on this listing. Each row names its own in the"
                " Validation column; no row was omitted."
            ).format(len(errors))
        )

    return validated_data

# `EL` is the VAT prefix the Belastingdienst and VIES use for Greece; `GR` is the
# ISO 3166 code, and it is what `resolve-tax-treatment.ts` writes. The SQL derives
# `Country Code` as LEFT(tax_id, 2), so whichever of the two TVS typed is the one
# that arrives here. They are one member state, not two, and refusing either files
# nothing for it.
COUNTRY_CODE_ALIASES = {"GR": "EL"}

EU_MEMBER_STATE_CODES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "PL", "PT", "RO", "SE", "SI", "SK",
}

# Written for the number WITHOUT its country prefix — see strip_country_prefix.
EU_VAT_PATTERNS = {
    'AT': r'^U[0-9]{8}$',  # Austria
    'BE': r'^[0-9]{10}$',  # Belgium
    'BG': r'^[0-9]{9,10}$',  # Bulgaria
    'CY': r'^[0-9]{8}[A-Z]$',  # Cyprus
    'CZ': r'^[0-9]{8,10}$',  # Czech Republic
    'DE': r'^[0-9]{9}$',  # Germany
    'DK': r'^[0-9]{8}$',  # Denmark
    'EE': r'^[0-9]{9}$',  # Estonia
    'EL': r'^[0-9]{9}$',  # Greece
    'ES': r'^[A-Z0-9][0-9]{7}[A-Z0-9]$',  # Spain
    'FI': r'^[0-9]{8}$',  # Finland
    'FR': r'^[A-Z0-9]{2}[0-9]{9}$',  # France
    'HR': r'^[0-9]{11}$',  # Croatia
    'HU': r'^[0-9]{8}$',  # Hungary
    'IE': r'^[0-9][A-Z0-9\+\*][0-9]{5}[A-Z]$|^[0-9]{7}[A-Z]{1,2}$',  # Ireland
    'IT': r'^[0-9]{11}$',  # Italy
    # F.9 — was r'^[0-9]{9}|[0-9]{12}$', which binds the alternation ACROSS the
    # anchors: `^[0-9]{9}` then matches any string opening with nine digits, so a
    # ten-digit number passed as Lithuanian. The group anchors both alternatives.
    'LT': r'^([0-9]{9}|[0-9]{12})$',  # Lithuania
    'LU': r'^[0-9]{8}$',  # Luxembourg
    'LV': r'^[0-9]{11}$',  # Latvia
    'MT': r'^[0-9]{8}$',  # Malta
    'PL': r'^[0-9]{10}$',  # Poland
    'PT': r'^[0-9]{9}$',  # Portugal
    'RO': r'^[0-9]{2,10}$',  # Romania
    'SE': r'^[0-9]{12}$',  # Sweden
    'SI': r'^[0-9]{8}$',  # Slovenia
    'SK': r'^[0-9]{10}$',  # Slovakia
}


def normalize_country_code(country_code):
    """The single code the patterns and the member-state list are keyed by."""
    if not country_code:
        return ""

    code = country_code.strip().upper()

    return COUNTRY_CODE_ALIASES.get(code, code)


def candidate_prefixes(country_code):
    """Every two-letter prefix a number of this member state may legitimately carry."""
    aliases = sorted(alias for alias, code in COUNTRY_CODE_ALIASES.items() if code == country_code)

    return [country_code] + aliases


def strip_country_prefix(clean_vat, country_code):
    """
    F.9 (audit A.5) — the prefix the SQL requires must not be what the pattern rejects.

    `Country Code` is derived in SQL as LEFT(tax_id, 2), so it is only ever right
    when the prefix is PRESENT; the patterns above are written for the number
    WITHOUT it. Both cannot be true of one string, and measured, 0 of 10
    well-formed EU VAT numbers survived.

    The prefix is removed only when it equals the code being validated against,
    so a number that never carried one is matched as it stands: `BE` is not two
    of the ten digits of a Belgian VAT number, and dropping the first two
    characters unconditionally would turn this into a validator that accepts a
    number two digits short.
    """
    for prefix in candidate_prefixes(country_code):
        if prefix and clean_vat.startswith(prefix):
            return clean_vat[len(prefix):]

    return clean_vat


def validate_eu_vat_number(vat_number, country_code):
    """
    Validate EU VAT number format according to EU regulations.

    Separators are formatting and are discarded; the two leading letters are
    data, and are discarded only when they are the country's own prefix.
    """
    if not vat_number or not country_code:
        return False

    country_code = normalize_country_code(country_code)

    pattern = EU_VAT_PATTERNS.get(country_code)
    if not pattern:
        return False

    clean_vat = re.sub(r'[^A-Z0-9]', '', vat_number.upper())

    return bool(re.match(pattern, strip_country_prefix(clean_vat, country_code)))

def is_eu_country(country_code):
    """
    Check if country code is an EU member state.

    Greece answers to both its codes here, or a Greek supply is dropped for
    wearing the wrong one of the two.
    """
    return normalize_country_code(country_code) in EU_MEMBER_STATE_CODES

def get_columns():
    """
    Define columns for ICP declaration report
    """
    return [
        {
            "fieldname": "Period",
            "label": _("Period"),
            "fieldtype": "Data",
            "width": 90
        },
        {
            "fieldname": "Customer Name", 
            "label": _("Customer Name"), 
            "fieldtype": "Data", 
            "width": 200
        },
        {
            "fieldname": "Customer Code", 
            "label": _("Customer Code"), 
            "fieldtype": "Link",
            "options": "Customer",
            "width": 120
        },
        {
            "fieldname": "VAT Identification Number", 
            "label": _("VAT Identification Number"), 
            "fieldtype": "Data", 
            "width": 180
        },
        {
            "fieldname": "Country Code", 
            "label": _("Country Code"), 
            "fieldtype": "Data", 
            "width": 80
        },
        {
            "fieldname": "Net Amount", 
            "label": _("Net Amount (EUR)"), 
            "fieldtype": "Currency", 
            "width": 120
        },
        {
            "fieldname": "Total VAT", 
            "label": _("Total VAT (EUR)"), 
            "fieldtype": "Currency", 
            "width": 120
        },
        {
            "fieldname": "Invoice Type", 
            "label": _("Invoice Type"), 
            "fieldtype": "Data", 
            "width": 100
        },
        {
            "fieldname": "Transaction Code", 
            "label": _("Transaction Code (L/D)"), 
            "fieldtype": "Data", 
            "width": 100
        },
        {
            "fieldname": "Transaction Count", 
            "label": _("Transaction Count"), 
            "fieldtype": "Int", 
            "width": 80
        },
        {
            "fieldname": "Currency", 
            "label": _("Currency"), 
            "fieldtype": "Data", 
            "width": 80
        },
        {
            "fieldname": "Exchange Rate", 
            "label": _("Avg Exchange Rate"), 
            "fieldtype": "Float", 
            "width": 100,
            "precision": 6
        },
        # F.10 — a reported failure with no column to appear in is still dropped.
        # Empty on every row that is ready to file.
        {
            "fieldname": "Validation",
            "label": _("Validation"),
            "fieldtype": "Data",
            "width": 260
        }
    ]

def export_to_belastingdienst_format(data, filters):
    """
    Export ICP data to Belastingdienst-compatible format
    This function can be called separately to generate the official submission file
    """
    # Implementation for generating XML/CSV file for Belastingdienst submission
    # This would create the proper format for electronic submission
    pass

# Additional utility functions for ICP processing

def get_icp_summary(data):
    """
    Generate summary statistics for ICP declaration
    """
    if not data:
        return {}
    
    summary = {
        "total_customers": len(set(row["Customer Code"] for row in data)),
        "total_transactions": sum(row.get("Transaction Count", 0) for row in data),
        "total_net_amount": sum(row.get("Net Amount", 0) for row in data),
        "total_vat_amount": sum(row.get("Total VAT", 0) for row in data),
        "countries_count": len(set(row["Country Code"] for row in data)),
        "credit_notes_count": len([row for row in data if row["Transaction Code"] == "D"]),
        "invoices_count": len([row for row in data if row["Transaction Code"] == "L"])
    }
    
    return summary

def validate_declaration_period(filters):
    """
    Which filing period this date range is, if it is a whole one.

    N.1 — "The ICP declarations need to be done every month." A monthly range
    used to be unrecognised: only whole quarters were named, so every monthly
    run reported no period at all and the caller could not tell a complete
    filing from an arbitrary range.

    Returns a dict describing the period, or None when the range is neither a
    whole month nor a whole quarter. None is informational: an arbitrary range
    is still reported, and its rows are still totalled per month.
    """
    from_date = datetime.strptime(filters.get("from_date"), "%Y-%m-%d").date()
    to_date = datetime.strptime(filters.get("to_date"), "%Y-%m-%d").date()

    last_day_of_month = calendar.monthrange(from_date.year, from_date.month)[1]
    if from_date.day == 1 and to_date.year == from_date.year and to_date.month == from_date.month and to_date.day == last_day_of_month:
        return {"type": "month", "label": from_date.strftime("%Y-%m"), "quarter": None}

    quarter = validate_quarterly_submission(filters)
    if quarter:
        return {"type": "quarter", "label": "%d-Q%d" % (from_date.year, quarter), "quarter": quarter}

    return None


def validate_quarterly_submission(filters):
    """
    Validate that the date range represents a complete quarter
    """
    from_date = datetime.strptime(filters.get("from_date"), "%Y-%m-%d")
    to_date = datetime.strptime(filters.get("to_date"), "%Y-%m-%d")
    
    # Define quarter start/end dates
    year = from_date.year
    quarters = {
        1: (datetime(year, 1, 1), datetime(year, 3, 31)),
        2: (datetime(year, 4, 1), datetime(year, 6, 30)),
        3: (datetime(year, 7, 1), datetime(year, 9, 30)),
        4: (datetime(year, 10, 1), datetime(year, 12, 31))
    }
    
    for quarter, (q_start, q_end) in quarters.items():
        if from_date.date() == q_start.date() and to_date.date() == q_end.date():
            return quarter
    
    return None

# Error handling and logging functions

@frappe.whitelist()
def generate_icp_report(filters):
    """
    API endpoint for generating ICP report with proper error handling
    """
    try:
        columns, data = execute(filters)
        summary = get_icp_summary(data)
        # `quarter` is kept for callers that already read it. `period` is what a
        # monthly filing needs, and is None for both when the range is neither
        # a whole month nor a whole quarter.
        period = validate_declaration_period(filters)
        
        return {
            "success": True,
            "columns": columns,
            "data": data,
            "summary": summary,
            "period": period,
            "quarter": period["quarter"] if period else None,
            "message": _(f"ICP declaration generated successfully. {len(data)} records found.")
        }
    
    except Exception as e:
        frappe.log_error(f"ICP Declaration Error: {str(e)}", "ICP Report Generation")
        return {
            "success": False,
            "error": str(e),
            "message": _("Error generating ICP declaration. Check error log for details.")
        }