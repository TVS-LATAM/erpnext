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

erpnext.checklist_grid.ANSWER_FIELDS = ["yes", "no", "na"];

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

// One stylesheet for every purely presentational rule this file owns.
// Injected from JS rather than erpnext.bundle.scss because every rule below
// only ever applies to grids this file has classed, so shipping them in the
// global bundle would put dead CSS on every page of the app.
erpnext.checklist_grid.injectStyles = function () {
	if (erpnext.checklist_grid._stylesInjected || typeof document === "undefined") return;
	erpnext.checklist_grid._stylesInjected = true;

	const style = document.createElement("style");
	style.textContent = `
		.tvs-checklist-grid-hide-row-selection .row-check,
		.tvs-checklist-grid-hide-row-selection .grid-row-check {
			display: none !important;
		}

		/* The stock grid is hidden, never removed: renderSheet only adds this
		   class after its table is in the DOM, so any failure to build the
		   sheet degrades to the ordinary Frappe grid instead of an empty
		   section with no way to answer anything. */
		.tvs-ckl-sheet-active .form-grid-container,
		.tvs-ckl-sheet-active .grid-footer,
		.tvs-ckl-sheet-active .grid-custom-buttons {
			display: none;
		}

		/* The sheet prints the table name in its own band cell, so the stock
		   label would be a duplicate. Clipped rather than display:none'd --
		   it is the accessible name of the region, and the band cell is a
		   <td>, not a heading.
		   Direct child of the classed element, NOT a descendant .grid-field:
		   the class lands on grid.wrapper, which IS .grid-field (grid.js:119),
		   so a nested-.grid-field selector would never match. */
		.tvs-ckl-sheet-active > .control-label {
			position: absolute;
			width: 1px;
			height: 1px;
			padding: 0;
			margin: -1px;
			overflow: hidden;
			clip: rect(0, 0, 0, 0);
			white-space: nowrap;
			border: 0;
		}

		.tvs-ckl-sheet-wrap {
			overflow-x: auto;
		}

		.tvs-ckl-sheet {
			width: 100%;
			border-collapse: collapse;
			background: var(--fg-color);
			font-size: var(--text-sm);
			color: var(--text-color);
		}

		.tvs-ckl-sheet th,
		.tvs-ckl-sheet td {
			border: 1px solid var(--table-border-color);
			padding: 5px 8px;
			vertical-align: middle;
		}

		.tvs-ckl-sheet thead th {
			background: var(--subtle-accent);
			color: var(--text-muted);
			font-size: var(--text-xs);
			font-weight: 600;
			letter-spacing: 0.05em;
			text-transform: uppercase;
			text-align: left;
			white-space: nowrap;
		}

		.tvs-ckl-sheet thead .tvs-ckl-h-idx,
		.tvs-ckl-sheet thead .tvs-ckl-h-ans {
			text-align: center;
		}

		/* A real rowspan-merged cell, which is what the Excel sheet does and
		   what the stock grid could not express at all. */
		.tvs-ckl-sheet .tvs-ckl-band {
			width: 28px;
			padding: 4px 0;
			background: var(--subtle-accent);
		}

		.tvs-ckl-sheet .tvs-ckl-band > span {
			display: block;
			margin: 0 auto;
			writing-mode: vertical-rl;
			transform: rotate(180deg);
			font-size: 9px;
			font-weight: 700;
			letter-spacing: 0.08em;
			text-transform: uppercase;
			color: var(--text-muted);
			white-space: nowrap;
		}

		.tvs-ckl-sheet .tvs-ckl-idx {
			width: 36px;
			text-align: center;
			font-size: var(--text-xs);
			color: var(--text-light);
		}

		.tvs-ckl-sheet .tvs-ckl-desc {
			line-height: 1.35;
		}

		.tvs-ckl-sheet .tvs-ckl-ans {
			width: 54px;
			text-align: center;
			cursor: pointer;
			user-select: none;
		}

		.tvs-ckl-sheet.tvs-ckl-readonly .tvs-ckl-ans {
			cursor: default;
		}

		.tvs-ckl-sheet .tvs-ckl-ans input {
			margin: 0;
			cursor: inherit;
			pointer-events: none;
		}

		.tvs-ckl-sheet tbody tr:hover > td {
			background: var(--highlight-color);
		}

		.tvs-ckl-sheet tbody tr:hover > .tvs-ckl-band {
			background: var(--subtle-accent);
		}

		.tvs-ckl-sheet .tvs-ckl-who {
			width: 170px;
			padding: 2px 4px;
		}

		.tvs-ckl-sheet .tvs-ckl-who-input {
			width: 100%;
			border: 0;
			background: transparent;
			color: var(--text-color);
			font-size: var(--text-sm);
			padding: 3px 4px;
		}

		.tvs-ckl-sheet .tvs-ckl-who-input:focus {
			outline: 0;
			background: var(--control-bg);
			box-shadow: inset 0 0 0 1px var(--border-color);
		}

		/* Collapsed, the whole note costs one row of height -- which is the
		   entire reason it collapses. A checklist stacks up to 4 of these
		   between its answer tables. */
		.tvs-ckl-note {
			border: 1px solid var(--table-border-color);
			border-top: 0;
			background: var(--fg-color);
		}

		.tvs-ckl-note-toggle {
			display: flex;
			align-items: center;
			gap: 6px;
			width: 100%;
			border: 0;
			background: transparent;
			padding: 5px 8px;
			font-size: var(--text-xs);
			font-weight: 600;
			letter-spacing: 0.05em;
			text-transform: uppercase;
			color: var(--text-muted);
			text-align: left;
			cursor: pointer;
		}

		.tvs-ckl-note-toggle:hover {
			background: var(--highlight-color);
		}

		.tvs-ckl-note-caret {
			display: inline-block;
			font-size: 9px;
			line-height: 1;
			transition: transform 0.12s ease;
		}

		.tvs-ckl-note.tvs-ckl-note-open .tvs-ckl-note-caret {
			transform: rotate(90deg);
		}

		/* A note written earlier is hidden behind a closed toggle, so the
		   toggle has to say that there is something under it -- otherwise the
		   collapse quietly buries data the mechanic typed. */
		.tvs-ckl-note-dot {
			width: 6px;
			height: 6px;
			border-radius: 50%;
			background: var(--text-light);
		}

		.tvs-ckl-note:not(.tvs-ckl-note-filled) .tvs-ckl-note-dot {
			visibility: hidden;
		}

		.tvs-ckl-note-body {
			padding: 0 8px 8px;
		}

		.tvs-ckl-note:not(.tvs-ckl-note-open) .tvs-ckl-note-body {
			display: none;
		}

		.tvs-ckl-note-input {
			display: block;
			width: 100%;
			min-height: 60px;
			resize: vertical;
			border: 1px solid var(--border-color);
			border-radius: var(--border-radius-sm);
			background: var(--control-bg);
			color: var(--text-color);
			font-size: var(--text-sm);
			line-height: 1.4;
			padding: 6px 8px;
		}

		.tvs-ckl-note-input:focus {
			outline: 0;
			box-shadow: inset 0 0 0 1px var(--primary);
		}
	`;
	document.head.appendChild(style);
};

