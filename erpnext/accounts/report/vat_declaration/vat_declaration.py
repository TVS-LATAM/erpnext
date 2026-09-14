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
    # D4. Aquí vivían "diensten buiten eu": "4a" y "diensten eu": "4b". Este
    # mapa lo lee una sola función, `classify_sales_rubric`, que sólo ve
    # facturas de VENTA, y 4a/4b son rubrieken de ADQUISICIONES — el propio
    # informe los rotula "Diensten uit landen buiten de EU" y "Diensten uit
    # EU-landen": servicios recibidos DE fuera. Una venta no puede declararse
    # ahí. El lado compras nunca leyó este mapa: compara las mismas dos
    # cadenas literales inline (ver el bucle de clasificación de compras), así
    # que estas claves no servían a nadie y sacaban de 3b/3a toda venta que
    # llevara la categoría, mientras su IVA seguía acumulando en 5a — la
    # contradicción de VD.14 por otro camino.
    #
    # Se borran en vez de reapuntarlas a 3b/3a porque el propio clasificador ya
    # decide bien cuando nada mapea: cliente UE cae a 3b, no-UE a 3a, y
    # nacional a 1c registrando la categoría en `unknown_categories`, que es lo
    # que dispara el aviso al usuario. Reapuntarlas fijaría una opinión fiscal
    # sobre una categoría que ninguna factura de venta neerlandesa debería
    # llevar, y además silenciaría ese aviso.
    #
    # P2.4. Estas tres claves apuntaban a "2a", verificado contra
    # belastingdienst.nl el 2026-09-14: rubriek 2a "Verleggingsregelingen
    # binnenland" es del COMPRADOR ("Bent u de afnemer? Dan moet u de btw die
    # naar u is verlegd, zelf uitrekenen... U vult dit bedrag in bij rubriek
    # 2a"). Esta función sólo ve Sales Invoices, es decir, siempre el lado
    # VENDEDOR de la operación. El vendedor que aplica una verlegging
    # nacional declara la facturación en 1e ("Leveringen/diensten belast met
    # 0% of niet bij u belast").
    #
    # Se reapuntan a 1e en vez de borrarse — a diferencia de las claves D4 de
    # arriba — porque borrarlas las haría caer en el fallback nacional 1c, que
    # es un rubriek GRAVADO: eso sería peor que el error que se corrige, no
    # mejor. 1e sí es un rubriek de tipo 0%/exento, coherente con una entrega
    # donde el vendedor no cobra IVA.
    "reverse charge": "1e",
    "verlegd": "1e",
    "verleggingsregeling": "1e",
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


def classify_sales_rubric(regime, category, incoterm, customer_type, reverse_charge=False):
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

    P2.2. `reverse_charge` es la señal por factura que `classify_period_sales`
    ya calcula a partir del account_head/description de la línea de impuesto
    (una que suena a "verlegd" o "reverse"). Es mejor evidencia que la ausencia
    de categoría, y peor evidencia que una categoría explícita, así que decide
    sólo cuando `category` no mapeó a nada en TAX_CATEGORY_MAPPING — un mapeo
    explícito sigue ganando.

    P2.4. La heurística manda a 1e, no a 2a. Verificado contra
    belastingdienst.nl el 2026-09-14: rubriek 2a "Verleggingsregelingen
    binnenland" es del COMPRADOR, y esta función sólo clasifica facturas de
    VENTA — siempre el lado vendedor. El vendedor que aplica una verlegging
    nacional declara la facturación en 1e. La heurística exige además
    `customer_type == "domestic"`: un cliente UE o de exportación con una
    línea de aspecto verlegd no es una verlegging binnenland en absoluto, y la
    reescritura de coherencia de más abajo (`rubric in ["1a", "1b", "1e"]`) ya
    lo manda a 3b o 3a cuando el mapeo explícito lo deja en 1e.
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

    # P2.2 / P2.4. Una línea de impuesto verlegd sólo decide cuando la
    # categoría no mapeó a nada, y sólo para el cliente nacional. Manda a 1e,
    # no a 2a: 2a es el rubriek del COMPRADOR de una verlegging binnenland, y
    # esta función sólo ve facturas de VENTA — el vendedor de esa misma
    # operación declara en 1e.
    elif not rubric and reverse_charge and customer_type == "domestic":
        rubric = "1e"

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


