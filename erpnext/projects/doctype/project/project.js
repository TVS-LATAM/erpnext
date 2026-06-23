// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// Import payment validation module
frappe.provide('erpnext.projects.payment_validation');

frappe.ui.form.on("Project", {
	setup(frm) {
		// Cargar el módulo de validación de pagos al inicio
		console.log("Project setup - Loading payment validation module");
		frm.make_methods = {
			Timesheet: () => {
				open_form(frm, "Timesheet", "Timesheet Detail", "time_logs");
			},
			"Purchase Order": () => {
				open_form(frm, "Purchase Order", "Purchase Order Item", "items");
			},
			"Purchase Receipt": () => {
				open_form(frm, "Purchase Receipt", "Purchase Receipt Item", "items");
			},
			"Purchase Invoice": () => {
				open_form(frm, "Purchase Invoice", "Purchase Invoice Item", "items");
			},
		};
	},
	onload: function (frm) {
		const so = frm.get_docfield("sales_order");
		so.get_route_options_for_new_doc = () => {
			if (frm.is_new()) return {};
			return {
				customer: frm.doc.customer,
				project_name: frm.doc.name,
			};
		};

		frm.set_query("user", "users", function () {
			return {
				query: "erpnext.projects.doctype.project.project.get_users_for_project",
			};
		});

		frm.set_query("department", function (doc) {
			return {
				filters: {
					company: doc.company,
				},
			};
		});

		// sales order
		frm.set_query("sales_order", function () {
			var filters = {
				project: ["in", frm.doc.__islocal ? [""] : [frm.doc.name, ""]],
				company: frm.doc.company,
			};

			if (frm.doc.customer) {
				filters["customer"] = frm.doc.customer;
			}

			return {
				filters: filters,
			};
		});

		frm.set_query("cost_center", () => {
			return {
				filters: {
					company: frm.doc.company,
				},
			};
		});

		frm.set_query('quotations', function () {
			var filters = [
				['status', '=', 'Draft']
			]

			return {
				filters,
			}
		})

		frm.set_query('sales_invoice', function () {
			const filters = [
				['status', '=', 'Unpaid']
			]
			return { filters }
		})

		frappe.realtime.off("docinfo_update");
		frappe.realtime.on('docinfo_update', (data) => {
			if (data.key === "attachment_logs") {
				insertCarousel(frm)
			}
		})

		const sidebar = $(".layout-side-section");

		if (sidebar.is(':visible')) {
			sidebar.hide();
		}
	},

	refresh: async function (frm) {
		if (frm.doc.__islocal) {
			frm.web_link && frm.web_link.remove();
		} else {
			frm.add_web_link("/projects?project=" + encodeURIComponent(frm.doc.name));
			frm.trigger("show_dashboard");
		}

		if (!frm.is_new()) {
			frm.trigger("setup_checklist_buttons");
		}

		const isWorkshopViewer = await erpnext.utils.isWorkshopViewer(frm);
		const isMechanic = await erpnext.utils.isMechanic(frm);
		const isJuniorMechanic = await erpnext.utils.isJuniorMechanic(frm);
		const isSeniorMechanic = await erpnext.utils.isSeniorMechanic(frm);

		if (!frm.is_new() && !isWorkshopViewer && !isMechanic && !isJuniorMechanic && !isSeniorMechanic) {
			frm.add_custom_button(__('Generate Quotation'), async () => {
				const doc = await frappe.model.get_new_doc('Quotation');
				doc.party_name = frm.doc.customer;
				frappe.new_doc('Quotation', {
					project_name: frm.doc.name,
					party_name: frm.doc.customer,
					quotation_to: 'Customer'
				});
			});

			insertValidateBankTransferPaymentButton(frm);
			insertTranslation(frm)
			viewCustomerDetails(frm);
		}
		if (isMechanic || isJuniorMechanic || isSeniorMechanic) {
			installQuotationItems(frm);
			insertCarousel(frm);
			insertVinSearchButton(frm);
		}

		if (!isWorkshopViewer && !isMechanic && !isJuniorMechanic && !isSeniorMechanic) {
			installChat(frm);
			installQuotationItems(frm);
			insertCarousel(frm);
			insertVinSearchButton(frm);
			insertResendPaymentLink(frm);
			insertUpdateQueuePositionButton(frm);
			insertLoanCarButton(frm)
			frm.trigger("set_custom_buttons");
		} else {
			const sidebar = $(".layout-side-section");
			if (sidebar.is(':visible')) {
				sidebar.hide();
			}
		}
		if (!frm.previous_status) {
			frm.previous_status = frm.doc.status
		}
	},

	setup_checklist_buttons: function (frm) {
		["Arrival Checklist", "Job Checklist", "Quality Control Checklist", "DSG Oil Change Checklist"].forEach((doctype) => {
			frm.add_custom_button(
				__(doctype),
				() => frappe.new_doc(doctype, { project: frm.doc.name }),
				__("Checklists")
			);
		});
	},

	set_custom_buttons: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Duplicate Project with Tasks"),
				() => {
					frm.events.create_duplicate(frm);
				},
				__("Actions")
			);

			frm.add_custom_button(
				__("Update Total Purchase Cost"),
				() => {
					frm.events.update_total_purchase_cost(frm);
				},
				__("Actions")
			);

			frm.trigger("set_project_status_button");

			if (frappe.model.can_read("Task")) {
				frm.add_custom_button(
					__("Gantt Chart"),
					function () {
						frappe.route_options = {
							project: frm.doc.name,
						};
						frappe.set_route("List", "Task", "Gantt");
					},
					__("View")
				);

				frm.add_custom_button(
					__("Kanban Board"),
					() => {
						frappe
							.call(
								"erpnext.projects.doctype.project.project.create_kanban_board_if_not_exists",
								{
									project: frm.doc.name,
								}
							)
							.then(() => {
								frappe.set_route("List", "Task", "Kanban", frm.doc.project_name);
							});
					},
					__("View")
				);
			}
		}
	},

	update_total_purchase_cost: function (frm) {
		frappe.call({
			method: "erpnext.projects.doctype.project.project.recalculate_project_total_purchase_cost",
			args: { project: frm.doc.name },
			freeze: true,
			freeze_message: __("Recalculating Purchase Cost against this Project..."),
			callback: function (r) {
				if (r && !r.exc) {
					frappe.msgprint(__("Total Purchase Cost has been updated"));
					frm.refresh();
				}
			},
		});
	},

	set_project_status_button: function (frm) {
		frm.add_custom_button(
			__("Set Project Status"),
			() => frm.events.get_project_status_dialog(frm).show(),
			__("Actions")
		);
	},

	get_project_status_dialog: function (frm) {
		const dialog = new frappe.ui.Dialog({
			title: __("Set Project Status"),
			fields: [
				{
					fieldname: "status",
					fieldtype: "Select",
					label: "Status",
					reqd: 1,
					options: "Completed\nCancelled",
				},
			],
			primary_action: function () {
				frm.events.set_status(frm, dialog.get_values().status);
				dialog.hide();
			},
			primary_action_label: __("Set Project Status"),
		});
		return dialog;
	},

	create_duplicate: function (frm) {
		return new Promise((resolve) => {
			frappe.prompt("Project Name", (data) => {
				frappe
					.xcall("erpnext.projects.doctype.project.project.create_duplicate_project", {
						prev_doc: frm.doc,
						project_name: data.value,
					})
					.then(() => {
						frappe.set_route("Form", "Project", data.value);
						frappe.show_alert(__("Duplicate project has been created"));
					});
				resolve();
			});
		});
	},

	set_status: function (frm, status) {
		frappe.confirm(__("Set Project and all Tasks to status {0}?", [__(status).bold()]), () => {
			frappe
				.xcall("erpnext.projects.doctype.project.project.set_project_status", {
					project: frm.doc.name,
					status: status,
				})
				.then(() => {
					frm.reload_doc();
				});
		});
	},
	before_save: async function (frm) {
		if (frm.doc.__islocal) {
			frm.previous_status = null;
			frm.previous_remote_diagnose_status = null;
			return;
		}
		const previousStatus = frm.previous_status;
		const currentRemoteDiagnoseStatus = frm.doc.remote_diagnose_status;
		const previousRemoteDiagnoseStatus = frm.previous_remote_diagnose_status;
		if (currentRemoteDiagnoseStatus === "After diagnosis" && previousRemoteDiagnoseStatus === "In diagnosis") {
			showSentMessageAfterRemoteDiagnoseDialog(frm.docname);
		}
		const isMechanic = await erpnext.utils.isMechanic(this.frm);
		const isJuniorMechanic = await erpnext.utils.isJuniorMechanic(this.frm);

		// Only block and notify when attempting to change the status field
		if ((isMechanic || isJuniorMechanic) && currentStatus !== previousStatus) {
			frm.doc.status = previousStatus;
			showMessageNotAllowedUpdateStatus();
		}
		frm.previous_status = frm.doc.status;
		frm.previous_remote_diagnose_status = frm.doc.remote_diagnose_status;
	},
	status: async function (frm) {
		let new_value = frm.doc.status;

		if (new_value === "Quality check approved") {
			const incomplete_requirements = frm.doc.requirements.filter(requirement => !requirement.completed)

			const quotations = await frappe.db.get_list("Quotation", {
				filters: [
					['project_name', '=', frm.docname],
					['status', "!=", "Approved"],
					['status', "!=", "Ordered"]
				],
				fields: ["name", "status"]
			})

			if (!quotations?.length && !incomplete_requirements.length) return

			showConfirmationDialog(frm, quotations, incomplete_requirements)
		}

		if (new_value === "Completed") {
			const loan_car = await frappe.db.get_list('Loan car', { fields: ["name", "status"], filters: [["project", "=", frm.docname], ["status", "!=", "Paid"], ["status", "!=", "Done"], ["status", "!=", "Cancelled"]] })

			if (loan_car.length) {
				frm.undo_manager.undo();
				showLoanCarNotPaidAlert(loan_car[0]);
				return;
			}
		}

		if (["Completed", "Cancelled", "No response from customer"].includes(new_value)) {
			showDoneStatusQueueDialog(frm, new_value);
		}

		if (new_value === "In parking") {
			deactivateChatbot(frm.doc.custom_customers_phone_number)
		}
	},
	validate: function (frm) {
		const regex = /^(?=.*[a-zA-Z0-9])[\s\S]{4,}$/g

		if (!regex.test(frm.doc.plate)) {
			frappe.msgprint(__('Please enter a valid license plate. It cannot be empty or contain only special characters.'));
			frappe.validated = false;
		}
	}
});

