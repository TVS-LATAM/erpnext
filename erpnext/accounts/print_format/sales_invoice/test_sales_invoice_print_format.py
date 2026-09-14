# Copyright (c) 2026, TVS and contributors
# For license information, please see license.txt

"""
R.1 — the invoice must print the legal declaration and the country of origin.

`resolveInvoiceTerms` composes both statements and `createSalesInvoice.ts` posts
them as the Sales Invoice `terms`, so the data has been written since 839c2140.
It never reached the customer, because the print format that actually renders
does not lay `terms` out at all.

Measured on the dev site, 2026-09-02, by rendering a real submitted invoice with
a unique marker placed in `terms`:

    Sales Invoice        (the default, this format)   marker NOT rendered
    Sales Invoice Print  (upstream's)                 marker rendered

`default_print_format` is set by a Property Setter to `Sales Invoice`, and the
delivery path never overrides it: `libs/erpnext/src/api.ts` declares
`format?: string` on `download` and then never puts it in the query string, so
`frappe.utils.print_format.download_pdf` receives `format=None` and falls back
to that default. No caller passes it either. The parameter is dead.

So the article 138(1) declaration, the article 146 sentence and the country of
origin were written to the database and dropped at the last step. 0 of 695
invoices carry a non-empty `terms` on the dev site, which is why nobody saw it.

This format is TVS's own — a Print Format Builder layout whose custom HTML
blocks live in `sales_invoice.json` in this fork — so the fix is a block added
to a file this repository already maintains, not a new format and not a change
of default.

Placement is part of the requirement. The ticket says *"agregar al final el país
de origen"*, and `resolveInvoiceTerms` already orders the declaration before the
origin inside `terms`. The block therefore sits after the totals and before the
closing line, so the statements read last, as a legal note on an invoice does.

Frappe renders print templates with autoescaping off (measured), so
`{{ doc.terms }}` emits the stored markup as markup. `terms` is a Text Editor
field and `INVOICE_ORIGIN_NOTE` is `<p>`-wrapped for exactly that reason.
"""

import json
import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

FORMAT_JSON = os.path.join(os.path.dirname(__file__), "sales_invoice.json")

TERMS_MARKUP = "<p>ARTICLE 138(1) ZZTERMSZZ</p><p>COUNTRY OF ORIGIN: THE NETHERLANDS</p>"


def _format_blocks():
	with open(FORMAT_JSON, encoding="utf-8") as handle:
		definition = json.load(handle)

	blocks = definition["format_data"]
	if isinstance(blocks, str):
		blocks = json.loads(blocks)

	return blocks


def _terms_blocks():
	return [block for block in _format_blocks() if "doc.terms" in (block.get("options") or "")]


class TestSalesInvoiceTermsBlock(FrappeTestCase):
	"""The `terms` block of the Sales Invoice print format — R.1."""

	# --- the defect: the layout never rendered the field -------------------

	def test_the_format_lays_out_the_terms_field(self):
		"""
		Before R.1 this list was empty, and the declaration written by
		resolveInvoiceTerms reached the database and stopped there.
		"""
		self.assertEqual(len(_terms_blocks()), 1)

	# --- what it renders ---------------------------------------------------

	def test_it_renders_the_stored_markup_as_markup(self):
		"""
		`terms` is a Text Editor field holding `<p>` markup. Frappe renders print
		templates with autoescaping off, so the tags must survive as tags rather
		than appear on the invoice as literal text.
		"""
		doc = frappe._dict({"terms": TERMS_MARKUP})

		rendered = frappe.render_template(_terms_blocks()[0]["options"], {"doc": doc})

		self.assertIn("ARTICLE 138(1) ZZTERMSZZ", rendered)
		self.assertIn("COUNTRY OF ORIGIN: THE NETHERLANDS", rendered)
		self.assertNotIn("&lt;p&gt;", rendered)

	def test_it_prints_nothing_when_there_are_no_terms(self):
		"""
		Historical invoices carry no terms — 695 of 695 on the dev site. They must
		not gain an empty box, a stray heading or a rule.
		"""
		for empty in ("", None):
			with self.subTest(terms=empty):
				rendered = frappe.render_template(
					_terms_blocks()[0]["options"], {"doc": frappe._dict({"terms": empty})}
				)

				self.assertEqual(rendered.strip(), "")

	def test_it_survives_a_doc_with_no_terms_attribute_at_all(self):
		"""A Quotation-shaped doc, or any doc rendered before the field exists."""
		rendered = frappe.render_template(_terms_blocks()[0]["options"], {"doc": frappe._dict({})})

		self.assertEqual(rendered.strip(), "")

	# --- where it sits -----------------------------------------------------

	def test_it_closes_the_document_after_the_totals(self):
		"""
		"Agregar AL FINAL el país de origen." The declaration and the origin are
		a legal note, so they read after the amounts, not between the item table
		and the totals.
		"""
		blocks = _format_blocks()
		terms_at = blocks.index(_terms_blocks()[0])
		totals_at = max(
			index
			for index, block in enumerate(blocks)
			if "Subtotal" in (block.get("options") or "")
		)

		self.assertGreater(terms_at, totals_at)

	def test_it_reads_before_the_closing_line(self):
		"""The thank-you line stays the last thing on the page."""
		blocks = _format_blocks()
		terms_at = blocks.index(_terms_blocks()[0])
		closing_at = max(
			index
			for index, block in enumerate(blocks)
			if "Thank you" in (block.get("options") or "")
		)

		self.assertLess(terms_at, closing_at)


