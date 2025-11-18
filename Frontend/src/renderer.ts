// Renderer (TypeScript)
// Chat interface with popup modals and PDF viewer

type FileEntry = {
  name: string
  file: File
  url?: string
  thumbnail?: string
}

type Platform = 'mindmap' | 'podcast' | 'more'

type ChatMessage = {
  text: string
  isUser: boolean
  timestamp: Date
}

document.addEventListener('DOMContentLoaded', () => {
  const fileInput = document.getElementById('fileInput') as HTMLInputElement | null
  const fileListEl = document.getElementById('fileList') as HTMLUListElement | null
  
  // Chat elements
  const chatContainer = document.getElementById('chatContainer') as HTMLDivElement | null
  const chatInput = document.getElementById('chatInput') as HTMLInputElement | null
  const sendButton = document.getElementById('sendButton') as HTMLButtonElement | null
  
  // Popup elements
  const popupModal = document.getElementById('popupModal') as HTMLDivElement | null
  const popupTitle = document.getElementById('popupTitle') as HTMLHeadingElement | null
  const popupBody = document.getElementById('popupBody') as HTMLDivElement | null
  const closePopup = document.getElementById('closePopup') as HTMLButtonElement | null
  
  // Radial menu
  const radialMenu = document.getElementById('radialMenu') as HTMLDivElement | null
  const menuItems = document.querySelectorAll('.menu-item')


  if (!fileInput || !fileListEl || !chatContainer || !chatInput || !sendButton || 
      !popupModal || !popupTitle || !popupBody || !closePopup || !radialMenu) {
    console.warn('Renderer: missing expected DOM elements')
    return
  }

  // Non-null aliases
  const fileListElm = fileListEl!
  const chatContainerEl = chatContainer!
  const chatInputEl = chatInput!

  let files: FileEntry[] = []
  let currentPlatform: Platform | null = null
  let selectedFileIndex: number | null = null
  let chatMessages: ChatMessage[] = []

  // Position menu items in a bottom-left quarter circle (reversed order)
  const radius = 150
  const itemCount = menuItems.length
  const angleStep = (Math.PI / 2) / (itemCount - 1) // Quarter circle (90 degrees)
  const startAngle = Math.PI / 2 // Start from bottom (90 degrees)

  menuItems.forEach((item, index) => {
    const reversedIndex = itemCount - 1 - index // Reverse the order
    const angle = startAngle + angleStep * reversedIndex // Goes from 90° to 180° in reverse
    const x = Math.cos(angle) * radius
    const y = Math.sin(angle) * radius
    
    const menuItem = item as HTMLElement
    // Start at center (0, 0)
    menuItem.style.left = '0px'
    menuItem.style.top = '0px'
    // Set CSS custom properties for the target position
    menuItem.style.setProperty('--tx', `${x}px`)
    menuItem.style.setProperty('--ty', `${y}px`)
  })

  function clearObjectURLs() {
    for (const f of files) {
      if (f.url) {
        try { URL.revokeObjectURL(f.url) } catch (_) { }
        delete f.url
      }
    }
  }

  // Show popup modal with platform-specific options
  function showPopup(platform: Platform) {
    currentPlatform = platform
    
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

    let title = ''
    let content = ''

    switch (platform) {
      case 'mindmap':
        title = '🧠 Mind Map Options'
        content = `
          <div style="display: flex; flex-direction: column; gap: 12px;">
            <p style="color: #e0e0e0;">Create a mind map from your documents:</p>
            <button style="background: linear-gradient(135deg, #ff8c00 0%, #ff6b00 100%); border: none; border-radius: 6px; padding: 10px 20px; color: white; font-weight: 600; cursor: pointer;">
              Generate Mind Map
            </button>
            <button style="background: #2a2a2a; border: 1px solid #ff8c00; border-radius: 6px; padding: 10px 20px; color: #ff8c00; font-weight: 600; cursor: pointer;">
              Upload Existing Mind Map
            </button>
          </div>
        `
        break
      case 'podcast':
        title = '🎙️ Podcast Options'
        content = `
          <div style="display: flex; flex-direction: column; gap: 12px;">
            <p style="color: #e0e0e0;">Generate or play podcasts:</p>
            <button style="background: linear-gradient(135deg, #ff8c00 0%, #ff6b00 100%); border: none; border-radius: 6px; padding: 10px 20px; color: white; font-weight: 600; cursor: pointer;">
              Generate Podcast from PDF
            </button>
            <button style="background: #2a2a2a; border: 1px solid #ff8c00; border-radius: 6px; padding: 10px 20px; color: #ff8c00; font-weight: 600; cursor: pointer;">
              Upload Audio File
            </button>
          </div>
        `
        break
      case 'more':
        title = '⚙️ More Options'
        content = `
          <div style="display: flex; flex-direction: column; gap: 12px;">
            <button style="background: #2a2a2a; border: 1px solid #ff8c00; border-radius: 6px; padding: 10px 20px; color: #ff8c00; font-weight: 600; cursor: pointer; text-align: left;">
              ⚙️ Settings
            </button>
            <button style="background: #2a2a2a; border: 1px solid #ff8c00; border-radius: 6px; padding: 10px 20px; color: #ff8c00; font-weight: 600; cursor: pointer; text-align: left;">
              📤 Export Data
            </button>
            <button style="background: #2a2a2a; border: 1px solid #ff8c00; border-radius: 6px; padding: 10px 20px; color: #ff8c00; font-weight: 600; cursor: pointer; text-align: left;">
              ℹ️ About GenHat
            </button>
          </div>
        `
        break
    }

    popupTitle!.textContent = title
    popupBody!.innerHTML = content
    popupModal!.classList.add('active')
  }

  // Open PDF viewer in popup
  function openPDFViewer(entry: FileEntry) {
    if (!entry.url) entry.url = URL.createObjectURL(entry.file)

    popupTitle!.textContent = `📄 ${entry.name}`
    popupBody!.innerHTML = `
      <iframe 
        src="${entry.url}" 
        style="width: 100%; height: calc(90vh - 100px); border: none; border-radius: 8px; background: #000;"
        title="PDF Viewer"
      ></iframe>
    `
    
    const popupContent = popupModal!.querySelector('.popup-content') as HTMLElement
    if (popupContent) {
      popupContent.classList.add('pdf-viewer')
    }
    
    popupModal!.classList.add('active')
  }

  // Add message to chat
  function addChatMessage(text: string, isUser: boolean) {
    const message: ChatMessage = {
      text,
      isUser,
      timestamp: new Date()
    }
    chatMessages.push(message)

    // Clear welcome message if this is first message
    if (chatMessages.length === 1) {
      chatContainerEl.innerHTML = ''
    }

    const messageEl = document.createElement('div')
    messageEl.style.cssText = `
      display: flex;
      flex-direction: column;
      align-items: ${isUser ? 'flex-end' : 'flex-start'};
      margin-bottom: 12px;
    `

    const bubble = document.createElement('div')
    bubble.textContent = text
    bubble.style.cssText = `
      background: ${isUser ? 'linear-gradient(135deg, #ff8c00 0%, #ff6b00 100%)' : '#2a2a2a'};
      color: white;
      padding: 12px 16px;
      border-radius: ${isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px'};
      max-width: 70%;
      word-wrap: break-word;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    `

    messageEl.appendChild(bubble)
    chatContainerEl.appendChild(messageEl)
    chatContainerEl.scrollTop = chatContainerEl.scrollHeight
  }

  // Send chat message
  function sendMessage() {
    const message = chatInputEl.value.trim()
    if (!message) return

    addChatMessage(message, true)
    chatInputEl.value = ''

    // Simulate AI response
    setTimeout(() => {
      let response = 'I received your message. How can I assist you further?'
      
      if (message.toLowerCase().includes('summarize') || message.toLowerCase().includes('summary')) {
        response = 'I can help summarize your documents. Please select a PDF from the menu to get started.'
      } else if (message.toLowerCase().includes('mind map')) {
        response = 'I can create mind maps from your PDFs. Click the 🧠 Mind Map option to generate one.'
      } else if (message.toLowerCase().includes('podcast')) {
        response = 'I can convert your documents into podcasts. Try the 🎙️ Podcast option!'
      }
      
      addChatMessage(response, false)
    }, 1000)
  }

  function rebuildFileList() {
    fileListElm.innerHTML = ''
    if (files.length === 0) {
      fileListElm.innerHTML = '<div style="text-align: center; color: #666; padding: 20px;">No files uploaded</div>'
      return
    }

    files.forEach((entry, idx) => {
      // Create file card container
      const card = document.createElement('div')
      card.className = 'file-card'
      if (selectedFileIndex === idx) {
        card.classList.add('selected')
      }
      
      // Create thumbnail container
      const thumbnailDiv = document.createElement('div')
      thumbnailDiv.className = 'file-thumbnail'
      thumbnailDiv.innerHTML = '<div style="font-size: 48px;">📄</div>' // Placeholder icon
      
      // Add numbering
      const numberSpan = document.createElement('span')
      numberSpan.className = 'file-number'
      numberSpan.textContent = (idx + 1).toString()
      thumbnailDiv.appendChild(numberSpan)
      
      // Add delete button
      const deleteBtn = document.createElement('button')
      deleteBtn.className = 'delete-btn'
      deleteBtn.textContent = '×'
      deleteBtn.title = 'Delete file'
      deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation() // Prevent card click
        // Remove file from array
        files.splice(idx, 1)
        // Adjust selected index if necessary
        if (selectedFileIndex !== null && selectedFileIndex >= idx && selectedFileIndex > 0) {
          selectedFileIndex--
        } else if (selectedFileIndex === idx) {
          selectedFileIndex = null
        }
        // Clear any object URLs for this file
        if (entry.url) {
          URL.revokeObjectURL(entry.url)
        }
        rebuildFileList()
        addChatMessage(`Removed "${entry.name}" from the list.`, false)
      })
      thumbnailDiv.appendChild(deleteBtn)
      
      // Create file info section
      const infoDiv = document.createElement('div')
      infoDiv.className = 'file-info'
      
      const nameSpan = document.createElement('div')
      nameSpan.className = 'file-name'
      nameSpan.textContent = entry.name
      nameSpan.title = entry.name
      
      const metaSpan = document.createElement('div')
      metaSpan.className = 'file-meta'
      metaSpan.textContent = `${(entry.file.size / 1024).toFixed(0)} KB • PDF`
      
      infoDiv.appendChild(nameSpan)
      infoDiv.appendChild(metaSpan)
      
      card.appendChild(thumbnailDiv)
      card.appendChild(infoDiv)
      
      // Click handler - open PDF viewer popup
      card.addEventListener('click', () => {
        selectedFileIndex = idx
        rebuildFileList()
        openPDFViewer(entry)
      })
      
      fileListElm.appendChild(card)
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

    // Show message for uploaded files
    if (newFiles.length > 0) {
      addChatMessage(`Uploaded ${newFiles.length} file(s) successfully!`, false)
    }
    
    // Reset the file input so the same file can be added again if needed
    fileInput.value = ''
  })

  // Radial menu item click handlers
  menuItems.forEach(item => {
    item.addEventListener('click', () => {
      const platform = (item as HTMLElement).getAttribute('data-platform') as Platform
      if (platform) {
        showPopup(platform)
      }
    })
  })

  // Chat send button
  sendButton!.addEventListener('click', sendMessage)

  // Chat input enter key
  chatInputEl.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      sendMessage()
    }
  })

  // Close popup
  closePopup!.addEventListener('click', () => {
    const popupContent = popupModal!.querySelector('.popup-content') as HTMLElement
    if (popupContent) {
      popupContent.classList.remove('pdf-viewer')
    }
    popupModal!.classList.remove('active')
  })

  // Close popup on background click
  popupModal!.addEventListener('click', (e) => {
    if (e.target === popupModal) {
      const popupContent = popupModal!.querySelector('.popup-content') as HTMLElement
      if (popupContent) {
        popupContent.classList.remove('pdf-viewer')
      }
      popupModal!.classList.remove('active')
    }
  })

  // Initialize with welcome message
  addChatMessage('Welcome to GenHat! 👋 Upload PDFs from the sidebar and use the menu to explore different features.', false)

  // Clean up object URLs when the page unloads
  window.addEventListener('beforeunload', () => {
    clearObjectURLs()
  })
})