function showConfirmationDialog(frm, quotations, incomplete_requirements) {
	const dialog = new frappe.ui.Dialog({
		title: 'Confirm',
		fields: buildFields(frm, quotations, incomplete_requirements),
		primary_action_label: 'Confirm',
		primary_action: function () {
			dialog.hide();
		},
		secondary_action_label: 'Cancel',
		secondary_action: function () {
			frm.undo_manager.undo();
			dialog.hide();
		}
	});

	dialog.$wrapper.find('.modal-header .modal-actions').hide();
	dialog.$wrapper.modal({ backdrop: 'static', keyboard: false })

	dialog.show();
}

function showDoneStatusQueueDialog(frm, new_status) {
	const dialog = new frappe.ui.Dialog({
		title: 'Confirm',
		fields: [
			{
				fieldtype: 'HTML',
				options: `<p>Moving this project to <strong>${new_status}</strong> will update queue positions and customers in the queue will be notified. Are you sure you want to proceed?</p>`
			}
		],
		primary_action_label: 'Confirm',
		primary_action: function () {
			dialog.hide();
		},
		secondary_action_label: 'Cancel',
		secondary_action: function () {
			frm.undo_manager.undo();
			dialog.hide();
		}
	});

	dialog.$wrapper.find('.modal-header .modal-actions').hide();
	dialog.$wrapper.modal({ backdrop: 'static', keyboard: false });

	dialog.show();
}

