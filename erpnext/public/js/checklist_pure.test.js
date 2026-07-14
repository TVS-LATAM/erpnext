// Run: node --test erpnext/public/js/checklist_pure.test.js
//
// checklist_pure.js MUST NOT use import/export (see its header comment for
// why -- the Desk client-script pipeline has no bundler/module system). This
// harness therefore loads the file's raw text and evaluates it with
// `node:vm` against a stub `frappe`/`erpnext` global, mirroring how
// `script_manager.js` actually runs hook JS in production
// (`new Function(client_script)()`), instead of `require()`-ing it as a
// CommonJS module.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const assert = require("node:assert/strict");

function loadChecklistPure() {
	const filePath = path.join(__dirname, "checklist_pure.js");
	const code = fs.readFileSync(filePath, "utf8");

	const sandbox = {
		erpnext: {},
		frappe: {
			provide(namespace) {
				let obj = sandbox;
				for (const part of namespace.split(".")) {
					obj[part] = obj[part] || {};
					obj = obj[part];
				}
				return obj;
			},
		},
	};
	vm.createContext(sandbox);
	vm.runInContext(code, sandbox, { filename: filePath });
	return sandbox.erpnext.checklist_pure;
}

const checklistPure = loadChecklistPure();

// vm.createContext gives the sandbox its own realm, so objects returned by
// checklistPure functions have a different Object prototype than literals
// written in this file. assert.deepEqual (strict) treats that as
// non-equal even when every own property matches, so plain-object results
// are copied into this realm before asserting.
function plain(value) {
	return Object.assign({}, value);
}

test("computeTickResult: tick sets exclusive state (CIG-2)", () => {
	// row.yes already flipped to 1 by Frappe before this function is called.
	const row = { yes: 1, no: 0, na: 0, who_did_it: "" };
	const result = checklistPure.computeTickResult(row, "yes", "mechanic-a");
	assert.deepEqual(plain(result), { yes: 1, no: 0, na: 0, who_did_it: "mechanic-a" });
});

test("computeTickResult: switching answer clears the previous one (CIG-2)", () => {
	// User had "yes" checked, then ticked "no" -- row.no is now 1.
	const row = { yes: 1, no: 1, na: 0, who_did_it: "mechanic-a" };
	const result = checklistPure.computeTickResult(row, "no", "mechanic-b");
	assert.deepEqual(plain(result), { yes: 0, no: 1, na: 0, who_did_it: "mechanic-a" });
});

test("computeTickResult: unticking the only answer clears the row, no auto-select (CIG-2)", () => {
	// User unticked "yes" -- row.yes is now 0.
	const row = { yes: 0, no: 0, na: 0, who_did_it: "" };
	const result = checklistPure.computeTickResult(row, "yes", "mechanic-a");
	assert.deepEqual(plain(result), { yes: 0, no: 0, na: 0, who_did_it: "" });
});

test("computeTickResult: unticking does not clear who_did_it (CIG-3)", () => {
	const row = { yes: 0, no: 0, na: 0, who_did_it: "mechanic-a" };
	const result = checklistPure.computeTickResult(row, "yes", "mechanic-b");
	assert.deepEqual(plain(result), { yes: 0, no: 0, na: 0, who_did_it: "mechanic-a" });
});

test("computeTickResult: first tick on empty row fills who_did_it (CIG-3)", () => {
	const row = { yes: 0, no: 0, na: 1, who_did_it: "" };
	const result = checklistPure.computeTickResult(row, "na", "mechanic-c");
	assert.deepEqual(plain(result), { yes: 0, no: 0, na: 1, who_did_it: "mechanic-c" });
});

test("computeTickResult: non-empty who_did_it is never overwritten by a re-tick (CIG-3)", () => {
	// who_did_it was already filled (manually or by a prior tick); a
	// different session user ticks a different answer on the same row.
	const row = { yes: 0, no: 1, na: 0, who_did_it: "hand-typed-name" };
	const result = checklistPure.computeTickResult(row, "no", "mechanic-d");
	assert.deepEqual(plain(result), { yes: 0, no: 1, na: 0, who_did_it: "hand-typed-name" });
});

