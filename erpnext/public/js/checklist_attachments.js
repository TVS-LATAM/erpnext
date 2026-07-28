// Mechanic-friendly attachment UI for the project checklists. Replaces the
// default child-table grids for `photos` and `attachments` with a single
// upload button (multi-select, drag-drop on desktop, camera on mobile) plus a
// thumbnail gallery. The child tables remain the data store; this only changes
// how rows are added/removed. Wired to each checklist via the doctype_js hook.

frappe.provide("erpnext.checklists");

erpnext.checklists.DOCTYPES = [
	"Arrival Checklist",
	"Job Checklist",
	"Quality Control Checklist",
	"DSG Oil Change Checklist",
];

// Callbacks run at the end of every setup() pass, i.e. after the galleries
// have been repainted -- on form refresh, and again after every upload and
// every delete. checklist_vehicle_diagram.js hooks this to keep its per-zone
// counters in step with the photo table without this file having to know the
// diagram exists.
erpnext.checklists.afterRender = erpnext.checklists.afterRender || [];

// One entry per managed child table.
erpnext.checklists.TABLES = [
	{
		fieldname: "photos",
		urlField: "image",
		buttonLabel: __("Upload photos"),
		icon: "📷",
		imagesOnly: true,
		// Photos carry a vehicle zone (Checklist Photo.zone) assigned by the
		// diagram, so the gallery groups by it. File attachments do not.
		zoned: true,
	},
	{
		fieldname: "attachments",
		urlField: "file",
		buttonLabel: __("Attach files"),
		icon: "📎",
		imagesOnly: false,
		// No way in: the workshop decided nothing is attached at the
		// checklist level any more -- everything a mechanic documents goes
		// through the vehicle diagram, which writes to `photos`.
		//
		// The rows are NOT dropped with the button. Checklists already in
		// production carry attachments, and a stored file behind a UI that
		// stopped rendering it is silent data loss: it stays in the table,
		// taking up storage, with no way to open or remove it. So the
		// gallery still paints existing rows, delete control and all. Once
		// the last one is cleared the whole control collapses on its own
		// (see `blank` in renderTable) and never comes back.
		noUploads: true,
	},
];

erpnext.checklists.injectStyle = function () {
	if (document.getElementById("ckl-uploader-style")) return;
	const style = document.createElement("style");
	style.id = "ckl-uploader-style";
	style.textContent = `
		.ckl-uploader { margin-top: 10px; }
		.ckl-uploader-attachments { margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--border-color, #ebeef0); }
		.ckl-upload-btn { margin-bottom: 10px; }
		.ckl-gallery { display: flex; flex-wrap: wrap; gap: 10px; }
		.ckl-gallery.ckl-grouped { display: block; }
		.ckl-tile { position: relative; width: 90px; height: 90px; border: 1px solid var(--border-color, #d1d8dd); border-radius: 6px; overflow: hidden; background: var(--control-bg, #f4f5f6); cursor: pointer; display: flex; align-items: center; justify-content: center; }
		.ckl-tile img { width: 100%; height: 100%; object-fit: cover; }
		.ckl-tile.ckl-file { padding: 6px; }
		.ckl-file-name { font-size: 11px; line-height: 1.2; word-break: break-word; text-align: center; color: var(--text-color, #1f272e); }
		.ckl-del { position: absolute; top: 2px; right: 4px; width: 18px; height: 18px; border-radius: 50%; background: rgba(0,0,0,0.6); color: #fff; font-size: 14px; line-height: 16px; text-align: center; cursor: pointer; }
		.ckl-del:hover { background: #e24c4c; }
		.ckl-empty { font-size: 12px; padding: 6px 0; }
		.ckl-blank { display: none; }
		.ckl-group { margin-bottom: 12px; }
		.ckl-group-head { display: flex; align-items: baseline; gap: 6px; font-size: 11px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--text-muted, #6b7280); margin-bottom: 6px; }
		.ckl-group-count { font-weight: 500; letter-spacing: 0; text-transform: none; }
		.ckl-zone-tag { position: absolute; left: 0; right: 0; bottom: 0; padding: 2px 4px; font-size: 9px; line-height: 1.2; text-align: center; color: #fff; background: rgba(0,0,0,0.55); }
		.ckl-private-locked .config-area label:last-child { display: none !important; }
	`;
	document.head.appendChild(style);
};

