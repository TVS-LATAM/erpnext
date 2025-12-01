# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors and contributors
# For license information, please see license.txt


from frappe.model.document import Document


class ProductBundleItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		description: DF.TextEditor | None
		description_visible: DF.Check
		is_stock_item: DF.Check
		item_code: DF.Link
		oe_pn: DF.Data | None
		oem_pn: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		qty: DF.Float
		sub_category_name: DF.Link | None
		tvs_pn: DF.Data | None
	# end: auto-generated types

	pass