function showLoanCarNotPaidAlert(loan_car) {
	const dialog = new frappe.ui.Dialog({
		title: 'Loan Car Alert',
		fields: [
			{
				fieldtype: 'HTML',
				options: `<p>Loan car: <a href="/app/loan-car/${loan_car.name}" target="__blank">${loan_car.name}</a> is is status: ${loan_car.status}</p> `
			},
		],
		primary_action_label: 'Ok',
		primary_action: function () {
			dialog.hide();
		},
	});

	dialog.$wrapper.find('.modal-header .modal-actions').hide();
	dialog.$wrapper.modal({ backdrop: 'static', keyboard: false })

	dialog.show();
}

function buildFields(frm, quotations, incomplete_requirements) {
	const quotation_fields = [
		{
			fieldtype: 'HTML',
			options: `<h3>Pending Quotations</h3> `
		},
		{
			fieldtype: 'HTML',
			options: `<p>Client <a href="/app/customer/${frm.doc.customer}"><strong>${frm.doc.customer}</strong></a> with project <strong>${frm.docname}</strong> has the following quotation pending approval:</p> `
		},
		{
			fieldtype: 'HTML',
			options: `
				<ul style="border-bottom: 1px solid black;padding-bottom:1rem;">
				${quotations.map(quotation => `<li><strong>Quotation:</strong> <a href="/app/quotation/${quotation.name}" target="__blank">${quotation.name}</a>, <strong>Status:</strong> ${quotation.status}.</li>\n`)}
				</ul>
			`
		}
	]
	const requirements_fields = [
		{
			fieldtype: 'HTML',
			options: `<h3>Incomplete Client Requirements</h3> `
		},
		{
			fieldtype: 'HTML',
			options: `
				<ul>
				${incomplete_requirements.map(item => `<li><strong>Requirement:</strong> ${item.requirement}</li>\n`)}
				</ul>
			`
		},
	]
	const question_field = {
		fieldtype: 'HTML',
		options: `
			<p>Are you sure you want to proceed? ${quotations.length ? "The quotations listed will not be included in the invoice" : ""}</p>
		`
	}

	let fields = []

	if (quotations.length) {
		fields.push(...quotation_fields)
	}

	if (incomplete_requirements.length) {
		fields.push(...requirements_fields)
	}

	fields.push(question_field)

	return fields
}

let instaling = false;
async function installChat(frm) {
	if (document.querySelector('#chat-container')) {
		document.querySelector('#chat-container').remove();
	}
	frm.page.container.removeClass("full-width");
	if (instaling) return;
	instaling = true;
	if (!frm.is_new()) {
		const { 0: conversation } = await frappe.db.get_list('Conversation', {
			filters: [['from', '=', frm.doc.custom_customers_phone_number]],
			fields: ["*"]
		});

		if (!conversation) {
			instaling = false;
			return;
		};
		const chatContainer = document.createElement('div')

		const button = document.createElement('button')
		button.classList.add('btn', 'btn-default', 'ellipsis')
		button.textContent = 'Toggle WhatsApp'
		button.addEventListener('click', () => {
			if (chatContainer.style.display === 'none') {
				chatContainer.style.display = 'block';
			} else {
				chatContainer.style.display = 'none';
			}
		})

		document.querySelector('#custom_actions')
			.innerHTML = '';
		document.querySelector('#custom_actions')
			.appendChild(button)

		chatContainer.id = 'chat-container'
		const chat = document.createElement('erp-chat')
		const section = document.querySelector('#page-Project > div.container.page-body > div.page-wrapper > div > div.row.layout-main')

		const { aws_url } = await frappe.db.get_doc('Whatsapp Config')
		chat.setAttribute('url', aws_url)
		chat.setAttribute('user-name', frappe.user_info().fullname)

		// Realtime wiring lives inside the component now — it subscribes to
		// `msg-{id}` / `translation-{id}` off the conversation we pass to
		// setConversation. (Previously this hooked `translation-${frm.doc.name}`,
		// i.e. the Project name, so translations never reached the chat here.)
		frappe.require('erp-whatsapp-chat.bundle.js')
			.then(() => {
				chatContainer.appendChild(chat)
				section.appendChild(chatContainer)
				setTimeout(() => {
					chat._instance.exposed.setFrappe(frappe)
					chat._instance.exposed.setConversation(conversation)
				}, 100);
			})


		frm.page.container.addClass("full-width");
	}
	instaling = false;
}

