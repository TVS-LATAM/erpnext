# Copyright (c) 2026, TVS and contributors
# For license information, please see license.txt

from frappe.core.doctype.file.file import File

# Files attached to these doctypes must always be private and stay private.
# Covers the parent checklists (uploads attach to the parent document) and the
# child tables, as a safeguard against any other attachment path.
FORCE_PRIVATE_DOCTYPES = {
	"Arrival Checklist",
	"Job Checklist",
	"Quality Control Checklist",
	"DSG Oil Change Checklist",
	"Checklist Photo",
	"Checklist Attachment",
}


class ChecklistFile(File):
	"""Forces files attached to the project checklists to be private.

	Privacy is set before ``save_file`` runs so the file is written to the
	private path from the start, and re-enforced on validate so it cannot be
	flipped to public afterwards (including via the API).
	"""

	def before_insert(self):
		if self.attached_to_doctype in FORCE_PRIVATE_DOCTYPES:
			self.is_private = 1
		super().before_insert()

	def validate(self):
		if self.attached_to_doctype in FORCE_PRIVATE_DOCTYPES:
			self.is_private = 1
		super().validate()
