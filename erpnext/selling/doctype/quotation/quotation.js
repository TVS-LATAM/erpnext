// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

cur_frm.cscript.tax_table = "Sales Taxes and Charges";

erpnext.accounts.taxes.setup_tax_validations("Sales Taxes and Charges Template");
erpnext.accounts.taxes.setup_tax_filters("Sales Taxes and Charges");
erpnext.pre_sales.set_as_lost("Quotation");
erpnext.sales_common.setup_selling_controller();

frappe.ui.form.on("Quotation", {
	setup: function (frm) {
		(frm.custom_make_buttons = {
			"Sales Order": "Sales Order",
		}),
			frm.set_query("quotation_to", function () {
				return {
					filters: {
						name: ["in", ["Customer", "Lead", "Prospect"]],
					},
				};
			});

		frm.set_df_property("packed_items", "cannot_add_rows", true);
		frm.set_df_property("packed_items", "cannot_delete_rows", true);

		frm.set_query("serial_and_batch_bundle", "packed_items", (doc, cdt, cdn) => {
			let row = locals[cdt][cdn];
			return {
				filters: {
					item_code: row.item_code,
					voucher_type: doc.doctype,
					voucher_no: ["in", [doc.name, ""]],
					is_cancelled: 0,
				},
			};
		});
		if (!frm.doc.selling_price_list) {
			frm.set_value('selling_price_list', "Retail");
		}
	},

	refresh: function (frm) {
		frm.trigger("set_label");
		frm.trigger("set_dynamic_field_label");
		if (!frm.doc.selling_price_list) {
			frm.set_value('selling_price_list', "Retail");
		}

		let sbb_field = frm.get_docfield("packed_items", "serial_and_batch_bundle");
		if (sbb_field) {
			sbb_field.get_route_options_for_new_doc = (row) => {
				return {
					item_code: row.doc.item_code,
					warehouse: row.doc.warehouse,
					voucher_type: frm.doc.doctype,
				};
			};
		}

		insertResendQuotationApprovalButton(frm);
		frm.trigger("set_custom_buttons");
	},

	quotation_to: function (frm) {
		frm.trigger("set_label");
		frm.trigger("toggle_reqd_lead_customer");
		frm.trigger("set_dynamic_field_label");
		// frm.set_value("party_name", ""); // removed to set party_name from url for crm integration
		frm.set_value("customer_name", "");
	},

	set_label: function (frm) {
		frm.fields_dict.customer_address.set_label(__(frm.doc.quotation_to + " Address"));
	},

	validate: function (frm) {
		// First, get all items that need stock validation
		let itemsToCheck = frm.doc.items.filter(item =>
			item.is_stock_item === 1 &&
			item.warehouse &&
			item.qty > 0
		);

		const productBundlesToCheck = frm.doc.items.filter(item =>
			item.is_product_bundle &&
			item.qty > 0
		);

		for (const product_bundle of productBundlesToCheck) {
			for (const bundle_item of product_bundle.product_bundle_items) {
				if (bundle_item.is_stock_item === 1 && bundle_item.qty > 0) {
					itemsToCheck.push(bundle_item);
				}

				const subItems = bundle_item.sub_items?.filter(subItem =>
					subItem.is_stock_item === 1 && subItem.qty > 0
				);
				itemsToCheck.push(...subItems);
			}
		}

		if (!itemsToCheck.length) return;

		// Group items by warehouse for more efficient querying
		const itemsByWarehouse = {};
		itemsToCheck.forEach(item => {
			if (!itemsByWarehouse[item.warehouse]) {
				itemsByWarehouse[item.warehouse] = [];
			}
			itemsByWarehouse[item.warehouse].push(item);
		});

		// Create an array to track all insufficient items
		const insufficientItems = [];

		// Create a promise for each warehouse (reduces number of server calls)
		const warehousePromises = Object.entries(itemsByWarehouse).map(([warehouse, items]) => {
			// Get all item codes for this warehouse
			const itemCodes = items.map(item => item.item_code);

			// Get stock data for all items in this warehouse in one call
			return frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Bin",
					filters: {
						item_code: ["in", itemCodes],
						warehouse: warehouse
					},
					fields: ["item_code", "actual_qty", "reserved_qty", "projected_qty"]
				}
			}).then(response => {
				const binData = response.message || [];

				// Create a lookup map for quick access
				const stockMap = {};
				binData.forEach(bin => {
					stockMap[bin.item_code] = bin;
				});

				// Check each item in this warehouse
				items.forEach(item => {
					const stock = stockMap[item.item_code] || {
						actual_qty: 0,
						reserved_qty: 0,
						projected_qty: 0
					};

					const available_qty = stock.actual_qty - stock.reserved_qty;

					// If requested quantity exceeds available, add to insufficient items
					if (item.qty > available_qty) {
						insufficientItems.push({
							item_code: item.item_code,
							item_name: item.item_name || item.item_code,
							warehouse: warehouse,
							available: available_qty,
							requested: item.qty
						});
					}
				});
			});
		});

		// Wait for all warehouse checks to complete
		return Promise.all(warehousePromises).then(() => {
			// If any items have insufficient stock, show a consolidated message
			if (insufficientItems.length) {
				// Create a formatted message with all insufficient items
				let message = __("The following items don't have sufficient stock:") + "<br><br>";
				message += "<table class='table table-bordered'>";
				message += "<tr><th>" + __("Item") + "</th>";
				message += "<th>" + __("Warehouse") + "</th>";
				message += "<th>" + __("Available Qty") + "</th>";
				message += "<th>" + __("Requested Qty") + "</th></tr>";

				insufficientItems.forEach(item => {
					message += `<tr>
            <td>${item.item_name}</td>
            <td>${item.warehouse}</td>
            <td>${item.available}</td>
            <td>${item.requested}</td>
          </tr>`;
				});

				message += "</table>";

				// Show the message to the user
				frappe.msgprint({
					title: __("Insufficient Stock"),
					indicator: "orange",
					message: message
				});

				// Prevent form submission
				frappe.validated = false;
				return false;
			}
		}).catch(error => {
			console.error("Stock validation error:", error);
			frappe.msgprint({
				title: __("Error"),
				indicator: "red",
				message: __("An error occurred while validating stock. Please try again.")
			});
			frappe.validated = false;
			return false;
		});
	}
});