let is_quotation_installed = false;
function installQuotationItems(frm) {
	if (frm.is_new()) return;
	if (is_quotation_installed) return;

	const container = document.querySelector('div[data-fieldname="customer_details"] .section-body');
	if (!container) {
		return;
	}

	// Eliminar el componente existente si está presente
	const existingComponent = container.querySelector("erp-quotation-items");
	if (existingComponent) {
		existingComponent.remove();
	}

	is_quotation_installed = true;

	// Crear un contenedor adicional para manejar el desbordamiento
	const wrapper = document.createElement("div");
	wrapper.style.width = '100%';  // Ajusta al tamaño del contenedor
	wrapper.style.overflow = 'auto';  // Permite el scroll si es necesario

	frappe.require("erp-quotation-items.bundle.js").then(() => {
		const element = document.createElement("erp-quotation-items");
		element.style.width = '100%';  // Asegura que el componente no exceda el contenedor
		element.style.maxWidth = '100%';  // Evita que el componente se expanda más allá del contenedor
		element.style.boxSizing = 'border-box';  // Incluye padding y border en el ancho total
		element.style.display = 'block';  // Asegura que el componente se comporte como un bloque

		// Añadir el componente al contenedor wrapper
		wrapper.appendChild(element);
		container.appendChild(wrapper);

		// Forzar un redibujado del contenedor
		container.style.overflow = 'hidden';  // Establecer overflow a hidden
		container.offsetHeight;  // Forzar un reflujo
		container.style.overflow = 'auto';  // Restaurar overflow a auto

		setTimeout(() => {
			element._instance.exposed.setFrappe(frappe);
			element._instance.exposed.setProjectName(frm.doc.name);
			element._instance.exposed.setUserSession(frappe.session)
			is_quotation_installed = false;
		}, 100);
	}).catch((err) => {
		console.error("Error loading erp-quotation-items", err);
		is_quotation_installed = false;
	});
}

function open_form(frm, doctype, child_doctype, parentfield) {
	frappe.model.with_doctype(doctype, () => {
		let new_doc = frappe.model.get_new_doc(doctype);

		// add a new row and set the project
		let new_child_doc = frappe.model.get_new_doc(child_doctype);
		new_child_doc.project = frm.doc.name;
		new_child_doc.parent = new_doc.name;
		new_child_doc.parentfield = parentfield;
		new_child_doc.parenttype = doctype;
		new_doc[parentfield] = [new_child_doc];
		new_doc.project = frm.doc.name;

		frappe.ui.form.make_quick_entry(doctype, null, null, new_doc);
	});
}

let touchTimeout;
async function insertCarousel(frm) {
	frappe.require('glider.bundle.js', () => {
		setTimeout(() => {
			frappe.db.get_list("File", {
				filters: [
					['attached_to_name', 'in', frm.doc.name],
					['attached_to_doctype', '=', "Project"]
				],
				fields: ["file_url", "file_type"],
				limit: 10
			}).then((attachments) => {
				const tracker = document.querySelector('.glider-track')
				const container = document.querySelector('.glider-contain')
				const gliderEl = document.querySelector('.glider')

				if (!gliderEl) return null

				const glider = new Glider(gliderEl, {
					slidesToShow: 1,
					draggable: true,
					dots: '.dots',
					arrows: {
						prev: '.glider-prev',
						next: '.glider-next'
					},
					responsive: [
						{
							breakpoint: 600,
							settings: {
								slidesToShow: 2,
								slidesToScroll: 2,
								duration: 0.25
							}
						}, {
							breakpoint: 1024,
							settings: {
								slidesToShow: 5,
								slidesToScroll: 5,
								duration: 0.25
							}
						}
					]
				})

				//remove all items
				if (tracker && glider) {
					for (let index = 0; index < tracker.childElementCount; index++) {
						glider.removeItem(index)
					}
				}

				if (attachments && attachments.length > 0 && glider) {
					container.style = 'height: auto;overflow:hidden;'

					for (const attachment of attachments) {
						const el = createAttachmentElement(attachment)
						if (el) {
							setListeners(el, attachment)
							glider.addItem(el)
						}
					}

				} else {
					container.style = 'height: 0;overflow:hidden;'
				}
			})
		}, 3000)// if this time is less than 3 sec it'll be render a wrong carousel
	})
}

function setListeners(el, attachment) {
	let element = el

	if (attachment.file_type === "MOV" || attachment.file_type === "MP4") return null
	if (attachment.file_type === 'PDF' || attachment.file_url === 'TXT') {
		element = el.querySelector('#touch-overlay')
	}
	element.addEventListener('touchstart', (e) => handleTouchStart(e, attachment))
	element.addEventListener('touchend', handleTouchEnd)

}

function createAttachmentElement(attachment) {
	let el;

	switch (attachment.file_type) {
		case "PDF":
		case "TXT":
			el = document.createElement('div')
			el.style = `width: 100%;overflow: hidden; position: relative;`
			el.innerHTML = `<iframe src="${attachment.file_url}" frameborder="0" class="glider-iframe"></iframe> <div id="touch-overlay"></div>`
			break;
		case "MOV":
		case "MP4":
			el = document.createElement('video')
			el.className = 'video-container'
			el.setAttribute('controls', 'true')
			el.setAttribute('src', attachment.file_url)
			break;
		default:
			el = document.createElement('img')
			el.setAttribute('src', attachment.file_url)
	}

	return el
}


function handleTouchStart(e, attachment) {
	touchTimeout = setTimeout(() => {
		const attachmentContainer = document.querySelector('#selected-attachment')
		const el = createAttachmentElement(attachment)
		attachmentContainer.addEventListener('touchend', handleTouchEnd)
		attachmentContainer.appendChild(el)
		attachmentContainer.removeAttribute('hidden')
	}, 1000)
}

