// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

/**
 * T1.9 — this dialog validates a VAT number. It does not classify the customer.
 *
 * It used to write four things on the way out: `customer_type: "Company"`,
 * `customer_group: "Garage"`, a `tax_category` it recomputed in the browser,
 * and that same category cascaded onto every matching Address.
 *
 * All four are gone, and each for its own reason.
 *
 * `customer_type` is the one with money attached. The booking form asks the
 * customer to choose it, `ContactView.vue` reads it back to prefill their next
 * visit, and `resolveTaxTreatment` reads it to decide between article 138 and
 * article 146. Overwriting it here falsified the customer's own answer and then
 * handed that falsified value to the fiscal decision. T1.3 removed the same
 * write from the server; this was the other writer.
 *
 * The category is subtler. Since T1.3 the server returns no category at all —
 * the regime is decided once, at invoice time, from the facts of the whole
 * sale. So the browser could only recompute one from the VAT prefix, which is
 * precisely the second source of truth this work exists to remove. There is no
 * third option: either the browser guesses, or it writes nothing.
 *
 * Verified in production on 2026-09-01 before removing it: of 1,311 submitted
 * invoices, 659 carry `Omzet Werkplaats (21%)` and 652 carry nothing. Neither
 * value is a key of TAX_CATEGORY_MAPPING in vat_declaration.py or
 * tax_declaration.py, the only two things in this app that read the field, so
 * the categories this dialog wrote have never once classified a VAT return.
 * Removing the write takes nothing away that was working.
 *
 * What the dialog does now is report what VIES said, in the four states T1.4
 * gave it. That is also the fix for the regression T1.3 caused here: a non-EU
 * number answers `isValid: false`, and this screen used to render that as
 * "Invalid VAT ID", so staff were told a perfectly good Swiss number was bad.
 * VIES only covers member states — that is not a verdict on the number.
 */

