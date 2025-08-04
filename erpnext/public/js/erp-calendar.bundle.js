import "@tvsgroup/erp-calendar";

(async () => {
  const isWorkshopViewer = await erpnext.utils.isWorkshopViewer(this.frm);
  const isMechanic = await erpnext.utils.isMechanic(this.frm);
  const isJuniorMechanic = await erpnext.utils.isJuniorMechanic(this.frm);
  const isSeniorMechanic = await erpnext.utils.isSeniorMechanic(this.frm);
  
  // If user is NOT a workshop viewer AND is NOT a mechanic, then show the component
  if (!isWorkshopViewer && !isMechanic && !isJuniorMechanic && !isSeniorMechanic  ) {
    const el = document.createElement('erp-calendar')
    const { aws_url } = await frappe.db.get_doc('Whatsapp Config')
    el.setAttribute('url', location.origin);
    el.setAttribute('aws_url', aws_url)
    if (!document.querySelector('erp-calendar')) {
      document.querySelector('body').appendChild(el)
      setTimeout(() => {
        el._instance.exposed.setFrappe(frappe)
      }, 100);
    }
  }
})()