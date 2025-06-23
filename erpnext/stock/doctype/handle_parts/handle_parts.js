// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Handle Parts", {
    upload: async function (frm) {
        const uploadButton = document.querySelector('.frappe-control[data-fieldname="upload"] button[data-fieldname="upload"]');
        frm.page.set_indicator(__('Uploading. Please wait...'), 'orange');
        if (!frm.doc.excel) {
            frappe.msgprint({
                title: __('Validation Error'),
                message: __('Please select an Excel file to upload.'),
                indicator: 'red',
            });
            frm.page.clear_indicator();
            return;
        }

        if (uploadButton) {
            uploadButton.disabled = true;
        }
        try {
            const fileResponse = await fetch(frm.doc.excel)
            const file = await fileResponse.blob()
            const fileBuffer = await file.arrayBuffer()
            

            const presignedUrl = await get_presigned_url(frm, file)
            if (!presignedUrl) {
                return;
            }
            await upload_file(frm, fileBuffer, presignedUrl)
            
        } catch (error) {
            console.error("Error in upload function:", error);
            frappe.msgprint({
                title: __('Error'),
                message: __('An error occurred during the upload process.'),
                indicator: 'red',
            });
        } finally {
            // Re-enable the button and reset the indicator
            if (uploadButton) {
                uploadButton.disabled = false;
            }
            frm.page.clear_indicator();
        }
    },
    product_bundle_errors: async function (frm) {
        frm.page.set_indicator(__('Searching and creating report. Please wait...'), 'orange');
        const { aws_url } = await frappe.db.get_doc('Handle Parts Config');
        if (!aws_url) {
            frappe.msgprint({
                title: __('Validation Error'),
                message: __('The URL for product bundle errors is missing or invalid.'),
                indicator: 'red',
            });
            return;
        }

        const response = await fetch(`${aws_url}/erpnext-excel/product-bundle-errors`);
        if (response.ok) {
            const errors = await response.json();
            if (!errors.length) {
                return frappe.msgprint({
                    title: __('Success'),
                    message: __('No errors found.'),
                    indicator: 'green',
                })
            }
            const createdAt = errors.length > 0 ? errors[0].created_at : '';
            const title = __('Product Bundle Errors (Red items are not found, and the bundle was not created)');

            let dialog = new frappe.ui.Dialog({
                title: title,
                fields: [
                    {
                        label: __('Errors'),
                        fieldtype: 'HTML',
                        fieldname: 'errors_list',
                        options: generate_error_table(errors, createdAt)
                    }
                ]
            });
            dialog.$wrapper.modal({
                backdrop: "static",
                keyboard: false,
                size: "1024px"
            });

            dialog.show();
            dialog.$wrapper.find('.modal-dialog').css("width", "90%").css("max-width", "90%");
            frm.page.clear_indicator();
        } else {
            frm.page.clear_indicator();
        }
    },
    parts_errors: async function (frm) {
        frm.page.set_indicator(__('Searching and creating report. Please wait...'), 'orange');
        const { aws_url } = await frappe.db.get_doc('Handle Parts Config');
        if (!aws_url) {
            frappe.msgprint({
                title: __('Validation Error'),
                message: __('The URL for parts errors is missing or invalid.'),
                indicator: 'red',
            });
            return;
        }

        const response = await fetch(`${aws_url}/erpnext-excel/parts-errors`);
        if (response.ok) {
            const errors = await response.json();
            if (!errors.length) {
                return frappe.msgprint({
                    title: __('Success'),
                    message: __('No errors found.'),
                    indicator: 'green',
                })
            }
            const createdAt = errors.length > 0 ? errors[0].created_at : '';
            const title = __('Parts Errors was no created. Fields are missing and are required.');

            let dialog = new frappe.ui.Dialog({
                title: title,
                fields: [
                    {
                        label: __('Errors'),
                        fieldtype: 'HTML',
                        fieldname: 'errors_list',
                        options: generate_parts_error_table(errors, createdAt)
                    }
                ]
            });
            dialog.$wrapper.modal({
                backdrop: "static",
                keyboard: false,
                size: "1024px"
            });

            dialog.show();
            dialog.$wrapper.find('.modal-dialog').css("width", "90%").css("max-width", "90%");
            frm.page.clear_indicator();
        } else {
            frm.page.clear_indicator();
        }
    },

    download_parts_excel_format: async function (frm) {
        frm.page.set_indicator(__('Downloading...'), 'orange');
        const data = await frappe.db.get_doc('Handle Parts Config');
        if (!data || !data.excel_format_url) {
            frappe.msgprint({
                title: __('Validation Error'),
                message: __('The URL for the Excel format is missing or invalid.'),
                indicator: 'red',
            });
            return;
        }
        window.location.href = data.excel_format_url;
        frm.page.clear_indicator();
    },
    compatibility_errors: function(frm) {
        frm.page.set_indicator(__('Searching and creating report. Please wait...'), 'orange');
        frappe.db.get_doc('Handle Parts Config').then(async config => {
            if (!config.aws_url) {
                frappe.msgprint({
                    title: __('Validation Error'),
                    message: __('The URL for compatibility errors is missing or invalid.'),
                    indicator: 'red',
                });
                return;
            }

            try {
                const response = await fetch(`${config.aws_url}/erpnext-excel/mongo-errors`);
                if (response.ok) {
                    const errors = await response.json();
                    if (!errors.length) {
                        frappe.msgprint({
                            title: __('No Errors'),
                            message: __('No compatibility errors found.'),
                            indicator: 'green',
                        });
                        return;
                    }

                    const dialog = new frappe.ui.Dialog({
                        title: __('Compatibility Errors'),
                        fields: [
                            {
                                label: __('Errors'),
                                fieldtype: 'HTML',
                                fieldname: 'errors_list',
                                options: generate_mongo_error_table(errors)
                            }
                        ]
                    });

                    dialog.$wrapper.modal({
                        backdrop: "static",
                        keyboard: false,
                        size: "1024px"
                    });

                    dialog.show();
                    dialog.$wrapper.find('.modal-dialog').css("width", "90%").css("max-width", "90%");
                } else {
                    throw new Error('Failed to fetch errors');
                }
            } catch (error) {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Failed to fetch compatibility errors.'),
                    indicator: 'red',
                });
            } finally {
                frm.page.clear_indicator();
            }
        });
    },
    compatibility_errors: function(frm) {
        frm.page.set_indicator(__('Searching and creating report. Please wait...'), 'orange');
        frappe.db.get_doc('Handle Parts Config').then(async config => {
            if (!config.aws_url) {
                frappe.msgprint({
                    title: __('Validation Error'),
                    message: __('The URL for transmission compatibility errors is missing or invalid.'),
                    indicator: 'red',
                });
                return;
            }

            try {
                const response = await fetch(`${config.aws_url}/erpnext-excel/transmissions-errors`);
                if (response.ok) {
                    const errors = await response.json();
                    if (!errors.length) {
                        frappe.msgprint({
                            title: __('No Errors'),
                            message: __('No transmission errors found.'),
                            indicator: 'green',
                        });
                        return;
                    }

                    const dialog = new frappe.ui.Dialog({
                        title: __('Transmission Errors'),
                        fields: [
                            {
                                label: __('Errors'),
                                fieldtype: 'HTML',
                                fieldname: 'errors_list',
                                options: generate_transmission_error_table(errors)
                            }
                        ]
                    });

                    dialog.$wrapper.modal({
                        backdrop: "static",
                        keyboard: false,
                        size: "1024px"
                    });

                    dialog.show();
                    dialog.$wrapper.find('.modal-dialog').css("width", "90%").css("max-width", "90%");
                } else {
                    throw new Error('Failed to fetch errors');
                }
            } catch (error) {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Failed to fetch transmission errors.'),
                    indicator: 'red',
                });
            } finally {
                frm.page.clear_indicator();
            }
        });
    },
});

