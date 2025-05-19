# tax.py
# TAX Declaration – Belastingdienst Compliant (Enhanced & Audited)

import frappe
from frappe import _
from frappe.utils import getdate, flt
from datetime import timedelta, date

# Enhanced tax_category to rubric mapping with validation
TAX_CATEGORY_MAPPING = {
    "21% binnenland": "1a",
    "9% binnenland": "1b", 
    "6% binnenland": "1b",  # Low rate variant
    "0% binnenland": "1e",
    "vrijgesteld": "1e",
    "eu customer": "3b",
    "afstandsverkopen": "3c",
    "privégebruik": "1d",
    "private gebruik": "1d",
    "diensten buiten eu": "4a",
    "diensten eu": "4b",
    "reverse charge": "2a",
    "verlegd": "2a",
    "export": "3a"
}

# EU Country codes for proper classification
EU_COUNTRIES = [
    'Austria', 'Belgium', 'Bulgaria', 'Croatia', 'Cyprus', 'Czech Republic',
    'Denmark', 'Estonia', 'Finland', 'France', 'Germany', 'Greece', 
    'Hungary', 'Ireland', 'Italy', 'Latvia', 'Lithuania', 'Luxembourg',
    'Malta', 'Netherlands', 'Poland', 'Portugal', 'Romania', 'Slovakia',
    'Slovenia', 'Spain', 'Sweden'
]


def execute(filters=None):
    if not filters:
        filters = {}

    # Set default date range to previous month
    today = date.today()
    first_day_current = date(today.year, today.month, 1)
    last_day_last_month = first_day_current - timedelta(days=1)
    first_day_last_month = date(last_day_last_month.year, last_day_last_month.month, 1)

    from_date = filters.get("from_date") or first_day_last_month.strftime('%Y-%m-%d')
    to_date = filters.get("to_date") or last_day_last_month.strftime('%Y-%m-%d')

    filters.update({
        "from_date": from_date,
        "to_date": to_date,
        "from_date_str": getdate(from_date).strftime('%d-%m-%Y'),
        "to_date_str": getdate(to_date).strftime('%d-%m-%Y'),
        "due_date": (getdate(to_date) + timedelta(days=30)).strftime('%d-%m-%Y'),
        "aangiftenummer": "823862021B014300",
        "rsin": "823862021",
        "naam": "Fiscale Eenheid R.M. Logmans Beheer B.V. en TVS Engineering B.V. C.S."
    })

    columns = get_columns()
    data = fetch_tax_data(filters)
    
    # Add validation summary
    validate_data_integrity(filters)

    return columns, data