erpnext.checklists.setup = function (frm) {
	erpnext.checklists.injectStyle();
	erpnext.checklists.TABLES.forEach((cfg) => erpnext.checklists.renderTable(frm, cfg));
	// A subscriber that throws must not take the galleries down with it --
	// they are already painted by this point, and the uploader must keep
	// working even if an add-on above it (the vehicle diagram) fails.
	erpnext.checklists.afterRender.forEach((callback) => {
		try {
			callback(frm);
		} catch (error) {
			console.error("checklist afterRender subscriber failed", error);
		}
	});
};

erpnext.checklists.renderTable = function (frm, cfg) {
	const field = frm.fields_dict[cfg.fieldname];
	if (!field) return;

	// A zoned table has the vehicle diagram sitting in front of it, and the
	// diagram IS the button -- every panel is a target, and it carries its
	// own "General" target for shots that belong to no panel. A second plain
	// button beside it would upload with no zone, which is the unsorted pile
	// the diagram exists to replace, and two buttons for one table is how a
	// mechanic ends up not knowing where a photo went. `noUploads` tables
	// have no entry point at all by decision (see TABLES).
	const showUploadButton = !cfg.zoned && !cfg.noUploads;

	// A control with no button and no rows would render as an empty bordered
	// strip, which on a worksheet reads as a broken row rather than as
	// absence. Collapse the whole field instead.
	//
	// `!cfg.zoned` is load-bearing, not belt-and-braces: a zoned table has no
	// button and starts with no rows, so without it EVERY fresh checklist
	// would collapse the photos control -- and the vehicle diagram lives
	// inside that control, so the entire feature would vanish on exactly the
	// forms that need it most. A zoned table is never blank; the diagram is
	// its content.
	//
	// Driven by a class rather than .hide(): setup() re-runs on every refresh
	// and after every upload and delete, so this has to be recomputed each
	// pass, not latched.
	const hasRows = (frm.doc[cfg.fieldname] || []).some((row) => row[cfg.urlField]);
	const blank = !showUploadButton && !hasRows && !cfg.zoned;
	field.$wrapper.toggleClass("ckl-blank", blank);

	// Build the custom UI once, then keep reusing it.
	let $ui = field.$wrapper.find(".ckl-uploader");
	if (!$ui.length) {
		$ui = $(`<div class="ckl-uploader ckl-uploader-${cfg.fieldname}"><div class="ckl-gallery"></div></div>`).appendTo(
			field.$wrapper
		);
		if (showUploadButton) {
			$(
				`<button class="btn btn-primary btn-sm ckl-upload-btn" type="button">
					${cfg.icon} ${frappe.utils.escape_html(cfg.buttonLabel)}
				</button>`
			)
				.on("click", () => erpnext.checklists.openUploader(frm, cfg))
				.prependTo($ui);
		}
	}

	// The stock child-table grid is hidden only once the replacement is in
	// the DOM, and it is hidden, never removed. Same degraded path the answer
	// sheet uses (checklist_grid.js): if building the uploader ever throws,
	// the section falls back to an ordinary Frappe grid instead of leaving no
	// way at all to attach a file -- which matters more now that the photos
	// table has no button of its own and depends entirely on this container.
	if (field.grid && field.grid.wrapper) {
		$(field.grid.wrapper).hide();
	}

	// Disable upload button while the doc is read-only (submitted / no write).
	$ui.find(".ckl-upload-btn").prop("disabled", frm.doc.docstatus > 0 || frm.read_only);

	erpnext.checklists.renderGallery(frm, cfg, $ui.find(".ckl-gallery"));
};

// `zone` is optional: it is set when the upload was started by clicking a part
// of the vehicle diagram, and left undefined for the plain upload button (a
// general shot of the whole car, which is a supported case -- Checklist
// Photo.zone is deliberately not mandatory).
erpnext.checklists.openUploader = function (frm, cfg, zone) {
	const zoneLabel = zone ? erpnext.checklist_zones.label(zone) : null;

	const uploader = new frappe.ui.FileUploader({
		doctype: frm.doc.doctype,
		docname: frm.doc.name,
		allow_multiple: true,
		dialog_title: zoneLabel ? `${cfg.buttonLabel} — ${zoneLabel}` : cfg.buttonLabel,
		// Default every upload to private; the server (ChecklistFile) enforces it.
		make_attachments_public: 0,
		restrictions: cfg.imagesOnly ? { allowed_file_types: ["image/*"] } : {},
		on_success: (file_doc) => {
			if (!file_doc || !file_doc.file_url) return;
			const row = frm.add_child(cfg.fieldname);
			row[cfg.urlField] = file_doc.file_url;
			if (zone) row.zone = zone;
			frm.refresh_field(cfg.fieldname);
			erpnext.checklists.setup(frm);
			frm.dirty();
		},
	});

	// Privacy cannot be changed from the UI: hide the per-file "Private" toggle
	// (via the ckl-private-locked style) and the dialog's "Set all public" button.
	if (uploader && uploader.dialog) {
		uploader.dialog.$wrapper.addClass("ckl-private-locked");
		const $secondary = uploader.dialog.get_secondary_btn && uploader.dialog.get_secondary_btn();
		if ($secondary) $secondary.hide();
	}
};