erpnext.selling.QuotationController = class QuotationController extends erpnext.selling.SellingController {
	onload(doc, dt, dn) {
		super.onload(doc, dt, dn);

		// TODO: think of better way to do this
		// this.frm.trigger("disable_customer_if_creating_from_opportunity");
	}
	quotation_template() {
		if (this.frm.doc.quotation_template) {
			frappe.db.get_doc("Quotation Templates", this.frm.doc.quotation_template).then((doc) => {
				const items = doc.items.map((item) => {
					return {
						item_code: item.item_code,
						item_name: item.item_name,
						description: item.description,
						qty: item.qty,
						rate: item.rate,
						amount: item.rate * item.qty
					};
				});
				this.frm.set_value('items', items);
				this.apply_price_list();
			})
		}
	}

	party_name() {
		var me = this;
		erpnext.utils.get_party_details(this.frm, null, null, function () {
			me.apply_price_list();
		});

		if (me.frm.doc.quotation_to == "Lead" && me.frm.doc.party_name) {
			me.frm.trigger("get_lead_details");
		}
	}
	refresh(doc, dt, dn) {
		super.refresh(doc, dt, dn);
		frappe.dynamic_link = {
			doc: this.frm.doc,
			fieldname: "party_name",
			doctype: doc.quotation_to,
		};

		var me = this;

		if (doc.__islocal && !doc.valid_till) {
			if (frappe.boot.sysdefaults.quotation_valid_till) {
				this.frm.set_value(
					"valid_till",
					frappe.datetime.add_days(
						doc.transaction_date,
						frappe.boot.sysdefaults.quotation_valid_till
					)
				);
			} else {
				this.frm.set_value("valid_till", frappe.datetime.add_months(doc.transaction_date, 1));
			}
		}

		if (doc.docstatus == 1 && !["Lost", "Ordered"].includes(doc.status)) {
			if (
				frappe.boot.sysdefaults.allow_sales_order_creation_for_expired_quotation ||
				!doc.valid_till ||
				frappe.datetime.get_diff(doc.valid_till, frappe.datetime.get_today()) >= 0
			) {
				this.frm.add_custom_button(__("Sales Order"), () => this.make_sales_order(), __("Create"));
			}

			if (doc.status !== "Ordered") {
				this.frm.add_custom_button(__("Set as Lost"), () => {
					this.frm.trigger("set_as_lost_dialog");
				});
			}

			cur_frm.page.set_inner_btn_group_as_primary(__("Create"));
		}

		if (this.frm.doc.docstatus === 0) {
			this.frm.add_custom_button(
				__("Opportunity"),
				function () {
					erpnext.utils.map_current_doc({
						method: "erpnext.crm.doctype.opportunity.opportunity.make_quotation",
						source_doctype: "Opportunity",
						target: me.frm,
						setters: [
							{
								label: "Party",
								fieldname: "party_name",
								fieldtype: "Link",
								options: me.frm.doc.quotation_to,
								default: me.frm.doc.party_name || undefined,
							},
							{
								label: "Opportunity Type",
								fieldname: "opportunity_type",
								fieldtype: "Link",
								options: "Opportunity Type",
								default: me.frm.doc.order_type || undefined,
							},
						],
						get_query_filters: {
							status: ["not in", ["Lost", "Closed"]],
							company: me.frm.doc.company,
						},
					});
				},
				__("Get Items From"),
				"btn-default"
			);
		}

		this.toggle_reqd_lead_customer();
	}

	make_sales_order() {
		var me = this;

		let has_alternative_item = this.frm.doc.items.some((item) => item.is_alternative);
		if (has_alternative_item) {
			this.show_alternative_items_dialog();
		} else {
			frappe.model.open_mapped_doc({
				method: "erpnext.selling.doctype.quotation.quotation.make_sales_order",
				frm: me.frm,
			});
		}
	}

	set_dynamic_field_label() {
		if (this.frm.doc.quotation_to == "Customer") {
			this.frm.set_df_property("party_name", "label", "Customer");
			this.frm.fields_dict.party_name.get_query = null;
		} else if (this.frm.doc.quotation_to == "Lead") {
			this.frm.set_df_property("party_name", "label", "Lead");
			this.frm.fields_dict.party_name.get_query = function () {
				return { query: "erpnext.controllers.queries.lead_query" };
			};
		} else if (this.frm.doc.quotation_to == "Prospect") {
			this.frm.set_df_property("party_name", "label", "Prospect");
			this.frm.fields_dict.party_name.get_query = null;
		}
	}

	toggle_reqd_lead_customer() {
		var me = this;

		// to overwrite the customer_filter trigger from queries.js
		this.frm.toggle_reqd("party_name", this.frm.doc.quotation_to);
		this.frm.set_query("customer_address", this.address_query);
		this.frm.set_query("shipping_address_name", this.address_query);
	}

	tc_name() {
		this.get_terms();
	}

	address_query(doc) {
		return {
			query: "frappe.contacts.doctype.address.address.address_query",
			filters: {
				link_doctype: frappe.dynamic_link.doctype,
				link_name: doc.party_name,
			},
		};
	}

	validate_company_and_party(party_field) {
		if (!this.frm.doc.quotation_to) {
			frappe.msgprint(
				__("Please select a value for {0} quotation_to {1}", [
					this.frm.doc.doctype,
					this.frm.doc.name,
				])
			);
			return false;
		} else if (this.frm.doc.quotation_to == "Lead") {
			return true;
		} else {
			return super.validate_company_and_party(party_field);
		}
	}

	get_lead_details() {
		var me = this;
		if (!this.frm.doc.quotation_to === "Lead") {
			return;
		}

		frappe.call({
			method: "erpnext.crm.doctype.lead.lead.get_lead_details",
			args: {
				lead: this.frm.doc.party_name,
				posting_date: this.frm.doc.transaction_date,
				company: this.frm.doc.company,
			},
			callback: function (r) {
				if (r.message) {
					me.frm.updating_party_details = true;
					me.frm.set_value(r.message);
					me.frm.refresh();
					me.frm.updating_party_details = false;
				}
			},
		});
	}

	show_alternative_items_dialog() {
		let me = this;

		const table_fields = [
			{
				fieldtype: "Data",
				fieldname: "name",
				label: __("Name"),
				read_only: 1,
			},
			{
				fieldtype: "Link",
				fieldname: "item_code",
				options: "Item",
				label: __("Item Code"),
				read_only: 1,
				in_list_view: 1,
				columns: 2,
				formatter: (value, df, options, doc) => {
					return doc.is_alternative ? `<span class="indicator yellow">${value}</span>` : value;
				},
			},
			{
				fieldtype: "Data",
				fieldname: "description",
				label: __("Description"),
				in_list_view: 1,
				read_only: 1,
			},
			{
				fieldtype: "Currency",
				fieldname: "amount",
				label: __("Amount"),
				options: "currency",
				in_list_view: 1,
				read_only: 1,
			},
			{
				fieldtype: "Check",
				fieldname: "is_alternative",
				label: __("Is Alternative"),
				read_only: 1,
			},
		];

		this.data = this.frm.doc.items
			.filter((item) => item.is_alternative || item.has_alternative_item)
			.map((item) => {
				return {
					name: item.name,
					item_code: item.item_code,
					description: item.description,
					amount: item.amount,
					is_alternative: item.is_alternative,
				};
			});

		const dialog = new frappe.ui.Dialog({
			title: __("Select Alternative Items for Sales Order"),
			fields: [
				{
					fieldname: "info",
					fieldtype: "HTML",
					read_only: 1,
				},
				{
					fieldname: "alternative_items",
					fieldtype: "Table",
					cannot_add_rows: true,
					cannot_delete_rows: true,
					in_place_edit: true,
					reqd: 1,
					data: this.data,
					description: __("Select an item from each set to be used in the Sales Order."),
					get_data: () => {
						return this.data;
					},
					fields: table_fields,
				},
			],
			primary_action: function () {
				frappe.model.open_mapped_doc({
					method: "erpnext.selling.doctype.quotation.quotation.make_sales_order",
					frm: me.frm,
					args: {
						selected_items: dialog.fields_dict.alternative_items.grid.get_selected_children(),
					},
				});
				dialog.hide();
			},
			primary_action_label: __("Continue"),
		});

		dialog.fields_dict.info.$wrapper.html(
			`<p class="small text-muted">
				<span class="indicator yellow"></span>
				${__("Alternative Items")}
			</p>`
		);
		dialog.show();
	}

	currency() {
		super.currency();
		let me = this;
		const company_currency = this.get_company_currency();
		if (this.frm.doc.currency && this.frm.doc.currency !== company_currency) {
			this.get_exchange_rate(
				this.frm.doc.transaction_date,
				this.frm.doc.currency,
				company_currency,
				function (exchange_rate) {
					if (exchange_rate != me.frm.doc.conversion_rate) {
						me.set_margin_amount_based_on_currency(exchange_rate);
						me.set_actual_charges_based_on_currency(exchange_rate);
						me.frm.set_value("conversion_rate", exchange_rate);
					}
				}
			);
		}
	}

	disable_customer_if_creating_from_opportunity(doc) {
		if (doc.opportunity) {
			this.frm.set_df_property("party_name", "read_only", 1);
		}
	}
};