# F.12. La clasificación por factura vivía dentro de `fetch_vat_data`, que sólo
# devuelve los rubrieken ya sumados. La reconciliación contra la ICP necesita
# saber QUÉ factura entró en 3b, no cuánto suma 3b, y la única forma honesta de
# saberlo es leer la misma clasificación que declara — no una segunda copia.
#
# Una copia que se desviara en una sola rama reportaría las dos declaraciones
# como coincidentes en un periodo en el que no coinciden, que es exactamente el
# fallo silencioso que F.12 existe para hacer visible.
def classify_period_sales(filters):
    """
    Cada factura de venta presentada del periodo, con el rubriek que la declara.

    Devuelve `(facturas, categorias_desconocidas, total_reverse_charge)`. Las
    facturas salen en el orden del `ORDER BY si.name` de la consulta, así que
    dos ejecuciones sobre los mismos datos devuelven la misma lista.

    `tax_id` y `posting_date` se seleccionan para la reconciliación y no
    intervienen en la clasificación: el rubriek lo decide `classify_sales_rubric`
    con exactamente los mismos cuatro argumentos que antes.
    """
    from_date = filters.get("from_date", "1900-01-01")
    to_date = filters.get("to_date", "2100-12-31")
    company = filters.get("company", "")

    # === ANÁLISIS DE FACTURAS DE VENTA MEJORADO ===
    sales_query = """
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            si.posting_date,
            si.tax_id,
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

    # Procesar datos de ventas
    processed_sales = {}
    unknown_categories = set()
    reverse_charge_total = 0.0

    for row in sales_rows:
        invoice_name = row.name
        if invoice_name not in processed_sales:
            processed_sales[invoice_name] = {
                "invoice": invoice_name,
                "customer": row.customer or "",
                "customer_name": row.customer_name or "",
                "period": row.posting_date.strftime("%Y-%m") if row.posting_date else "",
                "tax_id": row.tax_id or "",
                "net_total": row.base_net_total or 0,
                "category": row.category or "",
                "regime": row.tax_regime or "",
                "incoterm": row.incoterm or "",
                "customer_type": classify_customer_type(row.customer_country),
                "vat_amount": 0,
                "reverse_charge": 0,
                # P2.2. La PRESENCIA de una línea verlegd, aparte del importe
                # que esa línea acumule en `reverse_charge`. Bajo la
                # verleggingsregeling el IVA se traslada al comprador, así que
                # el vendedor no cobra nada y la línea vale 0: derivar la señal
                # del importe sumado haría invisible justo la factura que el
                # heurístico existe para encontrar.
                "has_reverse_charge_line": False
            }

        # Acumular IVA solo de cuentas de impuestos válidas
        if row.account_type == "Tax" and "vat" in (row.account_name or "").lower():
            processed_sales[invoice_name]["vat_amount"] += flt(row.base_tax_amount or 0)

        # Detectar reverse charge
        if (row.account_head and ("verlegd" in row.account_head.lower() or "reverse" in row.account_head.lower()) or
            row.description and "verlegd" in row.description.lower()):
            processed_sales[invoice_name]["reverse_charge"] += flt(row.base_tax_amount or 0)
            processed_sales[invoice_name]["has_reverse_charge_line"] = True
            reverse_charge_total += flt(row.base_tax_amount or 0)

    # Clasificar ventas en rubrieken
    for data in processed_sales.values():
        # VD.20 / P2.2. La decisión vive en `classify_sales_rubric`, que el
        # régimen gobierna cuando está, que conserva el camino heredado cuando
        # no, y a la que aquí se le pasa la señal de verlegd ya calculada
        # arriba para que la heurística pueda decidir 2a.
        rubric, unmapped_category = classify_sales_rubric(
            regime=data["regime"],
            category=data["category"],
            incoterm=data["incoterm"],
            customer_type=data["customer_type"],
            reverse_charge=data["has_reverse_charge_line"],
        )

        data["rubric"] = rubric

        if unmapped_category is not None:
            unknown_categories.add(unmapped_category)

    return list(processed_sales.values()), unknown_categories, reverse_charge_total


# P2.3 (opción A). Los rubrieken 4a, 4b y 5b son la mitad de COMPRAS de la
# declaración, y en este stack nada registra compras. Verificado read-only el
# 2026-09-14 sobre el único sitio alcanzable:
#
#   * `frappe.db.count("Purchase Invoice")` = 0, en cualquier docstatus. Las 37
#     filas de `Purchase Taxes and Charges` son todas de Templates.
#   * No hay un solo Custom Field en Purchase Invoice, y `tvs_tax_regime` existe
#     únicamente en Sales Invoice.
#   * Los `doc_events` de `tvs_accountancy` cubren Quotation, Customer y Sales
#     Invoice. No hay clave "Purchase Invoice" en ninguna parte de esa app.
#   * Ningún writer de Purchase Invoice en este bench ni en tvs-cloud-services.
#   * `Te vorderen Btw-verlegd` y `Af te dragen Btw-verlegd` existen en el plan
#     de cuentas con cero asientos en GL.
#   * La integración Moneybird es sólo de ventas: empuja Customer y Sales
#     Invoice, y su webhook entrante crea Items con `is_purchase_item: 0`.
#
# Un cero en una declaración fiscal es una MEDICIÓN. "5b Voorbelasting 0,00"
# afirma que no se soportó IVA deducible, y `Totaal` es `5a - 5b`: presentar ese
# cero sobredeclara el IVA a pagar por el total del deducible. Ausente no es
# cero — la misma distinción que VD.14 trazó para un país desconocido.
#
# 5c y Totaal son ambos `5a - 5b`, así que heredan la falta de fuente de 5b. 5a
# se deja intacto: es el lado ventas, y sí está medido.
#
# El disparador se MIDE, nunca se fija a mano: un período cuya consulta de
# compras devuelve filas se comporta exactamente como antes, byte por byte. Eso
# deja intacto cualquier entorno que sí registre compras y hace que el informe
# se cure solo el día que las haya, sin ninguna constante que tocar.
#
# Fuera de alcance acá, con seguimiento aparte como B8: aun con filas de compra,
# el acumulador de 5b compara el nombre de la cuenta contra "vat" más
# "input"/"soportado", y el plan de cuentas neerlandés usa "Btw te vorderen ...",
# así que ninguna de las 49 cuentas de tipo Tax del sitio puede coincidir nunca.
UNSOURCED_WITHOUT_PURCHASES = ("4a", "4b", "5b", "5c", "Totaal")


# P2.4. Rubriek 2a es del COMPRADOR ("Verleggingsregelingen binnenland",
# verificado contra belastingdienst.nl el 2026-09-14), y este informe no
# tiene, ni tuvo nunca, ningún camino de COMPRAS que lo calcule: el lado
# vendedor de una verlegging nacional ahora se declara en 1e (ver
# TAX_CATEGORY_MAPPING y classify_sales_rubric), así que ningún código escribe
# `rubrics["2a"]`, con o sin facturas de compra en el período.
#
# Por eso 2a NO entra en `UNSOURCED_WITHOUT_PURCHASES`: esa lista describe
# rubrieken que se curan solos el día que el sitio registre compras, y 2a no
# se cura nunca — necesitaría un camino de compras que hoy no existe y que
# construirlo está fuera del alcance de este cambio. Imprimir 0,00 para un
# rubriek que nadie calcula es la misma mentira que B8 y P2.3 existen para
# eliminar, así que se declara en blanco siempre, en su propio conjunto.
UNSOURCED_ALWAYS = ("2a",)


# B8. El acumulador de 5b exigía que el nombre de la cuenta contuviera "vat" Y
# además "input" o "soportado". El plan de cuentas de la empresa neerlandesa está
# escrito en neerlandés, y ninguna de las 49 cuentas de tipo Tax del sitio puede
# cumplir eso:
#
#     Btw te vorderen hoog / laag / overig      IVA soportado
#     Btw af te dragen hoog / laag / overig     IVA repercutido
#     Te vorderen Btw-verlegd                   lado deducible de una verlegging
#     Af te dragen Btw-verlegd                  lado repercutido de una verlegging
#     Btw-afdracht, Btw oude jaren
#     VAT 21%, VAT 6%, VAT 0% - TVS             las plantillas NL de compra
#
# "Btw te vorderen hoog" no contiene ni "vat" ni "input". Y "VAT 21%" tampoco
# contiene "input", siendo la cuenta a la que apunta la única plantilla NL de
# impuestos de compra que existe. Así que 5b quedaba clavado en 0,00 y `Totaal`,
# que es `5a - 5b`, sobredeclaraba el IVA a pagar por todo el deducible.
#
# Listar nombres era la forma equivocada de regla. El tipo de documento ya dice
# de qué lado del libro está una línea de impuesto: en una factura de COMPRA una
# cuenta de IVA es voorbelasting salvo que su propio nombre diga que es el lado
# de la afdracht o una cuenta verlegd. Eso se lee igual en neerlandés, inglés o
# español, y deja de depender de cómo nombró sus cuentas un despliegue.
VAT_ACCOUNT_MARKERS = ("vat", "btw", "iva", "omzetbelasting", "voorbelasting")

# El lado repercutido. En una compra no es deducible.
REMITTANCE_ACCOUNT_MARKERS = ("af te dragen", "afdracht", "output", "repercutido")

# La verlegging se reconoce, pero no se declara: ver classify_purchase_tax_account.
REVERSE_CHARGE_ACCOUNT_MARKER = "verlegd"


def classify_purchase_tax_account(account_type, account_name):
    """
    Qué es una línea de impuesto de una factura de compra.

    Devuelve `"input"` (voorbelasting, va a 5b), `"reverse_charge"` (una cuenta
    verlegd) o `None` (ni siquiera es IVA).

    La verlegging se reconoce y deliberadamente NO se suma a 5b. Su contrapartida
    pertenece a 5a, y declarar un lado de una autorepercusión sin el otro deja el
    neto MAL, no meramente incompleto — que es peor. Mientras la mitad de compras
    siga fuera de alcance (P2.3, opción A), el informe avisa en vez de declarar.

    BORDE CONOCIDO, sin decidir: `Btw oude jaren` clasifica como "input" y por lo
    tanto entraría en 5b. Es una cuenta de corrección de ejercicios anteriores, y
    una corrección de otro período pertenece a 5e ("Correctie vorige aangifte"),
    que hoy este informe emite fijo en 0,00. No se le hace una regla propia porque
    sería atarse al nombre que le puso un despliegue, y porque no hay dónde
    mandarla que sea correcto. Hoy es latente: ninguna factura de compra existe.
    """
    if account_type != "Tax":
        return None

    name = (account_name or "").lower()
    if not any(marker in name for marker in VAT_ACCOUNT_MARKERS):
        return None

    if REVERSE_CHARGE_ACCOUNT_MARKER in name:
        return "reverse_charge"

    if any(marker in name for marker in REMITTANCE_ACCOUNT_MARKERS):
        return None

    return "input"


def mark_unsourced_purchase_rubrics(rows, purchases_sourced):
    """
    Deja en blanco los rubrieken que ninguna compra alimentó.

    `rows` son las filas ya armadas del informe; `purchases_sourced` dice si la
    consulta de compras del período devolvió al menos una fila. El nombre
    sigue siendo apto tras P2.4: 2a también es, por definición, un rubriek del
    lado compras (del comprador), aunque la razón por la que no tiene fuente
    sea distinta de la de sus hermanos.

    Dos conjuntos, dos razones:

    - `UNSOURCED_WITHOUT_PURCHASES` (4a, 4b, 5b, 5c, Totaal): sin fuente sólo
      cuando `purchases_sourced` es falso. Un período que sí registra compras
      las cura solas.
    - `UNSOURCED_ALWAYS` (2a): sin fuente siempre, tenga o no el período
      facturas de compra, porque este informe no tiene ningún camino de
      compras que lo calcule.

    En ambos casos la fila pierde `amount` y `vat_amount` y queda marcada con
    `unsourced`, para que el dato siga siendo legible por una máquina y no
    sólo por el humano que ve el guión en el PDF.
    """
    for row in rows:
        rubric = row.get("rubric")

        if rubric in UNSOURCED_ALWAYS:
            blank = True
        elif not purchases_sourced and rubric in UNSOURCED_WITHOUT_PURCHASES:
            blank = True
        else:
            blank = False

        if not blank:
            continue

        row["amount"] = None
        if "vat_amount" in row:
            row["vat_amount"] = None
        row["unsourced"] = True

    return rows


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

    # P1.6. IVA realmente cobrado por rubriek, en paralelo a `rubrics`. Antes
    # sólo se sumaba a rubrics["5a"] y se perdía por rubriek en el camino, así
    # que el frontend no tenía de dónde leerlo y lo inventaba con una tarifa
    # fija (ver vat_declaration.js).
    rubrics_vat = {
        "1a": 0.0, "1b": 0.0, "1c": 0.0, "1d": 0.0, "1e": 0.0,
        "2a": 0.0, "3a": 0.0, "3b": 0.0, "3c": 0.0,
        "4a": 0.0, "4b": 0.0
    }

    sales_invoices, unknown_categories, reverse_charge_total = classify_period_sales(filters)

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

    # P2.3 (opción A). Medido, no fijado a mano. Ver mark_unsourced_purchase_rubrics.
    purchases_sourced = bool(purchase_rows)

    # Acumular en los rubrieken. La clasificación ya la hizo
    # `classify_period_sales`, que es lo que la reconciliación de F.12 lee.
    for data in sales_invoices:
        net_amount = data["net_total"]
        vat_amount = data["vat_amount"]
        rubric = data["rubric"]

        # Registrar en el rubrick correspondiente
        if rubric in rubrics:
            rubrics[rubric] += net_amount

        # P1.6. Retener el IVA cobrado en su propio rubriek, no sólo en 5a.
        if rubric in rubrics_vat:
            rubrics_vat[rubric] += vat_amount

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
    # P2.4 (actualiza esta nota, ya no vigente en su forma original). El
    # supuesto de arriba era que 2a lleva la omzet "como cada uno de sus
    # hermanos". Verificado contra belastingdienst.nl el 2026-09-14: 2a
    # "Verleggingsregelingen binnenland" es del COMPRADOR, no del vendedor, y
    # este informe sólo clasifica facturas de VENTA. Por eso el bucle de
    # arriba ya no escribe nunca en `rubrics["2a"]` — la categoría verlegd
    # ahora mapea a 1e (ver TAX_CATEGORY_MAPPING) — y `rubrics["2a"]` se
    # declara sin fuente de datos siempre (ver UNSOURCED_ALWAYS), exactamente
    # igual que 4a/4b/5b lo hacen cuando no hay compras.
    #
    # `reverse_charge_total` sigue calculándose en `classify_period_sales` y
    # sigue sin usarse en esta función: verificado con grep en todo el árbol
    # de erpnext, nada lo lee salvo este mismo desempaquetado. Sigue sin
    # borrarse por la misma razón que antes — dónde debe declararse el IVA
    # trasladado al comprador es una pregunta contable abierta que este
    # cambio no responde, y borrar el número la escondería en vez de dejarla
    # pendiente y visible en el código.
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
                "input_vat": 0,
                "reverse_charge_vat": 0
            }
        
        # B8. Acumular IVA soportado. La regla vive en
        # classify_purchase_tax_account, que se puede probar sin base de datos.
        kind = classify_purchase_tax_account(row.account_type, row.account_name)
        if kind == "input":
            processed_purchases[invoice_name]["input_vat"] += flt(row.base_tax_amount or 0)
        elif kind == "reverse_charge":
            processed_purchases[invoice_name]["reverse_charge_vat"] += flt(row.base_tax_amount or 0)

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

    # P1.5. Redondear una sola vez, en el límite del informe, después de
    # acumular todas las facturas — nunca por factura, que compondría el
    # error a lo largo de cientos de filas. `flt`, no el `round` nativo de
    # Python, para no arrastrar su artefacto de coma flotante binaria
    # (round(2.675, 2) da 2.67).
    rubrics = {k: flt(v, 2) for k, v in rubrics.items()}
    rubrics_vat = {k: flt(v, 2) for k, v in rubrics_vat.items()}

    # Calcular totales
    net_total = flt(rubrics["5a"] - rubrics["5b"], 2)

    # Mostrar advertencias
    if unknown_categories:
        frappe.msgprint(
            _("Categorías fiscales desconocidas detectadas (sumadas a 1c):") + 
            "<br>" + "<br>".join(sorted(unknown_categories)),
            title=_("Advertencia de Mapeo de Categorías"),
            indicator="orange"
        )

    # B8. Una verlegging reconocida y no declarada tiene que verse. Su
    # contrapartida en 5a está fuera de alcance (P2.3, opción A), y declarar sólo
    # el lado deducible dejaría el neto mal.
    undeclared_reverse_charge = sorted(
        invoice_name
        for invoice_name, data in processed_purchases.items()
        if data["reverse_charge_vat"]
    )
    if undeclared_reverse_charge:
        frappe.msgprint(
            _("Estas facturas de compra llevan una línea de IVA verlegd que este "
              "informe NO declara, ni en 5a ni en 5b, porque la mitad de compras "
              "está fuera de alcance:") +
            "<br>" + "<br>".join(undeclared_reverse_charge),
            title=_("Verlegging reconocida y no declarada"),
            indicator="orange"
        )

    # P2.4. Rubriek 2a no tiene fuente de datos NUNCA: a diferencia de
    # 4a/4b/5b, que se curan solos el día que el período registre compras,
    # este informe no tiene ningún cálculo del lado compras que alimente 2a
    # (ver UNSOURCED_ALWAYS). El aviso original de P2.3 sólo se disparaba
    # cuando el período no tenía facturas de compra; ahora también nombra 2a
    # ahí, y dispara un aviso propio cuando SÍ hay compras, porque 2a sigue
    # sin fuente igual.
    if not purchases_sourced:
        frappe.msgprint(
            _("Este período no tiene ninguna factura de compra, así que los rubrieken "
              "4a, 4b, 5b y 2a no tienen fuente de datos. Se informan en blanco, no en "
              "cero: un cero afirmaría que no se soportó IVA deducible o que no hubo "
              "verlegging. 5c y Totaal son 5a - 5b, así que tampoco pueden calcularse. "
              "2a en particular no tiene fuente en ningún período: este informe no "
              "tiene ningún cálculo del lado compras que lo alimente."),
            title=_("Mitad de compras sin fuente de datos"),
            indicator="orange"
        )
    else:
        frappe.msgprint(
            _("El rubriek 2a no tiene fuente de datos en este informe: no existe "
              "ningún cálculo del lado compras que lo alimente. Se informa en "
              "blanco, no en cero."),
            title=_("Rubriek sin fuente de datos"),
            indicator="orange"
        )

    # Retornar datos estructurados
    return mark_unsourced_purchase_rubrics([
        {"rubric": "1a", "description": _("1a. Leveringen binnenland hoog tarief (21%)"), "amount": rubrics["1a"], "vat_amount": rubrics_vat["1a"]},
        {"rubric": "1b", "description": _("1b. Leveringen binnenland laag tarief (9%/6%)"), "amount": rubrics["1b"], "vat_amount": rubrics_vat["1b"]},
        {"rubric": "1c", "description": _("1c. Overige tarieven"), "amount": rubrics["1c"], "vat_amount": rubrics_vat["1c"]},
        {"rubric": "1d", "description": _("1d. Privégebruik"), "amount": rubrics["1d"], "vat_amount": rubrics_vat["1d"]},
        {"rubric": "1e", "description": _("1e. Leveringen tegen 0% of vrijgesteld"), "amount": rubrics["1e"], "vat_amount": rubrics_vat["1e"]},
        # P2.4. Etiqueta con la redacción del COMPRADOR: es su rubriek, no el
        # del vendedor. Verificado contra belastingdienst.nl el 2026-09-14.
        {"rubric": "2a", "description": _("2a. Leveringen/diensten waarbij de omzetbelasting naar u is verlegd"), "amount": rubrics["2a"], "vat_amount": rubrics_vat["2a"]},
        {"rubric": "3a", "description": _("3a. Export buiten de EU"), "amount": rubrics["3a"], "vat_amount": rubrics_vat["3a"]},
        {"rubric": "3b", "description": _("3b. Leveringen binnen de EU"), "amount": rubrics["3b"], "vat_amount": rubrics_vat["3b"]},
        {"rubric": "3c", "description": _("3c. Afstandsverkopen binnen de EU"), "amount": rubrics["3c"], "vat_amount": rubrics_vat["3c"]},
        {"rubric": "4a", "description": _("4a. Diensten uit landen buiten de EU"), "amount": rubrics["4a"], "vat_amount": rubrics_vat["4a"]},
        {"rubric": "4b", "description": _("4b. Diensten uit EU-landen"), "amount": rubrics["4b"], "vat_amount": rubrics_vat["4b"]},
        {"rubric": "", "description": "", "amount": ""},  # Separador
        {"rubric": "5a", "description": _("5a. Verschuldigde omzetbelasting"), "amount": rubrics["5a"]},
        {"rubric": "5b", "description": _("5b. Voorbelasting"), "amount": rubrics["5b"]},
        {"rubric": "5c", "description": _("5c. Subtotaal (5a - 5b)"), "amount": net_total},
        {"rubric": "5d", "description": _("5d. KOR vermindering"), "amount": 0.0},
        {"rubric": "5e", "description": _("5e. Correctie vorige aangifte"), "amount": 0.0},
        {"rubric": "5f", "description": _("5f. Schatting deze aangifte"), "amount": 0.0},
        {"rubric": "Totaal", "description": _("Totaal te betalen of terug te vorderen"), "amount": net_total}
    ], purchases_sourced)


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