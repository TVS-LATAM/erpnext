# Copyright (c) 2026, TVS and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from erpnext.projects.checklist_templates import seed_rows


class JobChecklist(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from erpnext.projects.doctype.checklist_attachment.checklist_attachment import ChecklistAttachment
		from erpnext.projects.doctype.checklist_item.checklist_item import ChecklistItem
		from erpnext.projects.doctype.checklist_photo.checklist_photo import ChecklistPhoto
		from frappe.types import DF

		attachments: DF.Table[ChecklistAttachment]
		check_date: DF.Date | None
		checked_by: DF.Link | None
		job_items: DF.Table[ChecklistItem]
		notes: DF.Text | None
		photos: DF.Table[ChecklistPhoto]
		project: DF.Link | None
	# end: auto-generated types
	def before_insert(self):
		# Server-side backstop (design Decision 2): the client `onload` seed
		# path in checklist_grid.js is DOM-bound and races the initial paint,
		# so a doc inserted via the API/Data Import/console with no client
		# involved still gets its fixed rows. Idempotent -- a no-op if the
		# client already seeded them.
		seed_rows(self)
