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

// Global module variables
let paymentData = null;        // Payment data for current project
let selectedPayments = [];     // Array of selected payments to associate with the project

/**
 * Formats a monetary value according to German format (EUR)
 * @param {number|string} amount - Amount to format
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
 * Formats an ISO date in German format
 * @param {string} dateStr - Date in ISO format or string
 * @returns {string} Formatted date
 */
function formatDateValue(dateStr) {
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
}

/**
 * Renders individual rows for the payment details table
 * @param {Array} payments - Array of payment objects
 * @returns {string} HTML string with table rows
 */
function renderPaymentDetailsRows(payments) {
  if (!Array.isArray(payments) || payments.length === 0) {
    return '<tr><td colspan="4"><span class="text-danger text-center">No payment details available</span></td></tr>';
  }
  
  return payments.map(payment => {
    const gateway = payment.payment_gateway || 'Unknown';
    const amount = formatCurrencyValue(payment.amount);
    const id = payment.id || '—';
    const date = formatDateValue(payment.created_at);
    const reference = payment.reference || '—';
    const description = payment.description || '—';
    
    return `
      <tr data-payment-id="${id}" data-amount="${payment.amount || 0}" data-gateway="${gateway}" data-date="${payment.created_at || ''}" data-reference="${reference}" data-description="${description}">
        <td>${amount}</td>
        <td>${date}</td>
        <td>${reference}</td>
        <td>${description}</td>
      </tr>
    `;
  }).join('');
}

/**
 * Renders individual rows for the payment history table
 * @param {Array} payments - Array of payment objects
 * @param {Array} [historyIds=[]] - Array of IDs from history table to highlight matching rows
 * @returns {string} HTML string with table rows
 */
