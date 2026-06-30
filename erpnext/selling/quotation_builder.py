# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Diagnosis-driven quotation builder.

Given a Quotation linked to a Project, read the car's diagnosis, detect the
labour jobs needed, and propose reviewable line items per job:

- parts historically used for that job on the same car config (Sales Invoice history),
- the car's specific OEM part number as a reference line (from the Project),
- a labour line whose hours come from Standard Labour Hours (Manuren).

See get_standard_labour_hours() and get_item_insights() for the underlying data.
"""

import re

import frappe
from frappe import _

# Manuren DSG family (DQ250, DL382, ...) lives inside Project.dsg_model, e.g.
# "DQ250_1, DQ250_2, DQ250_3" or "DQ381_DQ380". Project.dsg_code is the VAG code
# (0AM, 02E, ...) used for part fitment, not for the labour-hours family.
DSG_FAMILY_RE = re.compile(r"(D[QL]\d{3})", re.IGNORECASE)


def _norm(value):
	return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _strip_html(value):
	"""Project diagnosis fields are Text Editor (HTML). Reduce to plain lowercase text."""
	text = re.sub(r"<[^>]+>", " ", str(value or ""))
	text = frappe.utils.unescape_html(text) if hasattr(frappe.utils, "unescape_html") else text
	return _norm(text)


def dsg_family_from_project(project):
	"""Return the Manuren DSG family (e.g. 'DQ250') from Project.dsg_model, or None."""
	m = DSG_FAMILY_RE.search(project.get("dsg_model") or "")
	return m.group(1).upper() if m else None


def _labour_skus():
	"""Reuse the same labour-SKU resolution as get_item_insights."""
	from erpnext.stock.doctype.item.item import _resolve_labour_set

	return _resolve_labour_set()


def extract_repair_advice(html):
	"""Return only the 'Reparatie advies' (repair advice) section of diagnose_result.

	The diagnosis is a structured Text Editor field with labelled sections
	(Systemscan, Opgemerkte klachten, Diagnose data, Reparatie advies, ...). Only
	the repair-advice section describes the work to quote, so job detection must run
	on that part alone — not the whole text. Returns "" if the section is absent.
	"""
	if not html:
		return ""
	low = html.lower()
	idx = low.find("reparatie advies")
	if idx == -1:
		idx = low.find("repair advice")
	if idx == -1:
		return ""

	rest = html[idx:]
	# The advice items sit in the first list right after the heading; capture it and
	# stop there so later sections (e.g. a "Werkplaatsreceptie"/offerte block) are excluded.
	m = re.search(r"<(ol|ul)\b[^>]*>(.*?)</\1>", rest, re.IGNORECASE | re.DOTALL)
	if m:
		segment = m.group(0)
	else:
		# No list — take text up to the next heading-like "<p>...:</p>" after the heading.
		after = rest.split("</p>", 1)[1] if "</p>" in rest else rest
		nxt = re.search(r"<p[^>]*>[^<]{0,60}:\s*</p>", after, re.IGNORECASE)
		segment = after[: nxt.start()] if nxt else after

	text = re.sub(r"<[^>]+>", " ", segment)
	text = frappe.utils.unescape_html(text) if hasattr(frappe.utils, "unescape_html") else text
	return re.sub(r"\s+", " ", text).strip()


def detect_jobs_from_text(text):
	"""Match free-text diagnosis against Labour Job.match_keywords.

	Returns a list of {job, matched_keyword} in keyword-specificity order
	(longer keywords first so 'koppeling + vliegwiel' wins over 'koppeling').
	"""
	norm_text = _strip_html(text)
	if not norm_text:
		return []

	pairs = []  # (keyword, job_name)
	for job in frappe.get_all("Labour Job", fields=["job_name", "match_keywords"]):
		for kw in re.split(r"[\n,]", job.match_keywords or ""):
			kw = _norm(kw)
			if kw:
				pairs.append((kw, job.job_name))

	# Longer keywords first; a hit on a longer phrase is more specific.
	pairs.sort(key=lambda p: -len(p[0]))

	detected = {}
	for kw, job_name in pairs:
		if kw in norm_text and job_name not in detected:
			detected[job_name] = kw
	return [{"job": j, "matched_keyword": k} for j, k in detected.items()]


def suggest_parts_for_job(job, engine_code=None, dsg_code=None, limit=12):
	"""Parts historically billed for `job` on the same car config.

	Finds submitted Sales Invoices whose linked Project (a) matches the car by
	dsg_code and/or engine_code, and (b) has a diagnosis mentioning one of the
	job's keywords; aggregates non-labour line items ranked by how many distinct
	invoices used them.
	"""
	keywords = [
		_norm(k)
		for k in re.split(r"[\n,]", frappe.db.get_value("Labour Job", job, "match_keywords") or "")
		if _norm(k)
	]
	if not keywords:
		return []

	conds = ["si.docstatus = 1"]
	params = {}

	car = []
	if dsg_code:
		car.append("p.dsg_code = %(dsg_code)s")
		params["dsg_code"] = dsg_code
	if engine_code:
		car.append("p.engine_code = %(engine_code)s")
		params["engine_code"] = engine_code
	if car:
		conds.append("(" + " OR ".join(car) + ")")

	kw_conds = []
	for i, kw in enumerate(keywords):
		key = f"kw{i}"
		kw_conds.append(f"LOWER(p.diagnose_result) LIKE %({key})s")
		params[key] = f"%{kw}%"
	conds.append("(" + " OR ".join(kw_conds) + ")")

	labour = _labour_skus()
	exclude = ""
	if labour:
		exclude = "AND UPPER(sii.item_code) NOT IN %(labour)s"
		params["labour"] = tuple(labour)

	params["limit"] = int(limit)

	rows = frappe.db.sql(
		f"""
		SELECT sii.item_code, sii.item_name,
		       COUNT(DISTINCT si.name) AS invoices,
		       SUM(sii.qty) AS total_qty
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		JOIN `tabProject` p ON p.name = si.project
		WHERE {' AND '.join(conds)} {exclude}
		GROUP BY sii.item_code, sii.item_name
		ORDER BY invoices DESC, total_qty DESC
		LIMIT %(limit)s
		""",
		params,
		as_dict=True,
	)
	return rows


def fitting_parts_for_job(job, dsg_code, family=None, limit=50):
	"""Catalogue items that fit the car AND belong to this job's category.

	Fitment: items whose Item DSG Compatibility includes the car's VAG dsg_code
	(e.g. 0AM, 0CW). Category: the item code or item name contains one of the job's
	`item_match_keywords` tokens (e.g. 'mec' for Mechatronics, 'clu'/'kop' for Clutch).
	So a Mechatronics template shows only the mechatronic items for that gearbox.

	Some categories (e.g. Oil Change) are not DSG-code-tagged but are keyed by the
	gearbox family in the item code/name (200OIL0001 / "DQ200 Olie..."). When the
	DSG-compatibility fitment finds nothing, fall back to a catalogue token match
	narrowed to the car's DSG family.
	"""
	tokens = [
		_norm(t)
		for t in re.split(r"[\n,]", frappe.db.get_value("Labour Job", job, "item_match_keywords") or "")
		if _norm(t)
	]
	if not tokens:
		return []

	out = []
	if dsg_code:
		rows = frappe.db.sql(
			"""
			SELECT DISTINCT i.item_code, i.item_name, i.item_group
			FROM `tabItem DSG Compatibility` c
			JOIN `tabItem` i ON i.name = c.parent
			WHERE c.dsg_code = %(dsg)s AND IFNULL(i.disabled, 0) = 0
			""",
			{"dsg": dsg_code},
			as_dict=True,
		)
		for r in rows:
			haystack = f"{r.item_code} {r.item_name or ''}".lower()
			if any(tok in haystack for tok in tokens):
				out.append(
					{"item_code": r.item_code, "item_name": r.item_name, "item_group": r.item_group, "source": "fit"}
				)

	# Fallback for family-keyed (non-DSG-tagged) categories like Oil Change.
	if not out:
		# e.g. family "DQ200" -> match items whose code/name contains "dq200" or "200".
		fam_keys = []
		if family:
			fl = family.lower()
			fam_keys = [fl, re.sub(r"^d[ql]", "", fl)]
			fam_keys = [k for k in fam_keys if k]
		cat = frappe.db.sql(
			"""
			SELECT item_code, item_name, item_group
			FROM `tabItem`
			WHERE IFNULL(disabled, 0) = 0
			""",
			as_dict=True,
		)
		for r in cat:
			haystack = f"{r.item_code} {r.item_name or ''}".lower()
			if not any(tok in haystack for tok in tokens):
				continue
			if fam_keys and not any(k in haystack for k in fam_keys):
				continue
			out.append(
				{"item_code": r.item_code, "item_name": r.item_name, "item_group": r.item_group, "source": "fit"}
			)

	out.sort(key=lambda x: x["item_code"])
	return out[:limit]


def transmission_parts_for_job(job, project, dsg_code=None, limit=50):
	"""Gearbox parts: the item that fits the car's transmission code.

	The car's transmission code (Project.transmission_code, a VAG 3-letter code such as
	'NSK') is matched against each Item's `transmission_code_list` compatibility table,
	yielding the gearbox SKU(s) built for that code. Falls back to the category fitment
	when the Project has no transmission code or nothing matches.
	"""
	code = (project.get("transmission_code") or "").strip()
	if not code:
		return fitting_parts_for_job(job, dsg_code)

	rows = frappe.db.sql(
		"""
		SELECT DISTINCT i.item_code, i.item_name, i.item_group
		FROM `tabTransmission code compatibility` t
		JOIN `tabItem` i ON i.name = t.parent
		WHERE t.transmission_code = %(code)s AND IFNULL(i.disabled, 0) = 0
		""",
		{"code": code},
		as_dict=True,
	)
	if not rows:
		return fitting_parts_for_job(job, dsg_code)

	return [
		{
			"item_code": r.item_code,
			"item_name": r.item_name,
			"item_group": r.item_group,
			"source": "oe",
			"match": "exact",
		}
		for r in rows
	][:limit]


def _tail4(value):
	"""Last 4 chars, spaces removed, upper-cased."""
	s = re.sub(r"\s+", "", str(value or "")).upper()
	return s[-4:]


def oe_pn_search_parts(job, project, dsg_code=None, engine_code=None, limit=50):
	"""Resolve a job's items by searching Item.oe_pn for the Project oe_pn value.

	For each Project field in `project_part_fields` (e.g. `mechatronic`), search
	Item.oe_pn (spaces ignored) for the value AND the value minus its last 3 chars
	— mechatronic numbers often carry a 3-char software suffix (e.g. "0AM 325 026 E
	Z3C") that must be dropped to match the bare part number. When several items
	match, the one whose item code ends with the same last 4 chars as the (trimmed)
	value is flagged `match="exact"` (rendered green); the rest are `candidate`.
	Falls back to catalogue fitment when the Project has no value.
	"""
	fields = [
		f.strip()
		for f in (frappe.db.get_value("Labour Job", job, "project_part_fields") or "").split(",")
		if f.strip()
	]

	results = []
	seen = set()
	any_value = False
	for fld in fields:
		raw = (project.get(fld) or "").strip()
		if not raw:
			continue
		any_value = True
		ns = re.sub(r"\s+", "", raw).upper()
		variants = [ns]
		if len(ns) > 3:
			variants.append(ns[:-3])

		conds, params = [], {}
		for i, v in enumerate(variants):
			params[f"v{i}"] = f"%{v}%"
			conds.append(f"UPPER(REPLACE(oe_pn, ' ', '')) LIKE %(v{i})s")

		rows = frappe.db.sql(
			f"""
			SELECT item_code, item_name, item_group
			FROM `tabItem`
			WHERE IFNULL(disabled, 0) = 0 AND ({' OR '.join(conds)})
			""",
			params,
			as_dict=True,
		)

		tails = {_tail4(v) for v in variants}
		for r in rows:
			if r.item_code in seen:
				continue
			seen.add(r.item_code)
			results.append(
				{
					"item_code": r.item_code,
					"item_name": r.item_name,
					"item_group": r.item_group,
					"source": "oe",
					"match": "exact" if _tail4(r.item_code) in tails else "candidate",
				}
			)

	if not any_value:
		return fitting_parts_for_job(job, dsg_code)

	# Exact (green) matches first.
	results.sort(key=lambda x: (x["match"] != "exact", x["item_code"]))
	matched = results[:limit]

	# Sold-together: anchor on the matched mechatronic, exact first, then fall through
	# the candidates until one has sales-invoice history (the exact part may never
	# have been invoiced even though a superseding/candidate variant was). Search the
	# broad history first (the mechatronic part number is already car-specific); only
	# if nothing is found, retry with the engine/DSG filter. Redundant sold-with items
	# that duplicate a sub-category already matched in another job are removed globally
	# in build_quotation_suggestions.
	matched_codes = {p["item_code"] for p in matched}
	enrich = []
	for filt in (False, True):
		for p in matched:
			enrich = sold_with_items(
				[p["item_code"]],
				engine_code=engine_code if filt else None,
				dsg_code=dsg_code if filt else None,
				exclude=matched_codes,
			)
			if enrich:
				break
		if enrich:
			break
	return matched + enrich


def _resolve_item_from_partno(partno):
	"""Best-effort map an OEM part-number string to an Item. Returns item_code or None."""
	npn = re.sub(r"\s+", " ", (partno or "").strip())
	if not npn:
		return None
	for fld in ("tvs_pn", "oem_pn", "oe_pn", "default_manufacturer_part_no", "item_code"):
		hit = frappe.db.sql(
			f"SELECT item_code FROM `tabItem` "
			f"WHERE UPPER(REGEXP_REPLACE({fld}, '[[:space:]]+', ' ')) = %s LIMIT 1",
			(npn.upper(),),
		)
		if hit:
			return hit[0][0]
	return None


def oem_reference_parts(job, project):
	"""The car's specific OEM part numbers for this job, from the Project fields
	listed in Labour Job.project_part_fields. Resolved to an Item when possible."""
	fields = [
		f.strip()
		for f in (frappe.db.get_value("Labour Job", job, "project_part_fields") or "").split(",")
		if f.strip()
	]
	refs = []
	for fld in fields:
		partno = (project.get(fld) or "").strip()
		if not partno:
			continue
		refs.append(
			{
				"project_field": fld,
				"part_no": partno,
				"item_code": _resolve_item_from_partno(partno),
			}
		)
	return refs


def cross_reference_oe_pns(oe_pns):
	"""POST the OE part numbers to the parts-integration cross-reference service.

	Returns (results, error). `results` is the list of per-oe_pn entries from the
	service (each with an `oem_pn` array); `error` is a message string on failure.
	"""
	oe_pns = [p for p in (oe_pns or []) if p and str(p).strip()]
	if not oe_pns:
		return [], None

	base = (frappe.db.get_single_value("Rest Config", "aws_url") or "").strip()
	if not base:
		return [], _("Rest Config base URL (aws_url) is not configured.")

	url = base.rstrip("/") + "/parts-integration/cross-reference"
	try:
		import requests

		resp = requests.post(url, json={"oe_pns": oe_pns}, timeout=15)
		resp.raise_for_status()
		return (resp.json() or {}).get("results", []), None
	except Exception as e:  # noqa: BLE001 — surface any failure as a soft message + fallback
		frappe.log_error(frappe.get_traceback(), "Parts cross-reference failed")
		return [], str(e)


def _item_subcats(item_codes):
	"""Map each item_code -> its Item.sub_category_name (e.g. FLYWHEEL / CLUTCH)."""
	codes = [c for c in (item_codes or []) if c]
	if not codes:
		return {}
	rows = frappe.get_all(
		"Item", filters={"name": ["in", codes]}, fields=["name", "sub_category_name"]
	)
	return {r.name: r.sub_category_name for r in rows}


def _items_by_oem_pn(oem_pns):
	"""Items whose oem_pn matches any of `oem_pns`, comparing whitespace-insensitively."""
	targets = {re.sub(r"\s+", "", str(p)).upper() for p in (oem_pns or []) if str(p).strip()}
	if not targets:
		return []
	return frappe.db.sql(
		"""
		SELECT item_code, item_name, item_group
		FROM `tabItem`
		WHERE IFNULL(disabled, 0) = 0
		  AND UPPER(REPLACE(oem_pn, ' ', '')) IN %(targets)s
		""",
		{"targets": tuple(targets)},
		as_dict=True,
	)


def sold_with_items(item_codes, engine_code=None, dsg_code=None, exclude=None, limit=12):
	"""Items historically sold alongside `item_codes` on the same car config.

	Reuses get_item_insights' co-occurrence (frequently_used_with), filtered to the
	car's engine/DSG, excluding labour lines and anything already in `exclude`.
	"""
	from erpnext.stock.doctype.item.item import get_item_insights

	seen = set(exclude or [])
	out = []
	for code in item_codes:
		try:
			insights = get_item_insights(code, engine_codes=engine_code or "", dsg_codes=dsg_code or "")
		except Exception:  # noqa: BLE001
			continue
		for f in insights.get("frequently_used_with") or []:
			if f.get("is_labour"):
				continue
			ic = f.get("item_code")
			if not ic or ic in seen:
				continue
			seen.add(ic)
			out.append(
				{
					"item_code": ic,
					"item_name": f.get("item_name"),
					"item_group": None,
					"source": "sold_with",
					"co_occurrence": f.get("co_occurrence_count"),
				}
			)
			if len(out) >= limit:
				return out
	return out


def crossref_parts_for_job(job, project, engine_code=None, dsg_code=None):
	"""Clutch/Flywheel parts via OE→OEM cross-reference, then sold-together enrichment.

	Takes the car's oe_pn from the Project fields in `project_part_fields`, cross-
	references them to OEM numbers, matches Items by oem_pn, then adds items sold
	with those. Falls back to the category fitment when no oe_pn / no service / no match.
	Returns (parts, messages).
	"""
	messages = []
	fields = [
		f.strip()
		for f in (frappe.db.get_value("Labour Job", job, "project_part_fields") or "").split(",")
		if f.strip()
	]
	oe_pns = [(project.get(f) or "").strip() for f in fields]
	oe_pns = [p for p in oe_pns if p]
	if not oe_pns:
		return fitting_parts_for_job(job, dsg_code), messages

	results, error = cross_reference_oe_pns(oe_pns)
	if error:
		messages.append(_("Parts cross-reference failed for {0} — used catalogue fitment instead.").format(job))
		return fitting_parts_for_job(job, dsg_code), messages

	oem_pns = []
	for r in results:
		oem_pns.extend(r.get("oem_pn") or [])

	oe_parts = []
	seen = set()
	for it in _items_by_oem_pn(oem_pns):
		if it["item_code"] in seen:
			continue
		seen.add(it["item_code"])
		oe_parts.append({**it, "source": "oe", "match": "exact"})

	# The catalogue-fitting SKUs for this job/car carry the invoice history (the OE
	# part numbers often map to specific SKUs that were rarely invoiced), so use them
	# to anchor the sold-together search — and as the fit list if no OE item matched.
	category = fitting_parts_for_job(job, dsg_code)
	category_codes = {p["item_code"] for p in category}

	if oe_parts:
		parts = oe_parts
	else:
		messages.append(
			_("No catalogue items matched the cross-referenced OEM numbers for {0} — used catalogue fitment.").format(job)
		)
		parts = category
		seen = set(category_codes)

	anchors = seen | category_codes
	# Sold-together history. Redundant sold-with items (e.g. another flywheel/clutch that
	# duplicates a part already matched in another job) are removed globally afterwards in
	# build_quotation_suggestions, where the whole bundle's sub-categories are known.
	sold = sold_with_items(
		list(anchors), engine_code=engine_code, dsg_code=dsg_code, exclude=anchors
	)
	parts = list(parts) + sold
	return parts, messages


def _attach_bundle_subitems(parts):
	"""Attach each suggested part's component sub-items so they follow it into the quote.

	Sub-items come from the Item's own `subitems_list` child table (Items Relate:
	item_code, qty, ...). If the item has none, fall back to a Product Bundle definition
	keyed by the same item_code. We tag `sub_items_source` so the client knows how to add
	them: "item" rows must be appended explicitly; "bundle" rows are expanded automatically
	by the Quotation Item product-bundle trigger.
	"""
	for p in parts or []:
		code = p.get("item_code")
		if not code:
			continue

		subs = []
		for row in frappe.get_all(
			"Items Relate",
			filters={"parent": code, "parenttype": "Item", "parentfield": "subitems_list"},
			fields=["item_code", "qty"],
			order_by="idx",
		):
			if not row.item_code:
				continue
			subs.append(
				{
					"item_code": row.item_code,
					"item_name": frappe.db.get_value("Item", row.item_code, "item_name") or row.item_code,
					"qty": frappe.utils.flt(row.qty) or 1,
				}
			)
		if subs:
			p["sub_items"] = subs
			p["sub_items_source"] = "item"
			continue

		# Fallback: a Product Bundle keyed by this item_code (expanded by the JS trigger).
		if frappe.db.exists("Product Bundle", {"name": code, "disabled": 0}, cache=True):
			for row in frappe.get_all(
				"Product Bundle Item",
				filters={"parent": code, "parenttype": "Product Bundle"},
				fields=["item_code", "qty", "description"],
				order_by="idx",
			):
				if not row.item_code:
					continue
				subs.append(
					{
						"item_code": row.item_code,
						"item_name": frappe.db.get_value("Item", row.item_code, "item_name") or row.description or row.item_code,
						"qty": frappe.utils.flt(row.qty) or 1,
					}
				)
			if subs:
				p["sub_items"] = subs
				p["sub_items_source"] = "bundle"
	return parts


def _dedupe_sold_with_by_subcategory(jobs):
	"""Drop sold-with items whose sub-category is already matched elsewhere in the bundle.

	Across all jobs, the primary (OE-matched / catalogue-fit) suggestions establish which
	part sub-categories the quotation already covers — e.g. the Flywheel job matches a
	FLYWHEEL, the Clutch job a CLUTCH. The Mechatronics job's sold-together history then
	lists another flywheel/clutch that was invoiced alongside the mechatronic; those are
	duplicates of parts already in the list, so any sold-with item whose sub-category is
	already covered by a primary part is removed. Sold-with items of a NOT-yet-covered
	sub-category are kept (genuine complements). Mutates `jobs` in place.
	"""
	# Sub-categories already covered by a primary (non sold-with) suggestion anywhere.
	primary_codes = [
		p["item_code"]
		for jb in jobs
		for p in jb["suggested_parts"]
		if p.get("source") != "sold_with" and p.get("item_code")
	]
	primary_subcats = {sc for sc in _item_subcats(primary_codes).values() if sc}
	if not primary_subcats:
		return

	for jb in jobs:
		sold_codes = [
			p["item_code"]
			for p in jb["suggested_parts"]
			if p.get("source") == "sold_with" and p.get("item_code")
		]
		if not sold_codes:
			continue
		sub_map = _item_subcats(sold_codes)
		jb["suggested_parts"] = [
			p
			for p in jb["suggested_parts"]
			if not (p.get("source") == "sold_with" and sub_map.get(p["item_code"]) in primary_subcats)
		]


@frappe.whitelist()
def build_quotation_suggestions(project):
	"""Assemble the diagnosis-driven suggestion bundle for a Project.

	Read-only: keyed off the Project so it works before the Quotation is saved.
	The client renders the bundle and appends the chosen lines to the Quotation
	in memory; nothing is written here.
	"""
	from erpnext.selling.doctype.standard_labour_hours.standard_labour_hours import (
		get_standard_labour_hours,
	)

	messages = []
	if not project:
		frappe.throw(_("Link this Quotation to a Project first (Project name)."))

	proj_doc = frappe.get_doc("Project", project)
	proj_doc.check_permission("read")
	project = proj_doc.as_dict()
	engine_code = (project.get("engine_code") or "").strip() or None
	dsg_code = (project.get("dsg_code") or "").strip() or None
	family = dsg_family_from_project(project)
	if not family:
		messages.append(
			_("Could not determine the DSG family from the Project (dsg_model) — labour hours will be unavailable.")
		)

	# Detect jobs from the 'Reparatie advies' section only (the work to quote), not
	# the whole diagnosis. Fall back to the full text / problem description if absent.
	diag_html = project.get("diagnose_result")
	repair_advice = extract_repair_advice(diag_html)
	if repair_advice:
		diagnosis_text = repair_advice
	elif diag_html:
		diagnosis_text = _strip_html(diag_html)
		messages.append(_("No 'Reparatie advies' section found — scanned the full diagnosis."))
	else:
		diagnosis_text = project.get("client_description") or ""

	detected = detect_jobs_from_text(diagnosis_text)
	if not detected:
		messages.append(_("No labour jobs detected in the Project diagnosis."))

	labour_sku = next(iter(sorted(_labour_skus())), None)

	jobs = []
	for d in detected:
		job = d["job"]
		variants = []
		if family:
			variants = get_standard_labour_hours(dsg_code=family, job=job) or []

		# Resolve parts: Clutch/Flywheel via OE→OEM cross-reference, Mechatronics via
		# local Item.oe_pn search, Gearbox via the transmission-code compatibility table,
		# everything else by item-match-keyword fitment.
		flags = frappe.db.get_value(
			"Labour Job", job, ["use_oe_crossref", "use_oe_pn_search", "use_transmission_search"], as_dict=True
		) or {}
		if flags.get("use_oe_crossref"):
			parts, part_msgs = crossref_parts_for_job(job, project, engine_code=engine_code, dsg_code=dsg_code)
			messages.extend(part_msgs)
		elif flags.get("use_oe_pn_search"):
			parts = oe_pn_search_parts(job, project, dsg_code=dsg_code, engine_code=engine_code)
		elif flags.get("use_transmission_search"):
			parts = transmission_parts_for_job(job, project, dsg_code=dsg_code)
		else:
			parts = fitting_parts_for_job(job, dsg_code, family=family)

		_attach_bundle_subitems(parts)

		jobs.append(
			{
				"job": job,
				"matched_keyword": d["matched_keyword"],
				"suggested_parts": parts,
				"oem_refs": oem_reference_parts(job, project),
				"labour": {"available": bool(variants), "variants": variants},
			}
		)

	_dedupe_sold_with_by_subcategory(jobs)

	return {
		"project": project.get("name"),
		"car": {
			"engine_code": engine_code,
			"dsg_code": dsg_code,
			"dsg_model": project.get("dsg_model"),
			"dsg_family": family,
		},
		"labour_item_code": labour_sku,
		"repair_advice": repair_advice,
		"jobs": jobs,
		"messages": messages,
	}


@frappe.whitelist()
def apply_suggestions_to_quotation(quotation, rows):
	"""Append the user-confirmed rows to the Quotation's items.

	`rows` is a JSON list of {item_code, qty, description?}. Labour lines are just
	rows whose item_code is the labour SKU with qty = hours; the client composes
	their description. Returns the number of rows added.
	"""
	rows = frappe.parse_json(rows)
	if not rows:
		return {"added": 0}

	quo = frappe.get_doc("Quotation", quotation)
	quo.check_permission("write")
	if quo.docstatus != 0:
		frappe.throw(_("Cannot add items to a submitted or cancelled Quotation."))

	added = 0
	for row in rows:
		item_code = (row.get("item_code") or "").strip()
		if not item_code:
			continue
		if not frappe.db.exists("Item", item_code):
			frappe.throw(_("Item {0} does not exist.").format(item_code))
		child = quo.append(
			"items",
			{
				"item_code": item_code,
				"qty": frappe.utils.flt(row.get("qty")) or 1,
			},
		)
		if row.get("description"):
			child.description = row.get("description")
		added += 1

	quo.save()
	return {"added": added, "quotation": quo.name}
