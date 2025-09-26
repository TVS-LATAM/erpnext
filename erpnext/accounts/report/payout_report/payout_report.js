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
			options: "\nmanual\nideal\nstripe\nrevolut",
			filterFunc: function(value) {
				// Convert to lowercase for case-insensitive filtering
				return value ? value.toLowerCase() : value;
			}
		}
	],
	// Formatter to customize data display
	formatter: function(value, row, column, data, default_formatter) {
		// Safety checks
		if (!column) return value;
		
		// Apply default formatter safely
		try {
			value = default_formatter(value, row, column, data);
		} catch (e) {
			console.warn('Error in default formatter:', e);
		}
		
		// If value is undefined or null, return empty string
		if (value === undefined || value === null) return '';
		
		// Apply custom formatting for amounts with max 3 decimals
		if (column.fieldtype === "Currency") {
			// Try to extract the numeric value
			let numValue = value;
			if (typeof value === 'string') {
				// Extract numeric value if it's wrapped in HTML
				const match = value.match(/[\d,]+\.?\d*/g);
				if (match && match.length) {
					numValue = parseFloat(match[0].replace(/,/g, ''));
					// Format with max 3 decimals
					if (!isNaN(numValue)) {
						numValue = flt(numValue, 3);
						// Replace the number in the original string
						value = value.replace(/[\d,]+\.?\d*/g, format_currency(numValue));
					}
				}
			}
			value = "<span style='font-weight: bold;'>" + value + "</span>";
		}
		
		// Add special formatting for invoice number to make it more readable and open links in new tab
		if (column.fieldname === "invoice_number" || column.fieldname === "payment_entry") {
			// Check if the value contains an anchor tag
			if (value && typeof value === 'string' && value.includes('<a')) {
				// Add target="_blank" to the anchor tag
				value = value.replace(/<a /g, '<a target="_blank" ');
			}
			
			if (column.fieldname === "invoice_number") {
				value = "<span style='font-family: monospace; font-weight: 500;'>" + value + "</span>";
			}
		}
		
		// Format invoice status - only if data and data.invoice_status exist
		if (column.fieldname === "invoice_status" && data && typeof data === 'object') {
			const status = data.invoice_status;
			if (status === "Paid") {
				value = "<span style='color: #38A169; font-weight: 500;'>" + value + "</span>";
			} else if (status === "Unpaid") {
				value = "<span style='color: #E53E3E; font-weight: 500;'>" + value + "</span>";
			}
		}
		
		return value;
	},
	// Function executed when the report loads
	onload: function(report) {
		// Apply styles to make the table take up 100% of the width
		setTimeout(function() {
			// Select the data table and apply styles for full width
			$('.datatable').css({
				'width': '100%',
				'max-width': '100%',
				'table-layout': 'fixed'
			});
			
			// Adjust the table container for full width
			$('.dt-scrollable').css({
				'width': '100%',
				'max-width': '100%',
				'overflow-x': 'auto'
			});
			
			// Make sure the table body takes full width
			$('.dt-body').css({
				'width': '100%',
				'max-width': '100%'
			});
			
			// Make sure the table wrapper takes full width
			$('.datatable-wrapper').css({
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
			
			// Fix the container width issue
			$('.dt-scrollable .dt-body').css({
				'min-width': '100%'
			});
			
			// Ensure the table container expands fully
			$('.dt-scrollable .dt-body table').css({
				'width': '100%',
				'min-width': '100%'
			});
			
			// Fix the parent container
			$('.report-container').css({
				'width': '100%',
				'max-width': '100%',
				'overflow-x': 'hidden'
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
				
				// Reajustar anchos para asegurar que la tabla ocupe el 100% del contenedor
				$('.datatable, .dt-scrollable, .report-wrapper, .dt-header, .dt-body, .datatable-wrapper').css({
					'width': '100%',
					'max-width': '100%'
				});
				
				// Ensure table takes full width with fluid layout
				$('.datatable').css({
					'table-layout': 'auto',
					'width': '100%'
				});
				
				// Make sure horizontal scrolling works if needed
				$('.dt-scrollable').css({
					'overflow-x': 'auto',
					'width': '100%'
				});
				
				// Fix the container width issue
				$('.dt-scrollable .dt-body').css({
					'min-width': '100%'
				});
				
				// Ensure the table container expands fully
				$('.dt-scrollable .dt-body table').css({
					'width': '100%',
					'min-width': '100%'
				});
				
				// Fix the parent container
				$('.report-container').css({
					'width': '100%',
					'max-width': '100%',
					'overflow-x': 'hidden'
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
		options.layout = 'fluid'; // Use fluid layout for better distribution
		options.cellHeight = 40; // Increase cell height for better visualization
		options.serialNoColumn = true; // Add serial number column
		options.checkboxColumn = false; // Remove checkbox column
		options.inlineFilters = true; // Enable inline filters
		options.dynamicRowHeight = true; // Allow rows to expand if needed
		options.showTotalRow = false; // Hide total row
		options.treeView = false; // Disable tree view
		options.fullWidth = true; // Ensure table takes full width
		options.autoWidth = true; // Auto adjust column widths
		
		// We've disabled the total row, so no need for a custom getTotalRow function
		
		// Set specific column widths for better alignment
		if (!options.columns) options.columns = [];
		
		// Calculate total width for visible columns
		let visibleColumns = options.columns.filter(col => {
			return !(col.fieldname === 'customer' || 
				col.fieldname === 'payment_type' || 
				col.fieldname === 'reference_no' ||
				col.fieldname === 'payment_status' ||
				col.fieldname === 'payment_date');
		});
		
		// Distribute column widths proportionally
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
			
			// Add flex property for better distribution
			column.flex = 1;
			
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
		// Safety check for datatable and its container
		if (!datatable || !datatable.$container) return;
		
		try {
			// Additional customization after the table is rendered
			const $scrollable = datatable.$container.find('.dt-scrollable');
			if ($scrollable && $scrollable.length) {
				$scrollable.css({
					'max-height': '500px', // Limit the height of the scrollable area
					'width': '100%',
					'max-width': '100%'
				});
			}
			
			// Ensure the table takes full width
			const $table = datatable.$container.find('.dt-scrollable table');
			if ($table && $table.length) {
				$table.css({
					'width': '100%',
					'min-width': '100%'
				});
			}
			
			// Make sure the body takes full width
			const $body = datatable.$container.find('.dt-body');
			if ($body && $body.length) {
				$body.css({
					'width': '100%',
					'min-width': '100%'
				});
			}
	
			// Add zebra striping for better readability
			const $evenRows = datatable.$container.find('.dt-row:nth-child(even)');
			if ($evenRows && $evenRows.length) {
				$evenRows.css({
					'background-color': '#f9f9f9'
				});
			}
	
			// Add hover effect
			const $rows = datatable.$container.find('.dt-row');
			if ($rows && $rows.length) {
				$rows.hover(
					function() { $(this).css('background-color', '#f0f4f8'); },
					function() { 
						if ($(this).index() % 2 === 0) {
							$(this).css('background-color', ''); 
						} else {
							$(this).css('background-color', '#f9f9f9'); 
						}
					}
				);
			}
	
			// Fix header alignment
			setTimeout(function() {
				try {
					// Ensure header text is properly aligned
					const $headers = datatable.$container.find('.dt-cell--header');
					if ($headers && $headers.length) {
						$headers.each(function() {
							const $header = $(this);
							const fieldname = $header.data('fieldname');
							
							// Center align certain headers
							if (fieldname === 'payment_status' || fieldname === 'invoice_status') {
								$header.css('text-align', 'center');
								const $content = $header.find('.dt-cell__content');
								if ($content && $content.length) {
									$content.css('text-align', 'center');
								}
							}
						});
					}
					
					// Total row has been disabled
				} catch (e) {
					console.warn('Error in header alignment or totals row:', e);
				}
			}, 100);
		} catch (e) {
			console.warn('Error in after_datatable_render:', e);
		}
	},
	
	// Add custom summary section at the bottom of the report
	onload_post_render: function(report) {
		// Check if report exists
		if (!report || !report.page || !report.page.main) return;
		
		// Add a summary section after the table
		if (!report.summary_area) {
			report.summary_area = $('<div class="summary-section">').appendTo(report.page.main.find('.report-wrapper'));
		}
		
		// Get totals from the backend
		let totalInvoiceAmount = 0;
		let totalPaidAmount = 0;
		
		// First try to get totals from custom properties in the first row
		if (report.data && report.data.length > 0 && report.data[0]) {
			if (report.data[0].total_invoices_amount !== undefined) {
				totalInvoiceAmount = flt(report.data[0].total_invoices_amount);
			}
			if (report.data[0].total_payments_amount !== undefined) {
				totalPaidAmount = flt(report.data[0].total_payments_amount);
			}
			console.log("=====> Using totals from data: ", totalInvoiceAmount, totalPaidAmount);
		} 
		// Fallback to report_summary if available
		else if (report.report_summary && Array.isArray(report.report_summary)) {
			// Find values by label in the report_summary array
			report.report_summary.forEach(function(item) {
				if (item.label === "Total Invoices") {
					totalInvoiceAmount = flt(item.value || 0);
				} else if (item.label === "Total Payments") {
					totalPaidAmount = flt(item.value || 0);
				}
			});
			console.log("=====> Using totals from report_summary: ", totalInvoiceAmount, totalPaidAmount);
		} 
		// Last resort: calculate from data
		else {
			// Only calculate paid amount as we can't reliably calculate invoice amount here
			if (report.data && Array.isArray(report.data)) {
				report.data.forEach(function(row) {
					if (row) {
						totalPaidAmount += flt(row.paid_amount || 0);
					}
				});
			}
			console.log("=====> Using fallback calculation for totals");
		}
		
		// Format the summary HTML with error handling
		try {
			// Ensure format_currency is available with max 3 decimals
			const formatCurrency = function(val) {
				// Round to 3 decimal places
				val = flt(val, 3);
				// Use format_currency if available, otherwise use toFixed(3)
				if (typeof format_currency === 'function') {
					// Get current number format
					const format = get_number_format();
					// Set precision to 3
					frappe.boot.sysdefaults.number_format = '#,###.###';
					// Format the currency
					const result = format_currency(val);
					// Restore original format
					frappe.boot.sysdefaults.number_format = format;
					return result;
				} else {
					return val.toFixed(3);
				}
			};
			
			// Calculate derived values safely
			const pendingAmount = totalInvoiceAmount - totalPaidAmount;
			const pendingColor = pendingAmount > 0 ? '#ea4335' : '#34a853';
			const completionPercentage = totalInvoiceAmount > 0 ? ((totalPaidAmount / totalInvoiceAmount) * 100).toFixed(2) : '0.00';
			
			const summaryHtml = `
				<div class="summary-box" style="margin-top: 20px; padding: 15px; background-color: #f5f7fa; border: 1px solid #d1d8dd; border-radius: 5px;">
					<h4 style="margin-top: 0; margin-bottom: 10px; font-size: 16px; font-weight: bold;">${__('Summary')}</h4>
					<div style="display: flex; justify-content: space-between; flex-wrap: wrap;">
						<div style="flex: 1; min-width: 250px;">
							<div style="margin-bottom: 8px;">
								<span style="font-weight: bold;">${__('Total Invoices')}:</span>
								<span style="font-size: 16px; color: #1a73e8; margin-left: 10px;">${formatCurrency(totalInvoiceAmount)}</span>
							</div>
							<div>
								<span style="font-weight: bold;">${__('Total Payments')}:</span>
								<span style="font-size: 16px; color: #34a853; margin-left: 10px;">${formatCurrency(totalPaidAmount)}</span>
							</div>
						</div>
						<div style="flex: 1; min-width: 250px;">
							<div style="margin-bottom: 8px;">
								<span style="font-weight: bold;">${__('Pending Amount')}:</span>
								<span style="font-size: 16px; color: ${pendingColor}; margin-left: 10px;">${formatCurrency(pendingAmount)}</span>
							</div>
							<div>
								<span style="font-weight: bold;">${__('Payment Completion')}:</span>
								<span style="font-size: 16px; margin-left: 10px;">${completionPercentage}%</span>
							</div>
						</div>
					</div>
				</div>
			`;
			
			// Update the summary area if it exists
			if (report.summary_area && typeof report.summary_area.html === 'function') {
				report.summary_area.html(summaryHtml);
			}
		} catch (e) {
			console.warn('Error generating summary HTML:', e);
			// Provide a simple fallback summary if there's an error
			if (report.summary_area && typeof report.summary_area.html === 'function') {
				// Round values to 3 decimal places
				const roundedInvoiceAmount = flt(totalInvoiceAmount, 3);
				const roundedPaidAmount = flt(totalPaidAmount, 3);
				
				report.summary_area.html(`
					<div class="summary-box" style="margin-top: 20px; padding: 15px; background-color: #f5f7fa; border: 1px solid #d1d8dd; border-radius: 5px;">
						<h4 style="margin-top: 0; margin-bottom: 10px; font-size: 16px; font-weight: bold;">${__('Summary')}</h4>
						<div>
							<div style="margin-bottom: 8px;">
								<span style="font-weight: bold;">${__('Total Invoices')}:</span>
								<span style="margin-left: 10px;">${roundedInvoiceAmount.toFixed(3)}</span>
							</div>
							<div>
								<span style="font-weight: bold;">${__('Total Payments')}:</span>
								<span style="margin-left: 10px;">${roundedPaidAmount.toFixed(3)}</span>
							</div>
						</div>
					</div>
				`);
			}
		}
	}
};
