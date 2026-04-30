// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Queue Settings", {
  refresh: function (frm) {
    frm.trigger('toggle_lanes');
  },
  lanes_enabled: function (frm) {
    frm.trigger('toggle_lanes');
  },
  toggle_lanes: function (frm) {
    frm.toggle_display('sb_lanes', frm.doc.lanes_enabled);
    frm.toggle_display('fast_cars_per_day', frm.doc.lanes_enabled);
    frm.toggle_display('heavy_cars_per_day', frm.doc.lanes_enabled);
  },
  validate: function (frm) {
    const check_positive = (val, label) => {
      const num = Number(val);
      if (num <= 0 || !Number.isInteger(num)) {
        frappe.msgprint(__('The value for {0} must be greater than 0.', [__(label)]));
        frappe.validated = false;
      }
    };

    if (frm.doc.lanes_enabled) {
      check_positive(frm.doc.fast_cars_per_day, 'Fast Cars per Day');
      check_positive(frm.doc.heavy_cars_per_day, 'Heavy Cars per Day');
    }
  }
});
