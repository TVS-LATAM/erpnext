// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Invoice Refunds", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.state === "cancelled") return;

		// The cancellation runs on the server, which checks the user's permission and signs the
		// request to AWS. The browser never calls AWS directly.
		frm.add_custom_button(
			__("Cancel Refunds"),
			function () {
				frappe.confirm(__("Are you sure you want to cancel this refund?"), function () {
					frappe
						.call({
							method: "erpnext.selling.doctype.sales_invoice_refunds.sales_invoice_refunds.cancel_revolut_payment_link",
							args: { name: frm.doc.name },
							freeze: true,
							freeze_message: __("Processing refund cancellation..."),
						})
						.then(() => {
							frappe.show_alert({
								message: __("Refund cancelled successfully"),
								indicator: "green",
							});
							frm.reload_doc();
						});
				});
			},
			__("Actions")
		);
	},
});
