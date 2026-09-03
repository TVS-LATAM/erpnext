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


# VD.14. La clasificación del cliente vivía dentro del SQL, como un CASE cuya
# última rama era `ELSE 'export'`. `customer_address` entra por un LEFT JOIN, así
# que una factura sin dirección vinculada da `addr.country = NULL`, ningún WHEN
# coincide y la fila cae en esa rama. Después, el bucle de clasificación reescribe
# un `1a` correcto (nacional al 21%) a `3a` (exportación fuera de la UE), mientras
# `rubrics["5a"]` sigue acumulando el 21% que sí se cobró: la declaración termina
# contradiciéndose, con facturación exenta de exportación al lado del IVA cobrado
# sobre ella.
#
# Ausente no es "fuera de la UE". Un país que nadie registró clasifica ahora como
# `unknown`, que ninguna reescritura de rubriek toca, así que la factura se queda
# en el rubriek que le ganó su categoría fiscal. Si además no tenía categoría, el
# fallback la manda a 1c y la suma a `unknown_categories`, que ya dispara el aviso
# al usuario: visible, no silencioso.
#
# Se decide en Python y no en SQL porque una regla que decide una declaración
# fiscal tiene que poder probarse sin base de datos.
def classify_customer_type(country):
    """
    Clasifica al cliente a partir del país de su dirección.

    Devuelve 'domestic', 'eu', 'export' o 'unknown'. 'unknown' es el caso que
    VD.14 separa: un país nulo, vacío o en blanco es una ausencia de dato, no
    una venta fuera de la UE.
    """
    name = (country or "").strip()

    if not name:
        return "unknown"

    # Países Bajos primero: EU_COUNTRIES lo contiene, así que invertir el orden
    # convertiría cada venta nacional en una entrega intracomunitaria.
    if name == "Netherlands":
        return "domestic"

    if name in EU_COUNTRIES:
        return "eu"

    return "export"


# VD.20. El rubriek de cada venta salía de `tax_category`, y la tubería de
# facturación dejó de postear ese campo a propósito (VD.4):
# `createSalesInvoice.ts` lo desestructura del payload por nombre para que la
# máquina de estados no pueda esquivar la omisión. ERPNext lo rellena desde el
# Customer en validate() cuando el Customer trae uno, y medido en el sitio dev
# la mayoría no trae.
#
# Medido el 2026-09-02 sobre `tabSales Invoice` con docstatus = 1:
#
#     (vacío)                  605 facturas   630.323,82 neto
#     omzet werkplaats (21%)    79 facturas    80.675,64 neto
#     netherlands vat 0%         1 factura         120,00 neto
#
# Ninguna de esas tres cadenas es clave de TAX_CATEGORY_MAPPING, así que las
# tres caían por la cadena hasta el fallback nacional `rubric = "1c"`. El
# informe sobre todas las fechas devolvía:
#
#     1a  Leveringen binnenland hoog tarief (21%)         0,00
#     1c  Overige tarieven                          701.074,89
#     5a  Verschuldigde omzetbelasting              148.800,84
#
# Una declaración que no reporta ni un euro de facturación nacional al tipo
# general mientras debe 148.800,84 de IVA sobre 701.074,89 de "otras tarifas"
# se contradice en su propia cara: 148.800,84 / 701.074,89 es el 21,2%, y 1c es
# por definición lo que no va al tipo general. No es un arrastre histórico:
# `(vacío)` es lo que lleva toda factura que la tubería crea hoy, así que el
# error es el estado permanente de aquí en adelante.
#
# `tvs_tax_regime` no aparecía en este informe ni una vez. Es el campo que todo
# el trabajo de regímenes calcula — VD.1, VD.2, VD.14 y VD.18 lo escriben o lo
# reparan — y la declaración que efectivamente se presenta nunca lo leyó.
TAX_REGIME_FIELD = "tvs_tax_regime"