cur_frm.script_manager.make(erpnext.selling.QuotationController);

frappe.ui.form.on(
	"Quotation Item",
	"items_on_form_rendered",
	"packed_items_on_form_rendered",
	function (frm, cdt, cdn) {
		// enable tax_amount field if Actual
	}
);

frappe.ui.form.on("Quotation Item", "stock_balance", function (frm, cdt, cdn) {
	var d = frappe.model.get_doc(cdt, cdn);
	frappe.route_options = { item_code: d.item_code };
	frappe.set_route("query-report", "Stock Balance");
});

//---------------------------------- Quotation on item code change and qty change
frappe.ui.form.on('Quotation Item', {
	item_code: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.is_product_bundle) {
			initializeLocalStorage(row);
			storeOriginalQuantities(row);
			const exist = validateItemsNotExist(frm, row.item_code, row);
			if (exist) {
				frappe.msgprint(__("Product bundle {0} already exists in the quotation. Please remove it before adding a new item.", [row.item_code]));
				return;
			}
			const confirmItems = [];
			let concatenatedDescription = '';
			processProductBundle(frm, row, confirmItems, concatenatedDescription);
		}
	},

	qty: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.qty < 0) {
			row.qty = Math.abs(row.qty);
			refreshQuotationFields(frm);
		}
		if (row.is_product_bundle) {
			const storage_name = `Quotation:OriginalQuantities:${row.item_code}`;
			const originalQuantities = JSON.parse(localStorage.getItem(storage_name));
			if (!originalQuantities) return;
			updateSubItemQuantities(frm, row, originalQuantities);
		}
	},
	discount_percentage: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const rate = row.base_price_list_rate;

		if (rate <= 0) return

		const discount_percentage = row.discount_percentage;
		const discount_amount = Number(((rate * discount_percentage) / 100).toFixed(2));

		row.rate = rate - discount_amount;
		row.discount_percentage = discount_percentage;
		row.discount_amount = discount_amount

		const allItems = frm.doc.items.map(item => {
			if (item.item_code === row.item_code) {
				item.discount_percentage = discount_percentage;
				item.discount_amount = discount_amount;
			}
			return item;
		});
		frm.set_value('items', allItems);
		refreshQuotationFields(frm);
	},
});

