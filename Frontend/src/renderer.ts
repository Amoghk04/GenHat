// Renderer (TypeScript)
// Chat interface with popup modals and PDF viewer

import {
  cachePDFs,
  waitForCacheReadyWithProgress,
  analyzeChunksWithGemini,
  removePDF
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
  id?: string
  branchFrom?: string
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
  
  // Sidebar action buttons
  const newChatBtn = document.getElementById('newChatBtn') as HTMLButtonElement | null
  const newMindmapBtn = document.getElementById('newMindmapBtn') as HTMLButtonElement | null
  const newPodcastBtn = document.getElementById('newPodcastBtn') as HTMLButtonElement | null

  const tabsContainerEl = document.getElementById('tabsContainer') as HTMLDivElement | null

  if (!fileInput || !fileListEl || !chatContainer || !chatInput || !sendButton || 
      !popupModal || !popupTitle || !popupBody || !closePopup || 
      !newChatBtn || !newMindmapBtn || !newPodcastBtn || !tabsContainerEl) {
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
      newChatBtn: !!newChatBtn,
      newMindmapBtn: !!newMindmapBtn,
      newPodcastBtn: !!newPodcastBtn,
      tabsContainerEl: !!tabsContainerEl
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

  // Tab system
  interface ChatTab {
    id: string
    name: string
    icon: string
    type: 'chat' | 'mindmap' | 'podcast'
    messages: ChatMessage[]
    platform: Platform | null
    isTyping: boolean
  }

  let tabs: Map<string, ChatTab> = new Map()
  let activeTabId: string = 'default'
  let tabCounter: number = 1
  let draggedTabId: string | null = null

  const handleTabWheel = (event: WheelEvent) => {
    event.preventDefault()
    
    let delta = 0
    // Prioritize X axis if it's significant (trackpad/shift+wheel), otherwise use Y (mouse wheel)
    if (Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
      delta = event.deltaX
    } else {
      delta = event.deltaY
    }

    // Normalize delta based on mode
    if (event.deltaMode === 1) { // DOM_DELTA_LINE
      delta *= 40
    } else if (event.deltaMode === 2) { // DOM_DELTA_PAGE
      delta *= tabsContainerEl.clientWidth
    }

    tabsContainerEl.scrollLeft += delta
  }

  tabsContainerEl.addEventListener('wheel', handleTabWheel, { passive: false })

  // Function to update scroll indicators visibility
  function updateScrollIndicators() {
    const leftIndicator = document.getElementById('scrollLeftIndicator')
    const rightIndicator = document.getElementById('scrollRightIndicator')
    
    if (!leftIndicator || !rightIndicator || !tabsContainerEl) return

    const scrollLeft = tabsContainerEl.scrollLeft
    const scrollWidth = tabsContainerEl.scrollWidth
    const clientWidth = tabsContainerEl.clientWidth

    // Show left indicator if we can scroll left
    if (scrollLeft > 5) {
      leftIndicator.classList.add('visible')
    } else {
      leftIndicator.classList.remove('visible')
    }

    // Show right indicator if we can scroll right
    if (scrollLeft < scrollWidth - clientWidth - 5) {
      rightIndicator.classList.add('visible')
    } else {
      rightIndicator.classList.remove('visible')
    }
  }

  // Update scroll indicators on scroll
  tabsContainerEl.addEventListener('scroll', updateScrollIndicators)

  // Add click handlers for scroll indicators
  const leftIndicator = document.getElementById('scrollLeftIndicator')
  const rightIndicator = document.getElementById('scrollRightIndicator')

  if (leftIndicator) {
    leftIndicator.addEventListener('click', () => {
      if (tabsContainerEl) {
        tabsContainerEl.scrollBy({ left: -200, behavior: 'smooth' })
      }
    })
  }

  if (rightIndicator) {
    rightIndicator.addEventListener('click', () => {
      if (tabsContainerEl) {
        tabsContainerEl.scrollBy({ left: 200, behavior: 'smooth' })
      }
    })
  }

  tabsContainerEl.addEventListener('dragover', (event) => {
    if (!draggedTabId) {
      return
    }

    event.preventDefault()
    if (event.target instanceof HTMLElement && event.target.closest('.tab')) {
      return
    }

    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move'
    }
  })

  tabsContainerEl.addEventListener('drop', (event) => {
    if (!draggedTabId) {
      return
    }

    if (event.target instanceof HTMLElement && event.target.closest('.tab')) {
      return
    }

    event.preventDefault()
    const orderedTabs = Array.from(tabs.values())
    const draggedIndex = orderedTabs.findIndex(tab => tab.id === draggedTabId)

    if (draggedIndex === -1) {
      draggedTabId = null
      return
    }

    const [draggedTab] = orderedTabs.splice(draggedIndex, 1)
    orderedTabs.push(draggedTab)
    tabs = new Map(orderedTabs.map(tab => [tab.id, tab]))
    draggedTabId = null
    renderTabs()
  })

  // Initialize default tab
  tabs.set('default', {
    id: 'default',
    name: 'Chat',
    icon: '💬',
    type: 'chat',
    messages: [],
    platform: null,
    isTyping: false
  })
  
  // Backend state
  const appState: AppState = {
    cacheKey: null,
    projectName: 'GenHat_Session_' + Date.now(),
    isProcessing: false,
    currentPersona: 'General User',
    currentTask: 'Analyze and summarize documents'
  }

  let currentPDFViewer: PDFViewer | null = null

  // Tab management functions
  function createNewTab(type: 'chat' | 'mindmap' | 'podcast'): string {
    const tabId = `tab-${tabCounter++}`
    const icon = type === 'chat' ? '💬' : type === 'mindmap' ? '🧠' : '🎙️'
    const typeName = type === 'chat' ? 'Chat' : type === 'mindmap' ? 'Mind Map' : 'Podcast'
    const tabName = `${typeName} ${tabs.size}`
    
    tabs.set(tabId, {
      id: tabId,
      name: tabName,
      icon,
      type,
      messages: [],
      platform: type === 'chat' ? null : (type as Platform),
      isTyping: false
    })

    switchToTab(tabId)
    renderTabs()
    return tabId
  }

  function reorderTabs(draggedId: string, targetId: string, dropBefore: boolean) {
    if (draggedId === targetId) {
      return
    }

    const orderedTabs = Array.from(tabs.values())
    const draggedIndex = orderedTabs.findIndex(tab => tab.id === draggedId)

    if (draggedIndex === -1) {
      return
    }

    const [draggedTab] = orderedTabs.splice(draggedIndex, 1)
    const targetIndex = orderedTabs.findIndex(tab => tab.id === targetId)

    if (targetIndex === -1) {
      orderedTabs.push(draggedTab)
    } else {
      const insertIndex = dropBefore ? targetIndex : targetIndex + 1
      orderedTabs.splice(insertIndex, 0, draggedTab)
    }

    tabs = new Map(orderedTabs.map(tab => [tab.id, tab]))
    renderTabs()
  }

  function switchToTab(tabId: string) {
    const tab = tabs.get(tabId)
    if (!tab) return

    // Save current tab's messages before switching
    const currentTab = tabs.get(activeTabId)
    if (currentTab) {
      currentTab.messages = chatMessages
      currentTab.platform = currentPlatform
      currentTab.isTyping = !!document.getElementById('typingIndicator')
    }

    // Load new tab
    activeTabId = tabId
    chatMessages = [...tab.messages] // Create a copy to avoid mutations
    currentPlatform = tab.platform
    
    // Update UI - clear and rebuild chat container
    chatContainerEl.innerHTML = ''
    if (chatMessages.length === 0 && !tab.isTyping) {
      const welcome = document.createElement('div')
      welcome.style.cssText = 'text-align: center; color: #666; margin-top: 20px;'
      const emoji = tab.type === 'mindmap' ? '🧠' : tab.type === 'podcast' ? '🎙️' : '💬'
      welcome.innerHTML = `<div style="font-size: 48px; margin-bottom: 12px;">${emoji}</div><p style="font-size: 16px;">Start a conversation...</p>`
      chatContainerEl.appendChild(welcome)
    } else {
      // Rebuild messages for this tab
      const tempMessages = chatMessages
      chatMessages = []
      tempMessages.forEach(msg => {
        addChatMessage(msg.text, msg.isUser, msg.branchFrom)
      })
      
      // Restore typing indicator if it was active
      if (tab.isTyping) {
        showTypingIndicator()
      }
    }

    renderTabs()
  }

  function closeTab(tabId: string) {
    if (tabs.size <= 1) return // Keep at least one tab
    
    tabs.delete(tabId)
    
    if (activeTabId === tabId) {
      // Switch to first remaining tab
      const remainingTabs = Array.from(tabs.keys())
      activeTabId = remainingTabs[0] || 'default'
      switchToTab(activeTabId)
    } else {
      renderTabs()
    }
  }

  function renderTabs() {
    if (!tabsContainerEl) return

    // Clear existing tabs
    tabsContainerEl.innerHTML = ''

    // Create tabs
    for (const tab of tabs.values()) {
      const tabEl = document.createElement('div')
      tabEl.className = `tab ${tab.id === activeTabId ? 'active' : ''}`
      tabEl.dataset.tabId = tab.id
      if (tabs.size > 1) {
        tabEl.setAttribute('draggable', 'true')
      }
      
      const iconEl = document.createElement('span')
      iconEl.className = 'tab-icon'
      iconEl.textContent = tab.icon
      
      const labelEl = document.createElement('span')
      labelEl.className = 'tab-label'
      labelEl.textContent = tab.name
      
      const closeEl = document.createElement('div')
      closeEl.className = 'tab-close'
      closeEl.innerHTML = '×'
      
      tabEl.appendChild(iconEl)
      tabEl.appendChild(labelEl)
      if (tabs.size > 1) {
        tabEl.appendChild(closeEl)
      }
      
      tabEl.addEventListener('click', (e) => {
        if ((e.target as HTMLElement).classList.contains('tab-close')) {
          closeTab(tab.id)
        } else {
          switchToTab(tab.id)
        }
      })

      tabEl.addEventListener('dragstart', (event) => {
        if (tabs.size <= 1) {
          return
        }

        draggedTabId = tab.id
        tabEl.classList.add('dragging')
        event.dataTransfer?.setData('text/plain', tab.id)
        event.dataTransfer?.setDragImage(tabEl, 20, 20)
      })

      tabEl.addEventListener('dragend', () => {
        tabEl.classList.remove('dragging', 'drag-over-before', 'drag-over-after')
        draggedTabId = null
      })

      tabEl.addEventListener('dragover', (event) => {
        if (!draggedTabId || draggedTabId === tab.id) {
          return
        }

        event.preventDefault()
        event.stopPropagation()
        if (event.dataTransfer) {
          event.dataTransfer.dropEffect = 'move'
        }

        const bounds = tabEl.getBoundingClientRect()
        const dropBefore = event.clientX < bounds.left + bounds.width / 2
        tabEl.classList.toggle('drag-over-before', dropBefore)
        tabEl.classList.toggle('drag-over-after', !dropBefore)
      })

      tabEl.addEventListener('dragleave', () => {
        tabEl.classList.remove('drag-over-before', 'drag-over-after')
      })

      tabEl.addEventListener('drop', (event) => {
        if (!draggedTabId || draggedTabId === tab.id) {
          return
        }

        event.preventDefault()
        event.stopPropagation()
        const bounds = tabEl.getBoundingClientRect()
        const dropBefore = event.clientX < bounds.left + bounds.width / 2
        tabEl.classList.remove('drag-over-before', 'drag-over-after')
        reorderTabs(draggedTabId, tab.id, dropBefore)
        draggedTabId = null
      })

      tabsContainerEl.appendChild(tabEl)
    }

    // Update scroll indicators after rendering tabs
    setTimeout(() => updateScrollIndicators(), 50)
  }

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

  // Show selection analysis popup
  function showSelectionAnalysisPopup(content: string, isLoading: boolean = false) {
    let popup = document.getElementById('selectionAnalysisPopup')
    
    if (!popup) {
      popup = document.createElement('div')
      popup.id = 'selectionAnalysisPopup'
      popup.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        width: 400px;
        max-height: 600px;
        background: #1a1a1a;
        border: 1px solid #ff8c00;
        border-radius: 8px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        z-index: 10000;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        transition: transform 0.3s ease, opacity 0.3s ease;
      `
      
      // Header
      const header = document.createElement('div')
      header.style.cssText = `
        padding: 12px 16px;
        background: #2a2a2a;
        border-bottom: 1px solid #333;
        display: flex;
        justify-content: space-between;
        align-items: center;
      `
      header.innerHTML = `
        <span style="color: #ff8c00; font-weight: 600;">📝 Selection Analysis</span>
        <button id="closeSelectionPopup" style="background: none; border: none; color: #888; cursor: pointer; font-size: 18px;">×</button>
      `
      
      // Body
      const body = document.createElement('div')
      body.id = 'selectionPopupBody'
      body.style.cssText = `
        padding: 16px;
        overflow-y: auto;
        color: #e0e0e0;
        font-size: 14px;
        line-height: 1.5;
        max-height: 500px;
      `
      
      popup.appendChild(header)
      popup.appendChild(body)
      document.body.appendChild(popup)
      
      // Close handler
      const closeBtn = popup.querySelector('#closeSelectionPopup')
      if (closeBtn) {
        closeBtn.addEventListener('click', () => {
          popup?.remove()
        })
      }
    }

    const body = popup.querySelector('#selectionPopupBody')
    if (body) {
      if (isLoading) {
        body.innerHTML = `
          <div style="display: flex; align-items: center; gap: 10px; color: #888;">
            <div class="typing-dot" style="background: #ff8c00;"></div>
            Analyzing selection...
          </div>
        `
      } else {
        body.innerHTML = parseMarkdown(content)
      }
    }
  }

  // Handle text selection in PDF
  async function handlePDFTextSelection(text: string, pageNumber: number, documentName: string) {
    if (!appState.cacheKey) {
      showSelectionAnalysisPopup('⚠️ Please wait for documents to finish processing before analyzing text selections.')
      return
    }

    if (appState.isProcessing) {
      showSelectionAnalysisPopup('⚠️ Already processing a request. Please wait...')
      return
    }

    try {
      appState.isProcessing = true
      showSelectionAnalysisPopup('', true)

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
        showSelectionAnalysisPopup(geminiText)
      } else {
        showSelectionAnalysisPopup('I couldn\'t analyze the selected text. Please try selecting a different section.')
      }

    } catch (error) {
      console.error('Error analyzing text selection:', error)
      showSelectionAnalysisPopup(`❌ Failed to analyze selection: ${error instanceof Error ? error.message : 'Unknown error'}`)
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
  function addChatMessage(text: string, isUser: boolean, branchFrom?: string) {
    const messageId = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    const message: ChatMessage = {
      text,
      isUser,
      timestamp: new Date(),
      id: messageId,
      branchFrom
    }
    chatMessages.push(message)

    // Clear welcome message if this is first message
    if (chatMessages.length === 1) {
      chatContainerEl.innerHTML = ''
    }

    // Create message wrapper (flex container for bubble and buttons)
    const messageWrapper = document.createElement('div')
    messageWrapper.className = `message-item-wrapper ${isUser ? 'user' : ''}`
    messageWrapper.setAttribute('data-message-id', messageId)

    const bubble = document.createElement('div')
    bubble.className = `message-bubble ${isUser ? 'user' : ''}`
    
    // For bot messages, render markdown; for user messages, use plain text
    if (!isUser) {
      bubble.innerHTML = parseMarkdown(text)
    } else {
      bubble.textContent = text
    }

    // Create buttons container (outside bubble)
    const buttonsContainer = document.createElement('div')
    buttonsContainer.className = 'message-buttons-container'

    // Create copy button
    const copyBtn = document.createElement('button')
    copyBtn.className = 'message-copy-btn'
    copyBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
        <rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect>
      </svg>
    `
    copyBtn.title = 'Copy message'
    copyBtn.addEventListener('click', async (e) => {
      e.stopPropagation()
      try {
        await navigator.clipboard.writeText(text)
        // Show toast notification
        const toast = document.createElement('div')
        toast.className = 'copy-toast'
        toast.textContent = 'Copied!'
        document.body.appendChild(toast)
        
        setTimeout(() => {
          toast.classList.add('hide')
          setTimeout(() => toast.remove(), 300)
        }, 2000)
      } catch (err) {
        console.error('Failed to copy:', err)
      }
    })

    buttonsContainer.appendChild(copyBtn)

    // Create edit button (only for user messages)
    if (isUser) {
      const editBtn = document.createElement('button')
      editBtn.className = 'message-edit-btn'
      editBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
        </svg>
      `
      editBtn.title = 'Edit and continue'
      editBtn.addEventListener('click', (e) => {
        e.stopPropagation()
        enterEditMode(messageWrapper, bubble, text, messageId, isUser)
      })
      buttonsContainer.appendChild(editBtn)
    }

    // Assemble: wrapper contains bubble and buttons
    messageWrapper.appendChild(bubble)
    messageWrapper.appendChild(buttonsContainer)

    chatContainerEl.appendChild(messageWrapper)
    chatContainerEl.scrollTop = chatContainerEl.scrollHeight
  }

  // Enter edit mode for a message
  function enterEditMode(messageEl: HTMLElement, bubble: HTMLElement, originalText: string, messageId: string, isUser: boolean) {
    const messageIndex = chatMessages.findIndex(m => m.id === messageId)
    if (messageIndex === -1) return

    // Get the current text from the data store (not the stale parameter)
    const currentText = chatMessages[messageIndex].text

    // Create a modal dialog for editing
    const modal = document.createElement('div')
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10000;
      backdrop-filter: blur(4px);
    `

    const dialog = document.createElement('div')
    dialog.style.cssText = `
      background: #0d0d0d;
      border: 2px solid #ff8c00;
      border-radius: 12px;
      padding: 24px;
      max-width: 500px;
      width: 90%;
      box-shadow: 0 8px 32px rgba(255, 140, 0, 0.3);
    `

    const title = document.createElement('h3')
    title.textContent = 'Edit Message & Continue'
    title.style.cssText = `
      margin: 0 0 16px 0;
      color: #ff8c00;
      font-size: 18px;
    `

    const textarea = document.createElement('textarea')
    textarea.value = currentText
    textarea.placeholder = 'Edit your message...'
    textarea.style.cssText = `
      width: 100%;
      min-height: 100px;
      background: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 8px;
      padding: 12px;
      color: #e0e0e0;
      font-size: 14px;
      outline: none;
      resize: vertical;
      font-family: inherit;
      box-sizing: border-box;
      margin-bottom: 16px;
    `

    const buttons = document.createElement('div')
    buttons.style.cssText = `
      display: flex;
      gap: 8px;
      justify-content: flex-end;
    `

    const cancelBtn = document.createElement('button')
    cancelBtn.textContent = 'Cancel'
    cancelBtn.style.cssText = `
      background: #2a2a2a;
      border: 1px solid #666;
      border-radius: 6px;
      padding: 10px 20px;
      color: #e0e0e0;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    `
    cancelBtn.addEventListener('click', () => {
      modal.remove()
    })

    const continueBtn = document.createElement('button')
    continueBtn.textContent = 'Continue Chat'
    continueBtn.style.cssText = `
      background: linear-gradient(135deg, #ff8c00 0%, #ff6b00 100%);
      border: none;
      border-radius: 6px;
      padding: 10px 20px;
      color: white;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    `
    continueBtn.addEventListener('click', async () => {
      const newText = textarea.value.trim()
      if (!newText) {
        alert('Message cannot be empty')
        return
      }

      // Update the edited message text in the data store only
      chatMessages = chatMessages.slice(0, messageIndex + 1)
      chatMessages[messageIndex].text = newText

      // Remove DOM elements after the edited message without clearing previous ones
      const allMessages = chatContainerEl.querySelectorAll('[data-message-id]')
      allMessages.forEach((el, index) => {
        if (index > messageIndex) {
          el.remove()
        }
      })

      // Update the edited message in the DOM (just the bubble text)
      const editedBubble = messageEl.querySelector('.message-bubble')
      if (editedBubble) {
        editedBubble.textContent = newText
      }

      modal.remove()

      // Send the edited message to continue conversation
      await sendEditedMessage(newText)
    })

    buttons.appendChild(cancelBtn)
    buttons.appendChild(continueBtn)
    dialog.appendChild(title)
    dialog.appendChild(textarea)
    dialog.appendChild(buttons)
    modal.appendChild(dialog)
    document.body.appendChild(modal)

    // Focus textarea
    setTimeout(() => textarea.focus(), 100)

    // Close on escape
    modal.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        modal.remove()
      }
    })
  }
  function showTypingIndicator() {
    // Remove existing typing indicator if any
    hideTypingIndicator()

    const typingEl = document.createElement('div')
    typingEl.id = 'typingIndicator'
    typingEl.className = 'typing-indicator'
    typingEl.innerHTML = `
      <div class="typing-bubble">
        <div class="typing-dots">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div> 
      </div>
    `

    chatContainerEl.appendChild(typingEl)
    chatContainerEl.scrollTop = chatContainerEl.scrollHeight
    
    // Set isTyping state for current tab
    const tab = tabs.get(activeTabId)
    if (tab) {
      tab.isTyping = true
    }
  }

  // Hide typing indicator
  function hideTypingIndicator() {
    const existing = document.getElementById('typingIndicator')
    if (existing) {
      existing.remove()
    }
    
    // Clear isTyping state for current tab
    const tab = tabs.get(activeTabId)
    if (tab) {
      tab.isTyping = false
    }
  }

  // Show loading overlay with custom text
  function showLoadingOverlay(text: string = 'Processing Documents...', subtext: string = 'This may take a few moments') {
    const overlay = document.getElementById('loadingOverlay') as HTMLElement
    const textEl = document.getElementById('loadingText') as HTMLElement
    const subtextEl = document.getElementById('loadingSubtext') as HTMLElement
    
    textEl.textContent = text
    subtextEl.textContent = subtext
    overlay.classList.add('active')
  }

  // Hide loading overlay
  function hideLoadingOverlay() {
    const overlay = document.getElementById('loadingOverlay') as HTMLElement
    overlay.classList.remove('active')
  }

  // Show individual file progress overlay
  function showFileProgressOverlay(fileNames: string[]) {
    const overlay = document.getElementById('loadingOverlay') as HTMLElement
    const textEl = document.getElementById('loadingText') as HTMLElement
    const subtextEl = document.getElementById('loadingSubtext') as HTMLElement
    
    textEl.textContent = 'Building Document Index...'
    subtextEl.innerHTML = `
      <div class="file-progress-container">
        ${fileNames.map((fileName, index) => `
          <div class="file-progress-item processing">
            <div class="radial-progress">
              <div class="radial-progress-circle" style="--progress-angle: 0deg;">
                <div class="radial-progress-inner">0%</div>
              </div>
            </div>
            <div class="file-progress-info">
              <div class="file-progress-name">${fileName}</div>
              <div class="file-progress-status">loading...</div>
            </div>
          </div>
        `).join('')}
      </div>
    `
    overlay.classList.add('active')
  }

  // Update file progress overlay
  function updateFileProgressOverlay(fileProgress: Record<string, any>) {
    const subtextEl = document.getElementById('loadingSubtext') as HTMLElement
    if (subtextEl) {
      subtextEl.innerHTML = `
        <div class="file-progress-container">
          ${Object.entries(fileProgress).map(([fileName, progress]: [string, any]) => {
            const statusText = progress.status === 'completed' ? 'done' : 
                             progress.status === 'processing' ? 'processing...' :
                             progress.status === 'error' ? `error: ${progress.error || 'unknown'}` : 
                             'pending...'
            const statusClass = progress.status === 'completed' ? 'completed' : 
                              progress.status === 'error' ? 'error' : 'processing'
            return `
            <div class="file-progress-item ${statusClass}">
              <div class="radial-progress">
                <div class="radial-progress-circle" style="--progress-angle: ${progress.progress * 3.6}deg;">
                  <div class="radial-progress-inner">${progress.progress}%</div>
                </div>
              </div>
              <div class="file-progress-info">
                <div class="file-progress-name">${fileName}</div>
                <div class="file-progress-status">${statusText}</div>
              </div>
            </div>
          `}).join('')}
        </div>
      `
    }
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

    // Check if cache is ready
    if (!appState.cacheKey) {
      addChatMessage('⏳ Please wait for documents to finish processing before querying...', false)
      return
    }

    // Check if processing
    if (appState.isProcessing) {
      addChatMessage('Please wait, I\'m processing your previous request...', false)
      return
    }

    try {
      appState.isProcessing = true
     

      // Extract persona and task from message, or use defaults
      const persona = appState.currentPersona
      const task = message

      // Call Gemini analysis - use typing indicator for AI processing
      showTypingIndicator()
      const analysisResponse = await analyzeChunksWithGemini(
        appState.cacheKey,
        persona,
        task,
        5, // k
        5  // max_chunks_to_analyze
      )

      hideTypingIndicator()

      // Format and display response as a single markdown message
      if (analysisResponse.gemini_analysis && analysisResponse.gemini_analysis.length > 0) {
        const geminiText = analysisResponse.gemini_analysis[0].gemini_analysis
        
        // Display entire Gemini response as one message with markdown formatting
        addChatMessage(geminiText, false)
      } else {
        addChatMessage('I analyzed your documents but couldn\'t generate insights. Please try rephrasing your question.', false)
      }

      // Show metadata
     

    } catch (error) {
      console.error('Error in sendMessage:', error)
      hideLoadingOverlay()
      hideTypingIndicator()
      addChatMessage(
        `❌ Error: ${error instanceof Error ? error.message : 'Failed to analyze documents. Make sure the backend server is running on http://localhost:8080'}`,
        false
      )
    } finally {
      appState.isProcessing = false
    }
  }

  // Send an edited message (used when continuing from edited point)
  async function sendEditedMessage(message: string) {
    if (!message) return

    // Check if PDFs are uploaded and cached
    if (files.length === 0) {
      addChatMessage('Please upload some PDF files first to enable AI analysis.', false)
      return
    }

    // Check if cache is ready
    if (!appState.cacheKey) {
      addChatMessage('⏳ Please wait for documents to finish processing before querying...', false)
      return
    }

    // Check if processing
    if (appState.isProcessing) {
      addChatMessage('Please wait, I\'m processing your previous request...', false)
      return
    }

    try {
      appState.isProcessing = true

      // Extract persona and task from message, or use defaults
      const persona = appState.currentPersona
      const task = message

      // Call Gemini analysis - use typing indicator for AI processing
      showTypingIndicator()
      const analysisResponse = await analyzeChunksWithGemini(
        appState.cacheKey,
        persona,
        task,
        5, // k
        5  // max_chunks_to_analyze
      )

      hideTypingIndicator()

      // Format and display response as a single markdown message
      if (analysisResponse.gemini_analysis && analysisResponse.gemini_analysis.length > 0) {
        const geminiText = analysisResponse.gemini_analysis[0].gemini_analysis
        
        // Display entire Gemini response as one message with markdown formatting
        addChatMessage(geminiText, false)
      } else {
        addChatMessage('I analyzed your documents but couldn\'t generate insights. Please try rephrasing your question.', false)
      }

    } catch (error) {
      console.error('Error in sendEditedMessage:', error)
      hideLoadingOverlay()
      hideTypingIndicator()
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
      deleteBtn.addEventListener('click', async (e) => {
        e.stopPropagation() // Prevent card click
        
        const fileToRemove = entry.name
        
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
        addChatMessage(`🗑️ Removed "${fileToRemove}" from the list.`, false)
        
        // If we have a cache key (PDFs were already uploaded), recompute embeddings
        if (appState.cacheKey && !appState.isProcessing) {
          try {
            appState.isProcessing = true
            showLoadingOverlay('Recomputing Embeddings...', 'Updating document index after removal')
            addChatMessage('🔄 Recomputing embeddings without this PDF...', false)
            
            // Call backend to remove PDF and rebuild index
            const removeResponse = await removePDF(appState.projectName, fileToRemove)
            
            // Update cache key with the new one
            appState.cacheKey = removeResponse.cache_key
            
            // Wait for the new cache to be ready
            await waitForCacheReadyWithProgress(appState.cacheKey)
            
            if (removeResponse.remaining_pdfs === 0) {
              addChatMessage('⚠️ All PDFs removed. Upload new files to continue.', false)
            } else {
              addChatMessage(`✅ Index rebuilt with ${removeResponse.remaining_pdfs} remaining PDF(s).`, false)
            }
          } catch (error) {
            console.error('Error recomputing embeddings:', error)
            addChatMessage(
              `⚠️ Could not recompute embeddings: ${error instanceof Error ? error.message : 'Unknown error'}. You may need to re-upload the remaining PDFs.`,
              false
            )
            // Clear cache key since it may be invalid
            appState.cacheKey = null
          } finally {
            appState.isProcessing = false
            hideLoadingOverlay()
          }
        }
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
      
      // Upload to backend and cache
      try {
        appState.isProcessing = true
        showLoadingOverlay('Processing PDFs...', 'Sending documents to backend')
        
        const pdfFiles = files.map(f => f.file)
        const cacheResponse = await cachePDFs(pdfFiles, appState.projectName)
        appState.cacheKey = cacheResponse.cache_key
        
        showFileProgressOverlay(uniqueNewFiles.map(f => f.name))
        await waitForCacheReadyWithProgress(appState.cacheKey, (status) => {
          if (status.file_progress) {
            updateFileProgressOverlay(status.file_progress)
          }
        })
        
        hideLoadingOverlay()
      } catch (error) {
        console.error('Error caching PDFs:', error)
        hideLoadingOverlay()
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

  // Initialize tab system
  renderTabs()

  // Chat send button
  sendButton!.addEventListener('click', sendMessage)

  // Sidebar action buttons
  newChatBtn!.addEventListener('click', () => {
    const tabId = createNewTab('chat')
    addChatMessage('Start a new conversation...', false)
  })

  newMindmapBtn!.addEventListener('click', () => {
    const tabId = createNewTab('mindmap')
    addChatMessage('🧠 Mind Map Mode - Describe the concepts you want to map, and I\'ll create a visual mind map from your documents.', false)
  })

  newPodcastBtn!.addEventListener('click', () => {
    const tabId = createNewTab('podcast')
    addChatMessage('🎙️ Podcast Mode - I can create or discuss podcast content based on your documents. What would you like to explore?', false)
  })

  // Chat input enter key
  chatInputEl.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      sendMessage()
    }
  })

  // Sidebar tab switching
  const sidebarTabs = document.querySelectorAll('.sidebar-tab') as NodeListOf<HTMLButtonElement>
  const tabContents = document.querySelectorAll('.sidebar-tab-content') as NodeListOf<HTMLDivElement>
  
  sidebarTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const tabName = tab.getAttribute('data-tab')
      
      // Remove active from all tabs and contents
      sidebarTabs.forEach(t => t.classList.remove('active'))
      tabContents.forEach(c => c.classList.remove('active'))
      
      // Add active to clicked tab and corresponding content
      tab.classList.add('active')
      const activeContent = document.querySelector(`.sidebar-tab-content[data-tab="${tabName}"]`)
      if (activeContent) {
        activeContent.classList.add('active')
      }
    })
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
  // addChatMessage('Welcome to GenHat! 👋 Upload PDFs from the sidebar and use the menu to explore different features.', false)

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