function handleTouchEnd(e) {
	clearTimeout(touchTimeout)
	const attachmentContainer = document.querySelector('#selected-attachment')
	if (attachmentContainer) {
		attachmentContainer.innerHTML = ``
		attachmentContainer.setAttribute('hidden', "true")
	}
}

async function insertVinSearchButton(frm) {
	const container = document.querySelector('div[data-fieldname="vin"] .form-group .clearfix');

	if (!container || document.getElementById('vinSearch')) {
		return;
	}

	const button = document.createElement('button');
	button.id = 'vinSearch';
	button.style = 'border:none;background:black;padding:2px;color:white;border-radius:5px;position:relative;'

	const tooltip = document.createElement('span');
	tooltip.textContent = "Vin Search";
	tooltip.style = 'font-size:12px;background:#171717;color:white;padding:4px;border-radius:4px;opacity:0;transition:opacity 0.3s;position:absolute;margin-left:4px;'

	const spinner = document.createElement('div')
	spinner.setAttribute('hidden', 'true')
	spinner.classList = 'vin-search-spinner'

	const iconSpan = document.createElement('span');
	iconSpan.innerHTML = `
	<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"><g fill="none" fill-rule="evenodd">
		<path d="m12.593 23.258l-.011.002l-.071.035l-.02.004l-.014-.004l-.071-.035q-.016-.005-.024.005l-.004.01l-.017.428l.005.02l.01.013l.104.074l.015.004l.012-.004l.104-.074l.012-.016l.004-.017l-.017-.427q-.004-.016-.017-.018m.265-.113l-.013.002l-.185.093l-.01.01l-.003.011l.018.43l.005.012l.008.007l.201.093q.019.005.029-.008l.004-.014l-.034-.614q-.005-.018-.02-.022m-.715.002a.02.02 0 0 0-.027.006l-.006.014l-.034.614q.001.018.017.024l.015-.002l.201-.093l.01-.008l.004-.011l.017-.43l-.003-.012l-.01-.01z"/><path fill="currentColor" d="M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 0 0 0-13M2 10.5a8.5 8.5 0 1 1 15.176 5.262l3.652 3.652a1 1 0 0 1-1.414 1.414l-3.652-3.652A8.5 8.5 0 0 1 2 10.5M9.5 7a1 1 0 0 1 1-1a4.5 4.5 0 0 1 4.5 4.5a1 1 0 1 1-2 0A2.5 2.5 0 0 0 10.5 8a1 1 0 0 1-1-1"/></g>
	</svg>
	`;

	button.addEventListener('mouseover', () => {
		tooltip.style.visibility = 'visible';
		tooltip.style.opacity = '1';
	});

	button.addEventListener('mouseout', () => {
		tooltip.style.visibility = 'hidden';
		tooltip.style.opacity = '0';
	});

	const setLoading = (loading) => {
		[button, cameraButton].forEach(b => b && (loading ? b.setAttribute('hidden', 'true') : b.removeAttribute('hidden')));
		loading ? spinner.removeAttribute('hidden') : spinner.setAttribute('hidden', 'true');
	};

	button.addEventListener('click', async function () {
		setLoading(true);
		try {
			await fetchAndPopulateVinData(frm, frm.doc.vin);
		} finally {
			setLoading(false);
		}
	});

	button.appendChild(iconSpan);
	container.appendChild(button);
	container.appendChild(tooltip);
	container.appendChild(spinner);

	const cameraButton = insertVinCameraButton(frm, container, setLoading);
}

async function fetchAndPopulateVinData(frm, vin) {
	if (!vin) return;

	const { vin_search_url } = await frappe.db.get_doc('Vin Search');

	const data = await fetch(`${vin_search_url}/${vin}`).then(response => response.json()).catch(error => {
		frappe.throw(__('Error', error));
	});

	if (data.errors) {
		frappe.show_alert({
			message: __(`${data.errors}`),
			indicator: 'red'
		}, 5);

		if (!data.vehicle_identification_no) return;
	}

	const partsObject = {};
	data.parts?.forEach(part => {
		partsObject[part.name] = part.partNumber;
	});

	await frm.set_value({
		vin: data.vehicle_identification_no,
		model: data.model,
		model_year: data.year,
		brand: data.make,
		engine_liters: data.engine_liters,
		engine_code: data.engine_code,
		dsg_model: data.dsg_family || (data.dsg ? data.dsg[0] : ''),
		dsg_code: data.dsg_code,
		ecu_number: data.ecu_code,
		sales_type: data.sales_type,
		date_of_production: data.date_of_production,
		axle_drive: data.axle_drive,
		equipment: data.equipment,
		roof_color: data.roof_color,
		exterior_color_paint_code: data.exterior_color_paint_code,
		model_description: data.model_description,
		gearbox_code: data.gearbox_code,
		dsg_family: data.dsg_family,
		transmission_code: data.transmission_code ?? "",

		dsg_gearbox: partsObject["gearbox"] ?? partsObject["speed dual clutch gearbox"] ?? "",
		mechatronic: partsObject["mechatronic"] ?? partsObject["mechatronic with software"] ?? "",
		flywheel: partsObject["flywheel"] ?? "",
		clutch: partsObject["clutch"] ?? partsObject["repair set for multi-coupling"] ?? "",
	});

	await frm.save();
}

async function compressImageToArrayBuffer(file, { maxDimension = 1920, quality = 0.8 } = {}) {
	const bitmap = await createImageBitmap(file);
	const scale = Math.min(1, maxDimension / Math.max(bitmap.width, bitmap.height));
	const width = Math.round(bitmap.width * scale);
	const height = Math.round(bitmap.height * scale);

	const canvas = document.createElement('canvas');
	canvas.width = width;
	canvas.height = height;
	canvas.getContext('2d').drawImage(bitmap, 0, 0, width, height);
	bitmap.close?.();

	const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', quality));
	return blob.arrayBuffer();
}

