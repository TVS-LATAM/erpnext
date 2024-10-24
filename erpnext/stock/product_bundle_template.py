import frappe

class ProductBundleTemplate:
    def __init__(self):
        self.item_code = None
        self.price_list = "Standard Selling"

    def set_item_code(self, item_code):
        if not item_code or item_code.strip() == "":
            return self  
        self.item_code = item_code
        return self
    
    def set_price_list(self, price_list):
        if not price_list or price_list.strip() == "":
            price_list = "Standard Selling"
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
            "item_code": item_details.name,
            "description": item_details.description,
            "subitems_list": self.get_sub_items(subitems_list)
        }

    def get_item_price(self, item_details):
        try:
            print("get_item_price: ", item_details.__dict__)

            price_list_rate = frappe.db.get_value(
                "Item Price", 
                {
                    "item_code": item_details.get('item_code'), 
                    "price_list": self.price_list
                },
                "price_list_rate"
            )
            if price_list_rate is None:
                price_list_rate = item_details.get('rate')
        except Exception:
            price_list_rate = 0

        return price_list_rate
    
    def get_sub_items(self, subitems_list):
        array_subitems = []
        
        if not subitems_list or not isinstance(subitems_list, list):
            return array_subitems
        for item in subitems_list:
            try:
                item_code = item.get("item_code", None)
                description = item.get("description", "No description available")
                description_visible = item.get("description_visible", "No UOM specified")
                qty = item.get("qty", 0)
            except AttributeError:
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
                "price": self.get_item_price(item),
                "sub_items": self.get_product_bundle_sub_items(item_code)
            })
            
        return array_subitems
    
    def get_product_bundle_sub_items(self, item_code):
        try:
            item = frappe.get_doc("Item", item_code)
            items = item.get("subitems_list", [])
            if not items or not isinstance(items, list):
                return []
            
            sub_items = []
            for item in items:
                code = item.get("item_code", "")
                sub_items.append({
                    "item_code": code,
                    "description": item.get("description", code),
                    "stock_uom": item.get("stock_uom", ""),
                    "stock_uom_qty": item.get("qty_unit_measure", 0),
                    "price": self.get_item_price(item),
                    "options": item.get("options", ""),
                    "qty": item.get("qty", 0),
                    "tvs_pn": item.get("tvs_pn", ""),
                    "rate": self.get_item_price(item),
                })
            return sub_items
        except Exception:
            return []