erpnext.checklist_grid.hideRowSelectionCheckboxes = function (frm, df) {
	const grid = frm.fields_dict[df.fieldname] && frm.fields_dict[df.fieldname].grid;
	if (!grid || !grid.wrapper) return;

	erpnext.checklist_grid.injectStyles();
	grid.wrapper.addClass("tvs-checklist-grid-hide-row-selection");
};

// Column headings are read off the Checklist Item meta rather than written as
// literals here, so a Customize Form relabel (or a translation) cannot leave
// the sheet disagreeing with the doctype it renders.
erpnext.checklist_grid.sheetLabels = function () {
	const labels = {
		description: __("Description"),
		yes: __("Yes"),
		no: __("No"),
		na: __("N/A"),
		who_did_it: __("Who Did It"),
	};
	const meta = frappe.get_meta && frappe.get_meta("Checklist Item");
	((meta && meta.fields) || []).forEach((docfield) => {
		if (docfield.label && labels[docfield.fieldname] !== undefined) {
			labels[docfield.fieldname] = __(docfield.label);
		}
	});
	return labels;
};

// grid.wrapper IS the .grid-field element, not a container around it:
// grid.js:119 does `this.wrapper = $(template).appendTo(this.parent)` and that
// template's ROOT node is <div class="grid-field">. jQuery's find() searches
// DESCENDANTS ONLY, so `grid.wrapper.find(".grid-field")` matches nothing and
// silently returns an empty set -- which is exactly how the first cut of this
// sheet never rendered even once, degrading to the stock grid every time.
// hasClass first, find() second, so this holds whichever way a future Frappe
// version nests it.
erpnext.checklist_grid.gridFieldOf = function (grid) {
	return grid.wrapper.hasClass("grid-field") ? grid.wrapper : grid.wrapper.find(".grid-field");
};

