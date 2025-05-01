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
	
	onload: function(report) {
		// Apply styles to make the table occupy 100% of the width
		setTimeout(function() {
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
		report.page.add_inner_button(__('Download PDF'), function() {
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
			
			// Función para obtener el valor VAT (impuesto) basado en el índice
			function getVat(idx) {
				// Por defecto, devolver "-"
				if (!reportData[idx] || reportData[idx].vat === undefined) return "-";
				return formatAmount(reportData[idx].vat);
			}
			
			// Obtener datos de la empresa desde los filtros
			const company = filters.company || "";
			
			// Crear HTML basado en el template del reporte VAT
			const html = `
			<div class="vat-declaration-report" style="width: 100%;">
				<!-- Encabezado específico para el reporte VAT -->
				<table style="width:100%; font-family:Arial, sans-serif; font-size:13px; border-collapse:collapse; border:1px solid #ccc; margin-bottom: 20px;">
					<tbody>
						<tr style="background:#e9ecef;">
							<td colspan="4" style="font-size:17px; font-weight:bold; padding:8px; border:1px solid #ccc;">
								BTW Aangifte – Kwartaaloverzicht
							</td>
						</tr>

						<!-- Gegevens onderneming -->
						<tr><td colspan="4" style="background:#f1f1f1; font-weight:bold; padding:6px;">Gegevens onderneming</td></tr>
						<tr>
							<td style="padding:6px;"><b>Naam:</b> Fiscale Eenheid R.M. Logmans Beheer B.V. en TVS Engineering B.V. C.S.</td>
							<td style="padding:6px;"><b>RSIN:</b> 823862021</td>
							<td style="padding:6px;"><b>BTW-nummer:</b> NL853871334B01</td>
							<td style="padding:6px;"><b>KvK-nummer:</b> [invullen]</td>
						</tr>

						<!-- Tijdvak -->
						<tr><td colspan="4" style="background:#f1f1f1; font-weight:bold; padding:6px;">Tijdvak</td></tr>
						<tr>
							<td style="padding:6px;"><b>Frequentie:</b> kwartaal</td>
							<td style="padding:6px;"><b>Periode:</b> ${frappe.datetime.str_to_user(filters.from_date)} – ${frappe.datetime.str_to_user(filters.to_date)}</td>
							<td style="padding:6px;"><b>Uiterste inzenddatum:</b> ${frappe.datetime.str_to_user(frappe.datetime.add_days(filters.to_date, 30))}</td>
							<td style="padding:6px;"></td>
						</tr>

						<!-- Contactpersoon -->
						<tr><td colspan="4" style="background:#f1f1f1; font-weight:bold; padding:6px;">Contactpersoon</td></tr>
						<tr>
							<td style="padding:6px;"><b>Naam:</b> Logmans JCA</td>
							<td style="padding:6px;"><b>Telefoon:</b> 0645921347</td>
							<td style="padding:6px;"><b>Email:</b> [email@bedrijf.nl]</td>
							<td style="padding:6px;"></td>
						</tr>
					</tbody>
				</table>
				
				<!-- Contenido original del reporte -->
				<div class="table-responsive" style="width: 100%;">
					<table class="table table-bordered vat-table" style="width: 100% !important; table-layout: fixed;">
						<thead>
							<tr>
								<th style="width: 60%;">${__("Omschrijving")}</th>
								<th style="width: 20%;" class="text-right">${__("Bedrag waarover omzetbelasting wordt berekend")}</th>
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
								<td class="text-right">${formatAmount(reportData[0]?.amount)}</td>
								<td class="text-right">${formatAmount(reportData[0]?.amount * 0.21)}</td>
							</tr>
							<tr>
								<td>1b. Leveringen/diensten belast met laag tarief</td>
								<td class="text-right">${formatAmount(reportData[1]?.amount)}</td>
								<td class="text-right">${formatAmount(reportData[1]?.amount * 0.09)}</td>
							</tr>
							<tr>
								<td>1c. Leveringen/diensten belast met overige tarieven, behalve 0%</td>
								<td class="text-right">${formatAmount(reportData[2]?.amount)}</td>
								<td class="text-right">${formatAmount(reportData[2]?.amount * 0.05)}</td>
							</tr>
							<tr>
								<td>1d. Prive-gebruik</td>
								<td class="text-right">${formatAmount(reportData[3]?.amount)}</td>
								<td class="text-right">${formatAmount(reportData[3]?.amount * 0.21)}</td>
							</tr>
							<tr>
								<td>1e. Leveringen/diensten belast met 0% of niet bij u belast</td>
								<td class="text-right">${formatAmount(reportData[4]?.amount)}</td>
								<td class="text-right">€ 0</td>
							</tr>
							
							<!-- 2. Verleggingsregelingen binnenland -->
							<tr style="background-color: #f2f2f2;">
								<td colspan="3"><strong>2. Verleggingsregelingen binnenland</strong></td>
							</tr>
							<tr>
								<td>2a. Leveringen/diensten waarbij de omzetbelasting naar u is verlegd</td>
								<td class="text-right">${formatAmount(reportData[5]?.amount)}</td>
								<td class="text-right">${formatAmount(reportData[5]?.amount * 0.21)}</td>
							</tr>
							
							<!-- 3. Prestaties naar of in het buitenland -->
							<tr style="background-color: #f2f2f2;">
								<td colspan="3"><strong>3. Prestaties naar of in het buitenland</strong></td>
							</tr>
							<tr>
								<td>3a. Leveringen naar landen buiten de EU (uitvoer)</td>
								<td class="text-right">${formatAmount(reportData[6]?.amount)}</td>
								<td class="text-right">€ 0</td>
							</tr>
							<tr>
								<td>3b. Leveringen naar of diensten in landen binnen de EU</td>
								<td class="text-right">${formatAmount(reportData[7]?.amount)}</td>
								<td class="text-right">€ 0</td>
							</tr>
							<tr>
								<td>3c. Installatie/afstandsverkopen binnen de EU</td>
								<td class="text-right">${formatAmount(reportData[8]?.amount)}</td>
								<td class="text-right">€ 0</td>
							</tr>
							
							<!-- 4. Prestaties vanuit het buitenland aan u verricht -->
							<tr style="background-color: #f2f2f2;">
								<td colspan="3"><strong>4. Prestaties vanuit het buitenland aan u verricht</strong></td>
							</tr>
							<tr>
								<td>4a. Leveringen/diensten uit landen buiten de EU</td>
								<td class="text-right">${formatAmount(reportData[9]?.amount)}</td>
								<td class="text-right">${formatAmount(reportData[9]?.amount * 0.21)}</td>
							</tr>
							<tr>
								<td>4b. Leveringen/diensten uit landen binnen de EU</td>
								<td class="text-right">${formatAmount(reportData[10]?.amount)}</td>
								<td class="text-right">${formatAmount(reportData[10]?.amount * 0.21)}</td>
							</tr>
							
							<!-- 5. Voorbelasting en kleineondernemersregeling -->
							<tr style="background-color: #f2f2f2;">
								<td colspan="3"><strong>5. Voorbelasting en kleineondernemersregeling</strong></td>
							</tr>
							<tr>
								<td>5a. Verschuldigde omzetbelasting (rubriek 1 t/m 4)</td>
								<td class="text-right"></td>
								<td class="text-right">${formatAmount(reportData[12]?.amount)}</td>
							</tr>
							<tr>
								<td>5b. Voorbelasting</td>
								<td class="text-right"></td>
								<td class="text-right">${formatAmount(reportData[11]?.amount)}</td>
							</tr>
							<tr class="subtotal-row">
								<td>5c. Subtotaal (rubriek 5a min 5b)</td>
								<td class="text-right"></td>
								<td class="text-right">
									<span class="${reportData[13]?.amount >= 0 ? 'text-danger' : 'text-success'}">
										${formatAmount(reportData[13]?.amount)}
									</span>
								</td>
							</tr>
							<tr>
								<td>5d. Vermindering volgens de kleineondernemersregeling (KOR)</td>
								<td class="text-right"></td>
								<td class="text-right">${formatAmount(reportData[14]?.amount)}</td>
							</tr>
							<tr>
								<td>5e. Schatting vorige aangifte(n)</td>
								<td class="text-right"></td>
								<td class="text-right">${formatAmount(reportData[15]?.amount)}</td>
							</tr>
							<tr>
								<td>5f. Schatting deze aangifte</td>
								<td class="text-right"></td>
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
			.vat-declaration-report {
				font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
				padding: 15px;
				width: 100%;
			}
			
			.report-summary {
				background-color: #f8f9fa;
				padding: 15px;
				margin-bottom: 20px;
				border-radius: 4px;
				width: 100%;
			}
			
			.summary-item {
				margin-bottom: 10px;
			}
			
			.summary-label {
				font-weight: bold;
				margin-right: 5px;
			}
			
			.summary-value {
				font-weight: normal;
			}
			
			.table-responsive {
				width: 100%;
				overflow-x: auto;
			}
			
			.vat-table {
				width: 100% !important;
				border-collapse: collapse;
				margin-bottom: 20px;
				table-layout: fixed;
			}
			
			.vat-table th {
				background-color: #f2f2f2;
				padding: 10px;
				border: 1px solid #ddd;
				font-weight: bold;
			}
			
			.vat-table td {
				padding: 8px 10px;
				border: 1px solid #ddd;
			}
			
			.vat-table .text-right {
				text-align: right;
			}
			
			.empty-row td {
				border-left-color: transparent;
				border-right-color: transparent;
				height: 20px;
			}
			
			.total-row {
				background-color: #f9f9f9;
			}
			
			.total-row th {
				font-weight: bold;
			}
			
			.subtotal-row {
				background-color: #f9f9f9;
				font-weight: bold;
			}
			
			.text-danger {
				color: #dc3545;
			}
			
			.text-success {
				color: #28a745;
			}
			
			/* Specific styles for PDF */
			@media print {
				.vat-declaration-report {
					padding: 0;
					width: 100%;
				}
				
				.report-summary {
					border: 1px solid #ddd;
					margin-bottom: 15px;
					width: 100%;
				}
				
				.table-responsive {
					width: 100%;
				}
				
				.vat-table {
					width: 100% !important;
					table-layout: fixed;
				}
				
				.vat-table th {
					background-color: #eee !important;
					-webkit-print-color-adjust: exact;
					print-color-adjust: exact;
				}
				
				.empty-row td {
					border-left-color: transparent !important;
					border-right-color: transparent !important;
					height: 20px;
				}
				
				.total-row, .subtotal-row {
					background-color: #f5f5f5 !important;
					-webkit-print-color-adjust: exact;
					print-color-adjust: exact;
				}
				
				.text-danger {
					color: #dc3545 !important;
					-webkit-print-color-adjust: exact;
					print-color-adjust: exact;
				}
				
				.text-success {
					color: #28a745 !important;
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