function validateItemsNotExist(frm, item_code, current_row) {
	return frm.doc.items.some(item => {
		return item.item_code === item_code && item.is_product_bundle && item.name !== current_row.name;
	});
}


function initializeLocalStorage(row) {
	const storage_name = `Quotation:OriginalQuantities:${row.item_code}`;
	if (!localStorage.getItem(storage_name)) {
		localStorage.setItem(storage_name, JSON.stringify({}));
	}
}

function storeOriginalQuantities(row) {
	const storage_name = `Quotation:OriginalQuantities:${row.item_code}`;
	const originalQuantities = JSON.parse(localStorage.getItem(storage_name));
	originalQuantities[row.item_code] = {
		qty: row.qty,
		rate: row.rate,
		product_bundle_items: row.product_bundle_items.map(bundleItem => ({
			item_code: bundleItem.item_code,
			qty: bundleItem.qty,
			sub_items: bundleItem.sub_items.map(subItem => ({
				item_code: subItem.item_code,
				qty: subItem.qty
			}))
		}))
	};
	localStorage.setItem(storage_name, JSON.stringify(originalQuantities));
}

function processProductBundle(frm, row, confirmItems, concatenatedDescription) {
	row.product_bundle_items.forEach(bundleItem => {
		const visibleDescriptions = row.product_bundle_items
			.filter(item => item.description_visible)
			.map(item => item.description || '');

		concatenatedDescription = visibleDescriptions.join(', ').trim();

		bundleItem.sub_items.forEach(subItem => {
			subItem.qty *= bundleItem.qty;

			if (subItem.options === "Recommended additional") {
				confirmItems.push({ ...subItem, _parent: subItem._product_bundle });
			} else {
				addSubItemToQuotation(frm, subItem, row);
			}
		});
	});

	updateRowDescription(frm, row, concatenatedDescription);
	showDialog(frm, row, confirmItems);
}

