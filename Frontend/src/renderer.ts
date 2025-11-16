// Renderer (TypeScript)
// Simple PDF upload and viewer using an iframe and object URLs.

type FileEntry = {
  name: string
  file: File
  url?: string
}

document.addEventListener('DOMContentLoaded', () => {
  const fileInput = document.getElementById('fileInput') as HTMLInputElement | null
  const pdfViewer = document.getElementById('pdfViewer') as HTMLIFrameElement | null
  const fileListEl = document.getElementById('fileList') as HTMLUListElement | null
  const rendererSelect = document.getElementById('rendererSelect') as HTMLSelectElement | null

  if (!fileInput || !pdfViewer || !fileListEl || !rendererSelect) {
    console.warn('Renderer: missing expected DOM elements')
    return
  }

  // Non-null aliases so TypeScript doesn't complain inside nested functions
  const pdfViewerEl = pdfViewer!
  const fileListElm = fileListEl!
  const rendererSel = rendererSelect!

  let files: FileEntry[] = []

  function clearObjectURLs() {
    for (const f of files) {
      if (f.url) {
        try { URL.revokeObjectURL(f.url) } catch (_) { }
        delete f.url
      }
    }
  }

  function renderFileEntry(entry: FileEntry) {
    // Only render when PDF renderer is selected
    if (rendererSel.value !== 'pdf') {
      pdfViewerEl.src = ''
      return
    }

    // Ensure we have an object URL
    if (!entry.url) entry.url = URL.createObjectURL(entry.file)
    pdfViewerEl.src = entry.url
  }

  function rebuildFileList() {
    fileListElm.innerHTML = ''
    files.forEach((entry, idx) => {
      const li = document.createElement('li')
      li.style.padding = '8px'
      li.style.borderBottom = '1px solid #f0f0f0'
      li.style.cursor = 'pointer'
      li.textContent = entry.name + ` (${(entry.file.size / 1024).toFixed(0)} KB)`
      li.addEventListener('click', () => renderFileEntry(entry))
      fileListElm.appendChild(li)
    })
  }

  fileInput.addEventListener('change', () => {
    const selected = fileInput.files
    if (!selected || selected.length === 0) return

    // Clear previous object URLs to avoid leaks
    clearObjectURLs()

    files = Array.from(selected).map(f => ({ name: f.name, file: f }))
    rebuildFileList()

    // Auto-render the first file if renderer is set to pdf
    if (files.length > 0 && rendererSel.value === 'pdf') {
      renderFileEntry(files[0])
    }
  })

  // When renderer option changes, if pdf is selected and there are files, render the first
  rendererSel.addEventListener('change', () => {
    if (rendererSel.value === 'pdf' && files.length > 0) {
      renderFileEntry(files[0])
    } else {
      pdfViewerEl.src = ''
    }
  })

  // Clean up object URLs when the page unloads
  window.addEventListener('beforeunload', () => {
    clearObjectURLs()
  })
})
