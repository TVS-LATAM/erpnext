// Copyright (c) 2026, TVS and contributors
// For license information, please see license.txt
//
// F.12 — the check that rubriek 3b and the ICP listing say the same thing.
//
// The default range is the previous quarter: this is opened to check a period
// that is closing, and the ICP listing is filed per period, never mid-flight.
// Company is required because a reconciliation across companies reconciles
// nothing — the ICP declaration refuses without one for the same reason.

frappe.query_reports["VAT ICP Reconciliation"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.month_start(), -3),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.month_start(), -1),
			reqd: 1,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// A difference is the whole finding, and a difference rendered like
		// every other number is a finding nobody reads. Zero stays plain: a
		// reconciled period should look calm.
		if (column.fieldname === "difference" && flt(data?.difference)) {
			value = "<span style='color: var(--red-500); font-weight: 600;'>" + value + "</span>";
		}

		// The report says so itself when its own itemisation does not add up.
		// That line outranks every other row on the page.
		if (data?.invoice === "UNEXPLAINED") {
			value = "<span style='color: var(--red-600); font-weight: 700;'>" + value + "</span>";
		}

		return value;
	},
};