// Locates a sheet row by child docname WITHOUT interpolating that name into a
// jQuery selector -- docnames are server-generated but they are still data,
// and `find('[data-x="' + name + '"]')` is a selector-injection waiting to
// happen the day one contains a quote or bracket.
erpnext.checklist_grid.findSheetRow = function (grid, cdn) {
	return grid.wrapper.find(".tvs-ckl-row").filter(function () {
		return this.getAttribute("data-ckl-cdn") === cdn;
	});
};

erpnext.checklist_grid.repaintSheetRow = function (frm, df, cdn) {
	const grid = frm.fields_dict[df.fieldname] && frm.fields_dict[df.fieldname].grid;
	if (!grid || !grid.wrapper) return;
	const row = frappe.get_doc("Checklist Item", cdn);
	const $tr = erpnext.checklist_grid.findSheetRow(grid, cdn);
	if (!row || !$tr.length) return;

	$tr.find(".tvs-ckl-ans").each(function () {
		const field = this.getAttribute("data-ckl-field");
		$(this)
			.find("input")
			.prop("checked", Boolean(row[field]));
	});

	// who_did_it is auto-filled by the tick cascade, but the mechanic may be
	// typing over it right now -- overwriting a focused input would eat the
	// keystroke that triggered this repaint.
	const $who = $tr.find(".tvs-ckl-who-input");
	if ($who.length && !$who.is(":focus")) $who.val(row.who_did_it || "");
};

