// Renderer (TypeScript)
// Chat interface with popup modals and PDF viewer

import {
  cachePDFs,
  waitForCacheReady,
  analyzeChunksWithGemini
} from './api.js'

import { PDFViewer } from './pdfViewer.js'

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

type AppState = {
  cacheKey: string | null
  projectName: string
  isProcessing: boolean
  currentPersona: string
  currentTask: string
}

// Main initialization function
function initializeApp() {
  console.log('🎩 GenHat renderer starting...')
  
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
    console.error('❌ Renderer: missing expected DOM elements', {
      fileInput: !!fileInput,
      fileListEl: !!fileListEl,
      chatContainer: !!chatContainer,
      chatInput: !!chatInput,
      sendButton: !!sendButton,
      popupModal: !!popupModal,
      popupTitle: !!popupTitle,
      popupBody: !!popupBody,
      closePopup: !!closePopup,
      radialMenu: !!radialMenu
    })
    return
  }
  
  console.log('✅ All DOM elements found')

  // Non-null aliases
  const fileListElm = fileListEl!
  const chatContainerEl = chatContainer!
  const chatInputEl = chatInput!

  let files: FileEntry[] = []
  let currentPlatform: Platform | null = null
  let selectedFileIndex: number | null = null
  let chatMessages: ChatMessage[] = []
  
  // Backend state
  const appState: AppState = {
    cacheKey: null,
    projectName: 'GenHat_Session_' + Date.now(),
    isProcessing: false,
    currentPersona: 'General User',
    currentTask: 'Analyze and summarize documents'
  }

  let currentPDFViewer: PDFViewer | null = null

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

  // Open PDF viewer in popup with text selection support
  function openPDFViewer(entry: FileEntry) {
    popupTitle!.textContent = `📄 ${entry.name}`
    
    // Create container for PDF viewer
    popupBody!.innerHTML = `
      <div id="pdfViewerContainer" style="width: 100%; height: calc(90vh - 100px); position: relative;"></div>
    `
    
    const popupContent = popupModal!.querySelector('.popup-content') as HTMLElement
    if (popupContent) {
      popupContent.classList.add('pdf-viewer')
    }
    
    popupModal!.classList.add('active')

    // Initialize PDF.js viewer with text selection
    const container = document.getElementById('pdfViewerContainer')
    if (container) {
      // Destroy previous viewer if exists
      if (currentPDFViewer) {
        currentPDFViewer.destroy()
      }

      currentPDFViewer = new PDFViewer({
        container,
        onTextSelected: async (selectedText: string, pageNumber: number) => {
          if (selectedText.length > 10) {
            handlePDFTextSelection(selectedText, pageNumber, entry.name)
          }
        },
        onError: (error: Error) => {
          console.error('PDF Viewer error:', error)
          addChatMessage(`❌ Error viewing PDF: ${error.message}`, false)
        }
      })

      // Load the PDF file
      currentPDFViewer.loadPDF(entry.file).catch(error => {
        console.error('Failed to load PDF:', error)
        addChatMessage(`❌ Failed to load PDF: ${error.message}`, false)
      })
    }
  }

  // Handle text selection in PDF
  async function handlePDFTextSelection(text: string, pageNumber: number, documentName: string) {
    if (!appState.cacheKey) {
      addChatMessage('⚠️ Please wait for documents to finish processing before analyzing text selections.', false)
      return
    }

    if (appState.isProcessing) {
      addChatMessage('⚠️ Already processing a request. Please wait...', false)
      return
    }

    try {
      appState.isProcessing = true
      addChatMessage(`📝 Analyzing selected text from ${documentName} (page ${pageNumber})...`, false)

      // Create a focused task from the selected text
      const task = `Analyze and explain this text in detail: "${text.substring(0, 200)}${text.length > 200 ? '...' : ''}"`

      // Call Gemini analysis with the selected text as context
      const analysisResponse = await analyzeChunksWithGemini(
        appState.cacheKey,
        appState.currentPersona,
        task,
        3, // Fewer chunks since we have specific text
        3
      )

      // Display analysis
      if (analysisResponse.gemini_analysis && analysisResponse.gemini_analysis.length > 0) {
        const geminiText = analysisResponse.gemini_analysis[0].gemini_analysis
        
        // Format as a focused response
        addChatMessage(`💡 **Analysis of selected text:**\n\n${geminiText}`, false)
      } else {
        addChatMessage('I couldn\'t analyze the selected text. Please try selecting a different section.', false)
      }

    } catch (error) {
      console.error('Error analyzing text selection:', error)
      addChatMessage(
        `❌ Failed to analyze selection: ${error instanceof Error ? error.message : 'Unknown error'}`,
        false
      )
    } finally {
      appState.isProcessing = false
    }
  }

  // Simple markdown to HTML converter
  function parseMarkdown(text: string): string {
    let html = text
    
    // Headers (## heading)
    html = html.replace(/^### (.+)$/gm, '<h3 style="color: #ff8c00; margin: 12px 0 8px 0; font-size: 16px;">$1</h3>')
    html = html.replace(/^## (.+)$/gm, '<h2 style="color: #ff8c00; margin: 16px 0 10px 0; font-size: 18px;">$1</h2>')
    html = html.replace(/^# (.+)$/gm, '<h1 style="color: #ff8c00; margin: 20px 0 12px 0; font-size: 20px;">$1</h1>')
    
    // Bold (**text** or __text__)
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong style="color: #ffa500;">$1</strong>')
    html = html.replace(/__(.+?)__/g, '<strong style="color: #ffa500;">$1</strong>')
    
    // Italic (*text* or _text_)
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
    html = html.replace(/_(.+?)_/g, '<em>$1</em>')
    
    // Code blocks (```code```)
    html = html.replace(/```([^`]+)```/g, '<pre style="background: #1a1a1a; padding: 12px; border-radius: 6px; overflow-x: auto; margin: 8px 0; border-left: 3px solid #ff8c00;"><code style="color: #e0e0e0; font-family: monospace;">$1</code></pre>')
    
    // Inline code (`code`)
    html = html.replace(/`([^`]+)`/g, '<code style="background: #1a1a1a; padding: 2px 6px; border-radius: 4px; color: #ff8c00; font-family: monospace;">$1</code>')
    
    // Unordered lists (- item or * item)
    html = html.replace(/^[\-\*] (.+)$/gm, '<li style="margin-left: 20px; margin-bottom: 4px;">$1</li>')
    html = html.replace(/(<li[^>]*>.*<\/li>)/s, '<ul style="margin: 8px 0; padding-left: 0;">$1</ul>')
    
    // Ordered lists (1. item)
    html = html.replace(/^\d+\. (.+)$/gm, '<li style="margin-left: 20px; margin-bottom: 4px;">$1</li>')
    
    // Links [text](url)
    html = html.replace(/\[([^\]]+)\]\(([^\)]+)\)/g, '<a href="$2" style="color: #ff8c00; text-decoration: underline;">$1</a>')
    
    // Line breaks (convert \n to <br> for paragraphs)
    html = html.replace(/\n\n/g, '</p><p style="margin: 8px 0;">')
    html = html.replace(/\n/g, '<br>')
    
    // Wrap in paragraph
    html = '<p style="margin: 8px 0;">' + html + '</p>'
    
    return html
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
    
    // For bot messages, render markdown; for user messages, use plain text
    if (!isUser) {
      bubble.innerHTML = parseMarkdown(text)
    } else {
      bubble.textContent = text
    }
    
    bubble.style.cssText = `
      background: ${isUser ? 'linear-gradient(135deg, #ff8c00 0%, #ff6b00 100%)' : '#2a2a2a'};
      color: white;
      padding: 12px 16px;
      border-radius: ${isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px'};
      max-width: 70%;
      word-wrap: break-word;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
      line-height: 1.6;
    `

    messageEl.appendChild(bubble)
    chatContainerEl.appendChild(messageEl)
    chatContainerEl.scrollTop = chatContainerEl.scrollHeight
  }

  // Send chat message
  async function sendMessage() {
    const message = chatInputEl.value.trim()
    if (!message) return

    addChatMessage(message, true)
    chatInputEl.value = ''

    // Check if PDFs are uploaded and cached
    if (files.length === 0) {
      addChatMessage('Please upload some PDF files first to enable AI analysis.', false)
      return
    }

    // Check if processing
    if (appState.isProcessing) {
      addChatMessage('Please wait, I\'m processing your previous request...', false)
      return
    }

    try {
      appState.isProcessing = true
      addChatMessage('🤔 Analyzing your documents with Gemini AI...', false)

      // If no cache key, upload PDFs first
      if (!appState.cacheKey) {
        addChatMessage('📤 Uploading and processing PDFs...', false)
        
        const pdfFiles = files.map(f => f.file)
        const cacheResponse = await cachePDFs(pdfFiles, appState.projectName)
        appState.cacheKey = cacheResponse.cache_key

        // Wait for cache to be ready
        addChatMessage('⏳ Building document index...', false)
        await waitForCacheReady(appState.cacheKey)
        addChatMessage('✅ Documents indexed and ready!', false)
      }

      // Extract persona and task from message, or use defaults
      const persona = appState.currentPersona
      const task = message

      // Call Gemini analysis
      const analysisResponse = await analyzeChunksWithGemini(
        appState.cacheKey,
        persona,
        task,
        5, // k
        5  // max_chunks_to_analyze
      )

      // Format and display response as a single markdown message
      if (analysisResponse.gemini_analysis && analysisResponse.gemini_analysis.length > 0) {
        const geminiText = analysisResponse.gemini_analysis[0].gemini_analysis
        
        // Display entire Gemini response as one message with markdown formatting
        addChatMessage(geminiText, false)
      } else {
        addChatMessage('I analyzed your documents but couldn\'t generate insights. Please try rephrasing your question.', false)
      }

      // Show metadata
      if (analysisResponse.metadata) {
        const meta = analysisResponse.metadata
        addChatMessage(
          `📊 Analyzed ${meta.chunks_analyzed} sections from ${meta.input_documents.length} document(s) using ${meta.gemini_model}`,
          false
        )
      }

    } catch (error) {
      console.error('Error in sendMessage:', error)
      addChatMessage(
        `❌ Error: ${error instanceof Error ? error.message : 'Failed to analyze documents. Make sure the backend server is running on http://localhost:8080'}`,
        false
      )
    } finally {
      appState.isProcessing = false
    }
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

  fileInput.addEventListener('change', async () => {
    const selected = fileInput.files
    if (!selected || selected.length === 0) return

    // Add new files to existing list instead of replacing
    const newFiles = Array.from(selected).map(f => ({ name: f.name, file: f }))
    
    // Filter out duplicates by name
    const uniqueNewFiles: FileEntry[] = []
    for (const newFile of newFiles) {
      const exists = files.some(f => f.name === newFile.name)
      if (!exists) {
        files.push(newFile)
        uniqueNewFiles.push(newFile)
      }
    }
    
    rebuildFileList()

    // Show message for uploaded files
    if (uniqueNewFiles.length > 0) {
      addChatMessage(`📄 Uploaded ${uniqueNewFiles.length} file(s) successfully!`, false)
      
      // Upload to backend and cache
      try {
        addChatMessage('📤 Sending PDFs to backend for processing...', false)
        appState.isProcessing = true
        
        const pdfFiles = files.map(f => f.file)
        const cacheResponse = await cachePDFs(pdfFiles, appState.projectName)
        appState.cacheKey = cacheResponse.cache_key
        
        addChatMessage('⏳ Building document index...', false)
        await waitForCacheReady(appState.cacheKey)
        
        addChatMessage('✅ Documents are ready! You can now ask questions about them.', false)
      } catch (error) {
        console.error('Error caching PDFs:', error)
        addChatMessage(
          `⚠️ Failed to process PDFs on backend: ${error instanceof Error ? error.message : 'Unknown error'}. You can still view them, but AI features may not work.`,
          false
        )
      } finally {
        appState.isProcessing = false
      }
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
    if (currentPDFViewer) {
      currentPDFViewer.destroy()
      currentPDFViewer = null
    }
    const popupContent = popupModal!.querySelector('.popup-content') as HTMLElement
    if (popupContent) {
      popupContent.classList.remove('pdf-viewer')
    }
    popupModal!.classList.remove('active')
  })

  // Close popup on background click
  popupModal!.addEventListener('click', (e) => {
    if (e.target === popupModal) {
      if (currentPDFViewer) {
        currentPDFViewer.destroy()
        currentPDFViewer = null
      }
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
}

// Run initialization when DOM is ready or immediately if already loaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeApp)
} else {
  // DOM is already loaded, run immediately
  initializeApp()
}