function insertVinCameraButton(frm, container, setLoading) {
	if (document.getElementById('vinCamera')) return null;

	const cameraButton = document.createElement('button');
	cameraButton.id = 'vinCamera';
	cameraButton.style = 'border:none;background:black;padding:2px;color:white;border-radius:5px;position:relative;margin-left:4px;';
	cameraButton.title = 'Scan VIN from photo';

	cameraButton.innerHTML = `
	<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
		<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
		<circle cx="12" cy="13" r="4"/>
	</svg>`;

	const fileInput = document.createElement('input');
	fileInput.type = 'file';
	fileInput.accept = 'image/*';
	fileInput.capture = 'environment';
	fileInput.style = 'display:none;';

	fileInput.addEventListener('change', async function () {
		const file = fileInput.files[0];
		if (!file) return;

		setLoading(true);
		try {
			const { aws_url } = await frappe.db.get_doc('Rest Config');
			const binaryData = await compressImageToArrayBuffer(file);
			const response = await fetch(`${aws_url}/image-rekognition`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/octet-stream' },
				body: binaryData
			});

			if (!response.ok) throw new Error(`HTTP ${response.status}`);

			const data = await response.json();

			if (!data.vin) {
				frappe.show_alert({ message: __('Could not detect a VIN in the image'), indicator: 'red' }, 5);
				return;
			}

			frappe.show_alert({ message: __('VIN detected: ') + data.vin, indicator: 'green' }, 4);

			await fetchAndPopulateVinData(frm, data.vin);
		} catch (err) {
			frappe.show_alert({ message: __('Image recognition failed: ') + err.message, indicator: 'red' }, 5);
		} finally {
			setLoading(false);
			fileInput.value = '';
		}
	});

	cameraButton.addEventListener('click', () => fileInput.click());

	container.appendChild(cameraButton);
	container.appendChild(fileInput);

	return cameraButton;
}

function showSentMessageAfterRemoteDiagnoseDialog(project_name) {
	const dialog = new frappe.ui.Dialog({
		title: 'Remote Diagnose Completed',
		fields: [
			{
				fieldtype: 'HTML',
				options: `<p>Would you like to send the customer an invitation to schedule an appointment with our workshop?</p> `
			},
		],
		primary_action_label: 'Yes',
		primary_action: async function () {
			const { aws_url } = await frappe.db.get_doc("Whatsapp Config")
			await frappe.call({
				method: 'frappe.desk.doctype.kanban_board.kanban_board.call_send_whatsapp_message',
				args: { aws_url: aws_url, project_name: project_name }
			})
			dialog.hide();
		},
		secondary_action_label: 'No',
		secondary_action: function () {
			dialog.hide();
		}
	});

	dialog.show();
}
function showMessageNotAllowedUpdateStatus() {
	frappe.msgprint({
		title: "Not Allowed",
		message: "You are not allowed to update the status of this project.",
		indicator: "red",
		alert: true
	});
}
async function insertResendPaymentLink(frm) {
	if (["Quality check approved"].includes(frm.doc.status)) {
		frm.add_custom_button(__('Resend Payment Link'), () => {
			var d = new frappe.ui.Dialog({
				title: __("The message and payment Link will be sent to the client"),
				fields: [],
				primary_action_label: __("Send"),
				primary_action: async function () {
					const { aws_url } = await frappe.db.get_doc('Queue Settings')
					const url = `${aws_url}project/quality-approved`;
					const obj = {
						"name": frm.doc.name,
					};

					fetch(url, {
						method: 'POST',
						headers: {
							'Content-Type': 'application/json',
						},
						body: JSON.stringify(obj),
					})
						.then(async (response) => {
							if (!response.ok) {
								// Manejo de error basado en el estado de la respuesta
								const errorMessage = await response.text();
								throw new Error(`HTTP error ${response.status}: ${errorMessage}`);
							}
							return response
						})
						.then((data) => {
							frappe.show_alert({
								message: __('Message sent successfully'),
								indicator: 'green'
							}, 10);
						})
						.catch((error) => {
							frappe.show_alert({
								message: __('An error occurred while sending the message'),
								indicator: 'red'
							}, 10);
							console.error('Error:', error);
						});


					d.hide();
				},
				secondary_action_label: __("Cancel"),
				secondary_action: function () {
					d.hide();
				}
			});

			d.show();
		});
	}
}

async function onClick(frm, spinner, field, lang, fieldType = 'diagnose_result') {
	const flags = field.getElementsByClassName('flag')

	for (const flag of flags) {
		flag.setAttribute('hidden', 'true')
	}
	spinner.removeAttribute('hidden')

	const { aws_url } = await frappe.db.get_doc('Queue Settings')

	if (!aws_url) return

	// Determine the API endpoint and field content based on fieldType

	const apiEndpoint = `${aws_url}project/translate-field`;
	let fieldContent = frm.doc[fieldType];

	let requestBody = {
		project_name: frm.docname,
		language: lang,
		content: fieldContent,
		field_name: fieldType
	};

	const response = await fetch(apiEndpoint, {
		method: "POST",
		body: JSON.stringify(requestBody)
	}).then(res => res.json())

	spinner.setAttribute('hidden', 'true')

	for (const flag of flags) {
		flag.removeAttribute('hidden')
	}

	if (!response.translation) {
		frappe.show_alert({
			message: __(response.message),
			indicator: 'red'
		}, 5);
		return
	}

	let translation = null;

	translation = field.querySelector('#translation-container') || document.createElement('div')
	translation.id = 'translation-container'

	translation.style = 'background:#f3f3f3;padding:12px 15px;height:300px;overflow:scroll;font-size:13px;margin-bottom:1rem;'
	translation.innerHTML = response.translation

	field.appendChild(translation)
}

