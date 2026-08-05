// Zone vocabulary: the parts a checklist photo can be filed against
// (Checklist Photo.zone).
//
// Two families live here: the body panels of the car, and the powertrain
// parts a DSG oil change documents. One map, not two, because the consumers
// below are family-blind -- the galleries and the Project "View Checklists"
// dialog label and sort photos from every checklist through the same two
// functions, and a photo does not carry which diagram produced it. Which
// family is DRAWN is the diagram's decision (checklist_vehicle_diagram.js
// picks the set by doctype), and no checklist ever mixes the two, so the
// families never interleave on screen.
//
// This is its own module because three callers need it and they do not all
// load the same things: checklist_vehicle_diagram.js draws the parts,
// checklist_attachments.js groups the gallery by them, and project.js labels
// the photo tiles in the Project "View Checklists" dialog -- a form that has
// no diagram and no uploader on it. Same split, and same reason, as
// checklist_pure.js: it was carved out so that dialog could count answers
// without pulling in the grid adapter.
//
// The keys are the contract. They are what lands in the database, so they are
// stable identifiers, never the display text.
frappe.provide("erpnext.checklist_zones");

// Source strings, NOT translated here. project.js documents the hazard on
// PROJECT_CHECKLIST_DOCTYPES: a __() evaluated while the module is still
// loading resolves against whichever translation dictionary happens to be in
// place at that moment. label() below translates at call time instead.
//
// Declaration order is meaningful -- it is the order the parts are drawn on
// the diagram, and rank() turns it into the sort order for galleries. Reading
// the order off this list rather than sorting alphabetically keeps the
// picture and the lists telling the same story, and alphabetical order is a
// different order in every UI language.
erpnext.checklist_zones.LABELS = {
	left_front_wing: "Left Front Wing",
	left_front_door: "Left Front Door",
	left_rear_door: "Left Rear Door",
	left_rear_wing: "Left Rear Wing",
	right_front_wing: "Right Front Wing",
	right_front_door: "Right Front Door",
	right_rear_door: "Right Rear Door",
	right_rear_wing: "Right Rear Wing",
	windshield: "Windshield",
	front_bumper: "Front Bumper",
	rear_window: "Rear Window",
	rear_bumper: "Rear Bumper",
	bonnet: "Bonnet",
	roof: "Roof",
	boot_lid: "Boot Lid",
	// Powertrain family (DSG Oil Change Checklist). Declared after the body
	// panels so adding them cannot renumber the existing ones -- rank() is
	// this list's index, and a photo already filed under `roof` must keep
	// sorting where it always did.
	engine_oil_cap: "Oil Filler Cap",
	engine_block: "Engine Block",
	engine_oil_filter: "Engine Oil Filter",
	engine_oil_sump: "Oil Sump",
	mechatronic_unit: "Mechatronic Unit",
	gearbox_housing: "Gearbox Housing",
	dsg_oil_filter: "DSG Oil Filter",
	dsg_oil_pan: "DSG Oil Pan",
};

erpnext.checklist_zones.ORDER = Object.keys(erpnext.checklist_zones.LABELS);

// Photos uploaded through the plain "Upload photos" button carry no zone.
// That is a supported case (a general shot of the whole car), which is why
// Checklist Photo.zone is not mandatory -- so an empty zone gets a name
// rather than an empty heading.
//
// An unknown key is echoed back verbatim instead of being blanked: a zone
// removed from the diagram must still be readable on the photos already
// filed under it.
erpnext.checklist_zones.label = function (zone) {
	if (!zone) return __("General");
	const source = erpnext.checklist_zones.LABELS[zone];
	return source ? __(source) : zone;
};

// Sort key. Unknown and unzoned photos rank last, after every drawn part.
erpnext.checklist_zones.rank = function (zone) {
	const index = erpnext.checklist_zones.ORDER.indexOf(zone);
	return index === -1 ? erpnext.checklist_zones.ORDER.length : index;
};