// countChecklistAnswers: real behavior (PCD-1, tasks 4.1/4.2). Replaces the
// slice-3 input-independent skeleton test.
//
// `excluded` here mirrors project.js's CHECKLIST_COUNT_EXCLUDED -- the union
// of CHECKLIST_NON_ANSWER_FIELDS (vehicle_model/licence_plate/mileage) and
// CHECKLIST_HEADER_FIELDS (project/check_date/checked_by/notes/photos/
// attachments) -- duplicated here as literal values rather than imported
// from project.js (a DOM-bound file with no module system) so this test
// proves the counting BEHAVIOR PCD-1 requires, independent of where the
// caller's exclusion set happens to live.
const CHECKLIST_COUNT_EXCLUDED_FOR_TEST = new Set([
	// CHECKLIST_NON_ANSWER_FIELDS (project.js:1304)
	"vehicle_model",
	"licence_plate",
	"mileage",
	// CHECKLIST_HEADER_FIELDS (project.js:1308)
	"project",
	"check_date",
	"checked_by",
	"notes",
	"photos",
	"attachments",
]);

test("countChecklistAnswers: sums Table(Checklist Item) rows by their yes/no/na flags (PCD-1)", () => {
	const result = checklistPure.countChecklistAnswers(
		{ arrival_items: [{ yes: 1, no: 0, na: 0 }] },
		["arrival_items"],
		new Set()
	);
	assert.deepEqual(plain(result), { yes: 1, no: 0, na: 0 });
});

test('countChecklistAnswers: notes:"No" is excluded from the count (PCD-1 -- the pre-existing bug this slice fixes)', () => {
	const doc = { notes: "No", check_date: "2026-01-01" };
	const result = checklistPure.countChecklistAnswers(doc, [], CHECKLIST_COUNT_EXCLUDED_FOR_TEST);
	assert.deepEqual(plain(result), { yes: 0, no: 0, na: 0 });
});

test('countChecklistAnswers: vehicle_model:"No" is excluded from the count (union guard, must not regress)', () => {
	const doc = { vehicle_model: "No", mileage: "No" };
	const result = checklistPure.countChecklistAnswers(doc, [], CHECKLIST_COUNT_EXCLUDED_FOR_TEST);
	assert.deepEqual(plain(result), { yes: 0, no: 0, na: 0 });
});

test("countChecklistAnswers: mixed flat + table doc sums both shapes (dual-shape, design Decision 5)", () => {
	const doc = {
		// flat Select answers -- pre-conversion shape (e.g. Job Checklist, not yet converted)
		brake_check: "Yes",
		lights_check: "No",
		tires_check: "N/A",
		notes: "No", // header field -- must NOT add to `no`
		// Checklist Item child-table rows -- post-conversion shape (e.g. Arrival Checklist, converted)
		arrival_items: [
			{ description: "Oil level", yes: 1, no: 0, na: 0, who_did_it: "mechanic-a" },
			{ description: "Coolant level", yes: 0, no: 1, na: 0, who_did_it: "mechanic-a" },
		],
	};
	const result = checklistPure.countChecklistAnswers(doc, ["arrival_items"], CHECKLIST_COUNT_EXCLUDED_FOR_TEST);
	// flat: 1 yes, 1 no, 1 na  +  table: 1 yes, 1 no  =  2 yes, 2 no, 1 na
	assert.deepEqual(plain(result), { yes: 2, no: 2, na: 1 });
});

test("countChecklistAnswers: unanswered flat fields and unanswered rows are counted in neither yes, no, nor na", () => {
	const doc = {
		brake_check: "", // unanswered flat field
		arrival_items: [
			{ description: "Oil level", yes: 0, no: 0, na: 0, who_did_it: "" }, // unanswered row -- valid terminal state (CIG-2)
		],
	};
	const result = checklistPure.countChecklistAnswers(doc, ["arrival_items"], CHECKLIST_COUNT_EXCLUDED_FOR_TEST);
	assert.deepEqual(plain(result), { yes: 0, no: 0, na: 0 });
});

