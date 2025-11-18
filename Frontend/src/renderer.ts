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
  let selectedFileIndex: number | null = null

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
      li.style.display = 'block'
      li.style.margin = '8px 0'
      li.style.padding = '10px 14px'
      li.style.color = 'white'
      li.style.borderRadius = '8px'
      li.style.cursor = 'pointer'
      li.style.fontSize = '13px'
      li.style.fontWeight = '500'
      li.style.transition = 'all 0.2s ease'
      li.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.1)'
      li.style.userSelect = 'none'
      li.style.whiteSpace = 'nowrap'
      li.style.overflow = 'hidden'
      li.style.textOverflow = 'ellipsis'
      
      // Set background based on selection state
      if (selectedFileIndex === idx) {
        li.style.background = 'linear-gradient(135deg, #1a1a1a 0%, #2a2a2a 100%)'
        li.style.border = '2px solid #ff6b00'
      } else {
        li.style.background = 'linear-gradient(135deg, #ff8c00 0%, #ff6b00 100%)'
        li.style.border = '2px solid transparent'
      }
      
      // Create content with icon
      const icon = document.createElement('span')
      icon.textContent = '📄 '
      icon.style.marginRight = '6px'
      
      const fileName = document.createElement('span')
      fileName.textContent = entry.name
      
      li.appendChild(icon)
      li.appendChild(fileName)
      li.title = entry.name + ` (${(entry.file.size / 1024).toFixed(0)} KB)`
      
      li.addEventListener('mouseenter', () => {
        if (selectedFileIndex !== idx) {
          li.style.background = 'linear-gradient(135deg, #ff6b00 0%, #ff4500 100%)'
        }
        li.style.transform = 'translateX(4px)'
        li.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.3)'
      })
      
      li.addEventListener('mouseleave', () => {
        if (selectedFileIndex === idx) {
          li.style.background = 'linear-gradient(135deg, #1a1a1a 0%, #2a2a2a 100%)'
          li.style.border = '2px solid #ff6b00'
        } else {
          li.style.background = 'linear-gradient(135deg, #ff8c00 0%, #ff6b00 100%)'
          li.style.border = '2px solid transparent'
        }
        li.style.transform = 'translateX(0)'
        li.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.2)'
      })
      
      li.addEventListener('click', () => {
        selectedFileIndex = idx
        rebuildFileList()
        renderFileEntry(entry)
      })
      
      fileListElm.appendChild(li)
    })
  }

  fileInput.addEventListener('change', () => {
    const selected = fileInput.files
    if (!selected || selected.length === 0) return

    // Add new files to existing list instead of replacing
    const newFiles = Array.from(selected).map(f => ({ name: f.name, file: f }))
    
    // Filter out duplicates by name
    newFiles.forEach(newFile => {
      const exists = files.some(f => f.name === newFile.name)
      if (!exists) {
        files.push(newFile)
      }
    })
    
    rebuildFileList()

    // Auto-render the first newly added file if PDF platform is active
    if (newFiles.length > 0 && currentPlatform === 'pdf') {
      selectedFileIndex = files.length - newFiles.length
      renderFileEntry(files[selectedFileIndex])
      rebuildFileList()
    }
    
    // Reset the file input so the same file can be added again if needed
    fileInput.value = ''
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
