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


@frappe.whitelist()
def build_quotation_suggestions(quotation):
	"""Assemble the diagnosis-driven suggestion bundle for a Quotation's Project."""
	from erpnext.selling.doctype.standard_labour_hours.standard_labour_hours import (
		get_standard_labour_hours,
	)

	quo = frappe.get_doc("Quotation", quotation)
	quo.check_permission("read")

	messages = []
	if not quo.project_name:
		frappe.throw(_("Link this Quotation to a Project first (Project name)."))

	project = frappe.get_doc("Project", quo.project_name).as_dict()
	engine_code = (project.get("engine_code") or "").strip() or None
	dsg_code = (project.get("dsg_code") or "").strip() or None
	family = dsg_family_from_project(project)
	if not family:
		messages.append(
			_("Could not determine the DSG family from the Project (dsg_model) — labour hours will be unavailable.")
		)

	diagnosis = project.get("diagnose_result") or project.get("client_description")
	detected = detect_jobs_from_text(diagnosis)
	if not detected:
		messages.append(_("No labour jobs detected in the Project diagnosis."))

	labour_sku = next(iter(sorted(_labour_skus())), None)

	jobs = []
	for d in detected:
		job = d["job"]
		variants = []
		if family:
			variants = get_standard_labour_hours(dsg_code=family, job=job) or []
		jobs.append(
			{
				"job": job,
				"matched_keyword": d["matched_keyword"],
				"suggested_parts": suggest_parts_for_job(job, engine_code=engine_code, dsg_code=dsg_code),
				"oem_refs": oem_reference_parts(job, project),
				"labour": {"available": bool(variants), "variants": variants},
			}
		)

	return {
		"quotation": quo.name,
		"project": quo.project_name,
		"car": {
			"engine_code": engine_code,
			"dsg_code": dsg_code,
			"dsg_model": project.get("dsg_model"),
			"dsg_family": family,
		},
		"labour_item_code": labour_sku,
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