function addSubItemToQuotation(frm, subItem, row) {
	frm.add_child('items', {
		item_name: subItem.item_code,
		item_code: subItem.item_code,
		description: subItem.description,
		weight_per_unit: row.weight_per_unit,
		qty: subItem.qty,
		rate: subItem.price,
		uom: row.uom,
		stock_uom: row.stock_uom,
		_parent: row.item_code,
		parentfield: "items",
		parenttype: "Quotation"
	});
}

function updateRowDescription(frm, row, concatenatedDescription) {
	setTimeout(() => {
		row.description = concatenatedDescription;
		const allItems = frm.doc.items.map(item => updateItemRate(item, row));
		frm.set_value('items', allItems);
		refreshQuotationFields(frm);
	}, 1000);
}

function updateItemRate(item, row) {
	if (item.name === row.name) {
		item.description = row.description;
	}
	item.rate = item.product_bundle_items?.reduce((total, bundleItem) =>
		total + (bundleItem.qty * bundleItem.price), 0) || item.rate || 0;

	return item;
}

function showDialog(frm, row, confirmItems) {
	const dialog = new frappe.ui.Dialog({
		title: __(row.item_code),
		fields: createDialogFields(row, confirmItems),
		primary_action_label: __("Add Items"),
		secondary_action_label: __("Cancel"),
		primary_action(values) {
			addSelectedItemsToQuotation(frm, values, confirmItems, row);
			dialog.hide();
		},
		secondary_action() {
			dialog.hide();
		}
	});

	dialog.$wrapper.modal({
		backdrop: "static",
		keyboard: false,
		size: "1024px"
	});
	dialog.show();
	dialog.$wrapper.find('.modal-dialog').css("max-width", "1024px").css("width", "1024px");
}

function createDialogFields(row, confirmItems) {
	const tableOptions = createSummaryTable(row);
	const fields = [{
		fieldtype: 'HTML',
		fieldname: 'summary_table',
		options: tableOptions
	}];
	confirmItems.forEach(item => {
		fields.push({
			label: item.item_code,
			fieldname: item.item_code,
			fieldtype: 'Check',
			default: 0
		});
	});
	return fields;
}

function createSummaryTable(row) {
	const tableHeader = `
        <thead>
            <tr>
                <th>${__("Quantity")}</th>
                <th>${__("Item Code")}</th>
                <th>${__("Description")}</th>
                <th>${__("Rate (EUR)")}</th>
                <th>${__("Amount (EUR)")}</th>
            </tr>
        </thead>
    `;
	const tableBody = row.product_bundle_items.map(bundleItem => createBundleItemRow(bundleItem)).join('');

	const totalRow = `
        <tr>
            <td colspan="4"><strong>${__("Total")}</strong></td>
            <td><strong>${format_currency(calculateTotal(row))}</strong></td>
        </tr>
    `;

	return `<table class="table table-bordered">${tableHeader}<tbody>${tableBody}${totalRow}</tbody></table>
            <p><strong>${__("Recommended Additional Items")}:</strong></p>`;
}

