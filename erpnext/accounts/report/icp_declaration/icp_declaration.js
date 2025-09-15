// icp_declaration.js
// Ajustes: usar dotted path completo a los @frappe.whitelist del reporte Python.

frappe.query_reports["ICP Declaration"] = {
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
      default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
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
      // Inicialmente solo Monthly/Quarterly; Yearly se añadirá si el server lo permite
      options: "Monthly\nQuarterly",
      default: "Quarterly",
      reqd: 1
    }
  ],

  formatter: function (value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (column.fieldname === "Net Amount") {
      value = "<span style='font-weight: bold;'>" + value + "</span>";
    }
    return value;
  },

  onload: async function (report) {
    setTimeout(function () {
      $('.datatable, .dt-scrollable, .report-wrapper, .dt-header').css({
        'width': '100%',
        'max-width': '100%'
      });
      if (report.datatable) report.datatable.refresh();
    }, 500);

    $(window).on('resize', function () {
      if (report.datatable) {
        report.datatable.refresh();
        $('.datatable, .dt-scrollable, .report-wrapper, .dt-header').css({
          'width': '100%',
          'max-width': '100%'
        });
      }
    });

    // Ajustar opciones de frecuencia según permiso anual y umbral trimestral
    async function tuneFrequencyOptions() {
      const filters = report.get_values();
      try {
        const r = await frappe.call({
          // ⬇️ DOTTED PATH COMPLETO AL PYTHON DEL REPORTE
          method: "erpnext.accounts.report.icp_declaration.icp_declaration.get_icp_config",
          args: {
            company: filters.company,
            from_date: filters.from_date,
            to_date: filters.to_date
          }
        });
        if (r && r.message) {
          const { allow_yearly, forced_frequency } = r.message;

          // Añadir Yearly si permitido
          const freqField = report.get_filter("frequency");
          const opts = ["Monthly", "Quarterly"];
          if (allow_yearly) opts.push("Yearly");
          freqField.df.options = opts.join("\n");
          freqField.refresh();

          // Forzar mensual si el umbral se excede
          if (forced_frequency === "monthly" && freqField.get_value() !== "Monthly") {
            frappe.show_alert({
              message: __("Goods total for the quarter exceeds €50,000. Frequency forced to Monthly."),
              indicator: "orange"
            });
            freqField.set_value("Monthly");
          }
        }
      } catch (e) {
        // noop
      }
    }

    // Inicial
    await tuneFrequencyOptions();

    // Recalcular al cambiar fechas o compañía
    ["from_date", "to_date", "company"].forEach(fn => {
      report.get_filter(fn).$input.on("change", () => tuneFrequencyOptions());
    });

    // Botón PDF
    report.page.add_inner_button(__('Download PDF'), async function () {
      const filters = report.get_values();
      const title = __("ICP Declaration") + ": " +
        frappe.datetime.str_to_user(filters.from_date) + " - " +
        frappe.datetime.str_to_user(filters.to_date);

      const reportData = report.data || [];

      function formatAmount(amount) {
        if (amount === undefined || amount === null) return "-";
        return frappe.format(amount, { fieldtype: 'Currency' });
      }

      // Letterhead (sin fecha límite inventada)
      async function getLetterHead() {
        let letterhead_html = "";
        try {
          const r = await frappe.call({
            method: "frappe.desk.form.load.getdoc?doctype=Letter%20Head&name=ICP%20Declaration",
            args: { doctype: "Letter Head", name: "ICP Declaration" },
            async: false
          });
          if (r && r.docs && r.docs.length > 0) {
            letterhead_html = r.docs[0].content || "";
            const formattedFromDate = frappe.datetime.str_to_user(filters.from_date);
            const formattedToDate = frappe.datetime.str_to_user(filters.to_date);
            const periode = `${formattedFromDate} – ${formattedToDate}`;
            letterhead_html = letterhead_html.replaceAll('${{periode}}', periode);
          }
        } catch (e) { /* noop */ }
        return letterhead_html;
      }

      const letterhead = await getLetterHead();

      // Filas
      let rows_html = '';
      let net_amount_total = 0;

      const rows_data = reportData.filter(row =>
        !row.is_total_row && row["Customer Name"] !== "Total"
      );

      rows_data.forEach(row => {
        net_amount_total += flt(row["Net Amount"]) || 0;
        rows_html += `
          <tr>
            <td>${row["Customer Name"] || ""}</td>
            <td>${row["VAT Identification Number"] || ""}</td>
            <td>${row["Country Code"] || ""}</td>
            <td>${row["ICP Type"] || ""}</td>
            <td class="text-right">${formatAmount(row["Net Amount"])}</td>
          </tr>
        `;
      });

      const html = `
      <div class="icp-declaration-report" style="width: 100%;">
        ${letterhead}
        <div class="table-responsive" style="width: 100%;">
          <table class="table table-bordered icp-table" style="width: 100% !important; table-layout: fixed;">
            <thead>
              <tr>
                <th style="width: 28%;">${__("Customer Name")}</th>
                <th style="width: 22%;">${__("VAT Identification Number")}</th>
                <th style="width: 10%;">${__("Country Code")}</th>
                <th style="width: 15%;">${__("ICP Type")}</th>
                <th style="width: 15%;" class="text-right">${__("Net Amount (EUR)")}</th>
              </tr>
            </thead>
            <tbody>
              ${rows_html}
            </tbody>
            <tfoot>
              <tr class="empty-row">
                <td colspan="5">&nbsp;</td>
              </tr>
              <tr class="total-row">
                <th>${__("Total")}</th>
                <th></th><th></th><th></th>
                <th class="text-right">${formatAmount(net_amount_total)}</th>
              </tr>
            </tfoot>
          </table>
        </div>
        <p style="font-size: 11px; color: #666; margin-top: 6px;">
          ${__("All amounts are converted to EUR at company-to-EUR exchange rates on document date.")}
        </p>
      </div>
      `;

      const styles = `
      <style>
      .icp-declaration-report { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; padding: 15px; width: 100%; }
      .icp-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 16px; }
      .icp-table th { background-color: #f5f5f5; padding: 6px 8px; border: 1px solid #ccc; text-align: left; font-weight: 600; }
      .icp-table td { padding: 6px 8px; border: 1px solid #ccc; vertical-align: top; }
      .icp-table .text-right { text-align: right; }
      .empty-row td { border-left-color: transparent; border-right-color: transparent; height: 20px; }
      .total-row th { font-weight: bold; background-color: #f9f9f9; }
      </style>`;

      const w = window.open('', '_blank');
      const htmlContent = `
        <!DOCTYPE html>
        <html>
        <head>
          <title>${title}</title>
          ${styles}
        </head>
        <body>
          <div style="max-width: 900px; margin: 0 auto; padding: 20px;">
            <div class="no-print" style="margin-bottom: 20px; text-align: center;">
              <h2 style="margin-bottom: 5px;">${title}</h2>
              <button id="printButton" style="padding: 8px 15px; background-color: black; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">Print</button>
            </div>
            ${html}
          </div>
        </body>
        </html>
      `;
      w.document.open();
      w.document.write(htmlContent);
      w.document.close();
      w.onload = function () {
        const btn = w.document.getElementById('printButton');
        if (btn) btn.addEventListener('click', () => w.print());
      };
    });

    // Export to Excel (core)
    report.page.add_inner_button(__('Export to Excel'), function () {
      const filters = report.get_values();
      const args = {
        cmd: 'frappe.desk.query_report.export_query',
        report_name: 'ICP Declaration',
        file_format_type: 'Excel',
        filters: JSON.stringify(filters),
        visible_idx: JSON.stringify([]),
        include_indentation: 0,
        csv_delimiter: ',',
        csv_quoting: '"'
      };
      open_url_post(frappe.request.url, args);
    });

    // Export CSV (ICP minimal)
    report.page.add_inner_button(__('Export ICP CSV'), async function () {
      const filters = report.get_values();
      try {
        const gen = await frappe.call({
          // ⬇️ DOTTED PATH COMPLETO
          method: "erpnext.accounts.report.icp_declaration.icp_declaration.generate_icp_report",
          args: { filters }
        });
        if (gen && gen.message && gen.message.success) {
          const exp = await frappe.call({
            // ⬇️ DOTTED PATH COMPLETO
            method: "erpnext.accounts.report.icp_declaration.icp_declaration.export_to_belastingdienst_format",
            args: { data: gen.message.data, filters, fmt: "CSV" }
          });
          if (exp && exp.message) {
            const { file_name, file_content } = exp.message;
            const blob = new Blob([file_content], { type: "text/csv;charset=utf-8;" });
            const link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.download = file_name;
            link.click();
          }
        }
      } catch (e) {
        frappe.msgprint(__("Could not export ICP CSV."));
      }
    });

  },

  get_datatable_options: function (options) {
    options.layout = 'fluid';
    options.cellHeight = 40;
    options.dynamicRowHeight = false;
    return options;
  },

  after_datatable_render: function (datatable) {
    datatable.$container.find('.dt-scrollable').css({ 'max-height': '500px' });
  }
};