function renderPaymentRows(payments, historyIds = []) {
  if (!Array.isArray(payments) || payments.length === 0) {
    return '<tr><td colspan="5">No payment history available</td></tr>';
  }
  
  // Convert historyIds to a Set for faster lookups
  const historyIdSet = new Set(historyIds);
  
  return payments.map(payment => {
    const date = formatDateValue(payment.created_at);
    const gateway = payment.payment_gateway || 'Unknown';
    const amount = formatCurrencyValue(payment.amount);
    const id = payment.id || '';
    const reference = payment.reference || '-';
    const description = payment.description || '-';
    
    // Check if this payment ID exists in the history IDs
    const isMatched = historyIdSet.has(id);
    const rowStyle = isMatched ? 'background-color: #d4edda;' : ''; // Light green background for matching rows
    const checked = isMatched ? 'checked' : ''; // Checkbox checked if matched
    
    return `
      <tr style="font-size: 0.8rem; ${rowStyle}" data-payment-id="${id}" data-amount="${payment.amount || 0}" data-gateway="${gateway}" data-date="${payment.created_at || ''}" data-reference="${reference}" data-description="${description}">
        <td>${date}</td>
        <td class="text-right">${amount}</td>
        <td>${reference}</td>
        <td>${description}</td>
        <td class="text-center">
          <input type="checkbox" class="payment-checkbox" ${checked} data-payment-id="${id}" onchange="erpnext.projects.payment_validation.togglePaymentSelection(this)">
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
  // Guardar los datos en la variable de módulo para que esté disponible para togglePaymentSelection
  paymentData = data;
  
  // Inicializar el array de pagos seleccionados con los pagos ya asociados al proyecto
  selectedPayments = data && data.response ? [...data.response] : [];
  
  const dialog = new frappe.ui.Dialog({
    title: 'Confirm Payment Method',
    fields: [
      {
        fieldtype: 'HTML',
        fieldname: 'payment_layout',
        options: `
          <div class="row">
            <!-- Left Column - Form Fields -->
            <div class="col-md-5" style="border-right: 1px solid #e5e7eb;">
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
                      <th colspan="6" class="text-center bg-light; text-danger">
                        Payment Details (Payments detected for this project)
                      </th>
                    </tr>
                    <tr>
                      <th>Amount</th>
                      <th>Date</th>
                      <th>Reference</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody id="payment-details-tbody">
                    ${data && data.response && data.response.length > 0
                      ? renderPaymentDetailsRows(data.response)
                      : '<tr><td colspan="6">No payment details available</td></tr>'
                    }
                  </tbody>
                  <tfoot>
                    <tr>
                      <th scope="row" colspan="1" class="text-end">Total Paid</th>
                      <td colspan="5">${formatCurrencyValue(data?.totalPaid || 0)}</td>
                    </tr>
                    <tr>
                      <th scope="row" colspan="1" class="text-end">Total Invoice</th>
                      <td colspan="5">${formatCurrencyValue(data?.totalToPaid || 0)}</td>
                    </tr>
                    <tr>
                      <th scope="row" colspan="1" class="text-end">Remaining</th>
                      <td colspan="5">
                        <strong style="${(data?.totalToPaid || 0) - (data?.totalPaid || 0) > 0 ? 'color: red;' : ''}">
                          ${formatCurrencyValue((data?.totalToPaid || 0) - (data?.totalPaid || 0))}
                        </strong>
                      </td>
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
            <div class="col-md-7">
              <div class="payment-history-table" style="height:100%; overflow-y: auto;">
                <table class="table table-bordered table-hover">
                  <thead>
                    <tr>
                      <th colspan="6" class="text-center bg-light">Revolut Payments List <small style="font-size: 0.8rem;" class="text-danger">(Select a payment to link to this project)</small></th>
                    </tr>
                    <tr>
                      <th>Date</th>
                      <th class="text-right">Amount</th>
                      <th>Reference</th>
                      <th>Description</th>
                      <th class="text-center">Options</th>
                    </tr>
                  </thead>
                  <tbody id="payment-history-tbody">
                    ${data && data.history
  ? renderPaymentRows(
      data.history,
      data.response ? data.response.map(item => item.id).filter(Boolean) : []
    )
  : '<tr><td colspan="6">No payment history available</td></tr>'}

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
      'height': '95%'
    });
    
    // Fijar los encabezados de las tablas
    $(dialog.$wrapper).find('thead').css({
      'position': 'sticky',
      'top': '0',
      'background-color': 'white',
      'z-index': '1'
    });
    $(dialog.$wrapper).find('.modal-body').css({
      'max-height': '90vh',
      'overflow-y': 'auto'
    });
    $(dialog.$wrapper).find('.modal-content').css({
      'height': '100%',
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
  // Confirmation message for the user
  const confirmMessage = "Are you sure you want to mark approved quotations as paid? " +
                        "By confirming, you acknowledge that the payment has been verified in the company's account.";
  
  frappe.confirm(confirmMessage, async () => {
    try {
      // 1. Get approved quotations for this project
      const response = await frappe.call({
        method: "frappe.desk.reportview.get_list",
        args: {
          doctype: "Quotation",
          filters: [["project_name", "=", frm.doc.name], ["status", "=", "Approved"]],
          fields: ["name", "grand_total"]
        }
      });

      // Check if there are approved quotations
      if (!response.message || response.message.length === 0) {
        frappe.msgprint({
          title: 'Error',
          indicator: 'red',
          message: 'No approved quotations found for this project'
        });
        return;
      }
      
      // 2. Calculate the total amount of quotations
      const quotations = response.message;
      const totalAmount = quotations.reduce((sum, q) => sum + q.grand_total, 0);
      
      // 3. Get API configuration
      const { aws_url, confirm_payment_webhook } = await frappe.db.get_doc('Rest Config');
      if (!aws_url || !confirm_payment_webhook) {
        frappe.msgprint('AWS URL or payment confirmation webhook not found');
        return;
      }

      // 4. Prepare data to send to the API
      const objData = {
        confirm_payment_webhook: confirm_payment_webhook,
        selected_method: values.confirm_method,
        name: frm.doc.name,
        payment_gateway: "manual",
        total: totalAmount,
        payment_confirmation: values.payment_confirmation,
        payment_details: values.payment_details || '',
        array_payment: selectedPayments.length ? selectedPayments : [],
      };

      // 5. Send request to the API
      const apiResponse = await fetch(`${aws_url}manual-confirm-payment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(objData)
      });

      // 6. Handle response
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
    } catch (error) {
      frappe.msgprint({
        title: 'Error',
        indicator: 'red',
        message: 'An error occurred while processing the payment: ' + error.message
      });
    }
  }, () => {
    frappe.msgprint('Payment action cancelled');
  });
}

/**
 * Main function to validate bank transfer payment
 * @param {Object} frm - The form object
 */
async function validateBankTransferPayment(frm) {
  // 1. Check if the project is already paid or completed
  const invalidStatuses = ["Invoice paid", "Completed", "Cancelled"];
  if (invalidStatuses.includes(frm.doc.status)) {
    frappe.msgprint('The project is already paid, completed, or cancelled');
    return;
  }
  
  try {
    // 2. Get the API URL from configuration
    const { aws_url } = await frappe.db.get_doc('Rest Config');
    if (!aws_url) {
      frappe.msgprint('AWS URL not found');
      return;
    }
    
    // 3. Get payment data from the API
    const response = await fetch(`${aws_url}manual-reconcile-payments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: frm.doc.name })
    });
    
    if ("error" in response) {
      frappe.msgprint(response.error);
      return;
    }
    
    // 4. Process the response
    const data = await response.json();
    
    // 5. Format payment details if history exists
    let manual_payment_details = '';
    if (data?.history?.length > 0) {
      manual_payment_details = data.history.map((payment, index) => {
        return [
          `Payment #${index + 1}`,
          `- Gateway: ${payment.payment_gateway || '-'}`,
          `- Amount: ${payment.amount ? payment.amount.toFixed(2) : '0.00'} €`,
          `- Request ID: ${payment.id || '-'}`,
          `- Transaction ID: ${payment.id || '-'}`,
          `- Date: ${payment.created_at || '-'}`,
          payment.details ? `- Details: ${payment.details}` : ''
        ].filter(Boolean).join('\n');
      }).join('\n');
    }
    
    // 6. Show the payment confirmation dialog
    createPaymentConfirmationDialog(frm, data, manual_payment_details);
    
  } catch (error) {
    frappe.msgprint({
      title: 'Error',
      indicator: 'red',
      message: 'An error occurred while validating the payment: ' + error.message
    });
  }
}

/**
 * Handles the selection/deselection of payments in the history table
 * @param {HTMLElement} checkbox - The checkbox that has been checked/unchecked
 */
function togglePaymentSelection(checkbox) {
  // Get payment data from row attributes
  const paymentId = checkbox.getAttribute('data-payment-id');
  const row = checkbox.closest('tr');
  const amount = row.getAttribute('data-amount');
  const gateway = row.getAttribute('data-gateway');
  const date = row.getAttribute('data-date');
  const reference = row.getAttribute('data-reference');
  const description = row.getAttribute('data-description');
  
  // Get the payment details table
  const paymentDetailsTable = document.getElementById('payment-details-tbody');
  
  // Create payment object with the obtained data
  const paymentItem = {
    id: paymentId,
    amount: parseFloat(amount) || 0,
    payment_gateway: gateway,
    created_at: date,
    reference: reference,
    description: description
  };
  
  if (checkbox.checked) {
    // CASE 1: Checkbox checked - Add payment
    
    // Check if it already exists in the details table
    if (!document.querySelector(`#payment-details-tbody tr[data-payment-id="${paymentId}"]`)) {
      // Create new row in the details table
      const newRow = document.createElement('tr');
      newRow.setAttribute('data-payment-id', paymentId);
      newRow.setAttribute('data-amount', amount);
      newRow.setAttribute('data-gateway', gateway);
      newRow.setAttribute('data-date', date);
      newRow.setAttribute('data-reference', reference);
      newRow.setAttribute('data-description', description);
      
      // Format values for display
      const formattedDate = formatDateValue(date);
      const formattedAmount = formatCurrencyValue(amount);
      
      // Set the HTML content of the row
      newRow.innerHTML = `
        <td>${formattedAmount}</td>
        <td>${formattedDate}</td>
        <td>${reference}</td>
        <td>${description}</td>
      `;
      
      // Add the row to the table
      paymentDetailsTable.appendChild(newRow);
      
      // Highlight the row in the history table
      row.style.backgroundColor = '#d4edda';
      
      // Add to the selected payments array if it doesn't exist
      const existingIndex = selectedPayments.findIndex(item => item.id === paymentId);
      if (existingIndex === -1) {
        selectedPayments.push(paymentItem);
      }
    }
  } else {
    // CASE 2: Checkbox unchecked - Remove payment
    
    // Remove from the details table
    const detailRow = document.querySelector(`#payment-details-tbody tr[data-payment-id="${paymentId}"]`);
    if (detailRow) {
      detailRow.remove();
    }
    
    // Remove highlighting from the row in the history table
    row.style.backgroundColor = '';
    
    // Remove from the selected payments array
    const existingIndex = selectedPayments.findIndex(item => item.id === paymentId);
    if (existingIndex !== -1) {
      selectedPayments.splice(existingIndex, 1);
    }
  }
  
  // Update totals
  updatePaymentTotals();
}

// Define the payment validation object with all public functions
const PaymentValidation = {
  // Main functions
  validateBankTransferPayment,   // Initiates the payment validation process
  togglePaymentSelection,        // Handles payment selection/deselection
  
  // Rendering functions
  renderPaymentHistoryTable,     // Renders the payment history table
  renderPaymentRows,             // Renders rows for the history table
  renderPaymentDetailsRows,      // Renders rows for the details table
  
  // Utility functions
  formatCurrencyValue,           // Formats monetary values
  formatDateValue,               // Formats dates
  
  // Internal functions (used by the main ones)
  createPaymentConfirmationDialog,
  handlePaymentConfirmation,
  updatePaymentTotals
};

// Export functions to the ERPNext namespace
frappe.provide('erpnext.projects.payment_validation');
erpnext.projects.payment_validation = PaymentValidation;

// Initialize the module when the document is ready
$(document).ready(function() {
  console.log("Payment validation module initialized");
});

/**
 * Updates the payment totals in the details table
 * based on the currently selected payments
 */
function updatePaymentTotals() {
  // Calculate the total paid directly from the selected payments array
  const totalPaid = selectedPayments.reduce((sum, payment) => sum + (payment.amount || 0), 0);
  
  // Get the invoice total from the table
  const totalInvoiceRow = Array.from(document.querySelectorAll('tfoot tr')).find(row => 
    row.textContent.includes('Total Invoice')
  );
  const totalInvoiceElement = totalInvoiceRow?.querySelector('td');
  const totalInvoiceText = totalInvoiceElement?.textContent || '0';
  const totalInvoice = parseFloat(totalInvoiceText.replace(/[^\d,-]/g, '').replace(',', '.')) || 0;
  
  // Calculate the remaining balance
  const remaining = Math.max(0, totalInvoice - totalPaid);
  
  // Update the elements in the table
  const totalPaidRow = Array.from(document.querySelectorAll('tfoot tr')).find(row => 
    row.textContent.includes('Total Paid')
  );
  const remainingRow = Array.from(document.querySelectorAll('tfoot tr')).find(row => 
    row.textContent.includes('Remaining')
  );
  
  // Update the total paid element
  const totalPaidElement = totalPaidRow?.querySelector('td');
  if (totalPaidElement) {
    totalPaidElement.textContent = formatCurrencyValue(totalPaid);
  }
  
  // Update the remaining balance element
  const remainingElement = remainingRow?.querySelector('td strong') || remainingRow?.querySelector('td');
  if (remainingElement) {
    remainingElement.textContent = formatCurrencyValue(remaining);
    remainingElement.style.color = remaining > 0 ? 'red' : '';
  }
}