function createBundleItemRow(bundleItem) {
	const bundleAmount = bundleItem.qty * bundleItem.price;
	let rows = `
        <tr>
            <td>${bundleItem.qty}</td>
            <td>${bundleItem.item_code}</td>
            <td>${bundleItem.description}</td>
            <td>${format_currency(bundleItem.price)}</td>
            <td>${format_currency(bundleAmount)}</td>
        </tr>
    `;
	rows += bundleItem.sub_items
		.filter(subItem => subItem.options !== "Recommended additional")
		.map(subItem => createSubItemRow(bundleItem, subItem)).join('');
	return rows;
}

function createSubItemRow(bundleItem, subItem) {
	const subItemAmount = subItem.qty * subItem.price;
	return `
        <tr>
            <td>${subItem.qty}</td>
            <td>${subItem.item_code}</td>
            <td>${subItem.description}</td>
            <td>${format_currency(subItem.price)}</td>
            <td>${format_currency(subItemAmount)}</td>
        </tr>
    `;
}

function calculateTotal(row) {
	return row.product_bundle_items.reduce((total, bundleItem) => {
		const bundleSubtotal = bundleItem.qty * (bundleItem.price || 0);
		const subItemsTotal = bundleItem.sub_items
			.filter(subItem => subItem.options !== "Recommended additional")
			.reduce((subTotal, subItem) => {
				return subTotal + (subItem.qty * (subItem.price || 0));
			}, 0);
		return total + bundleSubtotal + subItemsTotal;
	}, 0);
}

function addSelectedItemsToQuotation(frm, values, confirmItems, row) {
	confirmItems.forEach(item => {
		if (values[item.item_code]) {
			frm.add_child('items', {
				item_name: item.item_code,
				item_code: item.item_code,
				description: item.description,
				qty: item.qty,
				rate: item.price,
				uom: row.uom,
				stock_uom: row.stock_uom,
				parent: row.parent,
				_parent: item._parent,
				_product_bundle: item._product_bundle,
				parentfield: "items",
				parenttype: "Quotation",
				weight_per_unit: row.weight_per_unit
			});
		}
	});

	refreshQuotationFields(frm);
}

function updateSubItemQuantities(frm, row, originalQuantities) {
	const storage = originalQuantities[row.item_code];
	const nuevaQtyProductBundle = row.qty;
	frm.doc.items.forEach(item => {
		if (item._parent === row.item_code) {
			storage.product_bundle_items.forEach(bundleItem => {
				bundleItem.sub_items.forEach(subItem => {
					if (subItem.item_code === item.item_code) {
						const updatedQty = (subItem.qty * bundleItem.qty) * nuevaQtyProductBundle;
						frappe.model.set_value(item.doctype, item.name, 'qty', updatedQty);
					}
				});
			});
		}
	});
	refreshQuotationFields(frm);
}

//---------------------------------- Quotation on selling price list change
frappe.ui.form.on('Quotation', {
	selling_price_list: function (frm) {
		if (!frm.doc.items.length || (frm.doc.items.length > 0 && !frm.doc.items[0].item_code)) {
			return;
		}

		const itemCodesToSend = collectItemCodes(frm);

		const newSellingPriceList = frm.doc.selling_price_list;
		frappe.call({
			method: "erpnext.stock.get_item_details.get_item_product_bundle_template",
			args: {
				args: {
					item_codes: itemCodesToSend,
					selling_price_list: newSellingPriceList
				}
			},
			callback: function (r) {
				if (r.message) {
					updateItemRates(frm, r.message);
				}
			}
		});
	}
});

function collectItemCodes(frm) {
	const itemCodesToSend = [];

	frm.doc.items.forEach(item => {
		if (item.is_product_bundle) {
			item.product_bundle_items.forEach(bundleItem => {
				if (bundleItem.description_visible) {
					itemCodesToSend.push(bundleItem.item_code);
					bundleItem.sub_items.forEach(subItem => {
						if (!frm.doc.items.some(docItem => docItem.item_code === subItem.item_code)) {
							itemCodesToSend.push(subItem.item_code);
						}
					});
				}
			});
		} else {
			itemCodesToSend.push(item.item_code);
		}
	});

	return itemCodesToSend;
}