frappe.ui.form.on("Customer", {
	vat_validation: async function(frm) {
		if (!frm.doc.tax_id) {
			frappe.msgprint(__("Please enter a Tax ID before validating."));
			return;
		}

		frappe.dom.freeze(__("Validating VAT ID..."));

		const trimmedTaxId = frm.doc.tax_id.trim();
		if (trimmedTaxId !== frm.doc.tax_id) {
			frm.set_value("tax_id", trimmedTaxId);
		}
		const { aws_url } = await frappe.db.get_doc("Rest Config");
		// Make API call to validate VAT ID
		$.ajax({
			url: `${aws_url}vat-validation?vatId=${encodeURIComponent(trimmedTaxId)}`,
			type: "GET",
			success: function(response) {
				frappe.dom.unfreeze();

				// Create dialog to display validation results
				const dialog = new frappe.ui.Dialog({
					title: __("VAT Validation Results"),
					fields: [
						{
							fieldtype: "Section Break",
							label: __("Validation Status")
						},
						{
							fieldtype: "HTML",
							fieldname: "status_html"
						},
						{
							fieldtype: "Section Break",
							label: __("Company Details")
						},
						{
							fieldtype: "HTML",
							fieldname: "company_details"
						}
					],
					primary_action_label: __("Close"),
					primary_action: function() {
						dialog.hide();
					}
				});

				// T1.4 gives the endpoint four states, and collapsing them back into
				// valid/invalid here is what told staff a good Swiss number was bad.
				// `status` is preferred; `isValid` is the fallback for a deploy where
				// the service is older than this file.
				const status = response.status || (response.isValid ? "valid" : "invalid");

				let status_html = "";
				if (status === "valid") {
					status_html = `
                    <div class="alert alert-success">
                        <strong>${__("Valid VAT ID")}</strong>
                        <p>${__("VIES confirmed this VAT ID.")}</p>
                    </div>
                `;
				} else if (status === "invalid") {
					status_html = `
                    <div class="alert alert-danger">
                        <strong>${__("Invalid VAT ID")}</strong>
                        <p>${__("VIES was asked and rejected this VAT ID.")} ${response.userError || ""}</p>
                    </div>
                `;
				} else if (response.outsideEU) {
					// Not a verdict on the number. VIES answers only for member states.
					status_html = `
                    <div class="alert alert-info">
                        <strong>${__("Non-EU VAT ID — not checked")}</strong>
                        <p>${__("VIES only covers EU member states, so this number could not be checked. That is not an error, and it does not mean the number is wrong.")}</p>
                    </div>
                `;
				} else {
					// An outage. Emphatically not the same as a rejection: the sale may
					// genuinely be a zero-rated intra-community supply nobody could
					// confirm, and an invoice raised now is held for review at 21%.
					status_html = `
                    <div class="alert alert-warning">
                        <strong>${__("VIES could not answer")}</strong>
                        <p>${__("The VAT number was not rejected — the service did not respond. Try again later; do not record this as invalid.")} ${response.userError || ""}</p>
                    </div>
                `;
				}
				dialog.fields_dict.status_html.$wrapper.html(status_html);

				// Set company details HTML. The tax category row is gone with the
				// write behind it: showing a category this screen no longer applies
				// would be describing a decision made elsewhere, at invoice time.
				let company_details = "";
				if (status === "valid") {
					company_details = `
                    <div class="row">
                        <div class="col-xs-12">
                            <div class="row">
                                <div class="col-xs-4"><strong>${__("Company Name")}:</strong></div>
                                <div class="col-xs-8">${response.name || "-"}</div>
                            </div>
                            <div class="row">
                                <div class="col-xs-4"><strong>${__("Address")}:</strong></div>
                                <div class="col-xs-8">${response.address || "-"}</div>
                            </div>
                            <div class="row">
                                <div class="col-xs-4"><strong>${__("VAT Number")}:</strong></div>
                                <div class="col-xs-8">${response.vatNumber || "-"}</div>
                            </div>
                            <div class="row">
                                <div class="col-xs-4"><strong>${__("Request Date")}:</strong></div>
                                <div class="col-xs-8">${frappe.datetime.str_to_user(response.requestDate) ||
									"-"}</div>
                            </div>
                        </div>
                    </div>
                `;
				} else {
					company_details = `
                    <div class="alert alert-warning">
                        <p>${__("VIES returned no company details for this VAT ID.")}</p>
                    </div>
                `;
				}

				dialog.fields_dict.company_details.$wrapper.html(company_details);
				dialog.show();
			},
			error: function(xhr, status, error) {
				frappe.dom.unfreeze();
				frappe.msgprint({
					title: __("VAT Validation Error"),
					indicator: "red",
					message: __(xhr.responseJSON.error)
				});
				console.error("VAT validation error:", error);
			}
		});
	},
	setup: function(frm) {
		frm.make_methods = {
			Quotation: () =>
				frappe.model.open_mapped_doc({
					method: "erpnext.selling.doctype.customer.customer.make_quotation",
					frm: cur_frm
				}),
			Opportunity: () =>
				frappe.model.open_mapped_doc({
					method: "erpnext.selling.doctype.customer.customer.make_opportunity",
					frm: cur_frm
				})
		};

		frm.add_fetch("lead_name", "company_name", "customer_name");
		frm.add_fetch("default_sales_partner", "commission_rate", "default_commission_rate");
		frm.set_query("default_price_list", { selling: 1 });
		frm.set_query("account", "accounts", function(doc, cdt, cdn) {
			let d = locals[cdt][cdn];
			let filters = {
				account_type: "Receivable",
				root_type: "Asset",
				company: d.company,
				is_group: 0
			};

			if (doc.party_account_currency) {
				$.extend(filters, { account_currency: doc.party_account_currency });
			}
			return {
				filters: filters
			};
		});

		frm.set_query("advance_account", "accounts", function(doc, cdt, cdn) {
			let d = locals[cdt][cdn];
			return {
				filters: {
					account_type: "Receivable",
					root_type: "Liability",
					company: d.company,
					is_group: 0
				}
			};
		});

		if (frm.doc.__islocal == 1) {
			frm.set_value("represents_company", "");
		}

		frm.set_query("customer_primary_contact", function(doc) {
			return {
				query: "erpnext.selling.doctype.customer.customer.get_customer_primary_contact",
				filters: {
					customer: doc.name
				}
			};
		});
		frm.set_query("customer_primary_address", function(doc) {
			return {
				filters: {
					link_doctype: "Customer",
					link_name: doc.name
				}
			};
		});

		frm.set_query("default_bank_account", function() {
			return {
				filters: {
					is_company_account: 1
				}
			};
		});

		frm.set_query("user", "portal_users", function() {
			return {
				filters: {
					ignore_user_type: true
				}
			};
		});
	},
	customer_primary_address: function(frm) {
		if (frm.doc.customer_primary_address) {
			frappe.call({
				method: "frappe.contacts.doctype.address.address.get_address_display",
				args: {
					address_dict: frm.doc.customer_primary_address
				},
				callback: function(r) {
					frm.set_value("primary_address", r.message);
				}
			});
		}
		if (!frm.doc.customer_primary_address) {
			frm.set_value("primary_address", "");
		}
	},

	is_internal_customer: function(frm) {
		if (frm.doc.is_internal_customer == 1) {
			frm.toggle_reqd("represents_company", true);
		} else {
			frm.toggle_reqd("represents_company", false);
		}
	},

	customer_primary_contact: function(frm) {
		if (!frm.doc.customer_primary_contact) {
			frm.set_value("mobile_no", "");
			frm.set_value("email_id", "");
		}
	},

	loyalty_program: function(frm) {
		if (frm.doc.loyalty_program) {
			frm.set_value("loyalty_program_tier", null);
		}
	},

	refresh: function(frm) {
		if (frappe.defaults.get_default("cust_master_name") != "Naming Series") {
			frm.toggle_display("naming_series", false);
		} else {
			erpnext.toggle_naming_series();
		}

		if (!frm.doc.__islocal) {
			frappe.contacts.render_address_and_contact(frm);

			// custom buttons

			frm.add_custom_button(
				__("Accounts Receivable"),
				function() {
					frappe.set_route("query-report", "Accounts Receivable", {
						party_type: "Customer",
						party: frm.doc.name
					});
				},
				__("View")
			);

			frm.add_custom_button(
				__("Accounting Ledger"),
				function() {
					frappe.set_route("query-report", "General Ledger", {
						party_type: "Customer",
						party: frm.doc.name,
						party_name: frm.doc.customer_name
					});
				},
				__("View")
			);

			frm.add_custom_button(
				__("Pricing Rule"),
				function() {
					erpnext.utils.make_pricing_rule(frm.doc.doctype, frm.doc.name);
				},
				__("Create")
			);

			frm.add_custom_button(
				__("Get Customer Group Details"),
				function() {
					frm.trigger("get_customer_group_details");
				},
				__("Actions")
			);

			if (cint(frappe.defaults.get_default("enable_common_party_accounting"))) {
				frm.add_custom_button(
					__("Link with Supplier"),
					function() {
						frm.trigger("show_party_link_dialog");
					},
					__("Actions")
				);
			}

			// indicator
			erpnext.utils.set_party_dashboard_indicators(frm);
		} else {
			frappe.contacts.clear_address_and_contact(frm);
		}

		var grid = cur_frm.get_field("sales_team").grid;
		grid.set_column_disp("allocated_amount", false);
		grid.set_column_disp("incentives", false);
	},
	validate: function(frm) {
		if (!frm.doc.customer_name || frm.doc.customer_name.trim().length < 3) {
			frappe.msgprint(__("Please ensure this name is correct, as it will be used for your invoice."));
			frappe.validated = false;
		}
		if (frm.doc.lead_name) frappe.model.clear_doc("Lead", frm.doc.lead_name);
	},
	get_customer_group_details: function(frm) {
		frappe.call({
			method: "get_customer_group_details",
			doc: frm.doc,
			callback: function() {
				frm.refresh();
			}
		});
	},
	show_party_link_dialog: function(frm) {
		const dialog = new frappe.ui.Dialog({
			title: __("Select a Supplier"),
			fields: [
				{
					fieldtype: "Link",
					label: __("Supplier"),
					options: "Supplier",
					fieldname: "supplier",
					reqd: 1
				}
			],
			primary_action: function({ supplier }) {
				frappe.call({
					method: "erpnext.accounts.doctype.party_link.party_link.create_party_link",
					args: {
						primary_role: "Customer",
						primary_party: frm.doc.name,
						secondary_party: supplier
					},
					freeze: true,
					callback: function() {
						dialog.hide();
						frappe.msgprint({
							message: __("Successfully linked to Supplier"),
							alert: true
						});
					},
					error: function() {
						dialog.hide();
						frappe.msgprint({
							message: __("Linking to Supplier Failed. Please try again."),
							title: __("Linking Failed"),
							indicator: "red"
						});
					}
				});
			},
			primary_action_label: __("Create Link")
		});
		dialog.show();
	}
});
