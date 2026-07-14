// Pure state-transition logic for the checklist answer grid (Checklist Item
// child rows). Zero DOM, zero `frm`, zero `frappe.*` calls beyond
// `frappe.provide` -- this file is node-testable via `node:vm`
// (checklist_pure.test.js) because the Desk client-script pipeline has no
// bundler and no module system: `_add_code` (frappe/desk/form/meta.py)
// raw-concatenates hook JS into the doctype's `__js`, and `script_manager.js`
// runs the concatenated text via `new Function(client_script)()`. That is
// not a module context -- `import`/`export` throw a SyntaxError there -- so
// this file MUST stay plain-script and assign onto `erpnext.checklist_pure`.
frappe.provide("erpnext.checklist_pure");

/**
 * Compute the next {yes, no, na, who_did_it} state for a Checklist Item row
 * after one of its three answer checkboxes was just ticked or unticked.
 *
 * `row[field]` is read AFTER Frappe has already flipped it in the model (the
 * adapter calls this from that field's own change handler), so this
 * function only has to decide the OTHER two answer fields and who_did_it.
 *
 * @param {{yes:number,no:number,na:number,who_did_it:string}} row current row state
 * @param {"yes"|"no"|"na"} field the checkbox that was just toggled
 * @param {string} sessionUser current session user, used to auto-fill who_did_it
 * @returns {{yes:number,no:number,na:number,who_did_it:string}}
 */
erpnext.checklist_pure.computeTickResult = function (row, field, sessionUser) {
	const next = { yes: 0, no: 0, na: 0, who_did_it: row.who_did_it || "" };
	if (!row[field]) return next; // untick -> unanswered, who_did_it retained (CIG-3)
	next[field] = 1; // tick -> exclusive, the other two stay 0 (CIG-2)
	if (!next.who_did_it) next.who_did_it = sessionUser; // fill only if currently empty (CIG-3)
	return next;
};

/**
 * Sum yes/no/na answers for a document across its Checklist Item child
 * tables and any remaining flat answer fields.
 *
 * Dual-shape by design (design Decision 5): no checklist JSON is converted
 * yet in slice 4, so a doctype may be entirely flat Select fields
 * (unconverted), entirely Table(Checklist Item) fields (converted), or a
 * document may be read while mid-migration. Both walks always run
 * unconditionally -- no version flag, no branch. The two shapes are
 * disjoint per-doctype (a converted doctype's legacy columns are orphaned
 * from meta, an unconverted one has no Checklist Item arrays), so summing
 * both never double-counts the same answer.
 *
 * `excluded` (PCD-1) is the caller's exclusion set for the flat walk --
 * project.js passes the union of CHECKLIST_NON_ANSWER_FIELDS (free-text
 * fields like vehicle_model that must never be miscounted as an answer) and
 * CHECKLIST_HEADER_FIELDS (notes/check_date/etc., rendered separately from
 * the answer grid). This function stays domain-agnostic on purpose -- it
 * knows nothing about which fieldnames those are, only that the caller's
 * excluded set should be skipped.
 *
 * @param {object} doc
 * @param {string[]} tableFieldnames
 * @param {Set<string>} excluded
 * @returns {{yes:number,no:number,na:number}}
 */
erpnext.checklist_pure.countChecklistAnswers = function (doc, tableFieldnames, excluded) {
	let yes = 0;
	let no = 0;
	let na = 0;

	// Flat Select answers (pre-conversion shape): "Yes"/"No"/"N/A" string
	// values on top-level fields not in the caller's excluded set.
	for (const key in doc) {
		if (excluded.has(key)) continue;
		const value = doc[key];
		if (value === "Yes") yes++;
		else if (value === "No") no++;
		else if (value === "N/A") na++;
	}

	// Checklist Item child-table rows (post-conversion shape): yes/no/na are
	// mutually-exclusive 0/1 Check flags (CIG-2) -- at most one is set per
	// row, an unanswered row has all three at 0 and contributes to none.
	(tableFieldnames || []).forEach((fieldname) => {
		(doc[fieldname] || []).forEach((row) => {
			if (row.yes) yes++;
			else if (row.no) no++;
			else if (row.na) na++;
		});
	});

	return { yes, no, na };
};
