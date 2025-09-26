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
	
	// Formatter to customize data display
	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Apply custom formatting for amounts
		if (column.fieldtype == "Currency") {
			value = "<span style='font-weight: bold;'>" + value + "</span>";
		}
		
		// Highlight payment status
		if (column.fieldname == "payment_status") {
			if (data.payment_status == "Paid") {
				value = "<span style='color: #38A169; font-weight: bold; background-color: #E6FFEA; padding: 3px 8px; border-radius: 4px;'>" + value + "</span>";
			} else if (data.payment_status == "Unpaid") {
				value = "<span style='color: #E53E3E; font-weight: bold; background-color: #FFF5F5; padding: 3px 8px; border-radius: 4px;'>" + value + "</span>";
			} else {
				value = "<span style='color: #718096; font-weight: bold; background-color: #F7FAFC; padding: 3px 8px; border-radius: 4px;'>" + value + "</span>";
			}
		}

		// Add special formatting for invoice number to make it more readable
		if (column.fieldname == "invoice_number") {
			value = "<span style='font-family: monospace; font-weight: 500;'>" + value + "</span>";
		}

		// Format invoice status
		if (column.fieldname == "invoice_status") {
			if (data.invoice_status == "Paid") {
				value = "<span style='color: #38A169; font-weight: 500;'>" + value + "</span>";
			} else if (data.invoice_status == "Unpaid") {
				value = "<span style='color: #E53E3E; font-weight: 500;'>" + value + "</span>";
			}
		}
		
		return value;
	},
	
	// Function executed when the report loads
	onload: function(report) {
		// Apply styles to make the table take up 100% of the width
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

			// Improve cell padding and alignment
			$('.dt-cell').css({
				'padding': '8px 12px',
				'white-space': 'nowrap',
				'overflow': 'hidden',
				'text-overflow': 'ellipsis',
				'min-width': '100px'
			});

			// Improve header styling
			$('.dt-cell--header').css({
				'font-weight': 'bold',
				'background-color': '#f5f7fa',
				'padding': '10px 12px',
				'height': 'auto',
				'line-height': '1.5',
				'border-bottom': '2px solid #d1d8dd'
			});
			
			// Make sure text in headers is visible and properly formatted
			$('.dt-cell__content').css({
				'white-space': 'normal',
				'overflow': 'visible',
				'text-overflow': 'clip'
			});

			// Improve header text display
			$('.dt-cell--header .dt-cell__content').css({
				'font-weight': 'bold',
				'text-align': 'center',
				'white-space': 'pre-line',
				'line-height': '1.2'
			});
			
			// Force recalculation of column widths
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
	
	// Configuration for the data table
	get_datatable_options: function(options) {
		// Modify data table options
		options.layout = 'fixed'; // Use fixed layout for better column control
		options.cellHeight = 40; // Increase cell height for better visualization
		options.serialNoColumn = true; // Add serial number column
		options.checkboxColumn = false; // Remove checkbox column
		options.inlineFilters = true; // Enable inline filters
		options.dynamicRowHeight = true; // Allow rows to expand if needed
		options.showTotalRow = false; // Don't show total row
		options.treeView = false; // Disable tree view
		
		// Set specific column widths for better alignment
		if (!options.columns) options.columns = [];
		options.columns.forEach(function(column) {
			// Set minimum width for all columns
			column.minWidth = 100;
			
			// Set specific widths for important columns
			if (column.fieldname === 'invoice_number') column.width = 140;
			if (column.fieldname === 'invoice_date') column.width = 110;
			if (column.fieldname === 'customer_name') column.width = 180;
			if (column.fieldname === 'invoice_amount') column.width = 130;
			if (column.fieldname === 'payment_entry') column.width = 150;
			if (column.fieldname === 'paid_amount') column.width = 130;
			if (column.fieldname === 'payment_gateway') column.width = 150;
			
			// Hide columns that we don't want to display
			if (column.fieldname === 'customer' || 
				column.fieldname === 'payment_type' || 
				column.fieldname === 'reference_no' ||
				column.fieldname === 'payment_status' ||
				column.fieldname === 'payment_date') {
				column.hidden = true;
			}
		});
		
		return options;
	},
	
	// Function that runs after rendering the table
	after_datatable_render: function(datatable) {
		// Additional customization after the table is rendered
		datatable.$container.find('.dt-scrollable').css({
			'max-height': '500px' // Limit the height of the scrollable area
		});

		// Add zebra striping for better readability
		datatable.$container.find('.dt-row:nth-child(even)').css({
			'background-color': '#f9f9f9'
		});

		// Add hover effect
		datatable.$container.find('.dt-row').hover(
			function() { $(this).css('background-color', '#f0f4f8'); },
			function() { 
				if ($(this).index() % 2 === 0) {
					$(this).css('background-color', ''); 
				} else {
					$(this).css('background-color', '#f9f9f9'); 
				}
			}
		);

		// Fix header alignment
		setTimeout(function() {
			// Ensure header text is properly aligned
			datatable.$container.find('.dt-cell--header').each(function() {
				const $header = $(this);
				const fieldname = $header.data('fieldname');
				
				// Center align certain headers
				if (fieldname === 'payment_status' || fieldname === 'invoice_status') {
					$header.css('text-align', 'center');
					$header.find('.dt-cell__content').css('text-align', 'center');
				}
			});
		}, 100);
	}
};
