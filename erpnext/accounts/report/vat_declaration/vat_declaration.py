# vat_declaration.py – Declaración de IVA compatible con Belastingdienst (Versión Mejorada y Auditada)

import frappe
from frappe import _
from frappe.utils import getdate, flt
from datetime import timedelta, date

# Mapeo mejorado de categorías fiscales a rubrieken
TAX_CATEGORY_MAPPING = {
    "21% binnenland": "1a",
    "9% binnenland": "1b",
    "6% binnenland": "1b",  # Tarifa baja alternativa
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
    "verleggingsregeling": "2a",
    "export": "3a"
}

# Incoterms que indican exportación
EXPORT_INCOTERMS = ['EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP']

# Países de la UE para clasificación correcta
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

    # Establecer rango de fechas por defecto al mes anterior
    today = date.today()
    first_day_current = date(today.year, today.month, 1)
    last_day_last_month = first_day_current - timedelta(days=1)
    first_day_last_month = date(last_day_last_month.year, last_day_last_month.month, 1)

    from_date = filters.get("from_date") or first_day_last_month.strftime('%Y-%m-%d')
    to_date = filters.get("to_date") or last_day_last_month.strftime('%Y-%m-%d')
    
    # Actualizar filtros con fechas procesadas
    filters.update({
        "from_date": from_date,
        "to_date": to_date,
        "from_date_str": getdate(from_date).strftime('%d-%m-%Y'),
        "to_date_str": getdate(to_date).strftime('%d-%m-%Y'),
        "due_date": (getdate(to_date) + timedelta(days=30)).strftime('%d-%m-%Y')
    })

    columns = get_columns()
    data = fetch_vat_data(filters)
    
    # Validar integridad de datos
    validate_data_integrity(filters)

    return columns, data


