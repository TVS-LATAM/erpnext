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
	
	onload: function(report) {
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
		
		report.page.add_inner_button(__('Download PDF'), function() {
			// Obtener los filtros actuales del reporte
			const filters = report.get_values();
			
			// Crear un título para el PDF
			const title = __("ICP Declaration") + ": " + 
				frappe.datetime.str_to_user(filters.from_date) + " - " + 
				frappe.datetime.str_to_user(filters.to_date);
			
			// Usar directamente los datos del reporte
			let rows_data = [];
			
			// Verificar si hay datos disponibles
			if (report.data && report.data.length) {
				// Filtrar para incluir solo filas de datos (no totales)
				rows_data = report.data.filter(row => 
					!row.is_total_row && row["Customer Name"] !== "Total"
				);
				
				// Calcular totales
				let net_amount_total = 0;
				let vat_total = 0;
				
				rows_data.forEach(row => {
					net_amount_total += flt(row["Net Amount"]) || 0;
					vat_total += flt(row["Total VAT"]) || 0;
				});
				
				// Agregar una fila vacía para crear espacio
				let empty_row = {};
				for (let col of report.get_columns_for_print()) {
					empty_row[col.fieldname] = "";
				}
				empty_row.is_empty_row = true;
				rows_data.push(empty_row);
				
				// Agregar fila de totales
				let total_data = {};
				total_data["Customer Name"] = __("Total");
				total_data["VAT Identification Number"] = "";
				total_data["Net Amount"] = net_amount_total;
				total_data["Total VAT"] = vat_total;
				total_data["Invoice Type"] = "";
				total_data.is_total_row = true;
				rows_data.push(total_data);
			}
			
			// Generar el PDF usando frappe.render_grid
			frappe.ui.get_print_settings(false, (print_settings) => {
				frappe.render_grid({
					title: title,
					subtitle: __("Company") + ": " + filters.company,
					print_settings: print_settings,
					columns: report.get_columns_for_print(),
					data: rows_data,
					can_use_smaller_font: 1,
					report: true,
					// Función personalizada para formatear filas
					row_formatter: function(row, data) {
						if (data.is_empty_row) {
							row.css({
								'height': '20px',
								'border-left': 'none',
								'border-right': 'none'
							});
							row.find('td').css({
								'border-left': 'none',
								'border-right': 'none'
							});
						}
						if (data.is_total_row) {
							row.css({
								'background-color': '#f9f9f9',
								'font-weight': 'bold'
							});
						}
					}
				});
			});
		});
		
		// Agregar botón para exportar a Excel
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
		// Aplicar estilos adicionales a la tabla después de renderizarla
		$('.datatable').css({
			'width': '100%',
			'max-width': '100%'
		});
		
		// Ajustar el contenedor de la tabla
		$('.dt-scrollable').css({
			'width': '100%',
			'max-width': '100%'
		});
		
		// Forzar un recálculo del ancho
		datatable.refresh();
	}
};
