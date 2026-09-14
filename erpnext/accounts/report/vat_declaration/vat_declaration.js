// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

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
	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Apply custom formatting for amounts
		if (column.fieldname == "amount") {
			value = "<span style='font-weight: bold;'>" + value + "</span>";
		}
		
		// Highlight the net payable/refundable amount
		if (data && data.rubric === "5c" && !data.unsourced) {
			value = "<span style='font-weight: bold; color: " + 
				(data.amount >= 0 ? "red" : "green") + ";'>" + value + "</span>";
		}
		
		return value;
	},
	
	onload: async function(report) {
		// Apply styles to make the table occupy 100% of the width
		setTimeout(async function() {
			// Select the data table and apply styles
			$('.datatable').css({
				'width': '100%',
				'max-width': '100%'
			});
			
			// Adjust the table container
			$('.dt-scrollable').css({
				'width': '100%',
				'max-width': '100%'
			});
			
			// Adjust the main report container
			$('.report-wrapper').css({
				'width': '100%',
				'max-width': '100%'
			});
			
			// Ensure the header table also has full width
			$('.dt-header').css({
				'width': '100%',
				'max-width': '100%'
			});
			
			// Force recalculation of column widths
			if (report.datatable) {
				report.datatable.refresh();
			}
		}, 500);
		
		// Configure table adjustment when window size changes
		$(window).on('resize', function() {
			if (report.datatable) {
				report.datatable.refresh();
				
				// Readjust widths
				$('.datatable, .dt-scrollable, .report-wrapper, .dt-header').css({
					'width': '100%',
					'max-width': '100%'
				});
			}
		});
		
		// Add PDF download button
		report.page.add_inner_button(__('Download PDF'), async function() {
			// Get current report filters
			const filters = report.get_values();
			
			// Create a title for the PDF
			const title = __("VAT Declaration") + ": " + 
				frappe.datetime.str_to_user(filters.from_date) + " - " + 
				frappe.datetime.str_to_user(filters.to_date);
			
			// Prepare data for the HTML template
			const reportData = report.data;
			
			// Función para formatear montos
			function formatAmount(amount) {
				if (amount === undefined || amount === null) return "-";
				return frappe.format(amount, {fieldtype: 'Currency'});
			}

			// P1.7. La fila se busca por su rubriek, no por su posición en el
			// array. Un índice fijo es un contrato implícito entre Python y
			// JavaScript que cualquier fila nueva (o movida) puede romper sin
			// que nada avise; el rubriek es el único identificador estable.
			function pickRow(rows, rubric) {
				return (rows || []).find(function(row) { return row && row.rubric === rubric; });
			}

			// P2.3 (opción A). Una fila sin fuente de datos no imprime 0,00:
			// imprime un guión que dice por qué. Un cero en una declaración
			// fiscal es una MEDICIÓN — "5b Voorbelasting 0,00" afirma que no se
			// soportó IVA deducible — y 4a/4b/5b no miden nada mientras ninguna
			// compra se registre en ERPNext. Python marca esas filas con
			// `unsourced`; acá sólo se las muestra.
			function formatRubric(rows, rubric, field) {
				const row = pickRow(rows, rubric);
				if (row && row.unsourced) {
					return '<span class="text-muted">&mdash; geen bron</span>';
				}
				return formatAmount(row ? row[field || "amount"] : undefined);
			}

			// Un importe que no existe no es ni deuda ni crédito, así que no se
			// pinta de rojo ni de verde.
			function rubricTone(rows, rubric) {
				const row = pickRow(rows, rubric);
				if (!row || row.unsourced) return "";
				return row.amount >= 0 ? "text-danger" : "text-success";
			}

			async function getLetterHead(fromDate, toDate, frequency) {
				let letterhead_html = "";
				await frappe.call({
					method: "frappe.desk.form.load.getdoc?doctype=Letter%20Head&name=VAT%20Declaration",
					args: {
						doctype: "Letter Head",
						name: "VAT Declaration"
					},
					async: false,
					callback: function(r) {
						if(r.docs.length > 0) {
							letterhead_html = r.docs[0].content || "";
							
							// Replace placeholders in letterhead with actual date values if they exist
							if (fromDate && toDate) {
								const formattedFromDate = frappe.datetime.str_to_user(fromDate);
								const formattedToDate = frappe.datetime.str_to_user(toDate);
								const periode = `${formattedFromDate} – ${formattedToDate}`;
								
								// Calculate Uiterste inzenddatum (submission deadline)
								// Typically this is the last day of the month following the end of the quarter
								// For Dutch VAT declarations, it's typically +30 days after the end date
								const submissionDeadline = frappe.datetime.add_days(toDate, 30);
								const formattedDeadline = frappe.datetime.str_to_user(submissionDeadline);
								
								// Replace placeholders with actual values if they exist in the letterhead
								letterhead_html = letterhead_html.replace('${{periode}}', periode);
								letterhead_html = letterhead_html.replace('${{uiterste_inzenddatum}}', formattedDeadline);
								letterhead_html = letterhead_html.replace('${{frequency}}', frequency || "Quarterly");
							}
						}
					}
				});
				return letterhead_html;
			}
			// Get letterhead HTML content with date parameters and frequency
			const letterhead = await getLetterHead(filters.from_date, filters.to_date, filters.frequency);
			
			// Obtener datos de la empresa desde los filtros
			const company = filters.company || "";
			
			
			// Crear HTML basado en el template del reporte VAT
			const html = `
			<div class="vat-declaration-report" style="width: 100%;">
				${letterhead}	
				<!-- Contenido original del reporte -->
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
							<!-- 1. Prestaties binnenland -->
							<tr style="background-color: #f2f2f2;">
								<td colspan="3"><strong>1. Prestaties binnenland</strong></td>
							</tr>
							<tr>
								<td>1a. Leveringen/diensten belast met hoog tarief</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "1a")?.amount)}</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "1a")?.vat_amount)}</td>
							</tr>
							<tr>
								<td>1b. Leveringen/diensten belast met laag tarief</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "1b")?.amount)}</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "1b")?.vat_amount)}</td>
							</tr>
							<tr>
								<td>1c. Leveringen/diensten belast met overige tarieven, behalve 0%</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "1c")?.amount)}</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "1c")?.vat_amount)}</td>
							</tr>
							<tr>
								<td>1d. Prive-gebruik</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "1d")?.amount)}</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "1d")?.vat_amount)}</td>
							</tr>
							<tr>
								<td>1e. Leveringen/diensten belast met 0% of niet bij u belast</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "1e")?.amount)}</td>
								<td class="text-right">€ 0</td>
							</tr>
							
							<!-- 2. Verleggingsregelingen binnenland -->
							<tr style="background-color: #f2f2f2;">
								<td colspan="3"><strong>2. Verleggingsregelingen binnenland</strong></td>
							</tr>
							<tr>
								<td>2a. Leveringen/diensten waarbij de omzetbelasting naar u is verlegd</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "2a")?.amount)}</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "2a")?.vat_amount)}</td>
							</tr>
							
							<!-- 3. Prestaties naar of in het buitenland -->
							<tr style="background-color: #f2f2f2;">
								<td colspan="3"><strong>3. Prestaties naar of in het buitenland</strong></td>
							</tr>
							<tr>
								<td>3a. Leveringen naar landen buiten de EU (uitvoer)</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "3a")?.amount)}</td>
								<td class="text-right">€ 0</td>
							</tr>
							<tr>
								<td>3b. Leveringen naar of diensten in landen binnen de EU</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "3b")?.amount)}</td>
								<td class="text-right">€ 0</td>
							</tr>
							<tr>
								<td>3c. Installatie/afstandsverkopen binnen de EU</td>
								<td class="text-right">${formatAmount(pickRow(reportData, "3c")?.amount)}</td>
								<td class="text-right">€ 0</td>
							</tr>
							
							<!-- 4. Prestaties vanuit het buitenland aan u verricht -->
							<tr style="background-color: #f2f2f2;">
								<td colspan="3"><strong>4. Prestaties vanuit het buitenland aan u verricht</strong></td>
							</tr>
							<tr>
								<td>4a. Leveringen/diensten uit landen buiten de EU</td>
								<td class="text-right">${formatRubric(reportData, "4a")}</td>
								<td class="text-right">${formatRubric(reportData, "4a", "vat_amount")}</td>
							</tr>
							<tr>
								<td>4b. Leveringen/diensten uit landen binnen de EU</td>
								<td class="text-right">${formatRubric(reportData, "4b")}</td>
								<td class="text-right">${formatRubric(reportData, "4b", "vat_amount")}</td>
							</tr>
							
							<!-- 5. Voorbelasting en kleineondernemersregeling -->
							<tr style="background-color: #f2f2f2;">
								<td colspan="3"><strong>5. Voorbelasting en kleineondernemersregeling</strong></td>
							</tr>
							<tr>
								<td>5a. Verschuldigde omzetbelasting (rubriek 1 t/m 4)</td>
								<td class="text-right"></td>
								<td class="text-right">${formatAmount(pickRow(reportData, "5a")?.amount)}</td>
							</tr>
							<tr>
								<td>5b. Voorbelasting</td>
								<td class="text-right"></td>
								<td class="text-right">${formatRubric(reportData, "5b")}</td>
							</tr>
							<tr class="subtotal-row">
								<td>5c. Subtotaal (rubriek 5a min 5b)</td>
								<td class="text-right"></td>
								<td class="text-right">
									<span class="${rubricTone(reportData, "5c")}">
										${formatRubric(reportData, "5c")}
									</span>
								</td>
							</tr>
							<tr>
								<td>5d. Vermindering volgens de kleineondernemersregeling (KOR)</td>
								<td class="text-right"></td>
								<td class="text-right">${formatAmount(pickRow(reportData, "5d")?.amount)}</td>
							</tr>
							<tr>
								<td>5e. Schatting vorige aangifte(n)</td>
								<td class="text-right"></td>
								<td class="text-right">${formatAmount(pickRow(reportData, "5e")?.amount)}</td>
							</tr>
							<tr>
								<td>5f. Schatting deze aangifte</td>
								<td class="text-right"></td>
								<td class="text-right">${formatAmount(pickRow(reportData, "5f")?.amount)}</td>
							</tr>
						</tbody>
						<tfoot>
							<tr class="empty-row">
								<td>&nbsp;</td>
								<td>&nbsp;</td>
								<td>&nbsp;</td>
							</tr>
							<tr class="total-row">
								<th>Totaal</th>
								<th></th>
								<th class="text-right">
									<span class="${rubricTone(reportData, "Totaal")}">
										${formatRubric(reportData, "Totaal")}
									</span>
								</th>
							</tr>
						</tfoot>
					</table>
				</div>
			</div>
			`;
			
			// Estilos para el PDF
			const styles = `
			<style>
.vat-declaration-report {
  font-family: 'Segoe UI', Arial, sans-serif;
  font-size: 13px;
  padding: 15px;
  width: 100%;
}

.table-responsive {
  width: 100%;
  overflow-x: auto;
}

.vat-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-top: 16px;
}

.vat-table th {
  background-color: #f5f5f5;
  padding: 6px 8px;
  border: 1px solid #ccc;
  text-align: left;
  font-weight: 600;
}

.vat-table td {
  padding: 6px 8px;
  border: 1px solid #ccc;
  vertical-align: top;
}

.vat-table .text-right {
  text-align: right;
}

.vat-table .group-header td {
  background-color: #f0f0f0;
  font-weight: bold;
}

.subtotal-row td,
.total-row th {
  font-weight: bold;
  background-color: #f9f9f9;
}

.empty-row td {
  border-left-color: transparent;
  border-right-color: transparent;
  height: 20px;
}

.text-danger {
  color: #dc3545;
}

.text-success {
  color: #28a745;
}

@media print {
  .vat-declaration-report {
    padding: 0;
    width: 100%;
  }

  .vat-table th,
  .vat-table .group-header td,
  .subtotal-row td,
  .total-row th {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .text-danger,
  .text-success {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  .no-print {
    display: none !important;
  }
}
</style>

			`;
			
			// Crear ventana de impresión
			const w = window.open('', '_blank');
			
			// Contenido HTML para la ventana
			const htmlContent = `
				<!DOCTYPE html>
				<html>
				<head>
					<title>${title}</title>
					${styles}
				</head>
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
				</html>
			`;
			
			// Escribir el contenido en la ventana
			w.document.open();
			w.document.write(htmlContent);
			w.document.close();
			
			// Agregar el evento de impresión después de que el documento esté completamente cargado
			w.onload = function() {
				const printButton = w.document.getElementById('printButton');
				if (printButton) {
					printButton.addEventListener('click', function() {
						w.print();
					});
				}
			};
		});
		
		// Add Excel export button
		report.page.add_inner_button(__('Export to Excel'), function() {
			// Simplified method to export to Excel
			const filters = report.get_values();
			
			// Create arguments for export
			const args = {
				cmd: 'frappe.desk.query_report.export_query',
				report_name: 'VAT Declaration',
				file_format_type: 'Excel',
				filters: JSON.stringify(filters),
				// Ensure visible_idx is an empty array instead of null
				visible_idx: JSON.stringify([]),
				include_indentation: 0,
				// Add additional parameters for CSV if needed
				csv_delimiter: ',',
				csv_quoting: '"'
			};
			
			// Open URL to download the file
			open_url_post(frappe.request.url, args);
		});
	},
	
	// Configuration for the data table
	get_datatable_options: function(options) {
		// Modify data table options
		options.layout = 'fluid'; // Change from 'fixed' to 'fluid'
		options.cellHeight = 40; // Increase cell height for better visualization
		
		return options;
	},
	
	// Function that runs after rendering the table
	after_datatable_render: function(datatable) {
		// Additional customization after the table is rendered
		datatable.$container.find('.dt-scrollable').css({
			'max-height': '500px' // Limit the height of the scrollable area
		});
	}
};