def fetch_vat_data(filters):
    from_date = filters.get("from_date", "1900-01-01")
    to_date = filters.get("to_date", "2100-12-31")
    company = filters.get("company", "")

    # Inicializar rubrieken
    rubrics = {
        "1a": 0.0, "1b": 0.0, "1c": 0.0, "1d": 0.0, "1e": 0.0,
        "2a": 0.0, "3a": 0.0, "3b": 0.0, "3c": 0.0,
        "4a": 0.0, "4b": 0.0, "5a": 0.0, "5b": 0.0
    }

    # === ANÁLISIS DE FACTURAS DE VENTA MEJORADO ===
    sales_query = """
        SELECT
            si.name,
            si.customer,
            LOWER(TRIM(si.tax_category)) AS category,
            UPPER(TRIM(si.incoterm)) AS incoterm,
            si.base_net_total,
            si.customer_address,
            addr.country as customer_country,
            stc.rate,
            stc.base_tax_amount,
            stc.account_head,
            stc.description,
            acc.account_type,
            acc.account_name,
            CASE 
                WHEN addr.country = 'Netherlands' THEN 'domestic'
                WHEN addr.country IN ({eu_countries}) THEN 'eu'
                ELSE 'export'
            END AS customer_type
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc 
            ON stc.parent = si.name AND stc.parenttype = 'Sales Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = stc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.docstatus = 1 
            AND (%(company)s = '' OR si.company = %(company)s)
        ORDER BY si.name, stc.idx
    """.format(eu_countries="'" + "','".join(EU_COUNTRIES) + "'")

    sales_rows = frappe.db.sql(sales_query, {
        "from_date": from_date, 
        "to_date": to_date, 
        "company": company
    }, as_dict=True)

    # === ANÁLISIS DE FACTURAS DE COMPRA MEJORADO ===
    purchase_query = """
        SELECT
            pi.name,
            pi.supplier,
            LOWER(TRIM(pi.tax_category)) AS category,
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
        LEFT JOIN `tabPurchase Taxes and Charges` ptc 
            ON ptc.parent = pi.name AND ptc.parenttype = 'Purchase Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = ptc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = pi.supplier_address
        WHERE pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND pi.docstatus = 1 
            AND (%(company)s = '' OR pi.company = %(company)s)
        ORDER BY pi.name, ptc.idx
    """.format(eu_countries="'" + "','".join(EU_COUNTRIES) + "'")

    purchase_rows = frappe.db.sql(purchase_query, {
        "from_date": from_date, 
        "to_date": to_date, 
        "company": company
    }, as_dict=True)

    # Procesar datos de ventas
    processed_sales = {}
    unknown_categories = set()
    reverse_charge_total = 0.0
    
    for row in sales_rows:
        invoice_name = row.name
        if invoice_name not in processed_sales:
            processed_sales[invoice_name] = {
                "net_total": row.base_net_total or 0,
                "category": row.category or "",
                "incoterm": row.incoterm or "",
                "customer_type": row.customer_type or "unknown",
                "vat_amount": 0,
                "reverse_charge": 0
            }
        
        # Acumular IVA solo de cuentas de impuestos válidas
        if row.account_type == "Tax" and "vat" in (row.account_name or "").lower():
            processed_sales[invoice_name]["vat_amount"] += flt(row.base_tax_amount or 0)
        
        # Detectar reverse charge
        if (row.account_head and ("verlegd" in row.account_head.lower() or "reverse" in row.account_head.lower()) or
            row.description and "verlegd" in row.description.lower()):
            processed_sales[invoice_name]["reverse_charge"] += flt(row.base_tax_amount or 0)
            reverse_charge_total += flt(row.base_tax_amount or 0)

    # Clasificar ventas en rubrieken
    for invoice_name, data in processed_sales.items():
        category = data["category"]
        incoterm = data["incoterm"]
        net_amount = data["net_total"]
        customer_type = data["customer_type"]
        vat_amount = data["vat_amount"]
        
        # Lógica de clasificación mejorada
        rubric = None
        
        # 1. Prioridad a categoría fiscal para ventas nacionales
        if category in TAX_CATEGORY_MAPPING:
            rubric = TAX_CATEGORY_MAPPING[category]
        
        # 2. Verificar coherencia con tipo de cliente
        if rubric in ["1a", "1b", "1e"] and customer_type != "domestic":
            if customer_type == "eu":
                rubric = "3b"
            elif customer_type == "export":
                rubric = "3a"
        
        # 3. Considerar exportación solo si no es venta nacional
        elif not rubric and incoterm in EXPORT_INCOTERMS:
            rubric = "3a"
        
        # 4. Fallback por tipo de cliente
        elif not rubric:
            if customer_type == "eu":
                rubric = "3b"
            elif customer_type == "export":
                rubric = "3a"
            else:
                rubric = "1c"
                unknown_categories.add(category)
        
        # Registrar en el rubrick correspondiente
        if rubric in rubrics:
            rubrics[rubric] += net_amount
        
        # Acumular IVA repercutido
        rubrics["5a"] += vat_amount

    # Añadir reverse charge
    rubrics["2a"] = reverse_charge_total

    # Procesar datos de compras
    processed_purchases = {}
    
    for row in purchase_rows:
        invoice_name = row.name
        if invoice_name not in processed_purchases:
            processed_purchases[invoice_name] = {
                "net_total": row.base_net_total or 0,
                "category": row.category or "",
                "supplier_type": row.supplier_type or "unknown",
                "input_vat": 0
            }
        
        # Acumular IVA soportado solo de cuentas válidas
        if (row.account_type == "Tax" and 
            "vat" in (row.account_name or "").lower() and 
            ("input" in (row.account_name or "").lower() or "soportado" in (row.account_name or "").lower())):
            processed_purchases[invoice_name]["input_vat"] += flt(row.base_tax_amount or 0)

    # Clasificar compras
    for invoice_name, data in processed_purchases.items():
        category = data["category"]
        net_amount = data["net_total"]
        supplier_type = data["supplier_type"]
        
        # Servicios de fuera de la UE
        if category == "diensten buiten eu" or (supplier_type == "non_eu" and "dienst" in category):
            rubrics["4a"] += net_amount
        
        # Servicios de dentro de la UE
        elif category == "diensten eu" or (supplier_type == "eu" and "dienst" in category):
            rubrics["4b"] += net_amount
        
        # Acumular IVA soportado
        rubrics["5b"] += data["input_vat"]

    # Calcular totales
    net_total = rubrics["5a"] - rubrics["5b"]

    # Mostrar advertencias
    if unknown_categories:
        frappe.msgprint(
            _("Categorías fiscales desconocidas detectadas (sumadas a 1c):") + 
            "<br>" + "<br>".join(sorted(unknown_categories)),
            title=_("Advertencia de Mapeo de Categorías"),
            indicator="orange"
        )

    # Retornar datos estructurados
    return [
        {"rubric": "1a", "description": _("1a. Leveringen binnenland hoog tarief (21%)"), "amount": rubrics["1a"]},
        {"rubric": "1b", "description": _("1b. Leveringen binnenland laag tarief (9%/6%)"), "amount": rubrics["1b"]},
        {"rubric": "1c", "description": _("1c. Overige tarieven"), "amount": rubrics["1c"]},
        {"rubric": "1d", "description": _("1d. Privégebruik"), "amount": rubrics["1d"]},
        {"rubric": "1e", "description": _("1e. Leveringen tegen 0% of vrijgesteld"), "amount": rubrics["1e"]},
        {"rubric": "2a", "description": _("2a. Verleggingsregeling binnenland"), "amount": rubrics["2a"]},
        {"rubric": "3a", "description": _("3a. Export buiten de EU"), "amount": rubrics["3a"]},
        {"rubric": "3b", "description": _("3b. Leveringen binnen de EU"), "amount": rubrics["3b"]},
        {"rubric": "3c", "description": _("3c. Afstandsverkopen binnen de EU"), "amount": rubrics["3c"]},
        {"rubric": "4a", "description": _("4a. Diensten uit landen buiten de EU"), "amount": rubrics["4a"]},
        {"rubric": "4b", "description": _("4b. Diensten uit EU-landen"), "amount": rubrics["4b"]},
        {"rubric": "", "description": "", "amount": ""},  # Separador
        {"rubric": "5a", "description": _("5a. Verschuldigde omzetbelasting"), "amount": rubrics["5a"]},
        {"rubric": "5b", "description": _("5b. Voorbelasting"), "amount": rubrics["5b"]},
        {"rubric": "5c", "description": _("5c. Subtotaal (5a - 5b)"), "amount": net_total},
        {"rubric": "5d", "description": _("5d. KOR vermindering"), "amount": 0.0},
        {"rubric": "5e", "description": _("5e. Correctie vorige aangifte"), "amount": 0.0},
        {"rubric": "5f", "description": _("5f. Schatting deze aangifte"), "amount": 0.0},
        {"rubric": "Totaal", "description": _("Totaal te betalen of terug te vorderen"), "amount": net_total}
    ]


