// PDF Viewer with text selection support using PDF.js
// PDF.js is loaded globally from CDN in index.html

// Type declarations for PDF.js global
declare const pdfjsLib: any

export interface PDFViewerOptions {
  container: HTMLElement
  onTextSelected?: (text: string, pageNumber: number) => void
  onError?: (error: Error) => void
}

export class PDFViewer {
  private container: HTMLElement
  private pdf: any = null
  private currentPage: number = 1
  private scale: number = 1.5
  private onTextSelected?: (text: string, pageNumber: number) => void
  private onError?: (error: Error) => void

  constructor(options: PDFViewerOptions) {
    this.container = options.container
    this.onTextSelected = options.onTextSelected
    this.onError = options.onError
  }

  async loadPDF(file: File): Promise<void> {
    try {
      // Clear container
      this.container.innerHTML = '<div style="text-align: center; padding: 20px; color: #888;">Loading PDF...</div>'

      // Read file as ArrayBuffer
      const arrayBuffer = await file.arrayBuffer()
      const typedArray = new Uint8Array(arrayBuffer)

      // Load PDF
      const loadingTask = pdfjsLib.getDocument({ data: typedArray })
      this.pdf = await loadingTask.promise

      // Create viewer UI
      this.createViewerUI()

      // Render first page
      await this.renderPage(1)
    } catch (error) {
      console.error('Error loading PDF:', error)
      if (this.onError) {
        this.onError(error instanceof Error ? error : new Error('Failed to load PDF'))
      }
      this.container.innerHTML = `
        <div style="text-align: center; padding: 40px; color: #ff6b6b;">
          <div style="font-size: 48px; margin-bottom: 12px;">⚠️</div>
          <p>Failed to load PDF</p>
        </div>
      `
    }
  }

  private createViewerUI(): void {
    if (!this.pdf) return

    this.container.innerHTML = `
      <div style="display: flex; flex-direction: column; height: 100%; background: #1a1a1a;">
        <!-- Toolbar -->
        <div id="pdfToolbar" style="display: flex; align-items: center; justify-content: space-between; padding: 12px; background: #0d0d0d; border-bottom: 1px solid #2a2a2a;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <button id="prevPage" style="background: #2a2a2a; border: 1px solid #3a3a3a; color: #e0e0e0; padding: 6px 12px; border-radius: 4px; cursor: pointer;">◀</button>
            <span id="pageInfo" style="color: #e0e0e0; font-size: 14px;">Page 1 of ${this.pdf.numPages}</span>
            <button id="nextPage" style="background: #2a2a2a; border: 1px solid #3a3a3a; color: #e0e0e0; padding: 6px 12px; border-radius: 4px; cursor: pointer;">▶</button>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <button id="zoomOut" style="background: #2a2a2a; border: 1px solid #3a3a3a; color: #e0e0e0; padding: 6px 12px; border-radius: 4px; cursor: pointer;">−</button>
            <span style="color: #e0e0e0; font-size: 14px;">${Math.round(this.scale * 100)}%</span>
            <button id="zoomIn" style="background: #2a2a2a; border: 1px solid #3a3a3a; color: #e0e0e0; padding: 6px 12px; border-radius: 4px; cursor: pointer;">+</button>
          </div>
        </div>
        
        <!-- Canvas container -->
        <div id="pdfCanvasContainer" style="flex: 1; overflow: auto; display: flex; justify-content: center; align-items: flex-start; padding: 20px; background: #1a1a1a;">
          <div style="position: relative; background: white; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
            <canvas id="pdfCanvas"></canvas>
            <div id="textLayer" class="textLayer" style="position: absolute; left: 0; top: 0; right: 0; bottom: 0; overflow: hidden; opacity: 0.2; line-height: 1.0; cursor: text; text-align: initial;"></div>
          </div>
        </div>
      </div>
    `

    // Setup event listeners
    this.setupEventListeners()
  }

