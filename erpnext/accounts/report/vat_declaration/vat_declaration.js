// VAT Declaration – Client (PDF/Export) – No client-side math
// - Muestra net y vat calculados en servidor
// - Botones PDF/Excel y ajustes visuales

frappe.query_reports["VAT Declaration"] = {
  filters: [
    {
      fieldname: "company",
      label: __("Company"),
      fieldtype: "Link",
      options: "Company",
      default: frappe.defaults.get_user_default("Company"),
      reqd: 1
    },
    {
      fieldname: "from_date",
      label: __("From Date"),
      fieldtype: "Date",
      default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
      reqd: 1
    },
    {
      fieldname: "to_date",
      label: __("To Date"),
      fieldtype: "Date",
      default: frappe.datetime.get_today(),
      reqd: 1
    },
    {
      fieldname: "frequency",
      label: __("Frequency"),
      fieldtype: "Select",
      options: "Monthly\nQuarterly\nYearly",
      default: "Quarterly",
      reqd: 1
    }
  ],

  formatter: function(value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (["net","vat"].includes(column.fieldname)) {
      value = `<span style="font-weight:bold;">${value}</span>`;
    }
    if (data && data.rubric === "5c" && column.fieldname === "vat") {
      value = `<span style="font-weight:bold;color:${(data.vat >= 0 ? "red" : "green")}">${value}</span>`;
    }
    return value;
  },

  onload: async function(report) {
    setTimeout(function() {
      $('.datatable, .dt-scrollable, .report-wrapper, .dt-header').css({'width':'100%','max-width':'100%'});
      if (report.datatable) report.datatable.refresh();
    }, 250);

    $(window).on('resize', function() {
      if (report.datatable) {
        report.datatable.refresh();
        $('.datatable, .dt-scrollable, .report-wrapper, .dt-header').css({'width':'100%','max-width':'100%'});
      }
    });

    // PDF
    report.page.add_inner_button(__('Download PDF'), async function() {
      const filters = report.get_values();
      const title = __("VAT Declaration") + ": " +
        frappe.datetime.str_to_user(filters.from_date) + " - " +
        frappe.datetime.str_to_user(filters.to_date);

      const rd = report.data || [];

      function fmt(v) { return frappe.format(v, {fieldtype: 'Currency'}); }
      function safe(v) { return (v===undefined||v===null||v==="") ? "-" : fmt(v); }

      // Render tabla a partir de datos server: net & vat
      const block = (rows) => rows.map(r => `
        <tr>
          <td>${frappe.utils.escape_html(r.description || "")}</td>
          <td class="text-right">${safe(r.net)}</td>
          <td class="text-right">${safe(r.vat)}</td>
        </tr>
      `).join("");

      const html = `
      <div class="vat-declaration-report" style="width:100%;">
        <div class="table-responsive" style="width:100%;">
          <table class="table table-bordered vat-table" style="width:100%!important;table-layout:fixed;">
            <thead>
              <tr>
                <th style="width:60%;">${__("Omschrijving")}</th>
                <th style="width:20%;" class="text-right">${__("Grondslag")}</th>
                <th style="width:20%;" class="text-right">${__("Btw")}</th>
              </tr>
            </thead>
            <tbody>
              <tr class="group-header"><td colspan="3"><strong>1. Prestaties binnenland</strong></td></tr>
              ${block([rd[0], rd[1], rd[2], rd[3], rd[4]])}

              <tr class="group-header"><td colspan="3"><strong>2. Verleggingsregelingen binnenland</strong></td></tr>
              ${block([rd[5]])}

              <tr class="group-header"><td colspan="3"><strong>3. Prestaties naar of in het buitenland</strong></td></tr>
              ${block([rd[6], rd[7], rd[8]])}

              <tr class="group-header"><td colspan="3"><strong>4. Prestaties vanuit het buitenland aan u verricht</strong></td></tr>
              ${block([rd[9], rd[10]])}

              <tr class="group-header"><td colspan="3"><strong>5. Voorbelasting en kleineondernemersregeling</strong></td></tr>
              ${block([rd[12], rd[13]])}
              <tr>
                <td>${frappe.utils.escape_html((rd[14]||{}).description || "5c. Subtotaal (5a - 5b)")}</td>
                <td></td>
                <td class="text-right">
                  <span class="${(rd[14] && rd[14].vat >= 0) ? 'text-danger' : 'text-success'}">
                    ${safe(rd[14] && rd[14].vat)}
                  </span>
                </td>
              </tr>
              ${block([rd[15], rd[16], rd[17]])}
            </tbody>
            <tfoot>
              <tr class="total-row">
                <th>Totaal</th>
                <th></th>
                <th class="text-right">
                  <span class="${(rd[18] && rd[18].vat >= 0) ? 'text-danger' : 'text-success'}">
                    ${safe(rd[18] && rd[18].vat)}
                  </span>
                </th>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>`;

      const styles = `
      <style>
      .vat-declaration-report { font-family:'Segoe UI',Arial,sans-serif; font-size:13px; padding:15px; width:100%; }
      .vat-table { width:100%; border-collapse:collapse; font-size:13px; margin-top:16px; }
      .vat-table th { background:#f5f5f5; padding:6px 8px; border:1px solid #ccc; text-align:left; font-weight:600; }
      .vat-table td { padding:6px 8px; border:1px solid #ccc; vertical-align:top; }
      .text-right { text-align:right; }
      .group-header td { background:#f0f0f0; font-weight:700; }
      .total-row th { font-weight:700; background:#f9f9f9; }
      .text-danger { color:#dc3545; } .text-success { color:#28a745; }
      </style>`;

      const w = window.open('', '_blank');
      const htmlContent = `
        <!DOCTYPE html><html><head><title>${title}</title>${styles}</head>
        <body>
          <div style="max-width: 800px; margin: 0 auto; padding: 20px;">
            <div class="no-print" style="margin-bottom: 20px; text-align: center;">
              <h2 style="margin-bottom: 5px;">${title}</h2>
              <button id="printButton" style="padding:8px 15px;background:black;color:white;border:none;border-radius:4px;cursor:pointer;font-size:14px;">Print</button>
              <p style="color:#666;font-size:12px;margin-top:10px;">Server-calculated figures.</p>
            </div>
            ${html}
          </div>
        </body></html>`;
      w.document.open(); w.document.write(htmlContent); w.document.close();
      w.onload = function() {
        const btn = w.document.getElementById('printButton');
        if (btn) btn.addEventListener('click', () => w.print());
      };
    });

    // Excel
    report.page.add_inner_button(__('Export to Excel'), function () {
      const filters = report.get_values();
      const args = {
        cmd: 'frappe.desk.query_report.export_query',
        report_name: 'VAT Declaration',
        file_format_type: 'Excel',
        filters: JSON.stringify(filters),
        visible_idx: JSON.stringify([]),
        include_indentation: 0
      };
      open_url_post(frappe.request.url, args);
    });
  },

  get_datatable_options: function(options) {
    options.layout = 'fluid';
    options.cellHeight = 40;
    return options;
  },

  after_datatable_render: function(datatable) {
    datatable.$container.find('.dt-scrollable').css({ 'max-height': '500px' });
  }
};
