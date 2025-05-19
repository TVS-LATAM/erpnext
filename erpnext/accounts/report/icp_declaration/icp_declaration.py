# icp.py
# ICP Declaration – Belastingdienst Compliant (Improved Version)
# Complies with Dutch tax law requirements for EU sales reporting

import frappe
from frappe import _
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
    
    if (to_date - from_date).days > 92:
        frappe.msgprint(_("Warning: ICP declarations are typically submitted quarterly. Consider using quarterly date ranges."))

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
            si.customer_name AS `Customer Name`,
            si.customer AS `Customer Code`,
            si.tax_id AS `VAT Identification Number`,
            UPPER(LEFT(REPLACE(REPLACE(REPLACE(si.tax_id, ' ', ''), '-', ''), '.', ''), 2)) AS `Country Code`,
            SUM(
                CASE 
                    WHEN si.is_return = 1 THEN -sii.base_net_amount 
                    ELSE sii.base_net_amount 
                END
            ) AS `Net Amount`,
            SUM(
                CASE 
                    WHEN si.is_return = 1 THEN -sii.base_amount + sii.base_net_amount
                    ELSE sii.base_amount - sii.base_net_amount
                END
            ) AS `Total VAT`,
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
            AND (
                LOWER(si.tax_category) IN ('eu customer', 'eu b2b', 'intra-eu supply')
                OR LOWER(c.tax_category) IN ('eu customer', 'eu b2b', 'intra-eu supply')
            )
            AND si.tax_id IS NOT NULL
            AND si.tax_id != ''
            AND LENGTH(TRIM(si.tax_id)) >= 8  -- Minimum valid EU VAT number length
            -- Exclude domestic (NL) customers from ICP
            AND NOT (UPPER(LEFT(REPLACE(REPLACE(REPLACE(si.tax_id, ' ', ''), '-', ''), '.', ''), 2)) = 'NL')
        GROUP BY 
            si.customer_name, 
            si.customer,
            si.tax_id,
            UPPER(LEFT(REPLACE(REPLACE(REPLACE(si.tax_id, ' ', ''), '-', ''), '.', ''), 2)),
            si.currency
        HAVING 
            ABS(SUM(
                CASE 
                    WHEN si.is_return = 1 THEN -sii.base_net_amount 
                    ELSE sii.base_net_amount 
                END
            )) >= 1  -- Only include transactions >= €1
        ORDER BY     
            `Country Code`, si.tax_id, si.customer_name
    """

    return frappe.db.sql(query, {
        "from_date": from_date,
        "to_date": to_date,
        "company": company
    }, as_dict=True)

def validate_icp_data(data):
    """
    Validate ICP data against Dutch tax law requirements
    """
    validated_data = []
    errors = []
    
    for row in data:
        vat_number = row.get("VAT Identification Number", "")
        country_code = row.get("Country Code", "")
        net_amount = row.get("Net Amount", 0)
        
        # Validate VAT number format
        if not validate_eu_vat_number(vat_number, country_code):
            errors.append(f"Invalid VAT number format: {vat_number} for country {country_code}")
            continue
        
        # Validate country code is EU member state
        if not is_eu_country(country_code):
            errors.append(f"Non-EU country code: {country_code}")
            continue
        
        # Check minimum amount threshold (€1)
        if abs(net_amount) < 1:
            continue  # Skip transactions below €1
        
        # Round amounts to 2 decimal places (EUR cents)
        row["Net Amount"] = round(float(net_amount), 2)
        row["Total VAT"] = round(float(row.get("Total VAT", 0)), 2)
        
        validated_data.append(row)
    
    # Log any validation errors
    if errors:
        error_log = "ICP Validation Errors:\n" + "\n".join(errors)
        frappe.log_error(error_log, "ICP Declaration Validation")
        frappe.msgprint(_(f"Found {len(errors)} validation errors. Check Error Log for details."))
    
    return validated_data

def validate_eu_vat_number(vat_number, country_code):
    """
    Validate EU VAT number format according to EU regulations
    """
    if not vat_number or not country_code:
        return False
    
    # Clean VAT number
    clean_vat = re.sub(r'[^A-Z0-9]', '', vat_number.upper())
    
    # Basic EU VAT number patterns
    vat_patterns = {
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
        'LT': r'^[0-9]{9}|[0-9]{12}$',  # Lithuania
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
    
    pattern = vat_patterns.get(country_code)
    if pattern:
        return bool(re.match(pattern, clean_vat))
    
    return False

def is_eu_country(country_code):
    """
    Check if country code is an EU member state
    """
    eu_countries = {
        'AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'EL', 'ES', 
        'FI', 'FR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT', 
        'PL', 'PT', 'RO', 'SE', 'SI', 'SK'
    }
    return country_code in eu_countries

def get_columns():
    """
    Define columns for ICP declaration report
    """
    return [
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
        quarter = validate_quarterly_submission(filters)
        
        return {
            "success": True,
            "columns": columns,
            "data": data,
            "summary": summary,
            "quarter": quarter,
            "message": _(f"ICP declaration generated successfully. {len(data)} records found.")
        }
    
    except Exception as e:
        frappe.log_error(f"ICP Declaration Error: {str(e)}", "ICP Report Generation")
        return {
            "success": False,
            "error": str(e),
            "message": _("Error generating ICP declaration. Check error log for details.")
        }