// Worksheet skin for the 4 project checklists.
//
// The forms already carry the right DATA -- what makes them read as a web app
// instead of the paper worksheet they replace is Frappe's default form
// chrome: every section is its own floating card, and every field is a tall
// stack of (small grey label) over (wide filled input) with generous vertical
// rhythm. On paper the same information is one bordered sheet: a title band, a
// grid of labelled boxes, and the answer table flush against them.
//
// This file changes no data and no behaviour -- it is presentation only. It
// restyles the existing controls in place rather than rebuilding the form from
// HTML, so every Frappe control keeps working (validation, fetch_from,
// permissions, translations) and a field added to a checklist JSON later is
// skinned automatically with no change here.
//
// Scope: every rule below is prefixed with `.tvs-worksheet`, a class this file
// puts on the checklist form's page wrapper only. The classes it targets
// (.form-section, .frappe-control, .section-head) exist on EVERY form in the
// app, so an unscoped rule would repaint Sales Invoice and the rest.
// Precedent for classing frm.page.wrapper rather than document.body:
// project.js's hideProjectToolbarButtons -- Frappe swaps pages without
// reloading, so a body class would outlive the form it was meant for.
frappe.provide("erpnext.checklist_worksheet");

erpnext.checklist_worksheet.DOCTYPES = [
	"Arrival Checklist",
	"Job Checklist",
	"Quality Control Checklist",
	"DSG Oil Change Checklist",
];

erpnext.checklist_worksheet.SCOPE = "tvs-worksheet";

// Fieldtypes rendered as a two-column sheet row (label cell | value cell).
// An explicit allow-list rather than "everything except X": controls with
// their own internal layout (tables, text areas, attachments) break when
// squeezed into a fixed-width label column, and an exotic fieldtype added
// later should degrade to the stock stacked layout rather than collapse.
//
// The classification is applied from JS as a marker class instead of being
// spelled out as a dozen [data-fieldtype="..."] selectors in the stylesheet:
// one CSS rule stays readable, and the list above stays the single source of
// truth for which controls are rows.
erpnext.checklist_worksheet.ROW_FIELDTYPES = [
	"Data",
	"Link",
	"Select",
	"Date",
	"Datetime",
	"Time",
	"Int",
	"Float",
	"Currency",
	"Percent",
	"Read Only",
];

// Multi-line controls: the label becomes a band above a full-width box, the
// way a "Notes" block is printed on the paper form.
erpnext.checklist_worksheet.BLOCK_FIELDTYPES = ["Text", "Small Text", "Long Text", "Text Editor"];

erpnext.checklist_worksheet.injectStyles = function () {
	if (erpnext.checklist_worksheet._injected || typeof document === "undefined") return;
	erpnext.checklist_worksheet._injected = true;

	const style = document.createElement("style");
	style.textContent = `
		.tvs-worksheet .layout-main-section-wrapper {
			max-width: 1100px;
		}

		.tvs-worksheet .form-page {
			background: var(--fg-color);
			border: 1px solid var(--table-border-color);
			border-radius: 6px;
			overflow: hidden;
			padding: 0;
		}

		.tvs-worksheet .form-section,
		.tvs-worksheet .form-section.card-section {
			margin: 0;
			padding: 0;
			border: 0;
			border-radius: 0;
			box-shadow: none;
			background: transparent;
		}

		.tvs-worksheet .form-section + .form-section {
			border-top: 1px solid var(--table-border-color);
		}

		.tvs-worksheet .section-head {
			margin: 0;
			padding: 7px 12px;
			background: var(--subtle-accent);
			border-bottom: 1px solid var(--table-border-color);
			font-size: var(--text-xs);
			font-weight: 700;
			letter-spacing: 0.08em;
			text-transform: uppercase;
			color: var(--text-muted);
		}

		.tvs-worksheet .section-body {
			padding: 0;
		}

		.tvs-worksheet .form-column {
			padding: 0;
		}

		.tvs-worksheet .form-column + .form-column {
			border-left: 1px solid var(--table-border-color);
		}

		.tvs-worksheet .frappe-control {
			margin: 0;
		}

		.tvs-worksheet .frappe-control + .frappe-control {
			border-top: 1px solid var(--table-border-color);
		}

		.tvs-worksheet .frappe-control .form-group {
			margin: 0;
		}

		.tvs-worksheet .tvs-ws-row .form-group {
			display: flex;
			align-items: stretch;
			min-height: 34px;
		}

		.tvs-worksheet .tvs-ws-row .form-group > .clearfix {
			flex: 0 0 220px;
			display: flex;
			align-items: center;
			padding: 4px 12px;
			background: var(--subtle-accent);
			border-right: 1px solid var(--table-border-color);
		}

		.tvs-worksheet .tvs-ws-row .control-input-wrapper {
			flex: 1 1 auto;
			min-width: 0;
			display: flex;
			flex-direction: column;
			justify-content: center;
		}

		.tvs-worksheet .control-label {
			margin: 0;
			font-size: var(--text-sm);
			font-weight: 500;
			color: var(--text-muted);
		}

		.tvs-worksheet .control-input,
		.tvs-worksheet .control-value {
			width: 100%;
		}

		.tvs-worksheet .control-input .form-control,
		.tvs-worksheet .control-value.like-disabled-input {
			background: transparent;
			border: 0;
			border-radius: 0;
			box-shadow: none;
			padding: 6px 12px;
			height: auto;
			min-height: 0;
		}

		.tvs-worksheet .control-input .form-control:focus {
			background: var(--control-bg);
			box-shadow: inset 0 0 0 1px var(--border-color);
		}

		.tvs-worksheet .help-box {
			margin: 0 0 4px;
			padding: 0 12px;
		}

		.tvs-worksheet .tvs-ws-block .form-group > .clearfix {
			padding: 6px 12px;
			background: var(--subtle-accent);
			border-bottom: 1px solid var(--table-border-color);
		}

		.tvs-worksheet .tvs-ws-block textarea,
		.tvs-worksheet .tvs-ws-block .ql-container {
			background: transparent;
			border: 0;
			border-radius: 0;
			box-shadow: none;
			min-height: 120px;
			padding: 8px 12px;
			resize: vertical;
		}

		.tvs-worksheet .tvs-ckl-sheet-wrap {
			margin: 0;
		}

		.tvs-worksheet .tvs-ckl-sheet {
			border-collapse: collapse;
		}

		.tvs-worksheet .tvs-ckl-sheet tr > *:first-child {
			border-left: 0;
		}

		.tvs-worksheet .tvs-ckl-sheet tr > *:last-child {
			border-right: 0;
		}

		.tvs-worksheet .tvs-ckl-sheet thead th {
			border-top: 0;
		}

		.tvs-worksheet .ckl-uploader {
			margin: 0;
			padding: 12px;
		}

		.tvs-worksheet .ckl-uploader-attachments {
			margin: 0;
			border-top: 1px solid var(--table-border-color);
			padding-top: 12px;
		}

		.tvs-worksheet .tvs-ws-head {
			display: flex;
			align-items: baseline;
			justify-content: space-between;
			gap: 12px;
			flex-wrap: wrap;
			padding: 10px 12px;
			background: var(--fg-color);
			border-bottom: 2px solid var(--text-color);
		}

		.tvs-worksheet .tvs-ws-title {
			font-size: var(--text-md);
			font-weight: 700;
			letter-spacing: 0.06em;
			text-transform: uppercase;
			color: var(--text-color);
		}

		.tvs-worksheet .tvs-ws-meta {
			font-size: var(--text-xs);
			color: var(--text-muted);
		}

		@media (max-width: 767px) {
			.tvs-worksheet .tvs-ws-row .form-group {
				display: block;
			}

			.tvs-worksheet .tvs-ws-row .form-group > .clearfix {
				border-right: 0;
				border-bottom: 1px solid var(--table-border-color);
			}
		}

		@media print {
			.tvs-worksheet .form-page,
			.tvs-worksheet .section-head,
			.tvs-worksheet .tvs-ws-head,
			.tvs-worksheet .tvs-ws-row .form-group > .clearfix,
			.tvs-worksheet .tvs-ckl-sheet th,
			.tvs-worksheet .tvs-ckl-sheet td {
				-webkit-print-color-adjust: exact;
				print-color-adjust: exact;
				border-color: #333;
			}

			.tvs-worksheet .frappe-control + .frappe-control,
			.tvs-worksheet .form-section + .form-section {
				border-top-color: #333;
			}
		}
	`;
	document.head.appendChild(style);
};

