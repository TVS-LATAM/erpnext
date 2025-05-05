// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

// Definir el reporte con ambos nombres para compatibilidad
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
	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Apply custom formatting for amounts
		if (column.fieldname == "amount") {
			value = "<span style='font-weight: bold;'>" + value + "</span>";
		}
		
		// Highlight the net payable/refundable amount
		if (data && data.rubric === "5c") {
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
			const title = __("TAX Declaration") + ": " + 
				frappe.datetime.str_to_user(filters.from_date) + " - " + 
				frappe.datetime.str_to_user(filters.to_date);
			
			// Prepare data for the HTML template
			const reportData = report.data;
			
			// Función para formatear montos
			function formatAmount(amount) {
				if (amount === undefined || amount === null) return "-";
				return frappe.format(amount, {fieldtype: 'Currency'});
			}
			
			// Función para obtener el valor BTW (impuesto) basado en el índice
			function getBtw(idx) {
				// Por defecto, devolver "-"
				if (!reportData[idx] || reportData[idx].btw === undefined) return "-";
				return formatAmount(reportData[idx].btw);
			}
			
			async function getLetterHead(fromDate, toDate, frequency) {
				let letterhead_html = "";
				await frappe.call({
					method: "frappe.desk.form.load.getdoc?doctype=Letter%20Head&name=TAX%20Declaration",
					args: {
						doctype: "Letter Head",
						name: "TAX Declaration"
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
								
								// Calculate submission deadline
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
			
			// Crear HTML basado en el template mejorado
			const html = `
			<div class="tax-declaration-report" style="width: 100%;">
				${letterhead}	
				<!-- Contenido del reporte -->
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
							<tr>
								<td>${reportData[0]?.description || "1a. Leveringen/diensten belast met hoog tarief"}</td>
								<td class="text-right">${formatAmount(reportData[0]?.amount)}</td>
								<td class="text-right">${getBtw(0)}</td>
							</tr>
							<tr>
								<td>${reportData[1]?.description || "1b. Leveringen/diensten belast met laag tarief"}</td>
								<td class="text-right">${formatAmount(reportData[1]?.amount)}</td>
								<td class="text-right">${getBtw(1)}</td>
							</tr>
							<tr>
								<td>${reportData[2]?.description || "1c. Andere tarieven"}</td>
								<td class="text-right">${formatAmount(reportData[2]?.amount)}</td>
								<td class="text-right">${getBtw(2)}</td>
							</tr>
							<tr>
								<td>${reportData[3]?.description || "1d. Privégebruik"}</td>
								<td class="text-right">${formatAmount(reportData[3]?.amount)}</td>
								<td class="text-right">${getBtw(3)}</td>
							</tr>
							<tr>
								<td>${reportData[4]?.description || "1e. Leveringen/diensten belast met 0% of niet bij u belast"}</td>
								<td class="text-right">${formatAmount(reportData[4]?.amount)}</td>
								<td class="text-right">${getBtw(4)}</td>
							</tr>
						</tbody>
					</table>
					
					<h4 class="rubriek-title">Rubriek 2: Verleggingsregeling</h4>
					<table class="table table-bordered tax-table" style="width: 100% !important; table-layout: fixed;">
						<thead>
							<tr>
								<th style="width: 60%;">${__("Omschrijving")}</th>
								<th style="width: 20%;" class="text-right">${__("Omzet")}</th>
								<th style="width: 20%;" class="text-right">${__("Btw")}</th>
							</tr>
						</thead>
						<tbody>
							<tr>
								<td>${reportData[5]?.description || "2a. Leveringen waarop de verleggingsregeling van toepassing is"}</td>
								<td class="text-right">${formatAmount(reportData[5]?.amount)}</td>
								<td class="text-right">${getBtw(5)}</td>
							</tr>
						</tbody>
					</table>
					
					<h4 class="rubriek-title">Rubriek 3: Prestaties naar of in het buitenland</h4>
					<table class="table table-bordered tax-table" style="width: 100% !important; table-layout: fixed;">
						<thead>
							<tr>
								<th style="width: 60%;">${__("Omschrijving")}</th>
								<th style="width: 20%;" class="text-right">${__("Omzet")}</th>
								<th style="width: 20%;" class="text-right">${__("Btw")}</th>
							</tr>
						</thead>
						<tbody>
							<tr>
								<td>${reportData[6]?.description || "3a. Leveringen naar landen buiten de EU (uitvoer)"}</td>
								<td class="text-right">${formatAmount(reportData[6]?.amount)}</td>
								<td class="text-right">${getBtw(6)}</td>
							</tr>
							<tr>
								<td>${reportData[7]?.description || "3b. Leveringen naar of diensten in landen binnen de EU"}</td>
								<td class="text-right">${formatAmount(reportData[7]?.amount)}</td>
								<td class="text-right">${getBtw(7)}</td>
							</tr>
							<tr>
								<td>${reportData[8]?.description || "3c. Afstandsverkopen/installaties binnen de EU"}</td>
								<td class="text-right">${formatAmount(reportData[8]?.amount)}</td>
								<td class="text-right">${getBtw(8)}</td>
							</tr>
						</tbody>
					</table>
					
					<h4 class="rubriek-title">Rubriek 4: Prestaties vanuit het buitenland aan u verricht</h4>
					<table class="table table-bordered tax-table" style="width: 100% !important; table-layout: fixed;">
						<thead>
							<tr>
								<th style="width: 60%;">${__("Omschrijving")}</th>
								<th style="width: 20%;" class="text-right">${__("Omzet")}</th>
								<th style="width: 20%;" class="text-right">${__("Btw")}</th>
							</tr>
						</thead>
						<tbody>
							<tr>
								<td>${reportData[9]?.description || "4a. Leveringen/diensten uit landen buiten de EU"}</td>
								<td class="text-right">${formatAmount(reportData[9]?.amount)}</td>
								<td class="text-right">${getBtw(9)}</td>
							</tr>
							<tr>
								<td>${reportData[10]?.description || "4b. Leveringen/diensten uit landen binnen de EU"}</td>
								<td class="text-right">${formatAmount(reportData[10]?.amount)}</td>
								<td class="text-right">${getBtw(10)}</td>
							</tr>
						</tbody>
					</table>
					
					<h4 class="rubriek-title">Rubriek 5: Voorbelasting en eindtotaal</h4>
					<table class="table table-bordered tax-table" style="width: 100% !important; table-layout: fixed;">
						<thead>
							<tr>
								<th style="width: 60%;">${__("Omschrijving")}</th>
								<th style="width: 20%;"></th>
								<th style="width: 20%;" class="text-right">${__("Btw")}</th>
							</tr>
						</thead>
						<tbody>
							<tr>
								<td>${reportData[12]?.description || "5a. Verschuldigde btw"}</td>
								<td></td>
								<td class="text-right">${formatAmount(reportData[12]?.amount)}</td>
							</tr>
							<tr>
								<td>${reportData[11]?.description || "5b. Voorbelasting"}</td>
								<td></td>
								<td class="text-right">${formatAmount(reportData[11]?.amount)}</td>
							</tr>
							<tr class="subtotal-row">
								<td>${reportData[13]?.description || "5c. Subtotaal (verschuldigde btw - voorbelasting)"}</td>
								<td></td>
								<td class="text-right">
									<span class="${reportData[13]?.amount >= 0 ? 'text-danger' : 'text-success'}">
										${formatAmount(reportData[13]?.amount)}
									</span>
								</td>
							</tr>
							<tr>
								<td>${reportData[14]?.description || "5d. Vermindering volgens de kleineondernemersregeling (KOR)"}</td>
								<td></td>
								<td class="text-right">${formatAmount(reportData[14]?.amount)}</td>
							</tr>
							<tr>
								<td>${reportData[15]?.description || "5e. Correcties uit eerdere aangiften"}</td>
								<td></td>
								<td class="text-right">${formatAmount(reportData[15]?.amount)}</td>
							</tr>
							<tr>
								<td>${reportData[16]?.description || "5f. Voorlopige schatting"}</td>
								<td></td>
								<td class="text-right">${formatAmount(reportData[16]?.amount)}</td>
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
									<span class="${reportData[13]?.amount >= 0 ? 'text-danger' : 'text-success'}">
										${formatAmount(reportData[13]?.amount)}
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
.tax-declaration-report {
  font-family: 'Segoe UI', Arial, sans-serif;
  font-size: 13px;
  padding: 15px;
  width: 100%;
}

.table-responsive {
  width: 100%;
  overflow-x: auto;
}

.tax-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 20px;
}

.tax-table th {
  background-color: #f5f5f5;
  padding: 6px 8px;
  border: 1px solid #ccc;
  text-align: left;
  font-weight: 600;
}

.tax-table td {
  padding: 6px 8px;
  border: 1px solid #ccc;
  vertical-align: top;
}

.tax-table .text-right {
  text-align: right;
}

.rubriek-title {
  margin-top: 20px;
  margin-bottom: 10px;
  font-size: 16px;
  font-weight: 600;
  color: #333;
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
  .tax-declaration-report {
    padding: 0;
    width: 100%;
  }

  .tax-table th,
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
			// Método simplificado para exportar a Excel
			const filters = report.get_values();
			
			// Crear los argumentos para la exportación
			const args = {
				cmd: 'frappe.desk.query_report.export_query',
				report_name: 'TAX Declaration',
				file_format_type: 'Excel',
				filters: JSON.stringify(filters),
				// Asegurarse de que visible_idx sea un array vacío en lugar de null
				visible_idx: JSON.stringify([]),
				include_indentation: 0,
				// Agregar parámetros adicionales para CSV si es necesario
				csv_delimiter: ',',
				csv_quoting: '"'
			};
			
			// Abrir la URL para descargar el archivo
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