erpnext.checklists.renderTile = function (frm, cfg, row) {
	const url = row[cfg.urlField];
	const safeUrl = frappe.utils.escape_html(url);
	const $tile = cfg.imagesOnly
		? $(`<div class="ckl-tile"><img src="${safeUrl}" loading="lazy"></div>`)
		: $(`<div class="ckl-tile ckl-file"><span class="ckl-file-name">${frappe.utils.escape_html(url.split("/").pop())}</span></div>`);

	$tile.on("click", () => window.open(url, "_blank", "noopener"));

	const $del = $(`<span class="ckl-del" title="${__("Remove")}">&times;</span>`).on("click", (event) => {
		event.stopPropagation();
		frm.doc[cfg.fieldname] = (frm.doc[cfg.fieldname] || []).filter((r) => r.name !== row.name);
		frm.refresh_field(cfg.fieldname);
		erpnext.checklists.setup(frm);
		frm.dirty();
	});
	$tile.append($del);

	return $tile;
};

// Groups zoned rows under a heading per vehicle part, in checklist_zones.js's
// declaration order (the order the parts are drawn), with unzoned rows
// ("General") last. Reading that order rather than sorting alphabetically
// keeps the gallery and the picture telling the same story -- and
// alphabetical order is a different order in every UI language.
erpnext.checklists.groupByZone = function (rows) {
	const groups = new Map();
	const push = (zone, row) => {
		if (!groups.has(zone)) groups.set(zone, []);
		groups.get(zone).push(row);
	};

	const known = erpnext.checklist_zones.ORDER;
	known.forEach((zone) => {
		const matches = rows.filter((row) => row.zone === zone);
		if (matches.length) matches.forEach((row) => push(zone, row));
	});
	// Anything whose zone is not (or no longer) on the diagram still has to
	// appear, or deleting a shape from VIEWS would make existing photos
	// invisible in the UI while they sit in the table.
	rows.filter((row) => !known.includes(row.zone)).forEach((row) => push(row.zone || "", row));

	return groups;
};

erpnext.checklists.renderGallery = function (frm, cfg, $gallery) {
	const rows = frm.doc[cfg.fieldname] || [];
	$gallery.empty().toggleClass("ckl-grouped", Boolean(cfg.zoned));

	// No empty-state text. On a worksheet an "(empty)" line reads as broken
	// layout, and it says nothing the surrounding UI has not already said:
	// an unzoned table still shows its button, and a zoned one shows a
	// diagram with every panel grey and no counters.
	const withUrl = rows.filter((row) => row[cfg.urlField]);
	if (!withUrl.length) return;

	if (!cfg.zoned) {
		withUrl.forEach((row) => $gallery.append(erpnext.checklists.renderTile(frm, cfg, row)));
		return;
	}

	erpnext.checklists.groupByZone(withUrl).forEach((groupRows, zone) => {
		const label = erpnext.checklist_zones.label(zone);
		const $group = $('<div class="ckl-group"></div>').appendTo($gallery);
		const $head = $('<div class="ckl-group-head"></div>').appendTo($group);
		$("<span></span>").text(label).appendTo($head);
		$('<span class="ckl-group-count"></span>').text(`(${groupRows.length})`).appendTo($head);

		const $tiles = $('<div class="ckl-gallery"></div>').appendTo($group);
		groupRows.forEach((row) => $tiles.append(erpnext.checklists.renderTile(frm, cfg, row)));
	});
};

// Register the refresh handler for each checklist exactly once (the shared file
// can be loaded on multiple checklist forms within one session).
if (!erpnext.checklists._registered) {
	erpnext.checklists._registered = true;
	erpnext.checklists.DOCTYPES.forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			refresh: erpnext.checklists.setup,
		});
	});
}
