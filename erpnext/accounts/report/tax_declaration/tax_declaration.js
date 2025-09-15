// TAX Declaration – Frontend (2025)
// Correcciones:
// - No calcular IVA en el cliente (usar amount/vat del backend)
// - Ajuste de índices para coincidir con el backend (5a..5g)
// - Fecha límite: mostrar mes siguiente (el HTML ya lo hace)

frappe.query_reports["TAX Declaration"] = {
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
      options: "Monthly\nQuarterly\nYearly",
      default: "Quarterly",
      reqd: 1
    }
  ],

  formatter: function (value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (column.fieldname === "amount" || column.fieldname === "vat") {
      value = "<span style='font-weight: 600;'>" + value + "</span>";
    }
    if (data && data.rubric === "5c" && column.fieldname === "amount") {
      value = "<span style='font-weight: 700; color: " +
        (data.amount >= 0 ? "red" : "green") + ";'>" + value + "</span>";
    }
    return value;
  },

  onload: async function (report) {
    setTimeout(function () {
      $('.datatable, .dt-scrollable, .report-wrapper, .dt-header').css({ 'width': '100%', 'max-width': '100%' });
      if (report.datatable) report.datatable.refresh();
    }, 300);

    $(window).on('resize', function () {
      if (report.datatable) {
        report.datatable.refresh();
        $('.datatable, .dt-scrollable, .report-wrapper, .dt-header').css({ 'width': '100%', 'max-width': '100%' });
      }
    });

    // Botón PDF (render-only, sin cálculos)
    report.page.add_inner_button(__('Download PDF'), async function () {
      const filters = report.get_values();
      const title = __("TAX Declaration") + ": " +
        frappe.datetime.str_to_user(filters.from_date) + " - " +
        frappe.datetime.str_to_user(filters.to_date);

      const reportData = report.data || [];
      const fmt = (a) => (a === undefined || a === null) ? "-" : frappe.format(a, { fieldtype: 'Currency' });

      // Mapa por rúbrica (opcional para validaciones/avisos)
      const byRubric = {};
      reportData.forEach(r => { if (r.rubric) byRubric[r.rubric] = r; });

      const html = `
      <div class="tax-declaration-report" style="width: 100%;">
        <div class="table-responsive" style="width: 100%;">
          <h4 class="rubriek-title">Rubriek 1: Prestaties binnenland</h4>
          <table class="table table-bordered tax-table" style="width: 100% !important; table-layout: fixed;">
            <thead>
              <tr>
                <th style="width: 60%;">${__("Omschrijving")}</th>
                <th style="width: 20%;" class="text-right">${__("Omzet")}</th>
                <th style="width: 20%;" class="text-right">${__("Btw")}</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>${reportData[0]?.description || "1a. Leveringen/diensten belast met hoog tarief"}</td>
                  <td class="text-right">${fmt(reportData[0]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[0]?.vat)}</td></tr>
              <tr><td>${reportData[1]?.description || "1b. Leveringen/diensten belast met laag tarief"}</td>
                  <td class="text-right">${fmt(reportData[1]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[1]?.vat)}</td></tr>
              <tr><td>${reportData[2]?.description || "1c. Andere tarieven"}</td>
                  <td class="text-right">${fmt(reportData[2]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[2]?.vat)}</td></tr>
              <tr><td>${reportData[3]?.description || "1d. Privégebruik"}</td>
                  <td class="text-right">${fmt(reportData[3]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[3]?.vat)}</td></tr>
              <tr><td>${reportData[4]?.description || "1e. Leveringen/diensten 0% of vrijgesteld"}</td>
                  <td class="text-right">${fmt(reportData[4]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[4]?.vat)}</td></tr>
            </tbody>
          </table>

          <h4 class="rubriek-title">Rubriek 2: Verleggingsregeling</h4>
          <table class="table table-bordered tax-table" style="width: 100% !important; table-layout: fixed;">
            <thead><tr><th style="width: 60%;">${__("Omschrijving")}</th>
                     <th style="width: 20%;" class="text-right">${__("Omzet")}</th>
                     <th style="width: 20%;" class="text-right">${__("Btw")}</th></tr></thead>
            <tbody>
              <tr><td>${reportData[5]?.description || "2a. Verleggingsregeling (omzet)"}</td>
                  <td class="text-right">${fmt(reportData[5]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[5]?.vat)}</td></tr>
            </tbody>
          </table>

          <h4 class="rubriek-title">Rubriek 3: Prestaties naar of in het buitenland</h4>
          <table class="table table-bordered tax-table" style="width: 100% !important; table-layout: fixed;">
            <thead><tr><th style="width: 60%;">${__("Omschrijving")}</th>
                     <th style="width: 20%;" class="text-right">${__("Omzet")}</th>
                     <th style="width: 20%;" class="text-right">${__("Btw")}</th></tr></thead>
            <tbody>
              <tr><td>${reportData[6]?.description || "3a. Leveringen naar landen buiten de EU (uitvoer)"}</td>
                  <td class="text-right">${fmt(reportData[6]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[6]?.vat)}</td></tr>
              <tr><td>${reportData[7]?.description || "3b. Leveringen/diensten binnen de EU"}</td>
                  <td class="text-right">${fmt(reportData[7]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[7]?.vat)}</td></tr>
              <tr><td>${reportData[8]?.description || "3c. Afstandsverkopen/installaties binnen de EU"}</td>
                  <td class="text-right">${fmt(reportData[8]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[8]?.vat)}</td></tr>
            </tbody>
          </table>

          <h4 class="rubriek-title">Rubriek 4: Prestaties vanuit het buitenland aan u verricht</h4>
          <table class="table table-bordered tax-table" style="width: 100% !important; table-layout: fixed;">
            <thead><tr><th style="width: 60%;">${__("Omschrijving")}</th>
                     <th style="width: 20%;" class="text-right">${__("Omzet")}</th>
                     <th style="width: 20%;" class="text-right">${__("Btw")}</th></tr></thead>
            <tbody>
              <tr><td>${reportData[9]?.description || "4a. Prestaties uit landen buiten de EU"}</td>
                  <td class="text-right">${fmt(reportData[9]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[9]?.vat)}</td></tr>
              <tr><td>${reportData[10]?.description || "4b. Prestaties uit EU-landen"}</td>
                  <td class="text-right">${fmt(reportData[10]?.amount)}</td>
                  <td class="text-right">${fmt(reportData[10]?.vat)}</td></tr>
            </tbody>
          </table>

          <h4 class="rubriek-title">Rubriek 5: Voorbelasting en eindtotaal</h4>
          <table class="table table-bordered tax-table" style="width: 100% !important; table-layout: fixed;">
            <thead><tr><th style="width: 60%;">${__("Omschrijving")}</th>
                     <th style="width: 20%;"></th>
                     <th style="width: 20%;" class="text-right">${__("Btw")}</th></tr></thead>
            <tbody>
              <tr><td>${reportData[11]?.description || "5a. Verschuldigde btw"}</td>
                  <td></td><td class="text-right">${fmt(reportData[11]?.amount)}</td></tr>
              <tr><td>${reportData[12]?.description || "5b. Voorbelasting"}</td>
                  <td></td><td class="text-right">${fmt(reportData[12]?.amount)}</td></tr>
              <tr class="subtotal-row"><td>${reportData[13]?.description || "5c. Subtotaal (5a - 5b)"}</td>
                  <td></td><td class="text-right">
                    <span class="${((reportData[13]?.amount)||0) >= 0 ? 'text-danger' : 'text-success'}">
                      ${fmt(reportData[13]?.amount)}
                    </span>
                  </td></tr>
              <tr><td>${reportData[14]?.description || "5d. KOR vermindering"}</td>
                  <td></td><td class="text-right">${fmt(reportData[14]?.amount)}</td></tr>
              <tr><td>${reportData[15]?.description || "5e. Correcties uit eerdere aangiften"}</td>
                  <td></td><td class="text-right">${fmt(reportData[15]?.amount)}</td></tr>
              <tr><td>${reportData[16]?.description || "5f. Voorlopige schatting"}</td>
                  <td></td><td class="text-right">${fmt(reportData[16]?.amount)}</td></tr>
            </tbody>
            <tfoot>
              <tr class="empty-row"><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
              <tr class="total-row">
                <th>${reportData[17]?.description || "5g. Te betalen of terug te ontvangen"}</th>
                <th></th>
                <th class="text-right">
                  <span class="${((reportData[17]?.amount)||0) >= 0 ? 'text-danger' : 'text-success'}">
                    ${fmt(reportData[17]?.amount)}
                  </span>
                </th>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>`;

      const styles = `
      <style>
      .tax-declaration-report { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; padding: 15px; width: 100%; }
      .table-responsive { width: 100%; overflow-x: auto; }
      .tax-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 20px; }
      .tax-table th { background-color: #f5f5f5; padding: 6px 8px; border: 1px solid #ccc; text-align: left; font-weight: 600; }
      .tax-table td { padding: 6px 8px; border: 1px solid #ccc; vertical-align: top; }
      .tax-table .text-right { text-align: right; }
      .rubriek-title { margin-top: 20px; margin-bottom: 10px; font-size: 16px; font-weight: 600; color: #333; }
      .subtotal-row td, .total-row th { font-weight: bold; background-color: #f9f9f9; }
      .empty-row td { border-left-color: transparent; border-right-color: transparent; height: 20px; }
      .text-danger { color: #dc3545; }
      .text-success { color: #28a745; }
      @media print {
        .tax-declaration-report { padding: 0; width: 100%; }
        .tax-table th, .subtotal-row td, .total-row th, .text-danger, .text-success {
          -webkit-print-color-adjust: exact; print-color-adjust: exact;
        }
        .no-print { display: none !important; }
      }
      </style>`;

      const w = window.open('', '_blank');
      const htmlContent = `
        <!DOCTYPE html>
        <html>
        <head><title>${title}</title>${styles}</head>
        <body>
          <div style="max-width: 800px; margin: 0 auto; padding: 20px;">
            <div class="no-print" style="margin-bottom: 20px; text-align: center;">
              <h2 style="margin-bottom: 5px;">${title}</h2>
              <button id="printButton" style="padding: 8px 15px; background-color: black; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">Print</button>
              <p style="color: #666; font-size: 12px; margin-top: 10px;">This window will remain open after printing so you can review it or print it again.</p>
            </div>
            ${html}
          </div>
        </body>
        </html>`;

      w.document.open(); w.document.write(htmlContent); w.document.close();
      w.onload = function () {
        const btn = w.document.getElementById('printButton');
        if (btn) btn.addEventListener('click', () => w.print());
      };
    });

    // Exportar a Excel/CSV
    report.page.add_inner_button(__('Export to Excel'), function () {
      const filters = report.get_values();
      const args = {
        cmd: 'frappe.desk.query_report.export_query',
        report_name: 'TAX Declaration',
        file_format_type: 'Excel',
        filters: JSON.stringify(filters),
        visible_idx: JSON.stringify([]),
        include_indentation: 0,
        csv_delimiter: ',',
        csv_quoting: '"'
      };
      open_url_post(frappe.request.url, args);
    });
  },

  get_datatable_options: function (options) {
    options.layout = 'fluid';
    options.cellHeight = 40;
    return options;
  },

  after_datatable_render: function (datatable) {
    datatable.$container.find('.dt-scrollable').css({ 'max-height': '500px' });
  }
};
