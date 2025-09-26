// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Payout Report"] = {
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
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer"
		},
		{
			fieldname: "payment_gateway",
			label: __("Payment Gateway"),
			fieldtype: "Select",
			get_data: function() {
				return new Promise(function(resolve) {
					frappe.call({
						method: "erpnext.accounts.report.payout_report.payout_report.get_payment_gateways",
						callback: function(r) {
							let options = [];
							options.push({ value: "", label: __("All Payment Gateways") });
							
							(r.message || []).forEach(function(gateway) {
								options.push({ value: gateway, label: __(gateway) });
							});
							
							resolve(options);
						}
					});
				});
			}
		}
	],
	
	// Formateador para personalizar la visualización de los datos
	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Aplicar formato personalizado para montos
		if (column.fieldtype == "Currency") {
			value = "<span style='font-weight: bold;'>" + value + "</span>";
		}
		
		// Resaltar el estado de pago
		if (column.fieldname == "payment_status") {
			if (data.payment_status == "Paid") {
				value = "<span style='color: green; font-weight: bold;'>" + value + "</span>";
			} else if (data.payment_status == "Unpaid") {
				value = "<span style='color: red; font-weight: bold;'>" + value + "</span>";
			}
		}
		
		return value;
	},
	
	// Función que se ejecuta al cargar el reporte
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
			
			// Asegurar que la tabla de encabezado también tenga ancho completo
			$('.dt-header').css({
				'width': '100%',
				'max-width': '100%'
			});
			
			// Forzar recálculo de anchos de columnas
			if (report.datatable) {
				report.datatable.refresh();
			}
		}, 500);
		
		// Configurar ajuste de tabla cuando cambia el tamaño de la ventana
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
		
		// Agregar botón para descargar PDF
		report.page.add_inner_button(__("Download PDF"), function() {
			// Obtener filtros actuales del reporte
			const filters = report.get_values();
			
			// Crear título para el PDF
			const title = __("Payout Report") + ": " + 
				frappe.datetime.str_to_user(filters.from_date) + " - " + 
				frappe.datetime.str_to_user(filters.to_date);
			
			// Abrir la vista de impresión del reporte
			frappe.render_pdf(report);
		});
		
		// Agregar botón para exportar a Excel
		report.page.add_inner_button(__("Export to Excel"), function() {
			// Método simplificado para exportar a Excel
			const filters = report.get_values();
			
			// Crear argumentos para exportación
			const args = {
				cmd: 'frappe.desk.query_report.export_query',
				report_name: 'Payout Report',
				file_format_type: 'Excel',
				filters: JSON.stringify(filters),
				visible_idx: JSON.stringify([]),
				include_indentation: 0,
				csv_delimiter: ',',
				csv_quoting: '"'
			};
			
			// Abrir URL para descargar el archivo
			open_url_post(frappe.request.url, args);
		});
	},
	
	// Configuración para la tabla de datos
	get_datatable_options: function(options) {
		// Modificar opciones de la tabla de datos
		options.layout = 'fluid'; // Cambiar de 'fixed' a 'fluid'
		options.cellHeight = 40; // Aumentar altura de celda para mejor visualización
		
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