async function insertUpdateQueuePositionButton(frm) {
	const { aws_url } = await frappe.db.get_doc('Queue Settings')
	if (!aws_url) return
	const getSelectUrl = `${aws_url}queue/select`
	const setPositionUrl = `${aws_url}queue/set-position`

	const getSelect = (project_name) => {
		return fetch(
			`${getSelectUrl}?name=${project_name}`
		).then((res) => res.json());
	};

	const setPosition = (data) => {
		return fetch(setPositionUrl, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify(data)
		})
	}

	const option = $('.form-page select[data-fieldname="status"]')
		.find('option[value="In queue"]')

	const { doc } = frm;
	const cardName = $('.frappe-list .kanban-card-title.ellipsis');
	cardName.html(cardName.html() + doc.model != "" ? " " + doc.model : "");

	const isWorkshopViewer = await erpnext.utils.isWorkshopViewer(this.frm);
	const isMechanic = await erpnext.utils.isMechanic(this.frm);
	const isJuniorMechanic = await erpnext.utils.isJuniorMechanic(this.frm);
	frm.set_df_property("queue_position", "read_only", frm.is_new() ? 0 : 1);
	if (!frm.is_new() && doc.status === 'In queue' && !isWorkshopViewer && !isMechanic && !isJuniorMechanic) {
		frm.add_custom_button('Change queue position', async () => {
			const select = await getSelect(doc.name)

			let d = new frappe.ui.Dialog({
				title: 'Enter the new position.',
				fields: [
					{
						label: 'New position',
						fieldname: 'new_position',
						options: select.options,
						fieldtype: 'Select',
						default: select.current.toString()
					},
				],
				size: 'small', // small, large, extra-large
				primary_action_label: 'Submit',
				primary_action(values) {
					setPosition({
						name: doc.name,
						...values
					}).then(() => {
						frappe.show_alert({
							message: __('Position updated successfuly'),
							indicator: 'green'
						}, 5);
					})
					d.hide();
				},
			});
			d.show();
		}, null, false);
	}

	getSelect(doc.name).then((data) => {
		frm.set_df_property('queue_position', 'options', data.options)
		frm.set_value('queue_position', data.current)
	})
}

async function insertLoanCarButton(frm) {
	const loan_car = await frappe.db.get_list('Loan car', { filters: [['project', '=', frm.docname]], fields: ["name", "creation"], order_by: 'creation DESC' })

	if (!loan_car?.length) return

	frm.add_custom_button('View Loan Car Details', async () => {
		frappe.open_in_new_tab = true
		frappe.set_route('Form', 'Loan car', loan_car[0].name)
	})
}

