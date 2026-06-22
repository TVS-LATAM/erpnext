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


def fitting_parts_for_job(job, dsg_code, limit=50):
	"""Catalogue items that fit the car AND belong to this job's category.

	Fitment: items whose Item DSG Compatibility includes the car's VAG dsg_code
	(e.g. 0AM, 0CW). Category: the item code or item name contains one of the job's
	`item_match_keywords` tokens (e.g. 'mec' for Mechatronics, 'clu'/'kop' for Clutch).
	So a Mechatronics template shows only the mechatronic items for that gearbox.
	"""
	if not dsg_code:
		return []
	tokens = [
		_norm(t)
		for t in re.split(r"[\n,]", frappe.db.get_value("Labour Job", job, "item_match_keywords") or "")
		if _norm(t)
	]
	if not tokens:
		return []

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

	out = []
	for r in rows:
		haystack = f"{r.item_code} {r.item_name or ''}".lower()
		if any(tok in haystack for tok in tokens):
			out.append(
				{"item_code": r.item_code, "item_name": r.item_name, "item_group": r.item_group, "source": "fit"}
			)
	out.sort(key=lambda x: x["item_code"])
	return out[:limit]


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

	base = (frappe.db.get_single_value("Parts Integration Settings", "base_url") or "").strip()
	if not base:
		return [], _("Parts Integration base URL is not configured.")

	url = base.rstrip("/") + "/parts-integration/cross-reference"
	try:
		import requests

		resp = requests.post(url, json={"oe_pns": oe_pns}, timeout=15)
		resp.raise_for_status()
		return (resp.json() or {}).get("results", []), None
	except Exception as e:  # noqa: BLE001 — surface any failure as a soft message + fallback
		frappe.log_error(frappe.get_traceback(), "Parts cross-reference failed")
		return [], str(e)


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

	parts = []
	seen = set()
	for it in _items_by_oem_pn(oem_pns):
		if it["item_code"] in seen:
			continue
		seen.add(it["item_code"])
		parts.append({**it, "source": "oe"})

	if not parts:
		messages.append(_("No catalogue items matched the cross-referenced OEM numbers for {0}.").format(job))

	# Sold-together enrichment for the cross-reference path.
	parts.extend(
		sold_with_items(
			[p["item_code"] for p in parts], engine_code=engine_code, dsg_code=dsg_code, exclude=seen
		)
	)
	return parts, messages


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

		# Clutch/Flywheel resolve parts via OE→OEM cross-reference; others by catalogue
		# fitment on the job's item-match keywords.
		if frappe.db.get_value("Labour Job", job, "use_oe_crossref"):
			parts, part_msgs = crossref_parts_for_job(job, project, engine_code=engine_code, dsg_code=dsg_code)
			messages.extend(part_msgs)
		else:
			parts = fitting_parts_for_job(job, dsg_code)

		jobs.append(
			{
				"job": job,
				"matched_keyword": d["matched_keyword"],
				"suggested_parts": parts,
				"oem_refs": oem_reference_parts(job, project),
				"labour": {"available": bool(variants), "variants": variants},
			}
		)

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
