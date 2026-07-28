// Vehicle diagram for the project checklists: five schematic views of the car
// whose panels are the upload targets. Clicking a panel opens the ordinary
// file uploader and files every photo it produces under that panel's zone.
//
// Why a diagram at all: the checklists already had a flat "Upload photos"
// button, so a set of arrival photos arrived as an unordered pile with no
// record of what each one shows. A mechanic documenting a scratch had to
// remember to caption it, and nobody did. Making the panel the button removes
// the step -- the zone is a side effect of where you clicked.
//
// Why drawn in SVG rather than hotspots over a raster car: the panels ARE the
// artwork. Each clickable region is the same path that draws that part of the
// car, so a region can never drift out of alignment with the picture, the
// whole thing scales to any tablet width without resampling, and it inherits
// the theme's colours (including dark mode) instead of shipping a white JPG.
//
// Data: the zone lands on Checklist Photo.zone (a read-only Data field). The
// shapes below ARE the options, which is why that field is Data and not a
// Select: a Select would put a second copy of the list in the doctype JSON
// and adding a panel here would then fail validation on save until someone
// patched the JSON to match. Their display names live in checklist_zones.js,
// shared with the galleries and the Project "View Checklists" dialog.
frappe.provide("erpnext.checklist_diagram");
// hooks.py guarantees checklist_attachments.js loads first, so this normally
// finds the list already there. Declared defensively anyway (the assignment is
// idempotent on both sides) so a load-order regression degrades to "the
// diagram never repaints" instead of a TypeError at file scope, which would
// take the rest of this file's definitions down with it.
frappe.provide("erpnext.checklists");
erpnext.checklists.afterRender = erpnext.checklists.afterRender || [];

// The diagram uploads into the same child table the plain upload button uses.
erpnext.checklist_diagram.TABLE_FIELDNAME = "photos";

// Each physical panel is clickable in EXACTLY ONE view. A bonnet drawn as a
// hotspot on both the front and the top view would look friendlier and would
// split every bonnet photo across two buckets -- which is the one thing this
// feature exists to prevent. Panels that are visible but not clickable in a
// given view are drawn as `decor`: same line work, no hit target.
const SIDE = {
	front_wing: "M8 90 L13 66 L58 58 L74 46 L74 90 Z",
	front_door: "M74 46 L94 28 L138 26 L138 90 L74 90 Z",
	rear_door: "M138 26 L182 26 L202 40 L202 90 L138 90 Z",
	rear_wing: "M202 40 L226 58 L282 62 L288 90 L202 90 Z",
	decor: `
		<circle class="tvs-vd-decor" cx="46" cy="90" r="15"/>
		<circle class="tvs-vd-decor" cx="46" cy="90" r="6"/>
		<circle class="tvs-vd-decor" cx="234" cy="90" r="15"/>
		<circle class="tvs-vd-decor" cx="234" cy="90" r="6"/>
		<path class="tvs-vd-decor" d="M86 48 L100 34 L134 33 L134 48 Z"/>
		<path class="tvs-vd-decor" d="M144 33 L180 33 L196 46 L144 46 Z"/>
		<path class="tvs-vd-decor" d="M0 105 L300 105"/>
	`,
};

// Front and rear elevations share their geometry: the same trapezoid stack of
// glass over a bumper. Only the labels and the decor differ.
const FACE = {
	glass: "M52 22 L148 22 L160 52 L40 52 Z",
	bumper: "M34 62 L166 62 L172 100 L28 100 Z",
	panel_edge: "M40 52 L160 52 L163 62 L37 62 Z",
};