// Marks each control as a sheet row or a block, driven by ROW_FIELDTYPES /
// BLOCK_FIELDTYPES. Runs on refresh: Frappe reuses control wrappers across
// refreshes, so addClass is idempotent, and a control rendered later (a
// depends_on field becoming visible) is picked up on the next refresh.
erpnext.checklist_worksheet.classifyControls = function (frm) {
	Object.values(frm.fields_dict || {}).forEach((field) => {
		if (!field || !field.$wrapper || !field.df) return;
		if (erpnext.checklist_worksheet.ROW_FIELDTYPES.includes(field.df.fieldtype)) {
			field.$wrapper.addClass("tvs-ws-row");
		} else if (erpnext.checklist_worksheet.BLOCK_FIELDTYPES.includes(field.df.fieldtype)) {
			field.$wrapper.addClass("tvs-ws-block");
		}
	});
};

// A paper worksheet opens with a title block, not with the first field. The
// Frappe form has no such band, so one is inserted at the top of the form
// page -- built with .text() rather than string interpolation, since the
// docname and the checked_by user are data.
erpnext.checklist_worksheet.renderHeader = function (frm) {
	const $page = frm.$wrapper.find(".form-page").first();
	if (!$page.length) return;

	$page.find(".tvs-ws-head").remove();

	const parts = [];
	if (!frm.is_new()) parts.push(frm.doc.name);
	if (frm.doc.check_date) parts.push(frappe.datetime.str_to_user(frm.doc.check_date));
	if (frm.doc.checked_by) parts.push(frm.doc.checked_by);

	const $head = $('<div class="tvs-ws-head"></div>');
	$('<div class="tvs-ws-title"></div>').text(__(frm.doctype)).appendTo($head);
	$('<div class="tvs-ws-meta"></div>').text(parts.join("  ·  ")).appendTo($head);

	$page.prepend($head);
};

erpnext.checklist_worksheet.apply = function (frm) {
	erpnext.checklist_worksheet.injectStyles();
	frm.page.wrapper.addClass(erpnext.checklist_worksheet.SCOPE);
	erpnext.checklist_worksheet.classifyControls(frm);
	erpnext.checklist_worksheet.renderHeader(frm);
};

// Wired to 4 parent doctypes; ScriptManager evaluates a doctype's __js once
// per form load, so an unguarded registration would stack one refresh handler
// per checklist opened in the same browser session.
if (!erpnext.checklist_worksheet._registered) {
	erpnext.checklist_worksheet._registered = true;
	erpnext.checklist_worksheet.DOCTYPES.forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			refresh: erpnext.checklist_worksheet.apply,
		});
	});
}
