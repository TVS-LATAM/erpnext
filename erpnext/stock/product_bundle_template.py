from decimal import Decimal
from os import name
import frappe

class ProductBundleTemplate:
    def __init__(self):
        self.item_code = None
        self.price_list = "Retail"

    def set_item_code(self, item_code):
        if not item_code or item_code.strip() == "":
            return self  
        self.item_code = item_code
        return self
    
    def set_price_list(self, price_list):
        if not price_list or price_list.strip() == "":
            price_list = "Retail"
        self.price_list = price_list
        return self

    def validate(self):
        if not self.item_code or self.item_code.strip() == "":
            return self  
        return self
    
    def searchProductBundle(self):
        try:
            item_details = frappe.get_doc("Product Bundle", self.item_code)
            if not item_details:
                return None
        except Exception:    
            return None

        subitems_list = getattr(item_details, 'items', [])
        
        if not isinstance(subitems_list, list):
            return None
        return {
            "is_product_bundle": 1,
            "item_code": item_details.name,
            "description": item_details.description,
            "subitems_list": self.get_sub_items(subitems_list, item_details.name),
            "name": item_details.name
        }

    def get_item_price(self, item_details):
        try:
            # print("==========> get_item_price: ", item_details.__dict__)
            price_list_rate = frappe.db.get_value(
                "Item Price", 
                {
                    "item_code": item_details.get('item_code'), 
                    "price_list": self.price_list
                },
                "price_list_rate"
            )
            if price_list_rate is None:
                price_list_rate = item_details.get('standard_rate')  # valuation_rate
        except Exception as e:
            price_list_rate = 0

        return price_list_rate
    
    def get_sub_items(self, subitems_list, product_bundle_name):
        array_subitems = []
        
        if not subitems_list or not isinstance(subitems_list, list):
            return array_subitems
        for item in subitems_list:
            try:
                name = item.get("name")
                item_code = item.get("item_code", None)
                description = item.get("description", "No description available")
                description_visible = item.get("description_visible", "No UOM specified")
                qty = Decimal(item.get("qty", 0))
                is_stock_item = item.get("is_stock_item", 0)
            except AttributeError:
                name = None
                item_code = None
                description = "No description available"
                description_visible = "No UOM specified"
                qty = 0

            if not item_code:
                continue

            array_subitems.append({
                "item_code": item_code,
                "description": description,
                "description_visible": description_visible,
                "qty": qty,
                "is_stock_item": is_stock_item,
                "price": self.get_item_price(item),
                "sub_items": self.get_product_bundle_sub_items(item_code, product_bundle_name, item.get("name")),
                "_parent": product_bundle_name,  # Referencia al Product Bundle principal
                "name": item.get("name")
            })
            
        return array_subitems
    
    def get_product_bundle_sub_items(self, item_code, product_bundle_name, parent_item_name):
        try:
            item = frappe.get_doc("Item", item_code)
            items = item.get("subitems_list", [])
            if not items or not isinstance(items, list):
                return []
            sub_items = []
            for sub_item in items:
                code = sub_item.get("item_code", "")
                sub_items.append({
                    "item_code": code,
                    "description": sub_item.get("description", code),
                    "stock_uom": sub_item.get("stock_uom", ""),
                    "stock_uom_qty": sub_item.get("qty_unit_measure", 0),
                    "price": self.get_item_price(sub_item),
                    "options": sub_item.get("options", ""),
                    "qty": Decimal(sub_item.get("qty", 0)),
                    "tvs_pn": sub_item.get("tvs_pn", ""),
                    "rate": self.get_item_price(sub_item),
                    "_parent": parent_item_name,  # Referencia al item padre inmediato
                    "_product_bundle": product_bundle_name  # Referencia al Product Bundle principal
                })
            return sub_items
        except Exception:
            return []
