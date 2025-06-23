// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Invoice Refunds", {
	refresh(frm) {
		// Add "Cancel Refunds" button
		frm.add_custom_button(__('Cancel Refunds'), function() {
			// Show a confirmation dialog before proceeding
			frappe.confirm(
				__('Are you sure you want to cancel this refund?'),
				async function() {
					// User confirmed, proceed with the API call
					frappe.show_alert({
						message: __('Processing refund cancellation...'),
						indicator: 'orange'
					});
          const { aws_url } = await frappe.db.get_doc('Queue Settings')
          await fetch(`${aws_url}/refund/revolut-payment-link-cancel`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              name: frm.doc.name,
              reference: frm.doc.reference,
              id: frm.doc.trx_id
            })
          }).then(res => res.json()).then(data => {
            frappe.show_alert({
              message: __('Refund cancelled successfully'),
              indicator: 'green'
            });
            frm.reload_doc();
          })
				},
				function() {
					// User cancelled, do nothing
				}
			);
		}, __('Actions'));
	},
});