erpnext.checklist_diagram.VIEWS = [
	{
		id: "left",
		title: "Left Side",
		viewBox: "0 0 300 110",
		decor: SIDE.decor,
		zones: [
			{ key: "left_front_wing", d: SIDE.front_wing, badge: [40, 76] },
			{ key: "left_front_door", d: SIDE.front_door, badge: [106, 62] },
			{ key: "left_rear_door", d: SIDE.rear_door, badge: [170, 62] },
			{ key: "left_rear_wing", d: SIDE.rear_wing, badge: [246, 76] },
		],
	},
	{
		id: "right",
		title: "Right Side",
		viewBox: "0 0 300 110",
		// The right flank is the left flank seen from the other side, so it
		// reuses the same path data behind a mirror transform instead of a
		// hand-copied second set of coordinates that would drift on the first
		// edit to the silhouette.
		mirror: true,
		decor: SIDE.decor,
		zones: [
			{ key: "right_front_wing", d: SIDE.front_wing, badge: [40, 76] },
			{ key: "right_front_door", d: SIDE.front_door, badge: [106, 62] },
			{ key: "right_rear_door", d: SIDE.rear_door, badge: [170, 62] },
			{ key: "right_rear_wing", d: SIDE.rear_wing, badge: [246, 76] },
		],
	},
	{
		id: "front",
		title: "Front",
		viewBox: "0 0 200 115",
		decor: `
			<path class="tvs-vd-decor" d="M52 22 L62 10 L138 10 L148 22"/>
			<path class="tvs-vd-decor" d="${FACE.panel_edge}"/>
			<rect class="tvs-vd-decor" x="42" y="70" width="34" height="12" rx="3"/>
			<rect class="tvs-vd-decor" x="124" y="70" width="34" height="12" rx="3"/>
			<rect class="tvs-vd-decor" x="82" y="72" width="36" height="9" rx="2"/>
			<path class="tvs-vd-decor" d="M40 34 L28 40"/>
			<path class="tvs-vd-decor" d="M160 34 L172 40"/>
		`,
		zones: [
			{ key: "windshield", d: FACE.glass, badge: [100, 40] },
			{ key: "front_bumper", d: FACE.bumper, badge: [100, 94] },
		],
	},
	{
		id: "rear",
		title: "Rear",
		viewBox: "0 0 200 115",
		decor: `
			<path class="tvs-vd-decor" d="M52 22 L62 10 L138 10 L148 22"/>
			<path class="tvs-vd-decor" d="${FACE.panel_edge}"/>
			<rect class="tvs-vd-decor" x="38" y="68" width="30" height="14" rx="3"/>
			<rect class="tvs-vd-decor" x="132" y="68" width="30" height="14" rx="3"/>
			<path class="tvs-vd-decor" d="M86 92 L114 92"/>
		`,
		zones: [
			{ key: "rear_window", d: FACE.glass, badge: [100, 40] },
			{ key: "rear_bumper", d: FACE.bumper, badge: [100, 94] },
		],
	},
	{
		id: "top",
		title: "Top",
		viewBox: "0 0 300 130",
		decor: `
			<path class="tvs-vd-decor" d="M100 32 L122 44 L122 86 L100 98"/>
			<path class="tvs-vd-decor" d="M194 32 L172 44 L172 86 L194 98"/>
			<path class="tvs-vd-decor" d="M122 44 L172 44"/>
			<path class="tvs-vd-decor" d="M122 86 L172 86"/>
			<rect class="tvs-vd-decor" x="92" y="22" width="14" height="7" rx="2"/>
			<rect class="tvs-vd-decor" x="92" y="101" width="14" height="7" rx="2"/>
			<rect class="tvs-vd-decor" x="52" y="16" width="26" height="12" rx="3"/>
			<rect class="tvs-vd-decor" x="52" y="102" width="26" height="12" rx="3"/>
			<rect class="tvs-vd-decor" x="216" y="16" width="26" height="12" rx="3"/>
			<rect class="tvs-vd-decor" x="216" y="102" width="26" height="12" rx="3"/>
		`,
		zones: [
			{ key: "bonnet", d: "M26 30 Q12 65 26 100 L96 100 L96 30 Z", badge: [58, 65] },
			{ key: "roof", d: "M96 30 L198 30 L198 100 L96 100 Z", badge: [147, 65] },
			{ key: "boot_lid", d: "M198 30 L268 32 Q286 65 268 98 L198 100 Z", badge: [232, 65] },
		],
	},
];

