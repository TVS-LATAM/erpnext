# Copyright (c) 2026, TVS and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from erpnext.projects.checklist_templates import seed_rows


class DSGOilChangeChecklist(Document):
	def before_insert(self):
		# Server-side backstop (design Decision 2): the client `onload` seed
		# path in checklist_grid.js is DOM-bound and races the initial paint,
		# so a doc inserted via the API/Data Import/console with no client
		# involved still gets its fixed rows. Idempotent -- a no-op if the
		# client already seeded them.
		seed_rows(self)
