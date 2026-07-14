// Adapter for the checklist answer grid: wires DOM/frm/frappe.* around the
// pure state transitions in checklist_pure.js. Loaded via the `doctype_js`
// hook for the 4 checklist doctypes (checklist_pure.js MUST load first in
// that list -- this file calls erpnext.checklist_pure.*).
frappe.provide("erpnext.checklist_grid");

erpnext.checklist_grid.CHECKLIST_DOCTYPES = [
	"Arrival Checklist",
	"Job Checklist",
	"Quality Control Checklist",
	"DSG Oil Change Checklist",
];

// Child-table field handlers fire as (frm, cdt, cdn) with row[field] already
// updated in the model (frappe.model.set_value assigns synchronously before
// queuing triggers -- model.js -- so there is no read-your-own-write race).
//
// The sibling fields (and who_did_it) are applied via DIRECT MUTATION of the
// row object instead of frappe.model.set_value. Routing them back through
// set_value would re-fire that field's own change trigger, because set_value
// only skips the trigger when the value is UNCHANGED (model.js:557-565) --
// clearing a sibling from 1 to 0 IS a change. The per-form wildcard listener
// registered on every "Checklist Item" table field (form.js:307-321) would
// then re-invoke onTick for that sibling; the re-entrant call cannot tell
// "the user unticked this box" apart from "this box was just zeroed as a
// side effect of answering a different box", so computeTickResult's untick
// branch would wipe the answer just set (all 6 answer-switch transitions
// converge to all-zero -- see engram sdd/checklist-checkbox-grid/
// tick-cascade-correction). Direct mutation never re-enters the trigger
// system, so no reentrancy guard is needed either.
//
// Constraints this bypass gives up (accepted trade-off, cascade safety wins):
// - Any frappe.ui.form.on("Checklist Item", ...) handler registered by a
//   future Customize Form Client Script or another app fires only for the
//   field the user physically ticked -- NOT for the automatic sibling
//   clears or the who_did_it auto-fill, since those never go through
//   set_value/trigger.
// - frm.undo_manager only records changes made through a Control's own
//   set_value (base_control.js:220), so it only sees the ticked field.
//   Ctrl+Z on a sibling-clearing tick pops just that field and does NOT
//   restore the previous answer -- the row lands fully unanswered instead
//   (verified empirically; a reentrancy-guard + set_value alternative does
//   not fix this either -- see engram sdd/checklist-checkbox-grid/
//   tick-cascade-correction).
erpnext.checklist_grid.onTick = function (frm, cdt, cdn, field) {
	const row = frappe.get_doc(cdt, cdn);
	const result = erpnext.checklist_pure.computeTickResult(row, field, frappe.session.user);
	let changed = false;
	["yes", "no", "na", "who_did_it"].forEach((key) => {
		if (row[key] !== result[key]) {
			row[key] = result[key];
			changed = true;
		}
	});
	if (changed) {
		frm.dirty();
		// Row-scoped redraw only -- frm.refresh_field(row.parentfield) would
		// call Grid.refresh(), which rebuilds EVERY row's DOM via
		// grid_row.refresh() (frappe/public/js/frappe/form/grid.js:405-467,
		// grid_row.js:197-323). On a 14-row section that resets any
		// in-progress edit (e.g. who_did_it being typed on a different row)
		// the instant any checkbox in the table is ticked. grid.refresh_row
		// (grid.js:578-579) only rebuilds the touched row.
		frm.fields_dict[row.parentfield].grid.refresh_row(cdn);
	}
};

// Reads the doctype's own meta rather than a hardcoded fieldname list, so
// this self-populates once slices 5/6 convert a doctype's JSON (Table fields
// with options "Checklist Item" simply start appearing in frm.meta.fields)
// without this file needing to change.
erpnext.checklist_grid.checklistItemTables = function (frm) {
	return (frm.meta.fields || []).filter((df) => df.fieldtype === "Table" && df.options === "Checklist Item");
};

// cannot_add_rows/cannot_delete_rows are runtime-only grid properties, not
// JSON docfield keys (absent from docfield.json; grid.js reads them off
// grid.df at render time) -- they can only be set from client JS.
// onload_post_render is the only hook proven to run before the user can
// interact with a freshly rendered grid; the grid itself paints earlier
// (form.js render_form(): refresh_fields() before onload_post_render), but
// set_df_property's != guard makes it self-correct via refresh_field either
// way. Precedent: frappe/custom/doctype/doctype_layout/doctype_layout.js:9-10.
erpnext.checklist_grid.lockFixedRows = function (frm) {
	erpnext.checklist_grid.checklistItemTables(frm).forEach((df) => {
		frm.set_df_property(df.fieldname, "cannot_add_rows", true);
		frm.set_df_property(df.fieldname, "cannot_delete_rows", true);
	});
};

// New documents are built entirely client-side by
// frappe.model.get_new_doc -- before_insert never sees them until the first
// save, so a new checklist needs its own client-side seed or the mechanic
// sees an empty grid with no way to add rows. Idempotent per table (a table
// that already has rows, e.g. from a prior failed save, is left alone).
erpnext.checklist_grid.seedFromTemplate = function (frm) {
	if (!frm.is_new()) return;
	const tables = erpnext.checklist_grid.checklistItemTables(frm);
	if (!tables.length) return;
	if (tables.every((df) => (frm.doc[df.fieldname] || []).length)) return;

	frappe.call({
		method: "erpnext.projects.checklist_templates.get_template",
		args: { doctype: frm.doc.doctype },
	})
		.then((r) => {
			const template = r.message || {};
			Object.keys(template).forEach((fieldname) => {
				if ((frm.doc[fieldname] || []).length) return; // idempotent per table
				(template[fieldname] || []).forEach((row) => {
					const child = frm.add_child(fieldname);
					child.description = row.description;
				});
				frm.refresh_field(fieldname);
			});
		})
		.catch((e) => {
			// before_insert still seeds on save (backstop), so no data is
			// lost -- but the mechanic must be told why the grid is empty.
			frappe.show_alert({
				message: __("Could not load the checklist template. Reload the page."),
				indicator: "red",
			});
			console.error(e);
		});
};

// This file is wired to 4 parent doctypes via doctype_js; ScriptManager
// concatenates and evaluates a doctype's __js once per form load, so the
// top-level registration below can run up to 4x within one browser session
// (e.g. opening Arrival then Job in the same session). Without a guard,
// frappe.ui.form.handlers would end up with duplicate entries and every tick
// would fire its handler multiple times. Precedent: checklist_attachments.js:151-158.
if (!erpnext.checklist_grid._registered) {
	erpnext.checklist_grid._registered = true;

	// Registered on the child doctype so it is written once and serves all
	// 9 Checklist Item tables across the 4 parent doctypes.
	frappe.ui.form.on("Checklist Item", {
		yes(frm, cdt, cdn) {
			erpnext.checklist_grid.onTick(frm, cdt, cdn, "yes");
		},
		no(frm, cdt, cdn) {
			erpnext.checklist_grid.onTick(frm, cdt, cdn, "no");
		},
		na(frm, cdt, cdn) {
			erpnext.checklist_grid.onTick(frm, cdt, cdn, "na");
		},
	});

	erpnext.checklist_grid.CHECKLIST_DOCTYPES.forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			onload: erpnext.checklist_grid.seedFromTemplate,
			onload_post_render: erpnext.checklist_grid.lockFixedRows,
		});
	});
}