erpnext.checklist_diagram.injectStyles = function () {
	if (erpnext.checklist_diagram._injected || typeof document === "undefined") return;
	erpnext.checklist_diagram._injected = true;

	const style = document.createElement("style");
	style.textContent = `
		.tvs-vd { margin-bottom: 14px; }
		.tvs-vd-hint { font-size: var(--text-xs); color: var(--text-muted); margin-bottom: 8px; }
		.tvs-vd-views { display: flex; flex-wrap: wrap; gap: 10px; }
		.tvs-vd-view { flex: 1 1 220px; min-width: 200px; border: 1px solid var(--table-border-color); border-radius: 6px; background: var(--fg-color); overflow: hidden; }
		.tvs-vd-view-title { font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--text-muted); background: var(--subtle-accent); border-bottom: 1px solid var(--table-border-color); padding: 4px 8px; }
		.tvs-vd-svg { display: block; width: 100%; height: auto; }
		.tvs-vd-decor { fill: none; stroke: var(--text-muted); stroke-width: 1.2; opacity: .45; }
		.tvs-vd-zone { fill: var(--control-bg); stroke: var(--text-color); stroke-width: 1.4; opacity: .75; }
		.tvs-vd-editable .tvs-vd-zone { cursor: pointer; }
		.tvs-vd-editable .tvs-vd-zone:hover { fill: var(--bg-blue, #e8f0fe); opacity: 1; }
		.tvs-vd-zone.tvs-vd-filled { fill: var(--bg-green, #d3f2e0); opacity: 1; }
		.tvs-vd-count { font-size: 11px; font-weight: 700; fill: var(--text-color); pointer-events: none; }
		.tvs-vd-count-bg { fill: var(--fg-color); stroke: var(--text-color); stroke-width: 1; pointer-events: none; }
		.tvs-vd-group-title { font-size: var(--text-xs); font-weight: 600; color: var(--text-muted); margin: 12px 0 6px; }
		.tvs-vd-general { cursor: pointer; }
		.tvs-vd-general-body { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; min-height: 96px; margin: 8px; border: 1px dashed var(--text-muted); border-radius: 4px; opacity: .6; font-size: var(--text-xs); color: var(--text-muted); text-align: center; padding: 8px; }
		.tvs-vd-general:hover .tvs-vd-general-body { opacity: 1; border-style: solid; }
		.tvs-vd-general-plus { font-size: 22px; line-height: 1; font-weight: 300; }
	`;
	document.head.appendChild(style);
};

erpnext.checklist_diagram.tableConfig = function () {
	return (erpnext.checklists.TABLES || []).find(
		(cfg) => cfg.fieldname === erpnext.checklist_diagram.TABLE_FIELDNAME
	);
};

erpnext.checklist_diagram.countByZone = function (frm) {
	const counts = {};
	(frm.doc[erpnext.checklist_diagram.TABLE_FIELDNAME] || []).forEach((row) => {
		if (!row.zone) return;
		counts[row.zone] = (counts[row.zone] || 0) + 1;
	});
	return counts;
};

erpnext.checklist_diagram.renderView = function (view, counts) {
	const esc = frappe.utils.escape_html;
	const shapes = view.zones
		.map((zone) => {
			const label = erpnext.checklist_zones.label(zone.key);
			const count = counts[zone.key] || 0;
			const filled = count ? " tvs-vd-filled" : "";
			// <title> gives the native hover tooltip; aria-label names the
			// shape for assistive tech, which otherwise reads a bare <path>.
			return `<path class="tvs-vd-zone${filled}" d="${zone.d}" data-ckl-zone="${esc(zone.key)}"
				role="button" tabindex="0" aria-label="${esc(label)}"><title>${esc(label)}</title></path>`;
		})
		.join("");

	// Counters are painted after every zone so a badge sitting on a shared
	// edge is never covered by the neighbouring panel.
	const badges = view.zones
		.filter((zone) => counts[zone.key])
		.map((zone) => {
			const [x, y] = zone.badge;
			return `<circle class="tvs-vd-count-bg" cx="${x}" cy="${y}" r="9"/>
				<text class="tvs-vd-count" x="${x}" y="${y + 4}" text-anchor="middle">${counts[zone.key]}</text>`;
		})
		.join("");

	// The mirror transform flips the geometry only. Badges are drawn outside
	// it, or the counter digits would render backwards.
	const body = view.mirror
		? `<g transform="translate(300,0) scale(-1,1)">${view.decor}${shapes}</g>${badges}`
		: `${view.decor}${shapes}${badges}`;

	// Translated here, not on the VIEWS literal: a __() evaluated at module
	// scope resolves against whichever dictionary is loaded at that instant
	// (the hazard project.js documents on PROJECT_CHECKLIST_DOCTYPES).
	const title = esc(__(view.title));

	return `<div class="tvs-vd-view">
			<div class="tvs-vd-view-title">${title}</div>
			<svg class="tvs-vd-svg" viewBox="${view.viewBox}" role="group" aria-label="${title}">${body}</svg>
		</div>`;
};