// --- checklist_grid.js onTick cascade regression -----------------------
//
// The tests above call computeTickResult() directly, in isolation. That is
// NOT how production runs it: checklist_grid.js's onTick() is invoked from
// a `Checklist Item` field-change trigger, and every field write it makes
// through frappe.model.set_value() can itself queue and fire MORE triggers.
// A bug where onTick() re-enters itself and wipes the row is invisible to
// the isolated computeTickResult() tests above -- it only shows up when the
// full set_value -> trigger -> wildcard-listener -> onTick cascade actually
// runs.
//
// This harness simulates that cascade faithfully against the real Frappe
// client semantics (verified in frappe/public/js/frappe/model/model.js and
// frappe/public/js/frappe/form/form.js on this bench):
//   - frappe.model.set_value(cdt, cdn, field, value): assigns the value
//     SYNCHRONOUSLY, then -- ONLY if the value actually changed -- queues a
//     deferred trigger (model.js:557-565, "if (doc && doc[key] !== value)").
//   - frappe.model.trigger(field, value, doc): queues every listener
//     registered on that field AND on "*" for the doctype (model.js:617-620).
//   - The parent form registers exactly one "*" listener per child table
//     field pointing at "Checklist Item" (form.js:307-321); when a row in
//     that table changes, it calls script_manager.trigger(field, ...),
//     which re-dispatches to whatever was registered via
//     frappe.ui.form.on("Checklist Item", { field(frm, cdt, cdn) {...} })
//     (script_manager.js:89-142) -- i.e. back into onTick().
//   - Triggers are DEFERRED (queued, not called inline), matching
//     frappe.run_serially's task-queue semantics, so this harness drains a
//     FIFO task queue rather than calling handlers synchronously in place.
// tableFieldnames: the set of Checklist Item table fieldnames this harness
// instance simulates. Defaults to TWO distinct tables (mirroring that
// production wires the SAME onTick to 9 tables across 4 doctypes via one
// shared form.js wildcard-per-table-field registration -- see
// checklist_grid.js:137-149 and form.js:307-321) so that a production bug
// which hardcodes a single row's cdn or a single table's fieldname shows up
// as a cross-row or cross-table leak instead of passing silently against a
// harness that only ever has one row on one table.
function createCascadeHarness(tableFieldnames = ["arrival_items", "before_qc_items"]) {
	const pureFilePath = path.join(__dirname, "checklist_pure.js");
	const gridFilePath = path.join(__dirname, "checklist_grid.js");
	const pureCode = fs.readFileSync(pureFilePath, "utf8");
	const gridCode = fs.readFileSync(gridFilePath, "utf8");

	const CDT = "Checklist Item";
	const DEFAULT_PARENTFIELD = tableFieldnames[0]; // used by setRow() when no table is given (all pre-existing single-row/single-table tests)

	const locals = { [CDT]: {} };
	const modelEvents = {}; // doctype -> fieldname -> [fn(fieldname, value, doc)]
	const formHandlers = {}; // doctype -> fieldname -> [fn(frm, doctype, name)]
	const taskQueue = [];

	function queue(fn) {
		taskQueue.push(fn);
	}

	function drain() {
		let iterations = 0;
		while (taskQueue.length) {
			if (++iterations > 200) {
				throw new Error("Trigger cascade did not converge within 200 iterations (possible infinite loop)");
			}
			taskQueue.shift()();
		}
	}

	function modelOn(doctype, fieldname, fn) {
		modelEvents[doctype] = modelEvents[doctype] || {};
		modelEvents[doctype][fieldname] = modelEvents[doctype][fieldname] || [];
		modelEvents[doctype][fieldname].push(fn);
	}

	// Mirrors frappe.model.trigger (model.js:594-623): both the
	// field-specific listeners and the "*" listeners fire for one change.
	function modelTrigger(fieldname, value, doc) {
		const specific = (modelEvents[doc.doctype] && modelEvents[doc.doctype][fieldname]) || [];
		const wildcard = (modelEvents[doc.doctype] && modelEvents[doc.doctype]["*"]) || [];
		specific.concat(wildcard).forEach((fn) => queue(() => fn(fieldname, value, doc)));
	}

	// Mirrors frappe.model.set_value (model.js:530-575): synchronous
	// assignment, trigger only enqueued when the value actually changed.
	function setValue(cdt, cdn, fieldname, value) {
		const doc = locals[cdt][cdn];
		if (doc[fieldname] !== value) {
			doc[fieldname] = value;
			modelTrigger(fieldname, value, doc);
		}
	}

	// Mirrors frappe.ui.form.on (script_manager.js:24-57): registers
	// (fieldname -> handler) or ({fieldname: handler, ...} -> handlers).
	function formOn(doctype, fieldnameOrHandlers, maybeHandler) {
		formHandlers[doctype] = formHandlers[doctype] || {};
		const register = (fieldname, fn) => {
			formHandlers[doctype][fieldname] = formHandlers[doctype][fieldname] || [];
			formHandlers[doctype][fieldname].push(fn);
		};
		if (typeof fieldnameOrHandlers === "object") {
			Object.keys(fieldnameOrHandlers).forEach((fieldname) => register(fieldname, fieldnameOrHandlers[fieldname]));
		} else {
			register(fieldnameOrHandlers, maybeHandler);
		}
	}

	// Mirrors ScriptManager.trigger's new_style dispatch (script_manager.js:89-142).
	function scriptManagerTrigger(fieldname, doctype, name) {
		const handlers = (formHandlers[doctype] && formHandlers[doctype][fieldname]) || [];
		handlers.forEach((fn) => queue(() => fn(frm, doctype, name)));
	}

	const refreshFieldCalls = [];
	// Flat list of every grid.refresh_row() call across ALL tables, kept for
	// the pre-existing single-row/single-table tests that assert on it
	// directly. New multi-table tests use refreshRowCallsByTable instead,
	// which scopes calls to the specific table's own Grid instance -- this is
	// what proves a row's refresh went to ITS OWN table's grid and not a
	// sibling table's.
	const refreshRowCalls = [];
	const refreshRowCallsByTable = {};
	const fieldsDict = {};
	tableFieldnames.forEach((fieldname) => {
		refreshRowCallsByTable[fieldname] = [];
		// Mirrors frm.fields_dict[fieldname].grid, the Grid instance for a
		// table field (frappe/public/js/frappe/form/form.js:1538 and friends).
		// onTick calls grid.refresh_row(cdn) -- a row-scoped redraw
		// (grid.js:578-579) -- instead of frm.refresh_field(), which would
		// rebuild every row's DOM (see checklist_grid.js's onTick comment).
		// Each table field gets its OWN Grid instance here, exactly like
		// production's frm.fields_dict has one entry per Table field --
		// so a bug that resolves the wrong table's grid, or refreshes the
		// wrong row, shows up as a call landing in the wrong table's array.
		fieldsDict[fieldname] = {
			grid: {
				refresh_row(docname) {
					refreshRowCalls.push(docname);
					refreshRowCallsByTable[fieldname].push(docname);
				},
			},
		};
	});
	const frm = {
		dirty_calls: 0,
		dirty() {
			this.dirty_calls += 1;
		},
		refresh_field(fieldname) {
			refreshFieldCalls.push(fieldname);
		},
		fields_dict: fieldsDict,
	};

	const sandbox = {
		erpnext: {},
		frappe: {
			provide(namespace) {
				let obj = sandbox;
				for (const part of namespace.split(".")) {
					obj[part] = obj[part] || {};
					obj = obj[part];
				}
				return obj;
			},
			session: { user: "" },
			get_doc(doctype, name) {
				return locals[doctype][name];
			},
			model: { set_value: setValue, on: modelOn, trigger: modelTrigger },
			ui: { form: { on: formOn } },
		},
	};
	vm.createContext(sandbox);
	// Same load order as hooks.py's doctype_js list: pure before grid.
	vm.runInContext(pureCode, sandbox, { filename: pureFilePath });
	vm.runInContext(gridCode, sandbox, { filename: gridFilePath });

	// Registers the SAME per-table "*" listener production form.js installs
	// once per child table field whose child doctype is "Checklist Item"
	// (form.js:307-321) -- this is what re-invokes onTick() for a sibling
	// field after frappe.model.set_value() clears it. One listener is
	// registered PER TABLE, each independently guarded by
	// doc.parentfield === fieldname, exactly like production wires one
	// wildcard listener per Table field -- so a row's own table listener is
	// the only one that ever reacts to that row's changes.
	tableFieldnames.forEach((fieldname) => {
		modelOn(CDT, "*", (changedField, value, doc) => {
			if (doc.parentfield !== fieldname) return;
			frm.dirty();
			scriptManagerTrigger(changedField, doc.doctype, doc.name);
		});
	});

	// parentfield defaults to the harness's first table so every pre-existing
	// call site (h.setRow(name, row)) keeps behaving exactly as before.
	function setRow(name, row, parentfield = DEFAULT_PARENTFIELD) {
		locals[CDT][name] = Object.assign({ doctype: CDT, name, parentfield }, row);
	}

	// Simulates the user checking/unchecking a checkbox: the widget itself
	// calls frappe.model.set_value() on the ticked field before any of our
	// code runs (see checklist_grid.js's onTick header comment), so this is
	// the SAME entry point production code is driven from -- not a direct
	// call into onTick().
	function tick(name, field, value, sessionUser) {
		sandbox.frappe.session.user = sessionUser;
		setValue(CDT, name, field, value);
		drain();
	}

	return {
		setRow,
		tick,
		row: (name) => locals[CDT][name],
		frm,
		refreshFieldCalls,
		refreshRowCalls,
		refreshRowCallsByTable,
	};
}