"""
K.9 — the printed invoice may not assert a VAT rate it did not charge.

Found 2026-09-14 on `A00491`: an invoice rated `EU_B2B_INTRA`, 1500,00 net
against 1500,00 gross with 0,00 of tax, submitted and `Paid`, whose printed page
reads `VAT 21%: EUR 0.00` and carries the article 138(1) declaration nowhere.

The rate was a LITERAL in this format — `<td ...>21%</td>` in the item row and
`{{ _("VAT") }} 21%:` as the totals label, beside a live
`{{ doc.base_total_taxes_and_charges }}`. The amount was true and the rate next
to it was a constant, so every invoice not charging 21% mis-stated its own rate
to the customer. That is `V.6`/`V.7` in the print layer, and the shape of the
364-invoice defect on the one surface the customer reads.

WHAT REPLACES IT, AND WHY IT IS NOT A NEW DECISION
--------------------------------------------------
Accounting answered on 2026-09-02, quoted in `resolve-invoice-tax-rows.ts`: a
zero-rated document carries *"a VAT row showing 0% and an amount of EUR 0.00,
plus the legal text naming the article, so that the rate the invoice was given
stays visible on the document"*. `resolveInvoiceTaxRows` writes exactly that row
— `description: 'VAT 0%'`, `rate: 0`, `tax_amount: 0` — chosen from the regime.
So the document already states its rate; this format threw the statement away.
Printing the row's own `description` renders a decision already made and already
stored, and introduces no second implementation of the regime-to-rate mapping
(`V.1`, `V.4`).

WHY THE `rate` FIELD IS NOT THE SOURCE
-------------------------------------
`charge_type: 'Actual'` makes `rate` structurally `0` on EVERY row — on a 21%
sale exactly as on a 0% one (`V.6`). Reading it would print `0%` on a domestic
invoice. The percentage carries no information anywhere in this system, which is
why `V.7` forbids deriving anything from it, and `test_the_stored_rate_is_never
_what_is_printed` pins that a future "fix" may not reach for it.

WHY THE ITEM COLUMN IS GONE RATHER THAN CORRECTED
-------------------------------------------------
One `Actual` row covers the whole document, so there is no per-item rate to
state. A per-line VAT column is a claim the data cannot support, and filling it
with a constant is how the false `21%` reached `A00491` in the first place. The
rate is stated once, in the totals, from the row that holds it.
"""

def _totals_block():
	blocks = [block for block in _format_blocks() if "Subtotal" in (block.get("options") or "")]
	assert len(blocks) == 1
	return blocks[0]


def _item_table_block():
	blocks = [block for block in _format_blocks() if "items_custom" in (block.get("options") or "")]
	assert len(blocks) == 1
	return blocks[0]


def _without_styling(html):
	"""The template minus every place a percentage means a column width."""
	html = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
	return re.sub(r"\sstyle=\"[^\"]*\"", " ", html)


def _visible_text(html):
	"""What a reader sees: no stylesheet, no inline style attribute, no tags."""
	return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _without_styling(html))).strip()


def _render(block, doc):
	return _visible_text(frappe.render_template(block["options"], {"doc": frappe._dict(doc)}))


def _line(description="prueba 4", amount=1500.0):
	return frappe._dict({"qty": 1, "description": description, "rate": amount, "base_amount": amount})


def _zero_rated():
	"""`A00491` as it stands on staging: EU_B2B_INTRA, 1500,00 net, no VAT."""
	return {
		"base_total": 1500.0,
		"grand_total": 1500.0,
		"base_total_taxes_and_charges": 0.0,
		"items_custom": [_line()],
		# What resolveInvoiceTaxRows writes for a zero-rated regime.
		"taxes": [frappe._dict({"description": "VAT 0%", "rate": 0.0, "tax_amount": 0.0})],
	}


def _domestic():
	"""A 21% sale. Note `rate: 0` — charge_type 'Actual', V.6."""
	return {
		"base_total": 1500.0,
		"grand_total": 1815.0,
		"base_total_taxes_and_charges": 315.0,
		"items_custom": [_line()],
		"taxes": [frappe._dict({"description": "VAT 21% - TVS", "rate": 0.0, "tax_amount": 315.0})],
	}