// Replaces Frappe's editable grid with a purpose-built answer sheet.
//
// The stock grid cannot be made to answer in one click: grid_row.js:1029-1031
// calls toggle_editable_row() on the FIRST click of any cell, and only that
// call swaps the painted `static_area` for the real `field_area` control --
// so the checkbox literally does not exist yet when the first click lands.
// Answering costs two clicks per row (one to activate, one to tick), 8-14
// times per checklist. That is interaction, not styling, so no stylesheet
// over the grid could fix it.
//
// Persistence needs no grid involvement: save serialises frm.doc, and the
// tick path already mutates the child docs directly (see onTick above), so a
// hand-rolled table over the same child docs saves identically.
erpnext.checklist_grid.renderSheet = function (frm, df) {
	const grid = frm.fields_dict[df.fieldname] && frm.fields_dict[df.fieldname].grid;
	if (!grid || !grid.wrapper) return;
	const $gridField = erpnext.checklist_grid.gridFieldOf(grid);
	if (!$gridField.length) return;

	erpnext.checklist_grid.injectStyles();

	// Full rebuild rather than an in-place patch. At most 14 rows, and it
	// rules out a cell surviving with a stale answer after a save swaps the
	// child docs (and their docnames) underneath us. jQuery's remove() takes
	// the delegated handlers with it, so re-rendering cannot stack listeners.
	$gridField.find(".tvs-ckl-sheet-wrap").remove();

	const rows = frm.doc[df.fieldname] || [];
	if (!rows.length) {
		// A new doc before seedFromTemplate resolves. Fall back to the stock
		// grid rather than painting an empty sheet.
		grid.wrapper.removeClass("tvs-ckl-sheet-active");
		return;
	}

	const labels = erpnext.checklist_grid.sheetLabels();
	const editable = grid.is_editable();
	const band = df.label ? __(df.label) : "";

	const $wrap = $('<div class="tvs-ckl-sheet-wrap"></div>');
	const $table = $('<table class="tvs-ckl-sheet"></table>')
		.toggleClass("tvs-ckl-readonly", !editable)
		.appendTo($wrap);

	const $headRow = $("<tr></tr>").appendTo($("<thead></thead>").appendTo($table));
	if (band) $('<th class="tvs-ckl-h-band"></th>').appendTo($headRow);
	$('<th class="tvs-ckl-h-idx"></th>').appendTo($headRow);
	$('<th class="tvs-ckl-h-desc"></th>').text(labels.description).appendTo($headRow);
	erpnext.checklist_grid.ANSWER_FIELDS.forEach((field) => {
		$('<th class="tvs-ckl-h-ans"></th>').text(labels[field]).appendTo($headRow);
	});
	$('<th class="tvs-ckl-h-who"></th>').text(labels.who_did_it).appendTo($headRow);

	const $body = $("<tbody></tbody>").appendTo($table);
	rows.forEach((row, index) => {
		const description = row.description || "";
		const $tr = $('<tr class="tvs-ckl-row"></tr>')
			.attr("data-ckl-cdn", row.name)
			.appendTo($body);

		// The band is one rowspan-merged cell on the first row -- the actual
		// merged category cell from the Excel sheet, not a faked overlay.
		if (band && index === 0) {
			$('<td class="tvs-ckl-band"></td>')
				.attr("rowspan", rows.length)
				.append($("<span></span>").text(band))
				.appendTo($tr);
		}

		$('<td class="tvs-ckl-idx"></td>').text(index + 1).appendTo($tr);
		$('<td class="tvs-ckl-desc"></td>').text(description).appendTo($tr);

		erpnext.checklist_grid.ANSWER_FIELDS.forEach((field) => {
			const $cell = $('<td class="tvs-ckl-ans"></td>')
				.attr("data-ckl-field", field)
				.appendTo($tr);
			$('<input type="checkbox">')
				.prop("checked", Boolean(row[field]))
				.prop("disabled", !editable)
				// The three boxes are mutually exclusive per row (CIG-2) but
				// they are not a radio group: all three can be off, and a
				// radio cannot be unset by clicking it again.
				.attr("aria-label", `${labels[field]} — ${description}`)
				.appendTo($cell);
		});

		$('<td class="tvs-ckl-who"></td>')
			.append(
				$('<input type="text" class="tvs-ckl-who-input">')
					.val(row.who_did_it || "")
					.prop("disabled", !editable)
					.attr("aria-label", `${labels.who_did_it} — ${description}`)
			)
			.appendTo($tr);
	});

	if (editable) {
		// Delegated on the CELL, so the whole box column is a target instead
		// of the 13px checkbox itself -- these are answered on a workshop
		// tablet. The checkbox has pointer-events:none so a hit on the glyph
		// still resolves to this one handler.
		$table.on("click", ".tvs-ckl-ans", function (event) {
			// The checkbox is driven from the model, never from its own DOM
			// state: preventDefault stops the browser's native toggle so
			// there is exactly one path that decides what is checked. This
			// also keeps keyboard Space working -- browsers dispatch click
			// for it, and it lands here like any other activation.
			event.preventDefault();

			const cdn = this.closest("tr").getAttribute("data-ckl-cdn");
			const field = this.getAttribute("data-ckl-field");
			const row = cdn && frappe.get_doc("Checklist Item", cdn);
			if (!row || !field) return;

			// computeTickResult reads row[field] AFTER the flip
			// (checklist_pure.js:16-18). The stock grid gets that flip from
			// Frappe's own change trigger; the sheet has no control bound to
			// the field, so it performs the flip itself before delegating.
			row[field] = row[field] ? 0 : 1;
			// onTick only dirties the form when IT changed something, and on
			// a re-tick of an already-answered row the cascade is a no-op --
			// but the flip above is still a real edit.
			frm.dirty();
			erpnext.checklist_grid.onTick(frm, "Checklist Item", cdn, field);
			erpnext.checklist_grid.repaintSheetRow(frm, df, cdn);
		});

		$table.on("change", ".tvs-ckl-who-input", function () {
			const cdn = this.closest("tr").getAttribute("data-ckl-cdn");
			const row = cdn && frappe.get_doc("Checklist Item", cdn);
			if (!row) return;
			const value = this.value;
			if (row.who_did_it === value) return;
			row.who_did_it = value;
			frm.dirty();
		});
	}

	erpnext.checklist_grid.renderNote(frm, df, $wrap, editable);

	$gridField.append($wrap);
	grid.wrapper.addClass("tvs-ckl-sheet-active");
};