function generate_error_table(errors, createdAt) {
    let table_html = `
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>TVS PN</th>
                    <th>Item Codes (tvs pn)</th>
                    <th>Quantities</th>
                </tr>
            </thead>
            <tbody>
    `;

    if (createdAt) {
        const formattedDate = new Date(createdAt).toLocaleString();
        table_html += `
            <tr style="background-color: #f8d7da; color: #721c24;">
                <td colspan="3"><strong>Information Created At: ${formattedDate}</strong></td>
            </tr>
        `;
    }

    errors.forEach(error => {
        let row_html = `
            <tr>
                <td>${error.new_item_code}</td>
                <td>
        `;

        let qty_html = '';
        error.items.forEach(item => {
            const row_style = item.found ? "" : "background-color: #f8d7da; color: #721c24;";

            row_html += `<span style="${row_style}">${item.item_code}</span><br>`;
            qty_html += `<span style="${row_style}">${item.qty}</span><br>`;
        });

        row_html += `</td><td>${qty_html}</td></tr>`;
        table_html += row_html;
    });

    table_html += `
            </tbody>
        </table>
    `;
    return table_html;
}


function generate_parts_error_table(errors, createdAt) {
    let table_html = `
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>Item Code</th>
                    <th>Item Name</th>
                    <th>Item Category</th>
                    <th>Sub Category Name</th>
                    <th>Condition</th>
                    <th>Brand</th>
                    <th>Supplier</th>
                    <th>TVS PN</th>
                </tr>
            </thead>
            <tbody>
    `;

    if (createdAt) {
        const formattedDate = new Date(createdAt).toLocaleString();
        table_html += `
            <tr style="background-color: #f8d7da; color: #721c24;">
                <td colspan="12"><strong>Information Created At: ${formattedDate}</strong></td>
            </tr>
        `;
    }

    errors.forEach(error => {
        table_html += `
            <tr>
                <td style="${!error.item_code ? 'background-color: #f8d7da;' : ''}">${error.item_code || ''}</td>
                <td style="${!error.item_name ? 'background-color: #f8d7da;' : ''}">${error.item_name || ''}</td>
                <td style="${!error.item_category ? 'background-color: #f8d7da;' : ''}">${error.item_category || ''}</td>
                <td style="${!error.sub_category_name ? 'background-color: #f8d7da;' : ''}">${error.sub_category_name || ''}</td>
                <td style="${!error.condition ? 'background-color: #f8d7da;' : ''}">${error.condition || ''}</td>
                <td style="${!error.brand ? 'background-color: #f8d7da;' : ''}">${error.brand || ''}</td>
                <td style="${!error.supplier ? 'background-color: #f8d7da;' : ''}">${error.supplier || ''}</td>
                <td style="${!error.tvs_pn ? 'background-color: #f8d7da;' : ''}">${error.tvs_pn || ''}</td>
            </tr>
        `;
    });

    table_html += `
            </tbody>
        </table>
    `;
    return table_html;
}