test("cascade: yes -> no clears yes, sets no (CIG-2)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 1, no: 0, na: 0, who_did_it: "mechanic-a" });
	h.tick("r1", "no", 1, "mechanic-b");
	assert.deepEqual(plain(h.row("r1")), {
		doctype: "Checklist Item",
		name: "r1",
		parentfield: "arrival_items",
		yes: 0,
		no: 1,
		na: 0,
		who_did_it: "mechanic-a",
	});
});

test("cascade: yes -> na clears yes, sets na (CIG-2)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 1, no: 0, na: 0, who_did_it: "mechanic-a" });
	h.tick("r1", "na", 1, "mechanic-b");
	assert.equal(h.row("r1").yes, 0);
	assert.equal(h.row("r1").na, 1);
	assert.equal(h.row("r1").no, 0);
});

test("cascade: no -> yes clears no, sets yes (CIG-2)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 0, no: 1, na: 0, who_did_it: "mechanic-a" });
	h.tick("r1", "yes", 1, "mechanic-b");
	assert.equal(h.row("r1").no, 0);
	assert.equal(h.row("r1").yes, 1);
	assert.equal(h.row("r1").na, 0);
});

test("cascade: no -> na clears no, sets na (CIG-2)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 0, no: 1, na: 0, who_did_it: "mechanic-a" });
	h.tick("r1", "na", 1, "mechanic-b");
	assert.equal(h.row("r1").no, 0);
	assert.equal(h.row("r1").na, 1);
	assert.equal(h.row("r1").yes, 0);
});