function updateItemRates(frm, updatedPrices) {
	frm.doc.items.forEach(item => {
		if (item.is_product_bundle) {
			let newRate = 0;

			item.product_bundle_items.forEach(bundleItem => {
				if (updatedPrices[bundleItem.item_code]) {
					bundleItem.price = updatedPrices[bundleItem.item_code];
					if (bundleItem.description_visible) {
						newRate += bundleItem.qty * bundleItem.price;
					}
				}

				bundleItem.sub_items.forEach(subItem => {
					if (!frm.doc.items.some(docItem => docItem.item_code === subItem.item_code) && updatedPrices[subItem.item_code]) {
						subItem.price = updatedPrices[subItem.item_code];
						newRate += subItem.qty * subItem.price;
					}
				});
			});

			item.rate = newRate;
		} else if (updatedPrices[item.item_code]) {
			item.rate = updatedPrices[item.item_code];
		}
	});

	refreshQuotationFields(frm);
}

function refreshQuotationFields(frm) {
	frm.refresh_field('items');
	frm.trigger('calculate_taxes_and_totals');
	frm.refresh_fields(['rate', 'total', 'grand_total', 'net_total']);
}

// ---------------------------------------------------------------------------
// Diagnosis-driven quotation builder
// Reads the linked Project's diagnosis, detects labour jobs, and proposes parts
// (from Sales Invoice history for the same car config) + a labour line whose
// hours come from Standard Labour Hours (Manuren). See selling/quotation_builder.py
// ---------------------------------------------------------------------------
frappe.ui.form.on("Quotation", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || !frm.doc.project_name) {
			return;
		}
		frm.add_custom_button(__("Build from diagnosis"), () => build_from_diagnosis(frm));
	},
});

function build_from_diagnosis(frm) {
	frappe.dom.freeze(__("Reading diagnosis..."));
	frappe
		.call({
			method: "erpnext.selling.quotation_builder.build_quotation_suggestions",
			args: { quotation: frm.doc.name },
		})
		.then((r) => {
			frappe.dom.unfreeze();
			if (r && r.message) {
				show_builder_dialog(frm, r.message);
			}
		})
		.catch(() => frappe.dom.unfreeze());
}