# Los cinco regímenes que deciden un rubriek por sí solos.
#
# F.1 (auditoría A.4). REVIEW_HOLD estaba fuera a propósito, con el razonamiento
# de que meterlo en cualquier rubriek sería la adivinanza que el régimen existe
# para evitar. El razonamiento tiene un agujero: omitir no es "sin rubriek", es
# el camino heredado, y el camino heredado adivina por país. Medido con el
# arnés de F.1 sobre esta misma función antes del cambio:
#
#     REVIEW_HOLD + customer_type='eu'       -> 3b   (entrega intracomunitaria)
#     REVIEW_HOLD + customer_type='export'   -> 3a   (exportación fuera de la UE)
#     REVIEW_HOLD + customer_type='domestic' -> 1c   (otras tarifas)
#
# 3b y 3a son facturación exenta. Mientras tanto `rubrics["5a"]` sigue
# acumulando el 21% que la factura sí cobró — REVIEW_HOLD cobra 21% por
# definición, es la tarifa segura a la que degrada. Es VD.14 y VD.20 otra vez,
# reconstruido por el único régimen que significa "el sistema se NEGÓ a tasar
# este documento": declarar entrega exenta al lado del IVA cobrado sobre ella.
#
# 1a no es una adivinanza. Es lo único que este informe sabe con certeza del
# documento: se cobró el 21% y TVS lo debe. Si la revisión decide después que la
# entrega era de tipo cero, eso es una corrección — recuperable, a diferencia de
# una declaración exenta por un IVA que sí se cobró.
#
# La duda no desaparece por mapearlo; se mueve a donde se puede actuar sobre
# ella. F.2 avisa por Slack el día que ocurre y F.3 es la lista que el contador
# lee antes de presentar el periodo.
#
# Un valor de régimen que este informe no conoce sigue sin adivinarse: cae al
# camino heredado y dispara el aviso de categorías desconocidas.
TAX_REGIME_RUBRIC_MAPPING = {
    "NL_STANDARD": "1a",
    "NL_REDUCED": "1b",
    "EU_B2B_INTRA": "3b",
    "EXPORT_NON_EU": "3a",
    "REVIEW_HOLD": "1a",
}


def tax_regime_select():
    """
    La expresión SELECT que trae el régimen almacenado, o una constante.

    El régimen vive en un Custom Field que instala `tvs_accountancy`. Un entorno
    que no lo migró no tiene la columna, y nombrarla en SQL ahí convertiría un
    informe que funciona en un error de base de datos. Allí la constante vacía
    manda cada factura al camino heredado, que es lo que ese entorno ya corre.
    """
    if not frappe.db.has_column("Sales Invoice", TAX_REGIME_FIELD):
        return "'' AS tax_regime"

    return "si.{field} AS tax_regime".format(field=TAX_REGIME_FIELD)


