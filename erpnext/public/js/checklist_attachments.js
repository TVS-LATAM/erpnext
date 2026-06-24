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

// One entry per managed child table.
erpnext.checklists.TABLES = [
	{
		fieldname: "photos",
		urlField: "image",
		buttonLabel: __("Upload photos"),
		icon: "📷",
		imagesOnly: true,
	},
	{
		fieldname: "attachments",
		urlField: "file",
		buttonLabel: __("Attach files"),
		icon: "📎",
		imagesOnly: false,
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
		.ckl-tile { position: relative; width: 90px; height: 90px; border: 1px solid var(--border-color, #d1d8dd); border-radius: 6px; overflow: hidden; background: var(--control-bg, #f4f5f6); cursor: pointer; display: flex; align-items: center; justify-content: center; }
		.ckl-tile img { width: 100%; height: 100%; object-fit: cover; }
		.ckl-tile.ckl-file { padding: 6px; }
		.ckl-file-name { font-size: 11px; line-height: 1.2; word-break: break-word; text-align: center; color: var(--text-color, #1f272e); }
		.ckl-del { position: absolute; top: 2px; right: 4px; width: 18px; height: 18px; border-radius: 50%; background: rgba(0,0,0,0.6); color: #fff; font-size: 14px; line-height: 16px; text-align: center; cursor: pointer; }
		.ckl-del:hover { background: #e24c4c; }
		.ckl-empty { font-size: 12px; padding: 6px 0; }
	`;
	document.head.appendChild(style);
};

erpnext.checklists.setup = function (frm) {
	erpnext.checklists.injectStyle();
	erpnext.checklists.TABLES.forEach((cfg) => erpnext.checklists.renderTable(frm, cfg));
};

erpnext.checklists.renderTable = function (frm, cfg) {
	const field = frm.fields_dict[cfg.fieldname];
	if (!field) return;

	// Hide the default child-table grid.
	if (field.grid && field.grid.wrapper) {
		$(field.grid.wrapper).hide();
	}

	// Build the custom UI once, then keep reusing it.
	let $ui = field.$wrapper.find(".ckl-uploader");
	if (!$ui.length) {
		$ui = $(
			`<div class="ckl-uploader ckl-uploader-${cfg.fieldname}">
				<button class="btn btn-primary btn-sm ckl-upload-btn" type="button">
					${cfg.icon} ${frappe.utils.escape_html(cfg.buttonLabel)}
				</button>
				<div class="ckl-gallery"></div>
			</div>`
		).appendTo(field.$wrapper);
		$ui.find(".ckl-upload-btn").on("click", () => erpnext.checklists.openUploader(frm, cfg));
	}

	// Disable upload button while the doc is read-only (submitted / no write).
	$ui.find(".ckl-upload-btn").prop("disabled", frm.doc.docstatus > 0 || frm.read_only);

	erpnext.checklists.renderGallery(frm, cfg, $ui.find(".ckl-gallery"));
};

erpnext.checklists.openUploader = function (frm, cfg) {
	new frappe.ui.FileUploader({
		doctype: frm.doc.doctype,
		docname: frm.doc.name,
		allow_multiple: true,
		dialog_title: cfg.buttonLabel,
		restrictions: cfg.imagesOnly ? { allowed_file_types: ["image/*"] } : {},
		on_success: (file_doc) => {
			if (!file_doc || !file_doc.file_url) return;
			const row = frm.add_child(cfg.fieldname);
			row[cfg.urlField] = file_doc.file_url;
			frm.refresh_field(cfg.fieldname);
			erpnext.checklists.setup(frm);
			frm.dirty();
		},
	});
};

erpnext.checklists.renderGallery = function (frm, cfg, $gallery) {
	const rows = frm.doc[cfg.fieldname] || [];
	$gallery.empty();

	const withUrl = rows.filter((row) => row[cfg.urlField]);
	if (!withUrl.length) {
		$gallery.append(`<div class="ckl-empty text-muted">${__("Nothing uploaded yet")}</div>`);
		return;
	}

	withUrl.forEach((row) => {
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

		$gallery.append($tile);
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