test("cascade: na -> yes clears na, sets yes (CIG-2)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 0, no: 0, na: 1, who_did_it: "mechanic-a" });
	h.tick("r1", "yes", 1, "mechanic-b");
	assert.equal(h.row("r1").na, 0);
	assert.equal(h.row("r1").yes, 1);
	assert.equal(h.row("r1").no, 0);
});

test("cascade: na -> no clears na, sets no (CIG-2)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 0, no: 0, na: 1, who_did_it: "mechanic-a" });
	h.tick("r1", "no", 1, "mechanic-b");
	assert.equal(h.row("r1").na, 0);
	assert.equal(h.row("r1").no, 1);
	assert.equal(h.row("r1").yes, 0);
});

test("cascade: unticking the only answer clears the row, no auto-select, who_did_it retained (CIG-2/CIG-3)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 1, no: 0, na: 0, who_did_it: "mechanic-a" });
	h.tick("r1", "yes", 0, "mechanic-b");
	assert.deepEqual(plain(h.row("r1")), {
		doctype: "Checklist Item",
		name: "r1",
		parentfield: "arrival_items",
		yes: 0,
		no: 0,
		na: 0,
		who_did_it: "mechanic-a",
	});
});

test("cascade: first tick on an empty row fills who_did_it from the session user (CIG-3)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 0, no: 0, na: 0, who_did_it: "" });
	h.tick("r1", "na", 1, "mechanic-c");
	assert.equal(h.row("r1").na, 1);
	assert.equal(h.row("r1").who_did_it, "mechanic-c");
});

