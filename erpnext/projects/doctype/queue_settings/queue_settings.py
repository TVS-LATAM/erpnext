# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from frappe.integrations.utils import make_post_request
import json



class QueueSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from erpnext.projects.doctype.job_workload_item.job_workload_item import JobWorkloadItem
		from frappe.types import DF

		auto_move_paused: DF.Check
		aws_url: DF.Data | None
		job_workload_status: DF.Table[JobWorkloadItem]
		fast_cars_per_day: DF.Int
		heavy_cars_per_day: DF.Int
		lanes_enabled: DF.Check
		vacations_mode: DF.Check
	# end: auto-generated types
	def on_update(self):
		if self.aws_url:
			url = f"{self.aws_url}/queue-settings/updated"
			data = self.as_dict(convert_dates_to_str=True)

			make_post_request(
				url,
				headers={"Content-Type": "application/json"},
				data=json.dumps(data),
			)
	pass
