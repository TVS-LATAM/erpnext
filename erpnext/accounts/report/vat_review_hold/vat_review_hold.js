// Copyright (c) 2026, TVS and contributors
// For license information, please see license.txt
//
// F.3 — the list an accountant reads before filing a period.
//
// The default range is the previous month rather than the current one, because
// this report is opened to check a period that is closing, not one still in
// progress.

frappe.query_reports["VAT Review Hold"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.month_start(), -1),
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

		// A held invoice with no country is the commonest hold there is —
		// `resolveTaxTreatment` returns REVIEW_HOLD precisely because the
		// country could not be resolved — so the blank is the finding, and a
		// blank cell reads as nothing at all.
		if (column.fieldname === "country" && !data?.country) {
			value = "<span style='color: var(--red-500);'>" + __("no country on the address") + "</span>";
		}

		return value;
	},
};
