/**
 * Payment Validation Module for ERPNext Projects
 * 
 * This module contains all functions related to payment validation and display
 * for the Project doctype, including bank transfer validation, payment history
 * rendering, and UI components for the payment confirmation dialog.
 * 
 * @module payment_validation
 */

// Asegurarse de que el namespace esté disponible
frappe.provide('erpnext.projects.payment_validation');

// Indicar que el módulo se está cargando
console.log('Loading payment validation module...');

/**
 * Formats a currency value according to the German locale
 * @param {number} amount - Amount to format
 * @returns {string} Formatted currency string
 */
function formatCurrencyValue(amount) {
  try {
    return parseFloat(amount).toLocaleString('de-DE', {
      style: 'currency',
      currency: 'EUR'
    });
  } catch (e) {
    return amount || '—';
  }
}

/**
 * Renders individual payment rows for the payment details table
 * @param {Array} payments - Array of payment objects
 * @returns {string} HTML string with table rows
 */
function renderPaymentDetailsRows(payments) {
  if (!Array.isArray(payments) || payments.length === 0) {
    return '<tr><td colspan="4"><span class="text-danger text-center">No payment details available</span> </td></tr>';
  }
  
  // Format date helper function
  const formatDate = (dateStr) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString('de-DE', {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (e) {
      return dateStr || '—';
    }
  };
  
  // Format amount helper function
  const formatAmount = (amount) => {
    try {
      return parseFloat(amount).toLocaleString('de-DE', {
        style: 'currency',
        currency: 'EUR'
      });
    } catch (e) {
      return amount || '—';
    }
  };
  
  return payments.map(payment => {
    const gateway = payment.payment_gateway || 'Unknown';
    const amount = formatAmount(payment.amount);
    const id = payment.id || '—';
    const date = formatDate(payment.created_at);
    
    return `
      <tr data-payment-id="${id}">
        <td>${gateway}</td>
        <td>${amount}</td>
        <td>${id}</td>
        <td>${date}</td>
      </tr>
    `;
  }).join('');
}

/**
 * Renders individual payment rows for the payment history table
 * @param {Array} payments - Array of payment objects
 * @param {Array} [historyIds=[]] - Array of IDs from the history table to highlight matching rows
 * @returns {string} HTML string with table rows
 */
function renderPaymentRows(payments, historyIds = []) {
  if (!Array.isArray(payments) || payments.length === 0) {
    return '<tr><td colspan="4">No payment history available</td></tr>';
  }
  
  // Convert historyIds to a Set for faster lookups
  const historyIdSet = new Set(historyIds);
  
  // Format date helper function
  const formatDate = (dateStr) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString('de-DE', {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (e) {
      return dateStr || '—';
    }
  };
  
  // Format amount helper function
  const formatAmount = (amount) => {
    try {
      return parseFloat(amount).toLocaleString('de-DE', {
        style: 'currency',
        currency: 'EUR'
      });
    } catch (e) {
      return amount || '—';
    }
  };
  
  return payments.map(payment => {
    const date = formatDate(payment.created_at);
    const gateway = payment.payment_gateway || 'Unknown';
    const amount = formatAmount(payment.amount);
    const id = payment.id || '';
    
    // Check if this payment ID exists in the history IDs
    const isMatched = historyIdSet.has(id);
    const rowStyle = isMatched ? 'background-color: #d4edda;' : ''; // Light green background for matching rows
    const checked = isMatched ? 'checked' : ''; // Checkbox checked if matched
    
    return `
      <tr style="${rowStyle}" data-payment-id="${id}" data-amount="${payment.amount || 0}" data-gateway="${gateway}" data-date="${payment.created_at || ''}">
        <td>${date}</td>
        <td>${gateway}</td>
        <td class="text-right">${amount}</td>
        <td class="text-center">
          <input type="checkbox" class="payment-checkbox" ${checked} data-payment-id="${id}" onchange="window.togglePaymentSelection(this)">
        </td>
      </tr>
    `;
  }).join('');
}

/**
 * Renders a payment history table as an HTML string.
 * - Safe: escapes user-visible strings to prevent XSS.
 * - Robust: tolerates missing fields and mixed types.
 * - Internationalized: uses Intl for currency and date formatting.
 *
 * @param {Object} data
 * @param {Array}  data.history            - List of payments [{ created_at, amount, payment_gateway }]
 * @param {number} [data.fullAmount]       - Total invoice amount
 * @param {number} [data.totalPaid]        - Optional precomputed total paid
 * @param {Object} [opts]
 * @param {string} [opts.locale='en-US']   - BCP 47 locale for formatting
 * @param {string} [opts.currency='EUR']   - ISO 4217 currency code
 * @param {'asc'|'desc'} [opts.sortDir='desc'] - Sort by date ascending or descending
 * @param {Intl.DateTimeFormatOptions} [opts.dateOptions] - Override date display options
 * @returns {string} HTML string
 */
function renderPaymentHistoryTable(data, opts = {}) {
  const {
    locale = 'de-DE',
    currency = 'EUR',
    sortDir = 'desc',
    dateOptions = {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    }
  } = opts;

  const history = Array.isArray(data?.history) ? data.history : [];

  const dtf = new Intl.DateTimeFormat(locale, dateOptions);
  const nf = new Intl.NumberFormat(locale, { style: 'currency', currency, currencyDisplay: 'symbol' });

  const esc = (s) =>
    String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');

  const toNumber = (x) => {
    if (typeof x === 'number' && Number.isFinite(x)) return x;
    const n = Number(String(x).replace(/[^\d.-]/g, ''));
    return Number.isFinite(n) ? n : 0;
  };

  const formatDate = (isoLike) => {
    const d = new Date(isoLike);
    return Number.isFinite(d.getTime()) ? dtf.format(d) : '—';
  };

  const formatCurrency = (amount) => nf.format(toNumber(amount));

  // Sort payments by date
  const sorted = [...history].sort((a, b) => {
    const ta = new Date(a?.created_at).getTime();
    const tb = new Date(b?.created_at).getTime();
    const da = Number.isFinite(ta) ? ta : 0;
    const db = Number.isFinite(tb) ? tb : 0;
    return sortDir === 'asc' ? da - db : db - da;
  });

  // Totals
  const totalPaid = toNumber(data?.totalPaid);
  const fullAmount = toNumber(data?.totalToPaid);
  const remaining = Math.max(0, fullAmount - totalPaid);

  // Empty state
  if (sorted.length === 0) {
    return `
      <div style="margin-top:20px;">
        <h4>Revolut Payments List</h4>
        <p class="text-muted mb-0">No payment history available.</p>
      </div>
    `;
  }

  const rowsHtml = sorted
    .map((p) => {
      const gateway = p?.payment_gateway ? esc(p.payment_gateway) : 'Bank Transfer';
      const date = formatDate(p?.created_at);
      const amount = formatCurrency(p?.amount);
      return `
        <tr>
          <td data-label="Date">${date}</td>
          <td data-label="Payment Gateway">${gateway}</td>
          <td class="text-end" data-label="Amount">${amount}</td>
        </tr>
      `;
    })
    .join('');

  return `
    <div style="margin-top:20px;">
      <h4 class="mb-2">Payment History</h4>
      <table class="table table-bordered table-hover align-middle" style="margin-top:10px;">
        <caption class="visually-hidden">Payments made toward this invoice</caption>
        <thead class="table-light">
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Payment Gateway</th>
            <th scope="col" class="text-end">Amount</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" colspan="1" class="text-end">Total Paid</th>
            <td colspan="1">${formatCurrency(totalPaid)}</td>
            <td class="text-end"></td>
          </tr>
          <tr>
            <th scope="row" colspan="1" class="text-end">Total Invoice</th>
            <td colspan="1">${formatCurrency(fullAmount)}</td>
            <td class="text-end"></td>
          </tr>
          <tr>
            <th scope="row" colspan="1" class="text-end">Remaining</th>
            <td colspan="1"><strong style="${remaining > 0 ? 'color: red;' : ''}">${formatCurrency(remaining)}</strong></td>
            <td class="text-end"></td>
          </tr>
        </tfoot>
      </table>
    </div>
  `;
}

/**
 * Creates and displays a payment confirmation dialog with two-column layout
 * @param {Object} frm - The form object
 * @param {Object} data - Payment data from the API
 * @param {string} manual_payment_details - Formatted payment details string
 * @returns {frappe.ui.Dialog} The dialog object
 */
function createPaymentConfirmationDialog(frm, data, manual_payment_details) {
  const dialog = new frappe.ui.Dialog({
    title: 'Confirm Payment Method',
    fields: [
      {
        fieldtype: 'HTML',
        fieldname: 'payment_layout',
        options: `
          <div class="row">
            <!-- Left Column - Form Fields -->
            <div class="col-md-6" style="border-right: 1px solid #e5e7eb;">
              <div class="form-group">
                <label class="control-label">Confirm Method of Payment *</label>
                <select class="form-control" id="payment_confirmation">
                  <option value="Bank Transfer">Bank Transfer</option>
                  <option value="Cash">Cash</option>
                  <option value="Credit Card">Credit Card</option>
                  <option value="Other">Other</option>
                </select>
              </div>
              <div class="form-group">
                <label class="control-label">Select Payment Type *</label>
                <select class="form-control" id="confirm_method">
                  <option value="workshop">workshop</option>
                  <option value="loan car">loan car</option>
                </select>
              </div>
              <div class="form-group">
                <div class="payment-details-table" style="max-height: 300px; overflow-y: auto;">
                  <table class="table table-bordered table-hover">
                    <thead>
                      <tr>
                        <th colspan="4" class="text-center bg-light">Payment Details (Payments detected for this project)</th>
                      </tr>
                      <tr>
                        <th>Gateway</th>
                        <th>Amount</th>
                        <th>Transaction ID</th>
                        <th>Date</th>
                      </tr>
                    </thead>
                    <tbody id="payment-history-tbody">
                      ${data && data.history ? renderPaymentRows(data.history, data.response ? data.response.map(item => item.id).filter(Boolean) : []) : '<tr><td colspan="4">No payment history available</td></tr>'}
                    </tbody>
                    <tfoot>
                      <tr>
                        <th scope="row" colspan="1" class="text-end">Total Paid</th>
                        <td colspan="3">${formatCurrencyValue(data?.totalPaid || 0)}</td>
                      </tr>
                      <tr>
                        <th scope="row" colspan="1" class="text-end">Total Invoice</th>
                        <td colspan="3">${formatCurrencyValue(data?.fullAmount || 0)}</td>
                      </tr>
                      <tr>
                        <th scope="row" colspan="1" class="text-end">Remaining</th>
                        <td colspan="3"><strong style="${(data?.fullAmount || 0) - (data?.totalPaid || 0) > 0 ? 'color: red;' : ''}">${formatCurrencyValue((data?.fullAmount || 0) - (data?.totalPaid || 0))}</strong></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
                <input type="hidden" id="payment_details" value="${manual_payment_details}">
              </div>
              <ul style="color: #d14343; padding-left: 20px;">
                <li>Approved quotations will be marked as paid.</li>
                <li>An invoice will be generated.</li>
                <li>The invoice will be sent to the customer.</li>
                <li>The project status will be updated to "Invoice Paid".</li>
                <li>This action can <span style="font-weight: bold;">NOT</span> be undone.</li>
              </ul>
            </div>
            
            <!-- Right Column - Payment History Table -->
            <div class="col-md-6">
              <div class="payment-history-table" style="max-height: 55vh; overflow-y: auto;">
                <table class="table table-bordered table-hover">
                  <thead>
                    <tr>
                      <th colspan="4" class="text-center bg-light">Revolut Payments List <small style="font-size: 0.8rem;" class="text-danger">(Select a payment to link to this project)</small></th>
                    </tr>
                    <tr>
                      <th>Date</th>
                      <th>Payment Gateway</th>
                      <th class="text-right">Amount</th>
                      <th class="text-center">Options</th>
                    </tr>
                  </thead>
                  <tbody id="payment-history-tbody">
                    ${data && data.history ? renderPaymentRows(data.history, data.history ? data.history.map(item => item.id).filter(Boolean) : []) : '<tr><td colspan="4">No payment history available</td></tr>'}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        `
      }
    ],
    primary_action_label: 'Confirm Payment Type and Proceed',
    primary_action: function() {
      const values = {
        payment_confirmation: document.getElementById('payment_confirmation').value,
        payment_details: document.getElementById('payment_details').value,
        confirm_method: document.getElementById('confirm_method').value
      };
      
      handlePaymentConfirmation(frm, values, data);
    }
  });

  // Adjust dialog size
  dialog.show();
  setTimeout(() => {
    $(dialog.$wrapper).find('.modal-dialog').css({
      'max-width': '90%',
      'width': '90%',
      'height': '85%'
    });
    
    // Fijar los encabezados de las tablas
    $(dialog.$wrapper).find('thead').css({
      'position': 'sticky',
      'top': '0',
      'background-color': 'white',
      'z-index': '1'
    });
    $(dialog.$wrapper).find('.modal-body').css({
      'max-height': '75vh',
      'overflow-y': 'auto'
    });
  }, 200);

  return dialog;
}

/**
 * Handles the payment confirmation process
 * @param {Object} frm - The form object
 * @param {Object} values - Form values
 * @param {Object} data - Payment data from the API
 */
async function handlePaymentConfirmation(frm, values, data) {
  frappe.confirm(
    "Are you sure you want to mark approved quotations as paid? By confirming, you acknowledge that the payment has been verified in the company's account.",
    async () => {
      try {
        const response = await frappe.call({
          method: "frappe.desk.reportview.get_list",
          args: {
            doctype: "Quotation",
            filters: [["project_name", "=", frm.doc.name], ["status", "=", "Approved"]],
            fields: ["name", "grand_total"]
          }
        });

        if (response.message && response.message.length > 0) {
          const quotations = response.message;
          const totalAmount = quotations.reduce((sum, q) => sum + q.grand_total, 0);
          const { aws_url, confirm_payment_webhook } = await frappe.db.get_doc('Rest Config');
          if (!aws_url || !confirm_payment_webhook) {
            frappe.msgprint('AWS URL or Confirm Payment Webhook not found');
            return;
          }

          const paymentData = {
            confirm_payment_webhook: confirm_payment_webhook,
            selected_method: values.confirm_method,
            name: frm.doc.name,
            payment_gateway: "manual",
            total: totalAmount,
            payment_confirmation: values.payment_confirmation,
            payment_details: values.payment_details || '',
            manual_payment_details: values.payment_details || ''
          };

          const apiResponse = await fetch(`${aws_url}manual-confirm-payment`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify(paymentData)
          });

          if (apiResponse.ok) {
            frappe.msgprint({
              title: 'Success',
              indicator: 'green',
              message: 'Payment confirmed successfully'
            });
            frm.reload_doc();
          } else {
            throw new Error('API call failed');
          }
        } else {
          frappe.msgprint({
            title: 'Error',
            indicator: 'red',
            message: 'No quotations found for this project'
          });
        }
      } catch (error) {
        frappe.msgprint({
          title: 'Error',
          indicator: 'red',
          message: 'An error occurred while processing the payment: ' + error.message
        });
      }
    },
    () => {
      frappe.msgprint('Payment action cancelled');
    }
  );
}

/**
 * Main function to validate bank transfer payment
 * @param {Object} frm - The form object
 */
async function validateBankTransferPayment(frm) {
  if (frm.doc.status === "Invoice paid" || frm.doc.status === "Completed" || frm.doc.status === "Cancelled") {
    frappe.msgprint('The project is already paid, completed, or cancelled');
    return;
  }
  
  const { aws_url } = await frappe.db.get_doc('Rest Config');
  if (!aws_url) {
    frappe.msgprint('AWS URL not found');
    return;
  }
  
  try {
    // Fetch payment data from API
    const response = await fetch(`${aws_url}manual-reconcile-payments`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ name: frm.doc.name })
    });
    
    if ("error" in response) {
      frappe.msgprint(response.error);
      return;
    }
    
    const data = await response.json();
    console.log("Payment data:", data);
    console.log("History data:", data.history);
    console.log("Response data:", data.response);
    
    // Format payment details if history exists
    let manual_payment_details = '';
    if (data && data.history && data.history.length > 0) {
      const rawItems = data.history;
      const paymentDetails = rawItems.map((it, i) => {
        let payment = `Payment #${i + 1}\n`;
        payment += `- Gateway: ${it.payment_gateway || '-'}\n`;
        payment += `- Amount: ${it.amount ? it.amount.toFixed(2) : '0.00'} €\n`;
        payment += `- Request ID: ${it.id || '-'}\n`;
        payment += `- Transaction ID: ${it.id || '-'}\n`;
        payment += `- Date: ${it.created_at || '-'}`;
        if (it.details) {
          payment += `\n- Details: ${it.details}`;
        }
        return payment;
      });
      manual_payment_details = paymentDetails.join('\n');
    }
    
    // Create and show the payment confirmation dialog
    createPaymentConfirmationDialog(frm, data, manual_payment_details);
    
  } catch (error) {
    console.error("Error validating payment:", error);
    frappe.msgprint({
      title: 'Error',
      indicator: 'red',
      message: 'An error occurred while validating the payment: ' + error.message
    });
  }
}