function generate_mongo_error_table(errors) {
    let table_html = `
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>Type</th>
                    <th>Message</th>
                    <th>Items</th>
                    <th>Timestamp</th>
                </tr>
            </thead>
            <tbody>
    `;

    errors.forEach(error => {
        const type_style = error.type === "missing_items" ? "background-color: #f8d7da; color: #721c24;" : "background-color: #fff3cd; color: #856404;";
        const timestamp = new Date(error.timestamp).toLocaleString();

        let items_html = '';
        if (error.items && error.items.length) {
            items_html = error.items.map(item => `<div>${item}</div>`).join('');
        }

        table_html += `
            <tr>
                <td style="${type_style}">${error.type}</td>
                <td>${error.message || ''}</td>
                <td>${items_html}</td>
                <td>${timestamp}</td>
            </tr>
        `;
    });

    table_html += `
            </tbody>
        </table>
    `;
    return table_html;
}

function generate_transmission_error_table(errors) {
    let table_html = `
        <table class="table table-bordered">
            <thead>
                <tr>
                    <th>Type</th>
                    <th>Message</th>
                    <th>Items</th>
                    <th>Timestamp</th>
                </tr>
            </thead>
            <tbody>
    `;

    errors.forEach(error => {
        const type_style = error.type === "missing_items" ? "background-color: #f8d7da; color: #721c24;" : "background-color: #fff3cd; color: #856404;";
        const timestamp = new Date(error.timestamp).toLocaleString();

        let items_html = '';
        if (error.items && error.items.length) {
            items_html = error.items.map(item => `<div>${item}</div>`).join('');
        }

        table_html += `
            <tr>
                <td style="${type_style}">${error.type}</td>
                <td>${error.message || ''}</td>
                <td>${items_html}</td>
                <td>${timestamp}</td>
            </tr>
        `;
    });

    table_html += `
            </tbody>
        </table>
    `;
    return table_html;
}

async function get_presigned_url(frm, file) {
    const filename = frm.doc.excel.split('/').pop()
    const { aws_url } = await frappe.db.get_doc('Handle Parts Config');

    const action = {
        "Item": "parts",
        "Transmission Code Compatibility": "transmission_compatibility"
    }

    const presignedUrlResponse = await fetch(`${aws_url}/erpnext-excel/pre-signed-url`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            filename: filename,
            contentType: file.type,
            doctype: frm.doc.doctype,
            action: action[frm.doc.module],
            user_to_notify: frappe.session.user,
            timeout: 5 // minutes
        })
    }).then(response => response.json())

    if (!presignedUrlResponse || !presignedUrlResponse.url) {
        frappe.msgprint({
            title: __('Validation Error'),
            message: __('Failed to generate pre-signed URL.'),
            indicator: 'red',
        });
        frm.page.clear_indicator();
        if (uploadButton) {
            uploadButton.disabled = false;
        }
        return;
    }
    
    return presignedUrlResponse.url
}

async function upload_file(frm, fileBuffer, presignedUrl) {
    const uploadResponse = await fetch(presignedUrl, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        },
        body: fileBuffer
    });
 
    if (uploadResponse.ok) {
        frappe.msgprint({
            title: __('Success'),
            message: __('File uploaded successfully. The process will complete within 10 minutes, and you will be notified once it is done.'),
            indicator: 'green',
        });
        frm.set_value('excel', "");
        frm.refresh_field('excel');
    } else {
        const errorText = await uploadResponse.text();
        console.error('Upload failed:', errorText);
        frappe.msgprint({
            title: __('Error'),
            message: __('File upload failed: ') + errorText,
            indicator: 'red',
        });
    }
}
