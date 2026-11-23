# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import base64
import hashlib
import hmac
import json

import frappe
import requests
from frappe import _
from frappe.model.document import Document

CANCEL_ROUTE = "/refund/revolut-payment-link-cancel"
# The webhook that creates these refunds points at the same AWS API and is signed with the
# secret the cancel route checks, so its secret is reused instead of storing a second copy.
CREATE_ROUTE_SUFFIX = "/refund/revolut-payment-link"
SIGNATURE_HEADER = "X-Frappe-Webhook-Signature"
REQUEST_TIMEOUT_SECONDS = 30


class SalesInvoiceRefunds(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Data | None
		counterparty_name: DF.Data | None
		created_at: DF.Data | None
		expiry_date: DF.Data | None
		naming_series: DF.Data | None
		reference: DF.Data | None
		state: DF.Data | None
		trx_id: DF.Data | None
	# end: auto-generated types
	pass


def sign_body(secret: str, body: bytes) -> str:
	"""Same signature Frappe sends on webhooks: base64(HMAC-SHA256(secret, body))."""
	return base64.b64encode(hmac.new(secret.encode("utf8"), body, hashlib.sha256).digest()).decode()


def get_refund_webhook_secret() -> str:
	webhooks = frappe.get_all(
		"Webhook",
		filters={"request_url": ["like", f"%{CREATE_ROUTE_SUFFIX}"], "enable_security": 1},
		pluck="name",
	)
	for name in webhooks:
		secret = frappe.get_doc("Webhook", name).get_password("webhook_secret", raise_exception=False)
		if secret:
			return secret
	frappe.throw(_("No signed webhook for {0} was found, so the request cannot be signed.").format(CREATE_ROUTE_SUFFIX))


@frappe.whitelist(methods=["POST"])
def cancel_revolut_payment_link(name: str):
	"""Cancels the Revolut payout links of a refund. Runs with the caller's session and permissions."""
	doc = frappe.get_doc("Sales Invoice Refunds", name)
	doc.check_permission("write")
	if doc.state == "cancelled":
		frappe.throw(_("This refund is already cancelled."))
	if not doc.reference:
		frappe.throw(_("This refund has no reference invoice."))

	aws_url = (frappe.db.get_single_value("Queue Settings", "aws_url") or "").rstrip("/")
	if not aws_url:
		frappe.throw(_("Queue Settings has no AWS URL."))

	body = json.dumps({"name": doc.name, "reference": doc.reference}).encode("utf8")
	response = requests.post(
		f"{aws_url}{CANCEL_ROUTE}",
		data=body,
		headers={
			"Content-Type": "application/json",
			SIGNATURE_HEADER: sign_body(get_refund_webhook_secret(), body),
		},
		timeout=REQUEST_TIMEOUT_SECONDS,
	)
	if not response.ok:
		frappe.log_error(
			title="Revolut refund cancellation failed",
			message=f"{doc.name} ({doc.reference}): HTTP {response.status_code} {response.text[:500]}",
		)
		frappe.throw(_("The refund could not be cancelled (HTTP {0}).").format(response.status_code))

	return {"cancelled": True}