// Fieldtypes a section note may legitimately be stored in. Anything else
// carrying the derived name (a Check, a Link) is ignored rather than bound to a
// <textarea> that would write the wrong shape into the document.
erpnext.checklist_grid.NOTE_FIELDTYPES = ["Small Text", "Text", "Long Text", "Text Editor"];

// Resolves the parent-doc field holding this section's note, by the same
// reasoning the category band reads df.label rather than a lookup table: a
// doctype -> note-fieldname map here would be a second source of truth that
// drifts the first time a section is added or renamed in the JSON. The table's
// own fieldname already encodes it -- `before_dsg_items` pairs with
// `before_dsg_notes` -- and the derived name is checked against the doctype's
// meta, so a table with no sibling note renders no strip at all instead of
// binding to a field that does not exist.
erpnext.checklist_grid.noteFieldFor = function (frm, df) {
	const suffix = "_items";
	if (!df.fieldname || !df.fieldname.endsWith(suffix)) return null;
	const fieldname = df.fieldname.slice(0, -suffix.length) + "_notes";
	const matches = (frm.meta.fields || []).filter(
		(candidate) =>
			candidate.fieldname === fieldname &&
			erpnext.checklist_grid.NOTE_FIELDTYPES.indexOf(candidate.fieldtype) !== -1
	);
	return matches.length ? matches[0] : null;
};