def fetch_tax_data(filters):
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")

    # Initialize all rubrics
    rubrics = {}
    for rubric in ["1a", "1b", "1c", "1d", "1e", "2a", "3a", "3b", "3c", "4a", "4b"]:
        rubrics[rubric] = {"net_amount": 0.0, "tax_amount": 0.0}

    # Enhanced Sales Invoice Analysis with proper VAT validation
    sales_data = frappe.db.sql("""
        SELECT
            si.name,
            si.customer,
            si.tax_category,
            si.base_net_total,
            si.customer_address,
            addr.country as customer_country,
            stc.rate,
            stc.base_tax_amount,
            stc.account_head,
            acc.account_type,
            acc.account_name,
            CASE 
                WHEN addr.country = 'Netherlands' THEN 'domestic'
                WHEN addr.country IN ({eu_countries}) THEN 'eu'
                ELSE 'export'
            END AS customer_type
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name AND stc.parenttype = 'Sales Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = stc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(company)s = '' OR si.company = %(company)s)
        ORDER BY si.name, stc.idx
    """.format(eu_countries="'" + "','".join(EU_COUNTRIES) + "'"), {
        "from_date": from_date, 
        "to_date": to_date, 
        "company": company
    }, as_dict=True)

    # Process sales data with enhanced logic
    processed_invoices = {}
    unknown_categories = set()
    
    for row in sales_data:
        invoice_name = row.name
        if invoice_name not in processed_invoices:
            processed_invoices[invoice_name] = {
                "net_total": row.base_net_total or 0,
                "tax_category": (row.tax_category or "").lower().strip(),
                "customer_type": row.customer_type or "unknown",
                "vat_21": 0,
                "vat_9": 0,
                "vat_0": 0,
                "reverse_charge": 0,
                "is_export": False
            }
        
        # Validate VAT amounts (only from VAT accounts)
        if row.account_type == "Tax" and "vat" in (row.account_name or "").lower():
            rate = flt(row.rate or 0)
            tax_amount = flt(row.base_tax_amount or 0)
            
            if rate >= 20 and rate <= 22:  # 21% VAT (with tolerance)
                processed_invoices[invoice_name]["vat_21"] += tax_amount
            elif rate >= 8 and rate <= 10:  # 9% VAT (with tolerance)
                processed_invoices[invoice_name]["vat_9"] += tax_amount
            elif rate == 0:
                processed_invoices[invoice_name]["vat_0"] += tax_amount
                
        # Check for reverse charge
        if row.account_head and ("reverse" in row.account_head.lower() or "verlegd" in row.account_head.lower()):
            processed_invoices[invoice_name]["reverse_charge"] += flt(row.base_tax_amount or 0)

    # Classify transactions into rubrics
    for invoice_name, data in processed_invoices.items():
        tax_category = data["tax_category"]
        net_amount = data["net_total"]
        customer_type = data["customer_type"]
        
        # Determine rubric based on tax category and customer type
        rubric = None
        
        # First try direct mapping
        if tax_category in TAX_CATEGORY_MAPPING:
            rubric = TAX_CATEGORY_MAPPING[tax_category]
        else:
            # Fallback logic based on VAT rates and customer type
            if data["vat_21"] > 0 and customer_type == "domestic":
                rubric = "1a"
            elif data["vat_9"] > 0 and customer_type == "domestic":
                rubric = "1b"
            elif data["vat_0"] > 0 or (data["vat_21"] == 0 and data["vat_9"] == 0):
                if customer_type == "domestic":
                    rubric = "1e"
                elif customer_type == "eu":
                    rubric = "3b"
                elif customer_type == "export":
                    rubric = "3a"
            elif data["reverse_charge"] > 0:
                rubric = "2a"
            else:
                # Unknown category - add to 1c
                rubric = "1c"
                unknown_categories.add(tax_category)
        
        # Override based on customer type for certain rubrics
        if rubric in ["1a", "1b", "1e"]:
            if customer_type == "eu":
                rubric = "3b"
            elif customer_type == "export":
                rubric = "3a"
        
        # Add to appropriate rubric
        if rubric and rubric in rubrics:
            rubrics[rubric]["net_amount"] += net_amount
            rubrics[rubric]["tax_amount"] += data["vat_21"] + data["vat_9"]

    # Calculate total output VAT
    total_output_vat = sum([rubrics[r]["tax_amount"] for r in ["1a", "1b", "1c", "1d"]])
    
    # Add reverse charge VAT
    total_output_vat += rubrics["2a"]["tax_amount"]

    # Purchase Invoice Analysis for Input VAT and Services
    purchase_data = frappe.db.sql("""
        SELECT
            pi.name,
            pi.supplier,
            pi.tax_category,
            pi.base_net_total,
            pi.supplier_address,
            addr.country as supplier_country,
            ptc.rate,
            ptc.base_tax_amount,
            ptc.account_head,
            acc.account_type,
            acc.account_name,
            CASE 
                WHEN addr.country = 'Netherlands' THEN 'domestic'
                WHEN addr.country IN ({eu_countries}) THEN 'eu'
                ELSE 'non_eu'
            END AS supplier_type
        FROM `tabPurchase Invoice` pi
        LEFT JOIN `tabPurchase Taxes and Charges` ptc ON ptc.parent = pi.name AND ptc.parenttype = 'Purchase Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = ptc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = pi.supplier_address
        WHERE pi.docstatus = 1
            AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(company)s = '' OR pi.company = %(company)s)
        ORDER BY pi.name, ptc.idx
    """.format(eu_countries="'" + "','".join(EU_COUNTRIES) + "'"), {
        "from_date": from_date, 
        "to_date": to_date, 
        "company": company
    }, as_dict=True)

    # Process purchase data
    total_input_vat = 0
    services_outside_eu = 0
    services_within_eu = 0
    
    processed_purchases = {}
    
    for row in purchase_data:
        invoice_name = row.name
        if invoice_name not in processed_purchases:
            processed_purchases[invoice_name] = {
                "net_total": row.base_net_total or 0,
                "tax_category": (row.tax_category or "").lower().strip(),
                "supplier_type": row.supplier_type or "unknown",
                "input_vat": 0
            }
        
        # Only count VAT from proper VAT accounts
        if (row.account_type == "Tax" and 
            "vat" in (row.account_name or "").lower() and 
            "input" in (row.account_name or "").lower()):
            processed_purchases[invoice_name]["input_vat"] += flt(row.base_tax_amount or 0)

    # Classify purchase transactions
    for invoice_name, data in processed_purchases.items():
        tax_category = data["tax_category"]
        net_amount = data["net_total"]
        supplier_type = data["supplier_type"]
        
        # Classify services from outside/within EU
        if "dienst" in tax_category or "service" in tax_category:
            if supplier_type == "non_eu":
                services_outside_eu += net_amount
            elif supplier_type == "eu":
                services_within_eu += net_amount
        
        # Sum input VAT
        total_input_vat += data["input_vat"]

    # Update service rubrics
    rubrics["4a"]["net_amount"] = services_outside_eu
    rubrics["4b"]["net_amount"] = services_within_eu

    # Calculate final figures
    net_tax_payable = total_output_vat - total_input_vat

    # Display unknown categories warning
    if unknown_categories:
        frappe.msgprint(
            _("Unknown tax categories encountered (classified as 1c):") + 
            "<br>" + "<br>".join(unknown_categories),
            title=_("Tax Category Mapping Warning"),
            indicator="orange"
        )

    # Return structured data for report
    return [
        {"rubric": "1a", "description": _("Supplies/services taxed at high rate (21%)"), "amount": rubrics["1a"]["net_amount"]},
        {"rubric": "1b", "description": _("Supplies/services taxed at low rate (9%/6%)"), "amount": rubrics["1b"]["net_amount"]},
        {"rubric": "1c", "description": _("Supplies/services taxed at other rates"), "amount": rubrics["1c"]["net_amount"]},
        {"rubric": "1d", "description": _("Private use (privégebruik)"), "amount": rubrics["1d"]["net_amount"]},
        {"rubric": "1e", "description": _("Supplies/services at 0% rate or exempt"), "amount": rubrics["1e"]["net_amount"]},
        {"rubric": "2a", "description": _("Supplies/services whereby VAT was shifted (verlegd)"), "amount": rubrics["2a"]["net_amount"]},
        {"rubric": "3a", "description": _("Exports outside the EU"), "amount": rubrics["3a"]["net_amount"]},
        {"rubric": "3b", "description": _("Supplies to businesses in EU (ICP)"), "amount": rubrics["3b"]["net_amount"]},
        {"rubric": "3c", "description": _("Instalment/distance sales within EU"), "amount": rubrics["3c"]["net_amount"]},
        {"rubric": "4a", "description": _("Services from countries outside the EU"), "amount": rubrics["4a"]["net_amount"]},
        {"rubric": "4b", "description": _("Services from countries within the EU"), "amount": rubrics["4b"]["net_amount"]},
        {"rubric": "", "description": "", "amount": ""},  # Separator
        {"rubric": "5a", "description": _("VAT on supplies/services and VAT charged on import"), "amount": total_output_vat},
        {"rubric": "5b", "description": _("VAT on purchases of supplies/services"), "amount": total_input_vat},
        {"rubric": "5c", "description": _("Subtotal to be paid/reclaimed (5a minus 5b)"), "amount": net_tax_payable},
        {"rubric": "5d", "description": _("Small business scheme deduction"), "amount": 0.0},
        {"rubric": "5e", "description": _("Previously owed VAT"), "amount": 0.0},
        {"rubric": "5f", "description": _("Increase related to this return"), "amount": 0.0},
        {"rubric": "5g", "description": _("VAT to be paid/reclaimed"), "amount": net_tax_payable}
    ]


