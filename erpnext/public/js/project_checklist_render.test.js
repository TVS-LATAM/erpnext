// Run: node --test erpnext/public/js/project_checklist_render.test.js
//
// project.js's checklist-dialog renderers had no functional coverage: the
// existing test_project_checklist_render.py asserts on the file's SOURCE TEXT
// because project.js is a Desk client script with no module system and a
// top-level `frappe.ui.form.on("Project", {...})` call that cannot be
// require()d. Source assertions cannot answer the question that actually
// matters -- "does the modal render this checklist completely?" -- so this
// harness slices out the renderer region and EVALUATES it with `node:vm`
// against stub `frappe`/`erpnext` globals, exactly as checklist_pure.test.js
// already does for checklist_pure.js/checklist_grid.js.
//
// The slice is bounded by two markers rather than line numbers: project.js is
// edited constantly and any fixed window would rot within a week.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const assert = require("node:assert/strict");

const APP_ROOT = path.join(__dirname, "..", "..");
const PROJECT_JS = path.join(APP_ROOT, "projects", "doctype", "project", "project.js");
const JOB_CHECKLIST_JSON = path.join(
	APP_ROOT,
	"projects",
	"doctype",
	"job_checklist",
	"job_checklist.json"
);

const REGION_START = "const PROJECT_CHECKLIST_DOCTYPES = [";
const REGION_END = "function showChecklistsDialog(";

function rendererSource() {
	const source = fs.readFileSync(PROJECT_JS, "utf8");
	const start = source.indexOf(REGION_START);
	const end = source.indexOf(REGION_END);
	assert.ok(start !== -1, `marker not found in project.js: ${REGION_START}`);
	assert.ok(end !== -1, `marker not found in project.js: ${REGION_END}`);
	assert.ok(start < end, "renderer region markers are out of order in project.js");
	return source.slice(start, end);
}

