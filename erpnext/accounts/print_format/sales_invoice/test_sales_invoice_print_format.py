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
