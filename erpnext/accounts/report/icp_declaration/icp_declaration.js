// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

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
		}
	],
	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Apply custom formatting if needed
		if (column.fieldname == "Net Amount" || column.fieldname == "Total VAT") {
			value = "<span style='font-weight: bold;'>" + value + "</span>";
		}
		
		return value;
	},
	
	onload: async function(report) {
		// Aplicar estilos para que la tabla ocupe el 100% del ancho
		setTimeout(function() {
			// Seleccionar la tabla de datos y aplicar estilos
			$('.datatable').css({
				'width': '100%',
				'max-width': '100%'
			});
			
			// Ajustar el contenedor de la tabla
			$('.dt-scrollable').css({
				'width': '100%',
				'max-width': '100%'
			});
			
			// Ajustar el contenedor principal del reporte
			$('.report-wrapper').css({
				'width': '100%',
				'max-width': '100%'
			});
			
			// Asegurar que la tabla de encabezados también tenga ancho completo
			$('.dt-header').css({
				'width': '100%',
				'max-width': '100%'
			});
			
			// Forzar recálculo del ancho de las columnas
			if (report.datatable) {
				report.datatable.refresh();
			}
		}, 500);
		
		// Configurar ajuste de tabla cuando cambie el tamaño de la ventana
		$(window).on('resize', function() {
			if (report.datatable) {
				report.datatable.refresh();
				
				// Reajustar anchos
				$('.datatable, .dt-scrollable, .report-wrapper, .dt-header').css({
					'width': '100%',
					'max-width': '100%'
				});
			}
		});
		
		// Add PDF download button
		report.page.add_inner_button(__('Download PDF'), async function() {
			// Obtener los filtros actuales del reporte
			const filters = report.get_values();
			
			// Crear un título para el PDF
			const title = __("ICP Declaration") + ": " + 
				frappe.datetime.str_to_user(filters.from_date) + " - " + 
				frappe.datetime.str_to_user(filters.to_date);
			
			// Preparar datos para la plantilla HTML
			const reportData = report.data;
			
			// Función para formatear montos
			function formatAmount(amount) {
				if (amount === undefined || amount === null) return "-";
				return frappe.format(amount, {fieldtype: 'Currency'});
			}
			
			async function getLetterHead(fromDate, toDate) {
				let letterhead_html = "";
				await frappe.call({
					method: "frappe.desk.form.load.getdoc?doctype=Letter%20Head&name=ICP%20Declaration",
					args: {
						doctype: "Letter Head",
						name: "ICP Declaration"
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
								letterhead_html = letterhead_html.replaceAll('${{periode}}', periode);
								letterhead_html = letterhead_html.replaceAll('${{uiterste_inzenddatum}}', formattedDeadline);
							}
						}
					}
				});
				return letterhead_html;
			}
			
			// Get letterhead HTML content with date parameters
			const letterhead = await getLetterHead(filters.from_date, filters.to_date);
			
			// Obtener datos de la empresa desde los filtros
			const company = filters.company || "";
			
			// Verificar si hay datos disponibles
			let rows_html = '';
			let net_amount_total = 0;
			let vat_total = 0;
			
			if (reportData && reportData.length) {
				// Filtrar para incluir solo filas de datos (no totales)
				const rows_data = reportData.filter(row => 
					!row.is_total_row && row["Customer Name"] !== "Total"
				);
				
				// Generar filas HTML
				rows_data.forEach(row => {
					net_amount_total += flt(row["Net Amount"]) || 0;
					vat_total += flt(row["Total VAT"]) || 0;
					
					rows_html += `
					<tr>
						<td>${row["Customer Name"] || ""}</td>
						<td>${row["VAT Identification Number"] || ""}</td>
						<td class="text-right">${formatAmount(row["Net Amount"])}</td>
						<td class="text-right">${formatAmount(row["Total VAT"])}</td>
						<td>${row["Invoice Type"] || ""}</td>
					</tr>
					`;
				});
			}
			
			// Crear HTML basado en el template mejorado
			const html = `
			<div class="icp-declaration-report" style="width: 100%;">
				${letterhead}	
				<!-- Contenido del reporte -->
				<div class="table-responsive" style="width: 100%;">
					<table class="table table-bordered icp-table" style="width: 100% !important; table-layout: fixed;">
						<thead>
							<tr>
								<th style="width: 30%;">${__("Customer Name")}</th>
								<th style="width: 20%;">${__("VAT Identification Number")}</th>
								<th style="width: 15%;" class="text-right">${__("Net Amount")}</th>
								<th style="width: 15%;" class="text-right">${__("Total VAT")}</th>
								<th style="width: 20%;">${__("Invoice Type")}</th>
							</tr>
						</thead>
						<tbody>
							${rows_html}
						</tbody>
						<tfoot>
							<tr class="empty-row">
								<td>&nbsp;</td>
								<td>&nbsp;</td>
								<td>&nbsp;</td>
								<td>&nbsp;</td>
								<td>&nbsp;</td>
							</tr>
							<tr class="total-row">
								<th>${__("Total")}</th>
								<th></th>
								<th class="text-right">${formatAmount(net_amount_total)}</th>
								<th class="text-right">${formatAmount(vat_total)}</th>
								<th></th>
							</tr>
						</tfoot>
					</table>
				</div>
			</div>
			`;
			
			// Estilos para el PDF
			const styles = `
			<style>
.icp-declaration-report {
  font-family: 'Segoe UI', Arial, sans-serif;
  font-size: 13px;
  padding: 15px;
  width: 100%;
}

.table-responsive {
  width: 100%;
  overflow-x: auto;
}

.icp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-top: 16px;
}

.icp-table th {
  background-color: #f5f5f5;
  padding: 6px 8px;
  border: 1px solid #ccc;
  text-align: left;
  font-weight: 600;
}

.icp-table td {
  padding: 6px 8px;
  border: 1px solid #ccc;
  vertical-align: top;
}

.icp-table .text-right {
  text-align: right;
}

.icp-table .group-header td {
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
  .icp-declaration-report {
    padding: 0;
    width: 100%;
  }

  .icp-table th,
  .icp-table .group-header td,
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
				report_name: 'ICP Declaration',
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
	
	// Configuración para la tabla de datos
	get_datatable_options: function(options) {
		// Modificar opciones de la tabla de datos
		options.layout = 'fluid'; // Cambiar de 'fixed' a 'fluid'
		options.cellHeight = 40; // Aumentar altura de celdas para mejor visualización
		
		// Asegurar que la tabla ocupe todo el ancho disponible
		options.dynamicRowHeight = false;
		
		return options;
	},
	
	// Función que se ejecuta después de renderizar la tabla
	after_datatable_render: function(datatable) {
		// Personalización adicional después de que se renderiza la tabla
		datatable.$container.find('.dt-scrollable').css({
			'max-height': '500px' // Limitar la altura del área desplazable
		});
	}
};
