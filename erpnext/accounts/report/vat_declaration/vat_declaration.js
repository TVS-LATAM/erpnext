// VAT Declaration – Frontend (2025)
// Correcciones:
// - No calcular IVA en el cliente (usar amount/vat del backend)
// - Acceso robusto a rubros por clave (mapa), pero se mantiene compatibilidad con índices del HTML/PDF
// - Fecha límite: mes siguiente (no +30d); si necesitas un cálculo más preciso por residencia, muéstralo en backend

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

    // Botón PDF (sin cálculos en cliente)
    report.page.add_inner_button(__('Download PDF'), async function () {
      const filters = report.get_values();
      const title = __("VAT Declaration") + ": " +
        frappe.datetime.str_to_user(filters.from_date) + " - " +
        frappe.datetime.str_to_user(filters.to_date);

      const reportData = report.data || [];

      const formatAmount = (a) => (a === undefined || a === null) ? "-" : frappe.format(a, { fieldtype: 'Currency' });

      // Helper para construir mapa por rubric
      const byRubric = {};
      reportData.forEach(r => { if (r.rubric) byRubric[r.rubric] = r; });

      // Plantilla HTML (usa amount/vat provistos por backend)
      const html = `
      <div class="vat-declaration-report" style="width: 100%;">
        <div class="table-responsive" style="width: 100%;">
          <table class="table table-bordered vat-table" style="width: 100% !important; table-layout: fixed;">
            <thead>
              <tr>
                <th style="width: 60%;">${__("Omschrijving")}</th>
                <th style="width: 20%;" class="text-right">${__("Belaste omzet")}</th>
                <th style="width: 20%;" class="text-right">${__("Omzetbelasting")}</th>
              </tr>
            </thead>
            <tbody>
              <tr style="background-color: #f2f2f2;">
                <td colspan="3"><strong>1. Prestaties binnenland</strong></td>
              </tr>
              <tr>
                <td>1a. Leveringen/diensten belast met hoog tarief</td>
                <td class="text-right">${formatAmount((byRubric["1a"]||{}).amount)}</td>
                <td class="text-right">${formatAmount((byRubric["1a"]||{}).vat)}</td>
              </tr>
              <tr>
                <td>1b. Leveringen/diensten belast met laag tarief</td>
                <td class="text-right">${formatAmount((byRubric["1b"]||{}).amount)}</td>
                <td class="text-right">${formatAmount((byRubric["1b"]||{}).vat)}</td>
              </tr>
              <tr>
                <td>1c. Leveringen/diensten belast met overige tarieven, behalve 0%</td>
                <td class="text-right">${formatAmount((byRubric["1c"]||{}).amount)}</td>
                <td class="text-right">${formatAmount((byRubric["1c"]||{}).vat)}</td>
              </tr>
              <tr>
                <td>1d. Prive-gebruik</td>
                <td class="text-right">${formatAmount((byRubric["1d"]||{}).amount)}</td>
                <td class="text-right">${formatAmount((byRubric["1d"]||{}).vat)}</td>
              </tr>
              <tr>
                <td>1e. Leveringen/diensten belast met 0% of niet bij u belast</td>
                <td class="text-right">${formatAmount((byRubric["1e"]||{}).amount)}</td>
                <td class="text-right">${formatAmount(0)}</td>
              </tr>

              <tr style="background-color: #f2f2f2;">
                <td colspan="3"><strong>2. Verleggingsregelingen binnenland</strong></td>
              </tr>
              <tr>
                <td>2a. Leveringen/diensten waarbij de omzetbelasting naar u is verlegd</td>
                <td class="text-right">${formatAmount((byRubric["2a"]||{}).amount)}</td>
                <td class="text-right">${formatAmount(0)}</td>
              </tr>

              <tr style="background-color: #f2f2f2;">
                <td colspan="3"><strong>3. Prestaties naar of in het buitenland</strong></td>
              </tr>
              <tr>
                <td>3a. Leveringen naar landen buiten de EU (uitvoer)</td>
                <td class="text-right">${formatAmount((byRubric["3a"]||{}).amount)}</td>
                <td class="text-right">${formatAmount(0)}</td>
              </tr>
              <tr>
                <td>3b. Leveringen naar of diensten in landen binnen de EU</td>
                <td class="text-right">${formatAmount((byRubric["3b"]||{}).amount)}</td>
                <td class="text-right">${formatAmount(0)}</td>
              </tr>
              <tr>
                <td>3c. Installatie/afstandsverkopen binnen de EU</td>
                <td class="text-right">${formatAmount((byRubric["3c"]||{}).amount)}</td>
                <td class="text-right">${formatAmount(0)}</td>
              </tr>

              <tr style="background-color: #f2f2f2;">
                <td colspan="3"><strong>4. Prestaties vanuit het buitenland aan u verricht</strong></td>
              </tr>
              <tr>
                <td>4a. Leveringen/diensten uit landen buiten de EU</td>
                <td class="text-right">${formatAmount((byRubric["4a"]||{}).amount)}</td>
                <td class="text-right">${formatAmount((byRubric["4a"]||{}).vat)}</td>
              </tr>
              <tr>
                <td>4b. Leveringen/diensten uit landen binnen de EU</td>
                <td class="text-right">${formatAmount((byRubric["4b"]||{}).amount)}</td>
                <td class="text-right">${formatAmount((byRubric["4b"]||{}).vat)}</td>
              </tr>

              <tr style="background-color: #f2f2f2;">
                <td colspan="3"><strong>5. Voorbelasting en kleineondernemersregeling</strong></td>
              </tr>
              <tr>
                <td>5a. Verschuldigde omzetbelasting (rubriek 1 t/m 4)</td>
                <td class="text-right"></td>
                <td class="text-right">${formatAmount((byRubric["5a"]||{}).amount)}</td>
              </tr>
              <tr>
                <td>5b. Voorbelasting</td>
                <td class="text-right"></td>
                <td class="text-right">${formatAmount((byRubric["5b"]||{}).amount)}</td>
              </tr>
              <tr class="subtotal-row">
                <td>5c. Subtotaal (rubriek 5a min 5b)</td>
                <td class="text-right"></td>
                <td class="text-right">
                  <span class="${((byRubric["5c"]||{}).amount||0) >= 0 ? 'text-danger' : 'text-success'}">
                    ${formatAmount((byRubric["5c"]||{}).amount)}
                  </span>
                </td>
              </tr>
              <tr>
                <td>5d. Vermindering volgens de kleineondernemersregeling (KOR)</td>
                <td class="text-right"></td>
                <td class="text-right">${formatAmount((byRubric["5d"]||{}).amount)}</td>
              </tr>
              <tr>
                <td>5e. Schatting vorige aangifte(n)</td>
                <td class="text-right"></td>
                <td class="text-right">${formatAmount((byRubric["5e"]||{}).amount)}</td>
              </tr>
              <tr>
                <td>5f. Schatting deze aangifte</td>
                <td class="text-right"></td>
                <td class="text-right">${formatAmount((byRubric["5f"]||{}).amount)}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="empty-row"><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
              <tr class="total-row">
                <th>Totaal</th>
                <th></th>
                <th class="text-right">
                  <span class="${((byRubric["Totaal"]||{}).amount||0) >= 0 ? 'text-danger' : 'text-success'}">
                    ${formatAmount((byRubric["Totaal"]||{}).amount)}
                  </span>
                </th>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>`;

      const styles = `
      <style>
      .vat-declaration-report { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; padding: 15px; width: 100%; }
      .table-responsive { width: 100%; overflow-x: auto; }
      .vat-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 16px; }
      .vat-table th { background-color: #f5f5f5; padding: 6px 8px; border: 1px solid #ccc; text-align: left; font-weight: 600; }
      .vat-table td { padding: 6px 8px; border: 1px solid #ccc; vertical-align: top; }
      .vat-table .text-right { text-align: right; }
      .subtotal-row td, .total-row th { font-weight: bold; background-color: #f9f9f9; }
      .empty-row td { border-left-color: transparent; border-right-color: transparent; height: 20px; }
      .text-danger { color: #dc3545; }
      .text-success { color: #28a745; }
      @media print {
        .vat-declaration-report { padding: 0; width: 100%; }
        .vat-table th, .subtotal-row td, .total-row th, .text-danger, .text-success {
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

    // Export a Excel/CSV
    report.page.add_inner_button(__('Export to Excel'), function () {
      const filters = report.get_values();
      const args = {
        cmd: 'frappe.desk.query_report.export_query',
        report_name: 'VAT Declaration',
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
