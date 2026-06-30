// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Manuren Import", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frm.add_custom_button(__("Parse & Import"), () => {
			if (!frm.doc.attachment) {
				frappe.msgprint(__("Attach a Manuren .xlsx file first."));
				return;
			}
			frappe.dom.freeze(__("Importing Manuren sheet..."));
			frm
				.call("run_import")
				.then((r) => {
					frappe.dom.unfreeze();
					if (r && r.message) {
						frappe.show_alert({
							message: __("Imported: {0} new, {1} updated", [
								r.message.created,
								r.message.updated,
							]),
							indicator: "green",
						});
					}
					frm.reload_doc();
				})
				.catch(() => frappe.dom.unfreeze());
		});
	},
});