function viewCustomerDetails(frm) {
	frm.add_custom_button(__("View Customer Details"), async () => {
		const customer = await frappe.db.get_doc('Customer', frm.doc.customer);

		const linked_contacts_and_addresses = await frappe.db.get_list("Address", {
			filters: [
				["disabled", "=", 0],
				["address_type", "in", ["Billing", "Shipping"]],
				["Dynamic Link", "link_doctype", "=", "Customer"],
				["Dynamic Link", "link_name", "=", `${frm.doc.customer}`],
				["Dynamic Link", "parenttype", "=", "Address"]
			],
			fields: ["name", "address_line1", "address_line2", "country", "city", "pincode", "state", "address_type"]
		});

		// Primer Billing y Shipping
		let billingAddress = null;
		let shippingAddress = null;
		for (let address of linked_contacts_and_addresses) {
			if (address.address_type === 'Billing' && !billingAddress) billingAddress = address;
			else if (address.address_type === 'Shipping' && !shippingAddress) shippingAddress = address;
			if (billingAddress && shippingAddress) break;
		}

		// Utilidades de UI
		const escapeHtml = (val) => {
			if (val === null || val === undefined) return '—';
			if (frappe.utils && frappe.utils.escape_html) return frappe.utils.escape_html(String(val));
			return String(val)
				.replace(/&/g, '&amp;')
				.replace(/</g, '&lt;')
				.replace(/>/g, '&gt;')
				.replace(/"/g, '&quot;')
				.replace(/'/g, '&#039;');
		};

		const phoneRaw = customer.phone || customer.phone_number || customer.mobile_no;
		const phone = phoneRaw ? `<a href="tel:${escapeHtml(phoneRaw)}">${escapeHtml(phoneRaw)}</a>` : '—';
		const email = customer.email_id ? `<a href="mailto:${escapeHtml(customer.email_id)}">${escapeHtml(customer.email_id)}</a>` : '—';

		const addrBlock = (label, a) => a ? `
      <div class="cc-addr">
        <div class="cc-badge">${escapeHtml(label)}</div>
        <div class="cc-addr-lines">
          ${escapeHtml(a.address_line1)}${a.address_line2 ? `<br>${escapeHtml(a.address_line2)}` : ''}
          ${[a.city, a.state, a.pincode].some(Boolean) ? `<br>${[a.city, a.state, a.pincode].filter(Boolean).map(escapeHtml).join(', ')}` : ''}
          ${a.country ? `<br>${escapeHtml(a.country)}` : ''}
        </div>
      </div>` : '';

		const card = (title, inner) => `
      <div class="cc-card">
        <div class="cc-card-title">${escapeHtml(title)}</div>
        ${inner}
      </div>`;

		const html = `
      <style>
        .cc-wrap { font-size: 13px; line-height: 1.45; }
        .cc-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
        .cc-title { font-weight: 600; font-size: 16px; }
        .cc-meta { color: #6b7280; font-size: 12px; }
        .cc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .cc-card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; background: #fff; }
        .cc-card-title { font-weight: 600; margin-bottom: 8px; font-size: 13px; }
        .cc-kv { display: flex; align-items: center; margin: 6px 0; }
        .cc-kv label { width: 110px; color: #6b7280; }
        .cc-kv .val { flex: 1; }
        .cc-addr { border: 1px dashed #e5e7eb; border-radius: 8px; padding: 10px; margin-top: 8px; }
        .cc-badge { display: inline-block; font-size: 11px; padding: 2px 6px; border-radius: 999px; background: #f3f4f6; color: #374151; margin-bottom: 6px; }
        .cc-footer { margin-top: 12px; color: #6b7280; font-size: 12px; }
        @media (max-width: 768px) {
          .cc-grid { grid-template-columns: 1fr; }
          .cc-kv label { width: 90px; }
        }
      </style>

      <div class="cc-wrap">
        <div class="cc-header">
          <div class="cc-title">${escapeHtml(customer.customer_name || customer.name || __('Customer'))}</div>
          <div class="cc-meta"><a href="/app/customer/${encodeURIComponent(customer.name)}">${__('Open customer card')}</a></div>
        </div>

        <div class="cc-grid">
          ${card(__('Contact'), `
            <div class="cc-kv"><label>${__('Phone')}</label><div class="val">${phone}</div></div>
            <div class="cc-kv"><label>${__('Email')}</label><div class="val">${email}</div></div>
            <div class="cc-kv"><label>${__('VAT')}</label><div class="val">${escapeHtml(customer.tax_id || '—')}</div></div>
            <div class="cc-kv"><label>${__('Tax Category')}</label><div class="val">${escapeHtml(customer.tax_category || '—')}</div></div>
          `)}

          ${card(__('Addresses'), `
            ${addrBlock(__('Billing'), billingAddress)}
            ${addrBlock(__('Shipping'), shippingAddress)}
            ${!billingAddress && !shippingAddress ? `<div class="cc-kv" style="margin:4px 0;color:#6b7280;">— ${__('There are no addresses linked')}</div>` : ''}
          `)}
        </div>

        <div class="cc-footer">
          ${__('Last update')}: ${frappe.datetime.str_to_user(customer.modified || customer.creation)}
        </div>
      </div>
    `;

		const d = new frappe.ui.Dialog({
			title: __('Customer Information'),
			fields: [{ fieldtype: 'HTML', fieldname: 'preview' }],
			size: 'large',
			primary_action_label: __('Cerrar'),
			primary_action: () => d.hide()
		});

		d.show();
		d.get_field('preview').$wrapper.html(html);
	});
}


// Las funciones relacionadas con la validación de pagos se han movido al archivo payment_validation.js

function insertValidateBankTransferPaymentButton(frm) {
	frm.add_custom_button(__('Validate Bank Transfer Payment'), () => {
		try {
			if (window.erpnext && window.erpnext.projects && window.erpnext.projects.payment_validation) {
				window.erpnext.projects.payment_validation.validateBankTransferPayment(frm);
			} else if (erpnext.projects.payment_validation) {
				erpnext.projects.payment_validation.validateBankTransferPayment(frm);
			} else {
				throw new Error("Payment validation module not loaded");
			}
		} catch (error) {
			console.error("Error accessing payment validation module:", error);
			frappe.msgprint({
				title: 'Error',
				indicator: 'red',
				message: 'No se pudo cargar el módulo de validación de pagos. Por favor, inténtelo de nuevo.'
			});
		}
	});
}

function getLanguages() {
	const lang = frappe?.boot?.user?.language || 'nl'
	return new Set(['nl', 'en', 'uk', 'es', lang])
}


async function insertTranslation(frm) {
	const languages = getLanguages()
	const { aws_url } = await frappe.db.get_doc('Queue Settings')
	const { aws_url: chatbot_url } = await frappe.db.get_doc('Whatsapp Config')
	const fields = ['notes', 'internal_notes', 'client_description', 'diagnose_result']

	for (const field of fields) {
		const field_dict = frm.fields_dict[field]

		if (!field_dict) continue

		const quill = field_dict.quill || field_dict.editor?.quill || field_dict.editor;
		const fieldContainer = document.querySelector(`div[data-fieldname="${field}"][data-fieldtype="Text Editor"]`)

		if (!fieldContainer) continue

		const container = fieldContainer.querySelector('.clearfix')
		const fieldElement = document.createElement('div')
		fieldElement.id = `field-${field}`
		if (!container || container.querySelector(`#${fieldElement.id}`)) continue;
		container.style = 'display:flex;gap:1rem;align-items:center;'
		container.appendChild(fieldElement)

		new frappe.ui.FieldTranslator({
			docname: frm.docname,
			field_container: fieldContainer,
			field_element: fieldElement,
			field: field,
			languages: [...languages],
			chatbot_url,
			aws_url,
			quill
		})
	}
}

async function deactivateChatbot(phone_number) {
	const conversations = await frappe.db.get_list('Conversation', { filters: { from: phone_number } })
	for (const conversation of conversations) {
		await frappe.db.set_value('Conversation', conversation.name, { 'is_auto_reply': 0, 'seen': 0 })
	}
}