  private setupEventListeners(): void {
    const prevBtn = this.container.querySelector('#prevPage') as HTMLButtonElement
    const nextBtn = this.container.querySelector('#nextPage') as HTMLButtonElement
    const zoomInBtn = this.container.querySelector('#zoomIn') as HTMLButtonElement
    const zoomOutBtn = this.container.querySelector('#zoomOut') as HTMLButtonElement
    const textLayer = this.container.querySelector('#textLayer') as HTMLDivElement

    if (prevBtn) {
      prevBtn.addEventListener('click', () => this.previousPage())
    }

    if (nextBtn) {
      nextBtn.addEventListener('click', () => this.nextPage())
    }

    if (zoomInBtn) {
      zoomInBtn.addEventListener('click', () => this.zoomIn())
    }

    if (zoomOutBtn) {
      zoomOutBtn.addEventListener('click', () => this.zoomOut())
    }

    // Text selection handler
    if (textLayer) {
      textLayer.addEventListener('mouseup', () => {
        const selection = window.getSelection()
        if (selection && selection.toString().trim().length > 0) {
          const selectedText = selection.toString().trim()
          if (this.onTextSelected) {
            this.onTextSelected(selectedText, this.currentPage)
          }
        }
      })
    }
  }

  private async renderPage(pageNumber: number): Promise<void> {
    if (!this.pdf) return

    try {
      const page = await this.pdf.getPage(pageNumber)
      
      const canvas = this.container.querySelector('#pdfCanvas') as HTMLCanvasElement
      const textLayer = this.container.querySelector('#textLayer') as HTMLDivElement
      
      if (!canvas || !textLayer) return

      const context = canvas.getContext('2d')
      if (!context) return

      const viewport = page.getViewport({ scale: this.scale })

      // Set canvas dimensions
      canvas.height = viewport.height
      canvas.width = viewport.width

      // Set text layer dimensions
      textLayer.style.width = `${viewport.width}px`
      textLayer.style.height = `${viewport.height}px`

      // Render PDF page
      const renderContext = {
        canvasContext: context,
        viewport: viewport
      }
      await page.render(renderContext).promise

      // Render text layer for selection
      await this.renderTextLayer(page, viewport, textLayer)

      this.currentPage = pageNumber
      this.updatePageInfo()
    } catch (error) {
      console.error('Error rendering page:', error)
      if (this.onError) {
        this.onError(error instanceof Error ? error : new Error('Failed to render page'))
      }
    }
  }

  private async renderTextLayer(
    page: any,
    viewport: any,
    container: HTMLDivElement
  ): Promise<void> {
    // Clear existing text layer
    container.innerHTML = ''

    try {
      // Use PDF.js built-in text layer renderer for proper metrics and selection
      const textContent = await page.getTextContent({ disableCombineTextItems: false })
      const renderTask = pdfjsLib.renderTextLayer({
        textContent,
        container,
        viewport,
        textDivs: [],
        enhanceTextSelection: true
      })
      if (renderTask && renderTask.promise) {
        await renderTask.promise
      }

      // Make the glyphs barely visible but keep native selection highlight fully visible
      // We avoid forcing a font family or manual transforms to preserve accurate positioning
      container.style.opacity = '0.2'
      container.style.userSelect = 'text'
    } catch (error) {
      console.error('Error rendering text layer:', error)
    }
  }

  private updatePageInfo(): void {
    if (!this.pdf) return

    const pageInfo = this.container.querySelector('#pageInfo')
    if (pageInfo) {
      pageInfo.textContent = `Page ${this.currentPage} of ${this.pdf.numPages}`
    }
  }

  private async previousPage(): Promise<void> {
    if (this.currentPage > 1) {
      await this.renderPage(this.currentPage - 1)
    }
  }

  private async nextPage(): Promise<void> {
    if (this.pdf && this.currentPage < this.pdf.numPages) {
      await this.renderPage(this.currentPage + 1)
    }
  }

  private async zoomIn(): Promise<void> {
    this.scale = Math.min(this.scale + 0.25, 3.0)
    await this.renderPage(this.currentPage)
  }

  private async zoomOut(): Promise<void> {
    this.scale = Math.max(this.scale - 0.25, 0.5)
    await this.renderPage(this.currentPage)
  }

  destroy(): void {
    this.container.innerHTML = ''
    this.pdf = null
  }
}
