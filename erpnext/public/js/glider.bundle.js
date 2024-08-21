import 'glider-js';

(async () => {
  const container = document.querySelector('[data-fieldname=attachments] form')
  const el = document.createElement('div')
  const imageContainer = document.createElement('div')

  el.className = 'glider-contain'
  el.style = 'width: 90% !important;'
  el.innerHTML = `
			<div class="glider"></div>
			<button aria-label="Previous" class="glider-prev">«</button>
			<button aria-label="Next" class="glider-next">»</button>
			<div role="tablist" class="dots"></div>
		`
  imageContainer.className = 'selected-attachment'
  imageContainer.setAttribute('id', 'selected-attachment')
  imageContainer.setAttribute('hidden', 'true')
  imageContainer.innerHTML = `<img src="" />`

  container.append(el, imageContainer)
})()