function show_builder_dialog(frm, bundle) {
	const dialog = new frappe.ui.Dialog({
		title: __("Build from diagnosis"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
		primary_action_label: __("Add to Quotation"),
		primary_action: () => apply_builder_selection(frm, dialog, bundle),
	});

	const $body = dialog.fields_dict.body.$wrapper;
	$body.append(render_builder_html(bundle));
	dialog.show();
}

function render_builder_html(bundle) {
	const esc = frappe.utils.escape_html;
	const car = bundle.car || {};
	let html = `<div class="builder-suggestions">`;
	html += `<p class="text-muted">${__("Car")}: <b>${esc(car.dsg_family || "?")}</b>
		(dsg ${esc(car.dsg_code || "?")}, engine ${esc(car.engine_code || "?")})</p>`;

	(bundle.messages || []).forEach((m) => {
		html += `<div class="alert alert-warning" style="padding:6px 10px">${esc(m)}</div>`;
	});

	if (!bundle.jobs || !bundle.jobs.length) {
		html += `<p>${__("No jobs detected.")}</p></div>`;
		return html;
	}

	bundle.jobs.forEach((job, ji) => {
		html += `<div class="job-block" data-job="${esc(job.job)}" data-ji="${ji}"
			style="border:1px solid var(--border-color);border-radius:6px;padding:10px;margin-bottom:12px">`;
		html += `<h5 style="margin-top:0">${esc(job.job)}
			<small class="text-muted">(${__("matched")}: "${esc(job.matched_keyword)}")</small></h5>`;

		// Labour variant picker
		const variants = (job.labour && job.labour.variants) || [];
		const applicable = variants.filter((v) => v.applicable);
		if (bundle.labour_item_code && applicable.length) {
			html += `<div style="margin-bottom:8px">${__("Labour")}:
				<select class="form-control labour-variant" style="display:inline-block;width:auto">
				<option value="">${__("(no labour line)")}</option>`;
			applicable.forEach((v, idx) => {
				html += `<option value="${idx}" data-hours="${v.hours}" data-variant="${esc(v.vehicle_variant)}"
					${idx === 0 ? "selected" : ""}>${esc(v.vehicle_variant)} — ${v.hours} ${__("h")}</option>`;
			});
			html += `</select></div>`;
		} else {
			html += `<div class="text-muted" style="margin-bottom:8px">${__("No standard labour hours for this car/job.")}</div>`;
		}

		// OEM reference parts
		(job.oem_refs || []).forEach((ref) => {
			if (ref.item_code) {
				html += part_row(ref.item_code, `${esc(ref.part_no)} (${__("OEM")})`, "", true);
			} else {
				html += `<div class="text-muted small">${__("OEM part")} (${esc(ref.project_field)}):
					<b>${esc(ref.part_no)}</b> — ${__("not in catalog, add manually")}</div>`;
			}
		});

		// Historical part suggestions
		const parts = job.suggested_parts || [];
		if (parts.length) {
			html += `<table class="table table-bordered" style="margin:6px 0">
				<thead><tr><th width="30"></th><th>${__("Item")}</th><th width="90">${__("Used in")}</th>
				<th width="80">${__("Qty")}</th></tr></thead><tbody>`;
			parts.forEach((p) => {
				html += part_row(p.item_code, esc(p.item_name || p.item_code), `${p.invoices}×`, false);
			});
			html += `</tbody></table>`;
		} else {
			html += `<div class="text-muted small">${__("No historical parts found for this job/car.")}</div>`;
		}
		html += `</div>`;
	});

	html += `</div>`;
	return html;
}

function part_row(item_code, label, used, checked) {
	const esc = frappe.utils.escape_html;
	return `<tr class="part-row">
		<td><input type="checkbox" class="part-check" data-item="${esc(item_code)}" ${checked ? "checked" : ""}></td>
		<td>${label}<br><span class="text-muted small">${esc(item_code)}</span></td>
		<td>${used || ""}</td>
		<td><input type="number" class="form-control part-qty" value="1" min="0" step="0.5" style="width:70px"></td>
	</tr>`;
}

function apply_builder_selection(frm, dialog, bundle) {
	const $body = dialog.fields_dict.body.$wrapper;
	const rows = [];

	$body.find(".job-block").each(function () {
		const $block = $(this);
		const job = $block.data("job");

		// selected parts
		$block.find(".part-row").each(function () {
			const $r = $(this);
			if ($r.find(".part-check").is(":checked")) {
				rows.push({
					item_code: $r.find(".part-check").data("item"),
					qty: flt($r.find(".part-qty").val()) || 1,
				});
			}
		});

		// labour line
		const $sel = $block.find(".labour-variant");
		if ($sel.length && $sel.val() !== "") {
			const $opt = $sel.find("option:selected");
			const hours = flt($opt.data("hours"));
			if (bundle.labour_item_code && hours > 0) {
				rows.push({
					item_code: bundle.labour_item_code,
					qty: hours,
					description: `${job} – ${$opt.data("variant")} (${hours}u)`,
				});
			}
		}
	});

	if (!rows.length) {
		frappe.msgprint(__("Select at least one part or labour line."));
		return;
	}

	frappe.dom.freeze(__("Adding to quotation..."));
	frappe
		.call({
			method: "erpnext.selling.quotation_builder.apply_suggestions_to_quotation",
			args: { quotation: frm.doc.name, rows: JSON.stringify(rows) },
		})
		.then((r) => {
			frappe.dom.unfreeze();
			dialog.hide();
			if (r && r.message) {
				frappe.show_alert(
					{ message: __("Added {0} line(s) — review rates.", [r.message.added]), indicator: "green" },
					7
				);
			}
			frm.reload_doc();
		})
		.catch(() => frappe.dom.unfreeze());
}

async function insertResendQuotationApprovalButton(frm) {
	if (!["Approved", "Ordered"].includes(frm.doc.status)) {
		frm.add_custom_button(__('Resend Approve Message'), () => {
			var d = new frappe.ui.Dialog({
				title: __("The message and quotation attached will be sent to the client for approval"),
				fields: [],
				primary_action_label: __("Send"),
				primary_action: async function () {
					const { aws_url } = await frappe.db.get_doc('Queue Settings')
					const url = `${aws_url}quotation/created`;
					const obj = {
						"party_name": frm.doc.party_name,
						"customer_name": frm.doc.customer_name,
						"doctype": "Quotation",
						"name": frm.doc.name,
						"grand_total": frm.doc.grand_total
					};
					fetch(url, {
						method: 'POST',
						headers: {
							'Content-Type': 'application/json',
						},
						body: JSON.stringify(obj)
					})
						.then(() => {
							frappe.show_alert({
								message: __('Message sent'),
								indicator: 'green'
							}, 10);
						})
						.catch((error) => {
							frappe.show_alert({
								message: __('An error occurred while sending the message'),
								indicator: 'red'
							}, 10);
							console.error('Error:', error);
						});

					d.hide();
				},
				secondary_action_label: __("Cancel"),
				secondary_action: function () {
					d.hide();
				}
			});

			d.show();
		});
	}
}
