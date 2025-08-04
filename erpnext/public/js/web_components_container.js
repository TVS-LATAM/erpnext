(async () => {
  const isWorkshopViewer = await erpnext.utils.isWorkshopViewer(this.frm);
  const isMechanic = await erpnext.utils.isMechanic(this.frm);
  const isJuniorMechanic = await erpnext.utils.isJuniorMechanic(this.frm);
  const isSeniorMechanic = await erpnext.utils.isSeniorMechanic(this.frm);
  
  // If user is NOT a workshop viewer AND is NOT a mechanic, then show the icons
  if (!isWorkshopViewer && !isMechanic && !isJuniorMechanic && !isSeniorMechanic) {
    setTimeout(() => {
      const button = document.querySelector('#show-icons')
      const chat = document.querySelector('erp-full-chat').shadowRoot.querySelector('#full-chat-icon-container')
      const calendar = document.querySelector('erp-calendar').shadowRoot.querySelector('#calendar-icon-container')

      button.addEventListener('click', () => {
        chat.classList.toggle('hidden')
        calendar.classList.toggle('hidden')
        button.classList.toggle('close-icon-container')
      })
    }, 3000)
  }
})()