def _mixed():
	"""`A00435`'s shape (VD.28): two rows at different rates on one document."""
	return {
		"base_total": 75.0,
		"grand_total": 80.25,
		"base_total_taxes_and_charges": 5.25,
		"items_custom": [_line("gearbox", 50.0), _line("shipping box", 25.0)],
		"taxes": [
			frappe._dict({"description": "VAT 21% - TVS", "rate": 0.0, "tax_amount": 5.25}),
			frappe._dict({"description": "VAT  0% - TVS", "rate": 0.0, "tax_amount": 0.0}),
		],
	}


class TestSalesInvoiceStatesItsOwnVatRate(FrappeTestCase):
	"""K.9 — the rate on the page comes from the document, or it is not there."""

	# --- the defect --------------------------------------------------------

	def test_a_zero_rated_invoice_never_prints_21(self):
		"""`A00491`: 0,00 of VAT on 1500,00 of net, printed as `VAT 21%`."""
		self.assertNotIn("21%", _render(_totals_block(), _zero_rated()))

	def test_the_item_table_states_no_rate_of_its_own(self):
		"""
		One `Actual` row covers the document (V.6), so there is no per-item rate.
		The column printed the constant `21%` on every line of every invoice.
		"""
		self.assertNotIn("21%", _render(_item_table_block(), _zero_rated()))

	def test_no_block_hard_codes_a_percentage(self):
		"""
		The grep guard. Nothing in this fork plays the part
		`vat-rate-inference-guard.spec.ts` plays in tvs-cloud-services, so a
		literal rate can be put back here by anyone.

		It reads the TEMPLATE, never the rendering. A rendered `VAT 0%` is
		correct — it is the row's own description, chosen by the regime — while
		a percentage in the source is an assertion the document never made.
		Percentages that are column widths live in CSS and are stripped first.
		"""
		offenders = [
			_without_styling(block["options"]).strip()
			for block in _format_blocks()
			if block.get("options") and re.search(r"\d+\s*%", _without_styling(block["options"]))
		]

		self.assertEqual(offenders, [])

	# --- what it prints instead --------------------------------------------

	def test_the_totals_state_the_row_the_document_carries(self):
		"""
		`resolveInvoiceTaxRows` writes `description: 'VAT 0%'` for a zero-rated
		regime — accounting's answer of 2026-09-02, so the given rate stays
		visible. Printing it renders a decision already stored on the document.
		"""
		rendered = _render(_totals_block(), _zero_rated())

		self.assertIn("VAT 0%", rendered)

	def test_a_domestic_invoice_states_its_own_row_and_amount(self):
		rendered = _render(_totals_block(), _domestic())

		self.assertIn("VAT 21% - TVS", rendered)
		self.assertIn("315", rendered)

	def test_every_row_of_a_mixed_rate_invoice_is_stated(self):
		"""
		`A00435` (VD.28) collapsed two rows into one figure labelled `VAT 21%`.
		Stating each row makes a mixed document visible instead of hiding it
		behind a single total.
		"""
		rendered = _render(_totals_block(), _mixed())

		self.assertIn("VAT 21% - TVS", rendered)
		# `A00435` really carries two spaces there; _visible_text collapses runs
		# of whitespace, so the assertion is on the collapsed form.
		self.assertIn("VAT 0% - TVS", rendered)
		self.assertIn("5.25", rendered)

	# --- what must not move ------------------------------------------------

	def test_the_stored_rate_is_never_what_is_printed(self):
		"""
		V.6/V.7. `rate` is `0` on a 21% row because the row is `charge_type:
		'Actual'`, so a rendering that reached for it would print `0%` on a
		domestic invoice. This fails the moment somebody "simplifies" the
		template to `{{ tax.rate }}%`.
		"""
		self.assertNotIn("0%", _render(_totals_block(), _domestic()))

	def test_the_amounts_and_the_total_still_read(self):
		"""The totals block is still the totals block."""
		rendered = _render(_totals_block(), _domestic())

		self.assertIn("Subtotal", rendered)
		self.assertIn("1500", rendered)
		self.assertIn("1815", rendered)

	def test_an_invoice_with_no_tax_rows_gains_no_empty_label(self):
		"""Historical documents, and anything rendered before the rows exist."""
		doc = _zero_rated()
		doc["taxes"] = []

		rendered = _render(_totals_block(), doc)

		self.assertNotIn("VAT", rendered)
		self.assertIn("Subtotal", rendered)

	def test_it_survives_a_doc_with_no_taxes_attribute_at_all(self):
		doc = _zero_rated()
		del doc["taxes"]

		self.assertIn("Subtotal", _render(_totals_block(), doc))