function loadRenderers(meta) {
	const sandbox = {
		console,
		// The renderers translate every label they print. Identity + the
		// {0}-style interpolation frappe's __ supports, so a missing arg shows
		// up as a literal placeholder in the assertion rather than silently
		// passing.
		__: (text, args) =>
			args ? String(text).replace(/\{(\d+)\}/g, (_m, i) => args[Number(i)]) : text,
		frappe: {
			get_meta: (doctype) => (doctype === meta.name ? meta : { fields: [] }),
			utils: {
				escape_html: (value) =>
					String(value)
						.replace(/&/g, "&amp;")
						.replace(/</g, "&lt;")
						.replace(/>/g, "&gt;")
						.replace(/"/g, "&quot;")
						.replace(/'/g, "&#039;"),
			},
			datetime: { str_to_user: (value) => value },
			router: { slug: (value) => String(value).toLowerCase().replace(/ /g, "-") },
		},
		erpnext: {
			checklist_zones: { rank: () => 0, label: (zone) => zone || "Zone" },
		},
	};
	sandbox.frappe.provide = function (namespace) {
		let obj = sandbox;
		for (const part of namespace.split(".")) {
			obj[part] = obj[part] || {};
			obj = obj[part];
		}
		return obj;
	};
	vm.createContext(sandbox);
	// The real counter, not a stub: summarizeChecklistAnswers delegates to it
	// and the answer chips are part of what "renders completely" means.
	vm.runInContext(fs.readFileSync(path.join(__dirname, "checklist_pure.js"), "utf8"), sandbox, {
		filename: "checklist_pure.js",
	});
	vm.runInContext(rendererSource(), sandbox, { filename: "project.js#renderers" });
	return sandbox;
}

const jobMeta = JSON.parse(fs.readFileSync(JOB_CHECKLIST_JSON, "utf8"));

// Every checklist the Project modal lists. The dialog is meta-driven, so the
// completeness assertions below must hold for all four -- a renderer change
// made for one sheet must not quietly drop a section on another.
const ALL_CHECKLISTS = [
	"arrival_checklist",
	"job_checklist",
	"quality_control_checklist",
	"dsg_oil_change_checklist",
].map((slug) =>
	JSON.parse(
		fs.readFileSync(path.join(APP_ROOT, "projects", "doctype", slug, `${slug}.json`), "utf8")
	)
);

function tableFieldnames(meta) {
	return meta.fields
		.filter((f) => f.fieldtype === "Table" && f.options === "Checklist Item")
		.map((f) => f.fieldname);
}

function sectionLabels(meta) {
	// Only the sections that actually carry a Checklist Item table: the
	// Vehicle Details / General Notes / Attachments breaks hold nothing the
	// section walk renders, and renderChecklistFields drops empty sections.
	const labels = [];
	let current = null;
	for (const field of meta.fields) {
		if (field.fieldtype === "Section Break") current = field.label || null;
		if (field.fieldtype === "Table" && field.options === "Checklist Item" && current) {
			labels.push(current);
		}
	}
	return labels;
}

// A fully answered checklist: every table populated, every row ticked, so a
// row that the renderer drops shows up as a missing description AND a wrong
// chip count.
function makeAnsweredDoc(meta, { notes = {} } = {}) {
	const doc = { name: "JOB-CHK-00001", check_date: "2026-07-28", checked_by: "mechanic-a" };
	let counter = 0;
	for (const fieldname of tableFieldnames(meta)) {
		const rows = [];
		// 3 rows per table is enough to prove the grid walks the array; the
		// descriptions are unique per row so a dropped row is identifiable.
		for (let i = 0; i < 3; i++) {
			counter += 1;
			rows.push({
				description: `Row ${counter} in ${fieldname}`,
				yes: 1,
				no: 0,
				na: 0,
				who_did_it: `mechanic-${counter}`,
			});
		}
		doc[fieldname] = rows;
	}
	Object.assign(doc, notes);
	return doc;
}

test("modal renders every Proefrit section heading of the Job Checklist", () => {
	const sandbox = loadRenderers(jobMeta);
	const html = sandbox.renderChecklistCard("Job Checklist", makeAnsweredDoc(jobMeta));

	const expected = sectionLabels(jobMeta);
	assert.equal(expected.length, 6, "Job Checklist should carry the sheet's 6 answer sections");
	for (const label of expected) {
		assert.ok(html.includes(label), `modal dropped section heading: ${label}`);
	}
});

for (const meta of ALL_CHECKLISTS) {
	test(`modal renders every section, row, answer and who_did_it of ${meta.name}`, () => {
		const sandbox = loadRenderers(meta);
		const doc = makeAnsweredDoc(meta);
		const html = sandbox.renderChecklistCard(meta.name, doc);

		const tables = tableFieldnames(meta);
		assert.ok(tables.length, `${meta.name} declares no Checklist Item table`);
		// Every section that owns a table must print its heading.
		for (const label of sectionLabels(meta)) {
			assert.ok(html.includes(label), `${meta.name}: modal dropped section heading: ${label}`);
		}
		for (const fieldname of tables) {
			for (const row of doc[fieldname]) {
				assert.ok(html.includes(row.description), `${meta.name}: dropped row ${row.description}`);
				assert.ok(html.includes(row.who_did_it), `${meta.name}: dropped ${row.who_did_it}`);
			}
		}
		// makeAnsweredDoc ticks Yes on 3 rows per table.
		assert.ok(
			html.includes(`✓ ${tables.length * 3}`),
			`${meta.name}: answer chips did not count every seeded row`
		);
	});
}

test("modal skips the vehicle header section instead of printing an empty heading", () => {
	// vehicle_model/licence_plate/check_date/checked_by are all in
	// CHECKLIST_HEADER_FIELDS, so the "Vehicle Details" break contributes no
	// rows. An empty section heading in a quick-scan modal is pure noise.
	const sandbox = loadRenderers(jobMeta);
	const html = sandbox.renderChecklistCard("Job Checklist", makeAnsweredDoc(jobMeta));
	assert.ok(!html.includes("Vehicle Details"), "modal printed an empty Vehicle Details heading");
});

test("modal prints a section note only when the mechanic wrote one", () => {
	const sandbox = loadRenderers(jobMeta);

	const blank = sandbox.renderChecklistCard("Job Checklist", makeAnsweredDoc(jobMeta));
	assert.ok(!blank.includes("Tuning Checks Notes"), "empty section note should not be printed");

	const filled = sandbox.renderChecklistCard(
		"Job Checklist",
		makeAnsweredDoc(jobMeta, { notes: { tuning_notes: "boost 0.3 bar over spec" } })
	);
	assert.ok(filled.includes("Tuning Checks Notes"), "section note heading missing");
	assert.ok(filled.includes("boost 0.3 bar over spec"), "section note body missing");
});

test("a section note is flagged with the red alert marker", () => {
	// The note is the one thing on a checklist that is free text a mechanic
	// chose to write -- it is always an exception to the Yes/No grid. It has
	// to be findable at a glance in a modal that is otherwise a wall of ticks.
	const sandbox = loadRenderers(jobMeta);
	const html = sandbox.renderChecklistCard(
		"Job Checklist",
		makeAnsweredDoc(jobMeta, { notes: { status_notes: "pulls left under load" } })
	);
	assert.ok(html.includes("ckl-note-alert"), "section note is not flagged as an alert");
});

test("renderers survive a checklist whose tables were never seeded", () => {
	const sandbox = loadRenderers(jobMeta);
	const html = sandbox.renderChecklistCard("Job Checklist", { name: "JOB-CHK-00002" });
	assert.ok(html.includes("No checklist rows"), "unseeded checklist should say so, not render blank");
});