test("cascade: switching the answer never overwrites a non-empty who_did_it (CIG-3)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 0, no: 0, na: 0, who_did_it: "hand-typed-name" });
	h.tick("r1", "no", 1, "mechanic-d");
	assert.equal(h.row("r1").no, 1);
	assert.equal(h.row("r1").who_did_it, "hand-typed-name");
});

// --- checklist_grid.js onTick dirty/refresh regression -----------------
//
// The cascade tests above only assert on row *values*. They never checked
// that onTick actually marks the form dirty or repaints the touched row --
// so deleting onTick's `frm.dirty()` / row-refresh block entirely left every
// test above GREEN (confirmed by temporarily removing that block: see PR
// notes). In production that regression means the model clears a sibling
// answer but the checkbox stays visually ticked and/or the form is not
// marked unsaved.
//
// dirty_calls is asserted as an EXACT count, not just ">0": the harness's
// own per-table wildcard listener (mirroring form.js:314-318) already calls
// frm.dirty() once for the field the user physically ticked, independent of
// onTick. Only the second call comes from onTick's own explicit frm.dirty()
// guarding the sibling-clearing direct mutation -- an ">0" assertion would
// stay green even with onTick's block deleted.
test("cascade: a sibling-clearing tick marks the form dirty and refreshes only the touched row, not the whole table (WARN-1/WARN-2)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 1, no: 0, na: 0, who_did_it: "mechanic-a" });
	h.tick("r1", "no", 1, "mechanic-b");
	assert.equal(h.frm.dirty_calls, 2, "expected 1 wildcard dirty() + 1 onTick dirty() for the sibling clear");
	assert.deepEqual(h.refreshRowCalls, ["r1"], "onTick must call grid.refresh_row(cdn), not a whole-table refresh");
	assert.deepEqual(h.refreshFieldCalls, [], "onTick must not call frm.refresh_field(), which redraws every row");
});

// Unticking the ONLY answer is not a useful case here: row[field] is already
// flipped to 0 by set_value before onTick runs, and the other two fields plus
// who_did_it are already at their final (unchanged) values, so onTick's own
// changed-detection never fires (see the "unticking the only answer" cascade
// test above) -- there is nothing for onTick's own dirty()/refresh_row to do.
// The who_did_it auto-fill on a first tick is the other real case where
// onTick makes an additional mutation beyond the raw tick.
test("cascade: auto-filling who_did_it on a first tick also marks the form dirty and refreshes only the touched row (WARN-1/WARN-2)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 0, no: 0, na: 0, who_did_it: "" });
	h.tick("r1", "na", 1, "mechanic-c");
	assert.equal(h.frm.dirty_calls, 2, "expected 1 wildcard dirty() + 1 onTick dirty() for the who_did_it auto-fill");
	assert.deepEqual(h.refreshRowCalls, ["r1"], "onTick must call grid.refresh_row(cdn), not a whole-table refresh");
});