def classify_sales_rubric(regime, category, incoterm, customer_type):
    """
    En qué rubriek entra una factura de venta.

    Devuelve `(rubriek, categoria_no_mapeada)`. El segundo valor es la categoría
    que hay que sumar a `unknown_categories` para que dispare el aviso, o None
    cuando no hay nada que avisar.

    Una factura que guarda uno de los cinco regímenes decidibles se clasifica
    por él y nada lo reescribe después. El régimen se decidió al emitir el
    documento, con la respuesta de VIES delante; una dirección que nadie llenó o
    un incoterm suelto no pueden darlo vuelta. Reescribir un NL_STANDARD a 3b
    porque la dirección dice Alemania declararía una entrega intracomunitaria
    exenta mientras 5a sigue cargando el 21% que sí se cobró, que es la
    contradicción de VD.14 reconstruida por otro camino.

    Una factura que no guarda régimen conserva el comportamiento anterior byte
    por byte. Son las facturas históricas que nunca van a tener uno, y Q1 se
    respondió "para el pasado no cambia nada": no es algo que este cambio pueda
    decidir en silencio.
    """
    decided = TAX_REGIME_RUBRIC_MAPPING.get((regime or "").strip())
    if decided:
        return decided, None

    # --- camino heredado, sin tocar ---------------------------------------
    rubric = TAX_CATEGORY_MAPPING.get(category)
    unmapped = None

    # Coherencia con el tipo de cliente
    if rubric in ["1a", "1b", "1e"] and customer_type != "domestic":
        if customer_type == "eu":
            rubric = "3b"
        elif customer_type == "export":
            rubric = "3a"

    # Exportación sólo si no es venta nacional
    elif not rubric and incoterm in EXPORT_INCOTERMS:
        rubric = "3a"

    # Fallback por tipo de cliente
    elif not rubric:
        if customer_type == "eu":
            rubric = "3b"
        elif customer_type == "export":
            rubric = "3a"
        else:
            rubric = "1c"
            unmapped = category

    return rubric, unmapped


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
            {tax_regime_select},
            UPPER(TRIM(si.incoterm)) AS incoterm,
            si.base_net_total,
            si.customer_address,
            addr.country as customer_country,
            stc.rate,
            stc.base_tax_amount,
            stc.account_head,
            stc.description,
            acc.account_type,
            acc.account_name
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Taxes and Charges` stc 
            ON stc.parent = si.name AND stc.parenttype = 'Sales Invoice'
        LEFT JOIN `tabAccount` acc ON acc.name = stc.account_head
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.docstatus = 1 
            AND (%(company)s = '' OR si.company = %(company)s)
        ORDER BY si.name, stc.idx
    """

    sales_rows = frappe.db.sql(
        sales_query.replace("{tax_regime_select}", tax_regime_select()),
        {"from_date": from_date, "to_date": to_date, "company": company},
        as_dict=True,
    )

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
                "regime": row.tax_regime or "",
                "incoterm": row.incoterm or "",
                "customer_type": classify_customer_type(row.customer_country),
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
        net_amount = data["net_total"]
        vat_amount = data["vat_amount"]

        # VD.20. La decisión vive en `classify_sales_rubric`, que el régimen
        # gobierna cuando está y que conserva el camino heredado cuando no.
        rubric, unmapped_category = classify_sales_rubric(
            regime=data["regime"],
            category=data["category"],
            incoterm=data["incoterm"],
            customer_type=data["customer_type"],
        )

        if unmapped_category is not None:
            unknown_categories.add(unmapped_category)
        
        # Registrar en el rubrick correspondiente
        if rubric in rubrics:
            rubrics[rubric] += net_amount
        
        # Acumular IVA repercutido
        rubrics["5a"] += vat_amount

    # VD.15. Esta línea era `rubrics["2a"] = reverse_charge_total`, y hacía dos
    # cosas mal a la vez.
    #
    # 1. Asignaba en lugar de acumular, así que descartaba todo lo que el bucle
    #    de arriba ya había sumado a 2a (`rubrics[rubric] += net_amount`, con
    #    rubric = "2a" para las categorías 'reverse charge' / 'verlegd' /
    #    'verleggingsregeling').
    # 2. Y lo que asignaba era un importe de IVA, no de omzet. Todos los
    #    rubrieken 1a-4b de este informe son cubetas de facturación neta —
    #    `base_net_total` — y el IVA vive en 5a y 5b. Cambiar el `=` por un `+=`
    #    habría dejado de descartar, pero sumando IVA sobre neto en la misma
    #    cubeta.
    #
    # 2a lleva la omzet, como cada uno de sus hermanos, y el bucle ya la
    # acumuló. `reverse_charge_total` queda calculado a propósito: dónde debe
    # declararse el IVA trasladado es una pregunta contable abierta y sin
    # responder, y borrar el número la escondería.
    #
    # Latente hoy: ninguna factura de producción lleva una categoría de reverse
    # charge, que es la misma condición que hace disparar VD.13.

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