// Definir el objeto de validación de pagos
var PaymentValidation = {
  validateBankTransferPayment: validateBankTransferPayment,
  renderPaymentHistoryTable: renderPaymentHistoryTable,
  renderPaymentRows: renderPaymentRows,
  renderPaymentDetailsRows: renderPaymentDetailsRows,
  formatCurrencyValue: formatCurrencyValue,
  createPaymentConfirmationDialog: createPaymentConfirmationDialog,
  handlePaymentConfirmation: handlePaymentConfirmation
};

// Exportar las funciones globalmente
frappe.provide('erpnext.projects.payment_validation');
erpnext.projects.payment_validation = PaymentValidation;

// Asegurarse de que el namespace esté disponible cuando el documento esté listo
$(document).ready(function() {
  console.log("Payment validation module initialized");
  
  // Verificar que las funciones estén disponibles
  if (typeof erpnext.projects.payment_validation.validateBankTransferPayment === 'function') {
    console.log("Payment validation functions are available");
  }
});

// Función para manejar la selección/deselección de pagos
window.togglePaymentSelection = function(checkbox) {
  const paymentId = checkbox.getAttribute('data-payment-id');
  const row = checkbox.closest('tr');
  const amount = row.getAttribute('data-amount');
  const gateway = row.getAttribute('data-gateway');
  const date = row.getAttribute('data-date');
  
  // Obtener la tabla de detalles de pago
  const paymentDetailsTable = document.getElementById('payment-details-tbody');
  
  if (checkbox.checked) {
    // Si está marcado, agregar a la tabla de detalles de pago si no existe
    if (!document.querySelector(`#payment-details-tbody tr[data-payment-id="${paymentId}"]`)) {
      const formattedDate = new Date(date).toLocaleString('de-DE', {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
      
      const formattedAmount = parseFloat(amount).toLocaleString('de-DE', {
        style: 'currency',
        currency: 'EUR'
      });
      
      const newRow = document.createElement('tr');
      newRow.setAttribute('data-payment-id', paymentId);
      newRow.setAttribute('data-amount', amount); // Guardar el monto para cálculos futuros
      newRow.innerHTML = `
        <td>${gateway}</td>
        <td>${formattedAmount}</td>
        <td>${paymentId}</td>
        <td>${formattedDate}</td>
      `;
      
      paymentDetailsTable.appendChild(newRow);
      
      // Actualizar el estilo de la fila para marcarla como seleccionada
      row.style.backgroundColor = '#d4edda';
      
      console.log(`Added payment ${paymentId} with amount ${amount} to details table`);
    }
  } else {
    // Si está desmarcado, eliminar de la tabla de detalles de pago
    const detailRow = document.querySelector(`#payment-details-tbody tr[data-payment-id="${paymentId}"]`);
    if (detailRow) {
      detailRow.remove();
      console.log(`Removed payment ${paymentId} with amount ${amount} from details table`);
    }
    
    // Actualizar el estilo de la fila para marcarla como no seleccionada
    row.style.backgroundColor = '';
  }
  
  // Actualizar totales si es necesario
  updatePaymentTotals();
};

// Función para actualizar los totales de pago
function updatePaymentTotals() {
  // Obtener todas las filas seleccionadas en la tabla de historial de pagos
  const selectedCheckboxes = document.querySelectorAll('.payment-checkbox:checked');
  
  // Calcular el total pagado sumando los montos de las filas seleccionadas
  let totalPaid = 0;
  selectedCheckboxes.forEach(checkbox => {
    const row = checkbox.closest('tr');
    const amount = parseFloat(row.getAttribute('data-amount')) || 0;
    totalPaid += amount;
  });
  
  // Obtener el valor del total de la factura (que es innamovible)
  // Buscamos el elemento que contiene el texto "Total Invoice" y luego obtenemos su celda de valor
  const totalInvoiceRow = Array.from(document.querySelectorAll('tfoot tr')).find(row => 
    row.textContent.includes('Total Invoice')
  );
  const totalInvoiceElement = totalInvoiceRow?.querySelector('td');
  const totalInvoiceText = totalInvoiceElement?.textContent || '0';
  const totalInvoice = parseFloat(totalInvoiceText.replace(/[^\d,-]/g, '').replace(',', '.')) || 0;
  
  // Calcular el restante
  const remaining = totalInvoice - totalPaid;
  
  // Actualizar los elementos en la tabla
  // Buscamos las filas que contienen los textos "Total Paid" y "Remaining"
  const totalPaidRow = Array.from(document.querySelectorAll('tfoot tr')).find(row => 
    row.textContent.includes('Total Paid')
  );
  const remainingRow = Array.from(document.querySelectorAll('tfoot tr')).find(row => 
    row.textContent.includes('Remaining')
  );
  
  const totalPaidElement = totalPaidRow?.querySelector('td');
  const remainingElement = remainingRow?.querySelector('td strong') || remainingRow?.querySelector('td');
  
  if (totalPaidElement) {
    totalPaidElement.textContent = formatCurrencyValue(totalPaid);
  }
  
  if (remainingElement) {
    remainingElement.textContent = formatCurrencyValue(remaining);
    // Actualizar el color del texto según si hay saldo pendiente o no
    remainingElement.style.color = remaining > 0 ? 'red' : '';
  }
  
  console.log('Updated payment totals:', { totalPaid, totalInvoice, remaining });
}

// Exportar las funciones globalmente de nuevo para asegurarse
window.erpnext = window.erpnext || {};
window.erpnext.projects = window.erpnext.projects || {};
window.erpnext.projects.payment_validation = PaymentValidation;
