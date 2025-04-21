// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

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
		const { aws_url } = await frappe.db.get_doc('Rest Config')
    // Make API call to validate VAT ID
    $.ajax({
        url: `${aws_url}vat-validation?vatId=${encodeURIComponent(trimmedTaxId)}`,
        type: 'GET',
        success: function(response) {
            frappe.dom.unfreeze();

            // Create dialog to display validation results
            const dialog = new frappe.ui.Dialog({
                title: __('VAT Validation Results'),
                fields: [
                    {
                        fieldtype: 'Section Break',
                        label: __('Validation Status')
                    },
                    {
                        fieldtype: 'HTML',
                        fieldname: 'status_html'
                    },
                    {
                        fieldtype: 'Section Break',
                        label: __('Company Details')
                    },
                    {
                        fieldtype: 'HTML',
                        fieldname: 'company_details'
                    }
                ],
                primary_action_label: __('Update Customer Group'),
                primary_action: function() {
                    // Update customer information if validation is successful
                    if (response.isValid) {
                        frm.set_value("customer_group", "Commercial")
												frm.save();
                    }

                    dialog.hide();
                }
            });

            // Set the status HTML based on validation result
            let status_html = '';
            if (response.isValid) {
                status_html = `
                    <div class="alert alert-success">
                        <strong>${__('Valid VAT ID')}</strong>
                        <p>${__('The provided VAT ID is valid.')}</p>
                    </div>
                `;
            } else {
                status_html = `
                    <div class="alert alert-danger">
                        <strong>${__('Invalid VAT ID')}</strong>
                        <p>${__('Error: ')} ${response.userError || __('Validation failed')}</p>
                    </div>
                `;
            }
            dialog.fields_dict.status_html.$wrapper.html(status_html);

            // Set company details HTML
            let company_details = '';
            if (response.isValid) {
                company_details = `
                    <div class="row">
                        <div class="col-xs-12">
                            <div class="row">
                                <div class="col-xs-4"><strong>${__('Company Name')}:</strong></div>
                                <div class="col-xs-8">${response.name || '-'}</div>
                            </div>
                            <div class="row">
                                <div class="col-xs-4"><strong>${__('Address')}:</strong></div>
                                <div class="col-xs-8">${response.address || '-'}</div>
                            </div>
                            <div class="row">
                                <div class="col-xs-4"><strong>${__('VAT Number')}:</strong></div>
                                <div class="col-xs-8">${response.vatNumber || '-'}</div>
                            </div>
                            <div class="row">
                                <div class="col-xs-4"><strong>${__('Request Date')}:</strong></div>
                                <div class="col-xs-8">${frappe.datetime.str_to_user(response.requestDate) || '-'}</div>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                company_details = `
                    <div class="alert alert-warning">
                        <p>${__('No company details available for invalid VAT ID.')}</p>
                    </div>
                `;
            }

            dialog.fields_dict.company_details.$wrapper.html(company_details);
            dialog.show();
        },
        error: function(xhr, status, error) {
            frappe.dom.unfreeze();
            frappe.msgprint({
                title: __('VAT Validation Error'),
                indicator: 'red',
                message: __(xhr.responseJSON.error)
            });
            console.error("VAT validation error:", error);
        }
    });
},
	setup: function(frm) {

		frm.make_methods = {
			'Quotation': () => frappe.model.open_mapped_doc({
				method: "erpnext.selling.doctype.customer.customer.make_quotation",
				frm: cur_frm
			}),
			'Opportunity': () => frappe.model.open_mapped_doc({
				method: "erpnext.selling.doctype.customer.customer.make_opportunity",
				frm: cur_frm
			})
		}

		frm.add_fetch('lead_name', 'company_name', 'customer_name');
		frm.add_fetch('default_sales_partner','commission_rate','default_commission_rate');
		frm.set_query('customer_group', {'is_group': 0});
		frm.set_query('default_price_list', { 'selling': 1});
		frm.set_query('account', 'accounts', function(doc, cdt, cdn) {
			let d  = locals[cdt][cdn];
			let filters = {
				'account_type': 'Receivable',
				'root_type': 'Asset',
				'company': d.company,
				"is_group": 0
			};

			if(doc.party_account_currency) {
				$.extend(filters, {"account_currency": doc.party_account_currency});
			}
			return {
				filters: filters
			}
		});

		frm.set_query('advance_account', 'accounts', function (doc, cdt, cdn) {
			let d = locals[cdt][cdn];
			return {
				filters: {
					"account_type": 'Receivable',
					"root_type": "Liability",
					"company": d.company,
					"is_group": 0
				}
			}
		});


		if (frm.doc.__islocal == 1) {
			frm.set_value("represents_company", "");
		}

		frm.set_query('customer_primary_contact', function(doc) {
			return {
				query: "erpnext.selling.doctype.customer.customer.get_customer_primary_contact",
				filters: {
					'customer': doc.name
				}
			}
		})
		frm.set_query('customer_primary_address', function(doc) {
			return {
				filters: {
					'link_doctype': 'Customer',
					'link_name': doc.name
				}
			}
		})

		frm.set_query('default_bank_account', function() {
			return {
				filters: {
					'is_company_account': 1
				}
			}
		});

		frm.set_query("user", "portal_users", function() {
			return {
				filters: {
					"ignore_user_type": true,
				}
			};
		});
	},
	customer_primary_address: function(frm){
		if(frm.doc.customer_primary_address){
			frappe.call({
				method: 'frappe.contacts.doctype.address.address.get_address_display',
				args: {
					"address_dict": frm.doc.customer_primary_address
				},
				callback: function(r) {
					frm.set_value("primary_address", r.message);
				}
			});
		}
		if(!frm.doc.customer_primary_address){
			frm.set_value("primary_address", "");
		}
	},

	is_internal_customer: function(frm) {
		if (frm.doc.is_internal_customer == 1) {
			frm.toggle_reqd("represents_company", true);
		}
		else {
			frm.toggle_reqd("represents_company", false);
		}
	},

	customer_primary_contact: function(frm){
		if(!frm.doc.customer_primary_contact){
			frm.set_value("mobile_no", "");
			frm.set_value("email_id", "");
		}
	},

	loyalty_program: function(frm) {
		if(frm.doc.loyalty_program) {
			frm.set_value('loyalty_program_tier', null);
		}
	},

	refresh: function(frm) {
		if(frappe.defaults.get_default("cust_master_name")!="Naming Series") {
			frm.toggle_display("naming_series", false);
		} else {
			erpnext.toggle_naming_series();
		}

		if(!frm.doc.__islocal) {
			frappe.contacts.render_address_and_contact(frm);

			// custom buttons

			frm.add_custom_button(__('Accounts Receivable'), function () {
				frappe.set_route('query-report', 'Accounts Receivable', { party_type: "Customer", party: frm.doc.name });
			}, __('View'));

			frm.add_custom_button(__('Accounting Ledger'), function () {
				frappe.set_route('query-report', 'General Ledger',
					{party_type: 'Customer', party: frm.doc.name, party_name: frm.doc.customer_name});
			}, __('View'));

			frm.add_custom_button(__('Pricing Rule'), function () {
				erpnext.utils.make_pricing_rule(frm.doc.doctype, frm.doc.name);
			}, __('Create'));

			frm.add_custom_button(__('Get Customer Group Details'), function () {
				frm.trigger("get_customer_group_details");
			}, __('Actions'));

			if (cint(frappe.defaults.get_default("enable_common_party_accounting"))) {
				frm.add_custom_button(__('Link with Supplier'), function () {
					frm.trigger('show_party_link_dialog');
				}, __('Actions'));
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
		if(frm.doc.lead_name) frappe.model.clear_doc("Lead", frm.doc.lead_name);

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
			title: __('Select a Supplier'),
			fields: [{
				fieldtype: 'Link', label: __('Supplier'),
				options: 'Supplier', fieldname: 'supplier', reqd: 1
			}],
			primary_action: function({ supplier }) {
				frappe.call({
					method: 'erpnext.accounts.doctype.party_link.party_link.create_party_link',
					args: {
						primary_role: 'Customer',
						primary_party: frm.doc.name,
						secondary_party: supplier
					},
					freeze: true,
					callback: function() {
						dialog.hide();
						frappe.msgprint({
							message: __('Successfully linked to Supplier'),
							alert: true
						});
					},
					error: function() {
						dialog.hide();
						frappe.msgprint({
							message: __('Linking to Supplier Failed. Please try again.'),
							title: __('Linking Failed'),
							indicator: 'red'
						});
					}
				});
			},
			primary_action_label: __('Create Link')
		});
		dialog.show();
	}
});