def validate_data_integrity(filters):
    """Perform data integrity checks"""
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")
    
    issues = []
    
    # Check for invoices without addresses
    missing_address = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(company)s = '' OR si.company = %(company)s)
            AND (si.customer_address IS NULL OR si.customer_address = '')
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]
    
    if missing_address.count > 0:
        issues.append(f"{missing_address.count} sales invoices without customer addresses")
    
    # Check for invoices without tax categories
    missing_tax_category = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(company)s = '' OR si.company = %(company)s)
            AND (si.tax_category IS NULL OR si.tax_category = '')
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]
    
    if missing_tax_category.count > 0:
        issues.append(f"{missing_tax_category.count} sales invoices without tax categories")
    
    # Display validation issues
    if issues:
        frappe.msgprint(
            _("Data integrity issues found:") + "<br>" + "<br>".join(issues),
            title=_("Validation Warning"),
            indicator="red"
        )


def get_columns():
    return [
        {"fieldname": "rubric", "label": _("Rubric"), "fieldtype": "Data", "width": 80},
        {"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 400},
        {"fieldname": "amount", "label": _("Amount (EUR)"), "fieldtype": "Currency", "width": 150}
    ]


# Additional utility functions for extended functionality

def get_icp_details(filters):
    """Generate detailed ICP (Intracommunautaire Prestaties) report"""
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")
    
    return frappe.db.sql("""
        SELECT
            si.customer,
            si.customer_name,
            addr.country,
            SUM(si.base_net_total) as total_amount,
            COUNT(si.name) as invoice_count
        FROM `tabSales Invoice` si
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(company)s = '' OR si.company = %(company)s)
            AND addr.country IN ({eu_countries})
            AND addr.country != 'Netherlands'
            AND (si.tax_category LIKE '%%eu%%' OR si.taxes_and_charges_template LIKE '%%eu%%')
        GROUP BY si.customer, addr.country
        ORDER BY addr.country, si.customer_name
    """.format(eu_countries="'" + "','".join(EU_COUNTRIES) + "'"), {
        "from_date": from_date,
        "to_date": to_date,
        "company": company
    }, as_dict=True)


def validate_vat_numbers(filters):
    """Validate EU VAT numbers for ICP transactions"""
    eu_customers = frappe.db.sql("""
        SELECT DISTINCT 
            si.customer,
            si.customer_name,
            cust.tax_id
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND addr.country IN ({eu_countries})
            AND addr.country != 'Netherlands'
            AND (si.tax_category LIKE '%%eu%%' OR si.taxes_and_charges_template LIKE '%%eu%%')
    """.format(eu_countries="'" + "','".join(EU_COUNTRIES) + "'"), {
        "from_date": filters["from_date"],
        "to_date": filters["to_date"]
    }, as_dict=True)
    
    invalid_vat = []
    for customer in eu_customers:
        tax_id = customer.tax_id or ""
        if not tax_id or len(tax_id) < 8:
            invalid_vat.append(customer.customer_name)
    
    if invalid_vat:
        frappe.msgprint(
            _("EU customers without valid VAT numbers:") + "<br>" + "<br>".join(invalid_vat),
            title=_("VAT Number Validation"),
            indicator="yellow"
        )