// --- checklist_grid.js onTick multi-row/multi-table isolation regression ---
//
// All cascade tests above run against exactly one row on exactly one table,
// so a version of onTick that hardcodes a docname (e.g. "r1") or a table
// fieldname (e.g. "arrival_items") instead of using the real `cdn` /
// `row.parentfield` it was called with would still pass every test above --
// there is only ever one row and one table, so the hardcoded value and the
// real value happen to be identical. Slices 5/6 add 9 Checklist Item tables
// across 4 doctypes served by this ONE shared onTick, so a future copy/paste
// refactor that hardcodes either value must fail loudly here instead of
// shipping silently green. These tests use createCascadeHarness()'s default
// TWO tables and put MULTIPLE rows on them to make both mistakes observable:
//   - a second row on the SAME table catches a hardcoded docname/cdn, and
//   - a second table catches a hardcoded table fieldname / wrong
//     frm.fields_dict resolution, and proves the OTHER table's grid is
//     never touched by a tick that belongs to a different table.

test("cascade: ticking one row among several on the same table refreshes only that row's own cdn (multi-row isolation)", () => {
	const h = createCascadeHarness();
	h.setRow("r1", { yes: 1, no: 0, na: 0, who_did_it: "mechanic-a" }, "arrival_items");
	h.setRow("r2", { yes: 0, no: 1, na: 0, who_did_it: "mechanic-a" }, "arrival_items");

	h.tick("r2", "yes", 1, "mechanic-b");

	// r2's own answer switched; r1 must be completely untouched.
	assert.equal(h.row("r2").yes, 1);
	assert.equal(h.row("r2").no, 0);
	assert.deepEqual(plain(h.row("r1")), {
		doctype: "Checklist Item",
		name: "r1",
		parentfield: "arrival_items",
		yes: 1,
		no: 0,
		na: 0,
		who_did_it: "mechanic-a",
	});
	assert.deepEqual(
		h.refreshRowCallsByTable.arrival_items,
		["r2"],
		"refresh_row must be called with the ticked row's OWN cdn (r2), not a hardcoded/stale docname"
	);
});

test("cascade: ticking a row on one table refreshes only that table's own grid, not a sibling table's (multi-table isolation)", () => {
	const h = createCascadeHarness();
	h.setRow("a1", { yes: 1, no: 0, na: 0, who_did_it: "mechanic-a" }, "arrival_items");
	h.setRow("b1", { yes: 0, no: 1, na: 0, who_did_it: "mechanic-a" }, "before_qc_items");

	h.tick("b1", "yes", 1, "mechanic-b");

	assert.equal(h.row("b1").yes, 1);
	assert.equal(h.row("b1").no, 0);
	// a1 belongs to a different table and was never touched by this tick.
	assert.deepEqual(plain(h.row("a1")), {
		doctype: "Checklist Item",
		name: "a1",
		parentfield: "arrival_items",
		yes: 1,
		no: 0,
		na: 0,
		who_did_it: "mechanic-a",
	});
	assert.deepEqual(
		h.refreshRowCallsByTable.before_qc_items,
		["b1"],
		"onTick must resolve fields_dict via the ticked row's OWN parentfield (before_qc_items)"
	);
	assert.deepEqual(
		h.refreshRowCallsByTable.arrival_items,
		[],
		"onTick must not touch a sibling table's grid when the ticked row belongs to a different table"
	);
});

test("cascade: ticking a row on the other table (reverse direction) still resolves its own table only (multi-table isolation)", () => {
	const h = createCascadeHarness();
	h.setRow("a1", { yes: 0, no: 0, na: 0, who_did_it: "" }, "arrival_items");
	h.setRow("b1", { yes: 1, no: 0, na: 0, who_did_it: "mechanic-a" }, "before_qc_items");

	h.tick("a1", "na", 1, "mechanic-c");

	assert.equal(h.row("a1").na, 1);
	assert.equal(h.row("a1").who_did_it, "mechanic-c");
	assert.deepEqual(
		h.refreshRowCallsByTable.arrival_items,
		["a1"],
		"onTick must resolve fields_dict via the ticked row's OWN parentfield (arrival_items)"
	);
	assert.deepEqual(
		h.refreshRowCallsByTable.before_qc_items,
		[],
		"onTick must not touch a sibling table's grid when the ticked row belongs to a different table"
	);
});
