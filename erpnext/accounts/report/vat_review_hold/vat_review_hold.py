# vat_review_hold.py — Facturas retenidas para revisión de IVA (F.3, auditoría A.4)

import frappe
from frappe import _

# El régimen que la tubería de facturación escribe cuando se NEGÓ a tasar el
# documento. `resolveTaxTreatment` lo devuelve siempre que le falta un hecho —
# el país del cliente, el canal de venta, la respuesta de VIES — y siempre dice
# cuál faltaba. Cobra 21%, la tarifa segura a la que degrada.
REVIEW_HOLD_REGIME = "REVIEW_HOLD"

# El Custom Field que instala `tvs_accountancy`. Mismo nombre que lee la
# declaración de IVA, y por el mismo motivo: es el único campo legible por
# máquina que separa un artículo 138 de un artículo 146, y aquí, el único que
# distingue un documento tasado de uno que nadie pudo tasar.
TAX_REGIME_FIELD = "tvs_tax_regime"


# F.3. F.1 manda estas facturas al rubriek 1a, que acierta con el dinero — se
# cobró el 21% y TVS lo debe — y no dice nada de la duda. F.2 avisa por Slack el
# día que ocurre, y los avisos se van hacia arriba en el canal.
#
# Esta es la lista que un contador abre antes de presentar el periodo: toda
# factura presentada del periodo que el sistema no pudo tasar, con el cliente,
# el país, el neto, el IVA y la fecha. Sin ella, el único registro de que un
# humano tenía que mirar estos documentos vive en un chat.
#
# El importe de IVA se calcula con el mismo filtro de cuentas que usa `5a` en la
# declaración — `account_type = 'Tax'` y `'vat'` en el nombre de la cuenta — a
# propósito: esta lista y la declaración tienen que coincidir por construcción,
# porque de eso trata leerla antes de presentar. Si el filtro se cambia allí,
# se cambia aquí.
def held_invoice_query():
    """
    El SELECT de las facturas retenidas.

    Devuelto como texto y no ejecutado aquí para que la regla — sólo el régimen
    retenido, sólo documentos presentados, sólo el periodo — se pueda probar sin
    base de datos.
    """
    return """
        SELECT
            si.name AS invoice,
            si.posting_date,
            si.customer,
            si.customer_name,
            addr.country,
            si.base_net_total AS net_total,
            (
                SELECT COALESCE(SUM(stc.base_tax_amount), 0)
                FROM `tabSales Taxes and Charges` stc
                LEFT JOIN `tabAccount` acc ON acc.name = stc.account_head
                WHERE stc.parent = si.name
                    AND stc.parenttype = 'Sales Invoice'
                    AND acc.account_type = 'Tax'
                    AND LOWER(acc.account_name) LIKE '%%vat%%'
            ) AS vat_amount
        FROM `tabSales Invoice` si
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE si.docstatus = 1
            AND si.{field} = '{regime}'
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND (%(company)s = '' OR si.company = %(company)s)
        ORDER BY si.posting_date, si.name
    """.replace("{field}", TAX_REGIME_FIELD).replace("{regime}", REVIEW_HOLD_REGIME)


def get_columns():
    return [
        {
            "fieldname": "invoice",
            "label": _("Sales Invoice"),
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 140,
        },
        {"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 100},
        {
            "fieldname": "customer",
            "label": _("Customer"),
            "fieldtype": "Link",
            "options": "Customer",
            "width": 140,
        },
        {"fieldname": "customer_name", "label": _("Customer Name"), "fieldtype": "Data", "width": 200},
        {"fieldname": "country", "label": _("Country"), "fieldtype": "Data", "width": 120},
        {"fieldname": "net_total", "label": _("Net Amount (EUR)"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "vat_amount", "label": _("VAT Charged (EUR)"), "fieldtype": "Currency", "width": 130},
    ]


def execute(filters=None):
    filters = filters or {}

    columns = get_columns()

    # `tvs_tax_regime` lo instala `tvs_accountancy`. Un entorno que no lo migró
    # no tiene la columna, y nombrarla en SQL allí convertiría un informe que
    # funciona en un error de base de datos. La declaración de IVA ya se protege
    # así en `tax_regime_select`; este informe no puede ser el que lo olvide.
    #
    # Ahí no hay facturas retenidas que listar, porque nada escribió el campo:
    # una lista vacía es la respuesta correcta y no una avería.
    if not frappe.db.has_column("Sales Invoice", TAX_REGIME_FIELD):
        frappe.msgprint(
            _(
                "The field {0} is not installed on this site, so no invoice can be held for VAT review. "
                "Install or migrate tvs_accountancy if this site issues invoices."
            ).format(TAX_REGIME_FIELD),
            title=_("VAT Review Hold"),
            indicator="orange",
        )
        return columns, []

    data = frappe.db.sql(
        held_invoice_query(),
        {
            "from_date": filters.get("from_date"),
            "to_date": filters.get("to_date"),
            # Cadena vacía y no None: la condición es
            # `%(company)s = '' OR si.company = %(company)s`, y con None no
            # coincide ninguna factura — un periodo limpio que no lo está.
            "company": filters.get("company") or "",
        },
        as_dict=True,
    )

    if data:
        frappe.msgprint(
            _(
                "{0} submitted invoice(s) in this period were held for VAT review and charged 21%. "
                "They are declared in rubriek 1a. Check each one before the period is filed."
            ).format(len(data)),
            title=_("VAT Review Hold"),
            indicator="orange",
        )

    return columns, data
