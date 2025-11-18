// Renderer (TypeScript)
// PDF viewer with radial menu component

type FileEntry = {
  name: string
  file: File
  url?: string
}

type Platform = 'pdf' | 'mindmap' | 'podcast' | 'more'

document.addEventListener('DOMContentLoaded', () => {
  const fileInput = document.getElementById('fileInput') as HTMLInputElement | null
  const pdfViewer = document.getElementById('pdfViewer') as HTMLIFrameElement | null
  const fileListEl = document.getElementById('fileList') as HTMLUListElement | null
   
  // Platform areas
  const pdfArea = document.getElementById('pdfArea') as HTMLDivElement | null
  const mindmapArea = document.getElementById('mindmapArea') as HTMLDivElement | null
  const podcastArea = document.getElementById('podcastArea') as HTMLDivElement | null
  const moreArea = document.getElementById('moreArea') as HTMLDivElement | null
  
  // Radial menu
  const radialMenu = document.getElementById('radialMenu') as HTMLDivElement | null
  const menuItems = document.querySelectorAll('.menu-item')


  if (!fileInput || !pdfViewer || !fileListEl || !pdfArea || !mindmapArea || !podcastArea || !moreArea || !radialMenu) {
    console.warn('Renderer: missing expected DOM elements')
    return
  }

  // Non-null aliases so TypeScript doesn't complain inside nested functions
  const pdfViewerEl = pdfViewer!
  const fileListElm = fileListEl!

  let files: FileEntry[] = []
  let currentPlatform: Platform | null = null

  // Position menu items in a semi-circle matching the expanded semi-circle size
  const radius = 150
  const itemCount = menuItems.length
  const angleStep = Math.PI / (itemCount - 1) // Semi-circle (180 degrees)
  const startAngle = -Math.PI / 2 // Start from top

  menuItems.forEach((item, index) => {
    const angle = startAngle + angleStep * index
    const x = Math.cos(angle) * radius
    const y = Math.sin(angle) * radius
    
    const menuItem = item as HTMLElement
    menuItem.style.left = `calc(50% + ${-x}px)`
    menuItem.style.top = `calc(50% + ${y}px)`
    menuItem.style.transform = 'translate(-50%, -50%)'
  })

  function clearObjectURLs() {
    for (const f of files) {
      if (f.url) {
        try { URL.revokeObjectURL(f.url) } catch (_) { }
        delete f.url
      }
    }
  }

  function switchPlatform(platform: Platform) {
    currentPlatform = platform
    
    // Hide all areas
    pdfArea!.classList.remove('active')
    mindmapArea!.classList.remove('active')
    podcastArea!.classList.remove('active')
    moreArea!.classList.remove('active')
    
    // Show selected area
    if (platform === 'pdf') pdfArea!.classList.add('active')
    else if (platform === 'mindmap') mindmapArea!.classList.add('active')
    else if (platform === 'podcast') podcastArea!.classList.add('active')
    else if (platform === 'more') moreArea!.classList.add('active')
    
    // Update active menu item styling
    menuItems.forEach(item => {
      const itemEl = item as HTMLElement
      const itemPlatform = itemEl.getAttribute('data-platform')
      if (itemPlatform === platform) {
        itemEl.classList.add('active')
      } else {
        itemEl.classList.remove('active')
      }
    })

    // Render content based on platform
    if (platform === 'pdf' && files.length > 0) {
      renderFileEntry(files[0])
    } else if (platform !== 'pdf') {
      pdfViewerEl.src = ''
    }
  }

  function renderFileEntry(entry: FileEntry) {
    // Only render when PDF platform is selected
    if (currentPlatform !== 'pdf') {
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

    // Auto-render the first file if PDF platform is active
    if (files.length > 0 && currentPlatform === 'pdf') {
      renderFileEntry(files[0])
    }
  })

  // Radial menu item click handlers
  menuItems.forEach(item => {
    item.addEventListener('click', () => {
      const platform = (item as HTMLElement).getAttribute('data-platform') as Platform
      if (platform) {
        switchPlatform(platform)
      }
    })
  })

  // Set default platform to PDF viewer on load
  switchPlatform('pdf')

  // Clean up object URLs when the page unloads
  window.addEventListener('beforeunload', () => {
    clearObjectURLs()
  })
})
