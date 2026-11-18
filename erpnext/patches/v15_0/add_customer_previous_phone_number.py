import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Set by customer_phone_sync when the phone number changes. Hidden on the form;
# it rides along in the "on customer updated" webhook so the cloud side can
# re-key the data it stores under the old number (projects, quotations,
# pending notifications). No fixtures hook exists in this app, hence a patch.
CUSTOM_FIELDS = {
	"Customer": [
		{
			"fieldname": "previous_phone_number",
			"label": "Previous phone number",
			"fieldtype": "Data",
			"insert_after": "is_phone_number_verified",
			"read_only": 1,
			"hidden": 1,
			"no_copy": 1,
			"print_hide": 1,
			"report_hide": 1,
		}
	]
}


def execute():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=frappe.flags.in_patch)