erpnext.checklist_diagram.render = function (frm) {
	const cfg = erpnext.checklist_diagram.tableConfig();
	const field = cfg && frm.fields_dict[cfg.fieldname];
	if (!field) return;

	// checklist_attachments.js owns this container. If it has not built it
	// yet (or failed to), there is nothing to paint into -- and since the
	// photos table no longer renders a plain upload button, that is now the
	// only way in. The stock Frappe child-table grid stays in the DOM behind
	// it (hidden, never removed) precisely so this stays recoverable.
	const $host = field.$wrapper.find(".ckl-uploader").first();
	if (!$host.length) return;

	erpnext.checklist_diagram.injectStyles();

	const editable = !(frm.doc.docstatus > 0 || frm.read_only);
	const counts = erpnext.checklist_diagram.countByZone(frm);

	$host.find(".tvs-vd").remove();

	const views = erpnext.checklist_diagram.VIEWS.map((view) =>
		erpnext.checklist_diagram.renderView(view, counts)
	).join("");

	// A shot of the whole car belongs to no panel, and Checklist Photo.zone
	// is deliberately optional for exactly that case. Now that the photos
	// table has no plain upload button, this card IS that case's entry point
	// -- rendered as another card in the same grid so there is one
	// interaction model on screen (tap a target) instead of a diagram plus a
	// loose button that behave differently.
	const general = editable
		? `<div class="tvs-vd-view tvs-vd-general" role="button" tabindex="0"
				aria-label="${frappe.utils.escape_html(__("Add general photos"))}">
				<div class="tvs-vd-view-title">${frappe.utils.escape_html(__("General"))}</div>
				<div class="tvs-vd-general-body">
					<div class="tvs-vd-general-plus">+</div>
					<div>${frappe.utils.escape_html(__("Whole vehicle / other"))}</div>
				</div>
			</div>`
		: "";

	const $diagram = $(`<div class="tvs-vd">
			<div class="tvs-vd-hint">${frappe.utils.escape_html(
				editable
					? __("Tap a part of the vehicle to add photos of it.")
					: __("Photos are filed by vehicle part.")
			)}</div>
			<div class="tvs-vd-views">${views}${general}</div>
		</div>`).toggleClass("tvs-vd-editable", editable);

	if (editable) {
		// Delegated on the container so the handlers survive the full
		// re-render this function does on every repaint, and so one binding
		// covers all 15 shapes across 5 SVGs.
		const openZone = (element) => {
			const zone = element.getAttribute("data-ckl-zone");
			if (!zone) return;
			erpnext.checklists.openUploader(frm, cfg, zone);
		};
		// No zone argument: the row is left unzoned on purpose and the
		// galleries file it under "General" through the vocabulary's own
		// empty-zone fallback, rather than inventing a sentinel key that
		// would then have to be excluded from the diagram everywhere.
		const openGeneral = () => erpnext.checklists.openUploader(frm, cfg);

		$diagram.on("click", ".tvs-vd-zone", function () {
			openZone(this);
		});
		$diagram.on("click", ".tvs-vd-general", openGeneral);
		// Both targets are focusable (tabindex=0), but neither a <path> nor a
		// <div> has native activation, so Enter/Space have to be wired by hand.
		$diagram.on("keydown", ".tvs-vd-zone, .tvs-vd-general", function (event) {
			if (event.key !== "Enter" && event.key !== " ") return;
			event.preventDefault();
			if (this.classList.contains("tvs-vd-general")) openGeneral();
			else openZone(this);
		});
	}

	$host.prepend($diagram);
};

// No frappe.ui.form.on registration of its own: checklist_attachments.js
// already runs on every refresh of all 4 checklists, it OWNS the container
// this paints into, and it re-runs itself after every upload and every
// delete. Hooking its afterRender list is therefore both sufficient and the
// only way to stay in step with the photo table -- a separate refresh handler
// would repaint on reload but leave a stale counter the moment a photo was
// added without one.
//
// The guard is what stops this file being wired to 4 parent doctypes from
// pushing the same callback 4 times: ScriptManager evaluates a doctype's __js
// once per form load, so opening Arrival then Job in one browser session
// would otherwise repaint the diagram once per checklist ever opened.
if (!erpnext.checklist_diagram._registered) {
	erpnext.checklist_diagram._registered = true;
	erpnext.checklists.afterRender.push(erpnext.checklist_diagram.render);
}
