// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt
frappe.ui.form.on("Project", {
	setup(frm) {
		frm.make_methods = {
			'Timesheet': () => {
				open_form(frm, "Timesheet", "Timesheet Detail", "time_logs");
			},
			'Purchase Order': () => {
				open_form(frm, "Purchase Order", "Purchase Order Item", "items");
			},
			'Purchase Receipt': () => {
				open_form(frm, "Purchase Receipt", "Purchase Receipt Item", "items");
			},
			'Purchase Invoice': () => {
				open_form(frm, "Purchase Invoice", "Purchase Invoice Item", "items");
			},
		};
	},
	onload: function (frm) {
		const so = frm.get_docfield("sales_order");
		so.get_route_options_for_new_doc = () => {
			if (frm.is_new()) return {};
			return {
				"customer": frm.doc.customer,
				"project_name": frm.doc.name
			};
		};

		frm.set_query('customer', 'erpnext.controllers.queries.customer_query');

		frm.set_query("user", "users", function () {
			return {
				query: "erpnext.projects.doctype.project.project.get_users_for_project"
			};
		});

		// sales order
		frm.set_query('sales_order', function () {
			var filters = {
				'project': ["in", frm.doc.__islocal ? [""] : [frm.doc.name, ""]]
			};

			if (frm.doc.customer) {
				filters["customer"] = frm.doc.customer;
			}

			return {
				filters: filters
			};
		});

		frm.set_query('quotations', function() {
			var filters = [
				['status', '=', 'Draft']
			]

			return {
				filters,
			}
		})

		frm.set_query('sales_invoice', function() {
			const filters = [
				['status','=','Unpaid']
			]
			return { filters }
		})

		frappe.realtime.on('docinfo_update', (data) => {
			if (data.key === "attachment_logs") {
				insertCarousel(frm)
			}
		})
	},

	refresh: async function (frm) {
		if (frm.doc.__islocal) {
			frm.web_link && frm.web_link.remove();
		} else {
			frm.add_web_link("/projects?project=" + encodeURIComponent(frm.doc.name));
			frm.trigger('show_dashboard');
		}
		frm.trigger("set_custom_buttons");
		let store_autosave = localStorage.getItem("autosave")
		if(store_autosave){
			store_autosave = JSON.parse(store_autosave)
			if(!store_autosave.is_saved){
				const url = window.location.href.split("/app/")
				if(url.length > 0 && url[1] === "project/"+store_autosave.from_name){	
					setTimeout(()=>{
						frm.save();
						localStorage.removeItem("autosave")
						frappe.show_alert({
							message:__('New invoice or quotation was created and added to the project. Autosaving'),
							indicator:'green'
						}, 10);
						installQuotationItems(frm)
					},1500)
				}
			}
		}else{
			installQuotationItems(frm)
		}
		if(document.querySelector('#chat-container')){
			document.querySelector('#chat-container').remove()
		}
		installChat(frm);
		insertCarousel(frm)
	},
	after_save: function(frm){
		localStorage.removeItem("autosave")
		localStorage.removeItem("customer")
		localStorage.removeItem("mileage")
		localStorage.removeItem("plate")
		localStorage.removeItem("description_title")
	},	
	create_duplicate: function(frm) {
		return new Promise(resolve => {
			frappe.prompt('Project Name', (data) => {
				frappe.xcall('erpnext.projects.doctype.project.project.create_duplicate_project',
					{
						prev_doc: frm.doc,
						project_name: data.value
					}).then(() => {
					frappe.set_route('Form', "Project", data.value);
					frappe.show_alert(__("Duplicate project has been created"));
				});
				resolve();
			});
		});
	},

	set_status: function(frm, status) {
		frappe.confirm(__('Set Project and all Tasks to status {0}?', [status.bold()]), () => {
			frappe.xcall('erpnext.projects.doctype.project.project.set_project_status',
				{project: frm.doc.name, status: status}).then(() => {
				frm.reload_doc();
			});
		});
	},

});

let instaling = false;
async function installChat(frm) {
	frm.page.container.removeClass("full-width");
	if(instaling) return;
	instaling = true;
	if (!frm.is_new()){
		const {0: conversation} = await frappe.db.get_list('Conversation',{
			filters: [['from', '=', frm.doc.custom_customers_phone_number]],
			fields: ["*"]
		});

		console.log(conversation)
		
		if(!conversation) {
			instaling = false;
			return;
		};

		

		const chatContainer = document.createElement('div')

		const button = document.createElement('button')
		button.classList.add('btn','btn-default','ellipsis')
		button.textContent = 'Toggle WhatsApp'
		button.addEventListener('click', ()=>{
			if(chatContainer.style.display === 'none'){
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
		
		const {aws_url} = await frappe.db.get_doc('Whatsapp Config')
		chat.setAttribute('url', aws_url)
		chat.setAttribute('user-name', frappe.user.full_name())
		
		frappe.realtime.on(`msg-${conversation.name}`, (data) => {
			chat._instance.exposed.addMessage(data); 
		})
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
    const container = document.querySelector('div[data-fieldname="customer_details"]');
    if (!container) {
        return;
    }
    const existingComponent = container.querySelector("erp-quotation-items");
    if (existingComponent) {
        container.removeChild(existingComponent);
    }
    is_quotation_installed = true;
    frappe.require("erp-quotation-items.bundle.js").then(() => {
        const element = document.createElement("erp-quotation-items");
        element.style.width = '100%';
        container.appendChild(element);
		setTimeout(() => {
			element._instance.exposed.setFrappe(frappe)
			element._instance.exposed.setProjectName(frm.doc.name)
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
				fields: ["file_url"],
				limit: 10
			}).then((attachments) => {
				const tracker = document.querySelector('.glider-track')
				const container = document.querySelector('.glider-contain')
				const gliderEl = document.querySelector('.glider')

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
					container.style = 'height: auto;'

					for (const attachment of attachments) {
						const img = document.createElement('img')
						img.setAttribute('src', attachment.file_url)
						img.addEventListener('touchstart', (e) => handleTouchStart(e, attachment.file_url))
						img.addEventListener('touchend', handleTouchEnd)
						glider.addItem(img)
					}

				} else {
					container.style = 'height: 0;'
					console.log('No attachments found for this project.');
				}
			})
		}, 2000)// if this time is less than 2 sec it'll be render a wrong carousel
	})
}

function handleTouchStart(e, url) {
	touchTimeout = setTimeout(() => {
		const imageContainer = document.querySelector('#selected-attachment')
		const img = imageContainer.querySelector('img')
		img.setAttribute('src', url)
		img.addEventListener('touchend', handleTouchEnd)
		imageContainer.removeAttribute('hidden')
	}, 1000)
}

function handleTouchEnd(e) {
	clearTimeout(touchTimeout)
	const imageContainer = document.querySelector('#selected-attachment')
	if (imageContainer) {
		imageContainer.setAttribute('hidden', "true")
	}
}