def validate_data_integrity(filters):
    """Realizar verificaciones de integridad de datos"""
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")
    
    issues = []
    
    # Verificar facturas sin direcciones
    missing_address = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(company)s = '' OR si.company = %(company)s)
            AND (si.customer_address IS NULL OR si.customer_address = '')
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]
    
    if missing_address.count > 0:
        issues.append(f"{missing_address.count} facturas de venta sin direcciones de cliente")
    
    # Verificar facturas sin categorías fiscales
    missing_tax_category = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(company)s = '' OR si.company = %(company)s)
            AND (si.tax_category IS NULL OR si.tax_category = '')
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]
    
    if missing_tax_category.count > 0:
        issues.append(f"{missing_tax_category.count} facturas de venta sin categorías fiscales")
    
    # Verificar facturas con Incoterms pero sin países
    export_without_country = frappe.db.sql("""
        SELECT COUNT(*) as count
        FROM `tabSales Invoice` si
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(company)s = '' OR si.company = %(company)s)
            AND si.incoterm IN ('EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP')
            AND (addr.country IS NULL OR addr.country = '')
    """, {"from_date": from_date, "to_date": to_date, "company": company}, as_dict=True)[0]
    
    if export_without_country.count > 0:
        issues.append(f"{export_without_country.count} facturas con Incoterms de exportación pero sin país de destino")
    
    # Mostrar problemas de validación
    if issues:
        frappe.msgprint(
            _("Problemas de integridad de datos encontrados:") + "<br>" + "<br>".join(issues),
            title=_("Advertencia de Validación"),
            indicator="red"
        )


def get_columns():
    return [
        {"fieldname": "rubric", "label": _("Rubriek"), "fieldtype": "Data", "width": 80},
        {"fieldname": "description", "label": _("Omschrijving"), "fieldtype": "Data", "width": 400},
        {"fieldname": "amount", "label": _("Bedrag (EUR)"), "fieldtype": "Currency", "width": 150}
    ]


# === FUNCIONES ADICIONALES PARA ANÁLISIS DETALLADO ===

def get_icp_details(filters):
    """Generar reporte detallado de ICP (Intracommunautaire Prestaties)"""
    from_date = filters["from_date"]
    to_date = filters["to_date"]
    company = filters.get("company", "")
    
    return frappe.db.sql("""
        SELECT
            si.customer,
            si.customer_name,
            addr.country,
            cust.tax_id,
            SUM(si.base_net_total) as total_amount,
            COUNT(si.name) as invoice_count
        FROM `tabSales Invoice` si
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(company)s = '' OR si.company = %(company)s)
            AND addr.country IN ({eu_countries})
            AND addr.country != 'Netherlands'
            AND (LOWER(si.tax_category) LIKE '%%eu%%' OR si.base_net_total > 0)
        GROUP BY si.customer, addr.country
        ORDER BY addr.country, si.customer_name
    """.format(eu_countries="'" + "','".join(EU_COUNTRIES) + "'"), {
        "from_date": from_date,
        "to_date": to_date,
        "company": company
    }, as_dict=True)


def validate_eu_vat_numbers(filters):
    """Validar números de IVA de la UE para transacciones ICP"""
    icp_details = get_icp_details(filters)
    
    invalid_vat = []
    for customer in icp_details:
        tax_id = customer.tax_id or ""
        country_code = customer.country[:2].upper() if customer.country else ""
        
        # Validación básica de formato de número de IVA
        if not tax_id or len(tax_id) < 8:
            invalid_vat.append(f"{customer.customer_name} ({customer.country})")
        elif not tax_id.startswith(country_code):
            invalid_vat.append(f"{customer.customer_name} - Número de IVA no coincide con país")
    
    if invalid_vat:
        frappe.msgprint(
            _("Clientes de la UE con números de IVA no válidos:") + "<br>" + "<br>".join(invalid_vat),
            title=_("Validación de Números de IVA"),
            indicator="yellow"
        )
    
    return invalid_vat


def export_to_belastingdienst_format(filters):
    """Exportar datos en formato compatible con Belastingdienst"""
    data = fetch_vat_data(filters)
    
    # Formato específico para declaración electrónica
    declaration_data = {}
    for row in data:
        if row["rubric"] and row["rubric"] != "":
            declaration_data[row["rubric"]] = row["amount"]
    
    return {
        "period": f"{filters['from_date_str']} - {filters['to_date_str']}",
        "declaration_data": declaration_data,
        "validation_passed": len(validate_eu_vat_numbers(filters)) == 0
    }