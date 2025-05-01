frappe.listview_settings["Project"] = {
	add_fields: ["status", "priority", "is_active", "percent_complete", "expected_end_date", "project_name"],
	filters: [["status", "=", "Open"]],
	get_indicator: function (doc) {
		if (doc.status == "Open" && doc.percent_complete) {
			return [__("{0}%", [cint(doc.percent_complete)]), "orange", "percent_complete,>,0|status,=,Open"];
		} else {
			return [__(doc.status), frappe.utils.guess_colour(doc.status), "status,=," + doc.status];
		}
	},
	async before_render() {
		if(!await erpnext.utils.isWorkshopViewer(this.frm)){
			insertFreezeQueuePosition()
		}else{
			const sidebar = $(".layout-side-section");
			if (sidebar.is(':visible')) {
				sidebar.hide();
			}
		}
	}
};

async function insertFreezeQueuePosition() {
	const { auto_move_paused } = await frappe.db.get_doc('Queue Settings')
		setTimeout(() => {
			const exists = document.querySelector("#page-List\\/Project\\/List > div.page-head.flex > div > div > div.flex.col.page-actions.justify-content-end #queue-freeze")
			if (!exists) {
				const container = document.querySelector('#page-List\\/Project\\/List > div.page-head.flex > div > div > div.flex.col.page-actions.justify-content-end')
				const input = document.createElement('input')
				const label = document.createElement('label')
				label.setAttribute('style', 'margin: 0')
				label.setAttribute('id', 'queue-freeze')
				label.innerText = 'freeze queue positions'
				label.appendChild(input)
				input.setAttribute('type', 'checkbox')
				if (auto_move_paused) {
					input.setAttribute('checked', 'checked')
				}
				container.prepend(label);
				input.addEventListener('change', (event) => {
					const isChecked = event.target.checked;
					if (isChecked) {
						showConfirmationDialog(input)
						return
					}

					frappe.db.set_value('Queue Settings', 'Queue Settings', 'auto_move_paused', Number(isChecked))
					frappe.msgprint(__('Status updated successfully'));
				})
			}
		}, 1500)
}

function showConfirmationDialog(input) {
	const dialog = new frappe.ui.Dialog({
		title: 'Confirm',
		fields: [
			{
				fieldtype: 'HTML',
				options: '<p>If you enable the freeze queue position process, job cards will not move even if they are marked as completed.</p>'
			},
			{
				fieldtype: 'HTML',
				options: 'Do you want to continue?'
			}
		],
		primary_action_label: 'Confirm',
		primary_action: function () {
			dialog.hide();
			frappe.db.set_value('Queue Settings', 'Queue Settings', 'auto_move_paused', 1).then(res => {
				frappe.warn('Status updated successfully', 'Would you like to send a WhatsApp message to notify the clients in the queue?',
					async () => {
						const { aws_url } = await frappe.db.get_doc('Queue Settings')
						return frappe.call({
							method: "frappe.desk.doctype.kanban_board.kanban_board.call_freeze_queue_position_message",
							args: { aws_url: aws_url },
							callback: (result) => {
								console.log("message queue position freeze sent: ", result);
							},
						});
					},
					'Yes',
					true // Sets dialog as minimizable
				)
			})
		},
		secondary_action_label: 'Cancel',
		secondary_action: function () {
			input.checked = false
			dialog.hide();
		}
	});

	dialog.$wrapper.find('.modal-header .modal-actions').hide();
	dialog.$wrapper.modal({ backdrop: 'static', keyboard: false })

	dialog.show();
}