// Appends this section's collapsible note strip to the sheet.
//
// Appended to $wrap, NOT to $gridField: renderSheet rebuilds by removing
// .tvs-ckl-sheet-wrap and building a fresh one, and every save fires a refresh.
// A strip outside the wrap would survive each removal and stack another
// textarea under the sheet, all of them bound to the same field.
//
// The note docfield is hidden:1 in the JSON precisely so this is the only
// control bound to it -- left visible, Frappe would paint its own standard
// textarea right below the table and the space the collapse exists to save
// would be spent anyway.
erpnext.checklist_grid.renderNote = function (frm, df, $wrap, editable) {
	const noteField = erpnext.checklist_grid.noteFieldFor(frm, df);
	if (!noteField) return;

	const value = frm.doc[noteField.fieldname] || "";
	// Collapsed is the default, because an empty note should cost one row of
	// height -- that is the whole point. But a note saved earlier must NOT
	// start hidden: it is text the mechanic wrote, and it would stay invisible
	// until someone happened to click the toggle.
	const expanded = Boolean(value);
	const bodyId = `tvs-ckl-note-${noteField.fieldname}`;
	const label = __(noteField.label || "Notes");
	const band = df.label ? __(df.label) : "";

	const $note = $('<div class="tvs-ckl-note"></div>')
		.toggleClass("tvs-ckl-note-open", expanded)
		.toggleClass("tvs-ckl-note-filled", Boolean(value))
		.appendTo($wrap);

	// type="button" is not decoration: a <button> with no type defaults to
	// type="submit", and this markup lives inside Frappe's form.
	const $toggle = $('<button type="button" class="tvs-ckl-note-toggle"></button>')
		.attr("aria-expanded", expanded ? "true" : "false")
		.attr("aria-controls", bodyId)
		.appendTo($note);
	$('<span class="tvs-ckl-note-caret" aria-hidden="true"></span>').text("▶").appendTo($toggle);
	$("<span></span>").text(label).appendTo($toggle);
	$('<span class="tvs-ckl-note-dot" aria-hidden="true"></span>').appendTo($toggle);

	const $body = $('<div class="tvs-ckl-note-body"></div>').attr("id", bodyId).appendTo($note);
	const $input = $('<textarea class="tvs-ckl-note-input"></textarea>')
		.val(value)
		.prop("disabled", !editable)
		.attr("aria-label", band ? `${label} — ${band}` : label)
		.appendTo($body);

	$toggle.on("click", function () {
		const open = !$note.hasClass("tvs-ckl-note-open");
		$note.toggleClass("tvs-ckl-note-open", open);
		$toggle.attr("aria-expanded", open ? "true" : "false");
		if (open && editable) $input.trigger("focus");
	});

	if (!editable) return;

	// "input" as well as "change": nothing else marks the form dirty for this
	// field (the docfield is hidden, so no Control is bound to it), and
	// "change" alone only fires on blur -- typing a note and hitting Ctrl+S
	// without leaving the textarea would save the document without it. Writing
	// straight to frm.doc is how the sheet already persists who_did_it; save
	// serialises frm.doc either way.
	$input.on("input change", function () {
		const next = this.value;
		if (frm.doc[noteField.fieldname] === next) return;
		frm.doc[noteField.fieldname] = next;
		$note.toggleClass("tvs-ckl-note-filled", Boolean(next));
		frm.dirty();
	});
};

erpnext.checklist_grid.renderSheets = function (frm) {
	erpnext.checklist_grid.checklistItemTables(frm).forEach((df) => {
		erpnext.checklist_grid.renderSheet(frm, df);
	});
};

// cannot_add_rows/cannot_delete_rows are runtime-only grid properties, not
// JSON docfield keys (absent from docfield.json; grid.js reads them off
// grid.df at render time) -- they can only be set from client JS.
// onload_post_render is the only hook proven to run before the user can
// interact with a freshly rendered grid; the grid itself paints earlier
// (form.js render_form(): refresh_fields() before onload_post_render), but
// set_df_property's != guard makes it self-correct via refresh_field either
// way. Precedent: frappe/custom/doctype/doctype_layout/doctype_layout.js:9-10.
//
// These still matter with the sheet in front: the stock grid stays in the DOM
// as the degraded path, and static_rows is what grid.is_editable() reads.
erpnext.checklist_grid.lockFixedRows = function (frm) {
	erpnext.checklist_grid.checklistItemTables(frm).forEach((df) => {
		frm.set_df_property(df.fieldname, "cannot_add_rows", true);
		frm.set_df_property(df.fieldname, "cannot_delete_rows", true);
		erpnext.checklist_grid.hideRowSelectionCheckboxes(frm, df);
		erpnext.checklist_grid.renderSheet(frm, df);
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
			// The seed resolves after onload_post_render has already run and
			// found every table empty, so the sheet has to be built again
			// here or a new checklist shows the fallback grid until reload.
			erpnext.checklist_grid.renderSheets(frm);
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
			// Saving replaces every child doc (and its docname), so the
			// sheet's data-ckl-cdn handles would point at docs that no
			// longer exist. renderSheet rebuilds from frm.doc, and it
			// no-ops harmlessly on the refresh passes that fire before the
			// grid wrapper exists.
			refresh: erpnext.checklist_grid.renderSheets,
		});
	});
}
