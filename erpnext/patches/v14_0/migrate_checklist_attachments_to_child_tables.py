import frappe

# Maps each checklist DocType to the child-table fieldname / child DocType that
# now holds its files after the single Attach fields were replaced by tables.
CHECKLIST_DOCTYPES = (
	"Arrival Checklist",
	"Job Checklist",
	"Quality Control Checklist",
	"DSG Oil Change Checklist",
)


def execute():
	"""Move legacy single-file values into the new attachment child tables.

	The `photo` (Attach Image) and `attachment` (Attach) fields were replaced by
	the `photos` (Checklist Photo) and `attachments` (Checklist Attachment) child
	tables. The old columns are orphaned after the schema sync but still hold the
	previously uploaded urls, so we read them with raw SQL (they are no longer in
	the DocType meta) and copy each value into a child row. Idempotent: rows that
	already have child entries are skipped.
	"""
	for doctype in CHECKLIST_DOCTYPES:
		table = f"tab{doctype}"
		existing_columns = {
			column.Field for column in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`", as_dict=True)
		}

		has_photo = "photo" in existing_columns
		has_attachment = "attachment" in existing_columns
		if not (has_photo or has_attachment):
			continue

		select_columns = ["name"]
		if has_photo:
			select_columns.append("photo")
		if has_attachment:
			select_columns.append("attachment")

		rows = frappe.db.sql(
			"SELECT {} FROM `{}`".format(", ".join(f"`{c}`" for c in select_columns), table),
			as_dict=True,
		)

		for row in rows:
			photo = row.get("photo")
			attachment = row.get("attachment")
			if not (photo or attachment):
				continue

			doc = frappe.get_doc(doctype, row["name"])
			changed = False

			if photo and not doc.get("photos"):
				doc.append("photos", {"image": photo})
				changed = True

			if attachment and not doc.get("attachments"):
				doc.append("attachments", {"file": attachment})
				changed = True

			if changed:
				doc.save(ignore_permissions=True)

	frappe.db.commit()
