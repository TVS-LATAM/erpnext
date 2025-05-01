frappe.ui.form.on("Product Bundle", {
	refresh: function (frm) {
		frm.toggle_enable("new_item_code", frm.is_new());
		frm.set_query("new_item_code", () => {
			return {
				query: "erpnext.selling.doctype.product_bundle.product_bundle.get_new_item_code",
			};
		});

		frm.set_query("item_code", "items", () => {
			return {
				filters: {
					has_variants: 0,
				},
			};
		});
	},product_bundle_template: function(frm) {
		const current_items = frm.doc.items || [];
        let new_items = [];

        if (frm.doc.product_bundle_template) {
			console.log("current items ", current_items)
            const existing_item_names = new Set(current_items.map(item => item.item_code));

            frappe.db.get_doc("Product Bundle Template", frm.doc.product_bundle_template).then((doc) => {
                new_items = doc.product_bundle_template_items
                    .filter(item => !existing_item_names.has(item.item_code))
                    .map((item, index) => {
                        return {
                            creation: new Date().toISOString(),
                            description: item.description || "",
                            description_visible: 0,
                            docstatus: 0,
                            doctype: "Product Bundle Item",
                            idx: current_items.length + index + 1,
                            item_code: item.item_code,
                            modified: new Date().toISOString(),
                            modified_by: frappe.session.user,
                            name: item.name,
                            owner: frappe.session.user,
                            parent: frm.doc.name,
                            parentfield: "items",
                            parenttype: "Product Bundle",
                            qty: item.qty,
                            rate: 0,
                            tvs_pn: ''
                        };
                    });

					frm.set_value('items', [...current_items, ...new_items]);
                    frm.refresh_field('items');
					frm.save()
            });
        }
    },
});
