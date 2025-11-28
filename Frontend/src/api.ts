// API service for backend communication
// Base URL can be configured via environment or hardcoded

const BACKEND_URL = 'http://localhost:8080'

export interface CachePDFsResponse {
  cache_key: string
  message: string
  pdf_count: number
  project_name: string
  reused: boolean
  empty?: boolean
}

export interface CacheStatusResponse {
  ready: boolean
  chunk_count?: number
  pdf_files?: string[]
  domain?: string
  project_name?: string
  file_progress?: Record<string, {
    index: number
    progress: number
    status: 'pending' | 'processing' | 'completed' | 'error'
    total_files: number
    error?: string
  }>
  processing?: boolean
}

export interface QueryPDFsResponse {
  metadata: {
    input_documents: string[]
    persona: string
    job_to_be_done: string
    domain: string
  }
  extracted_sections: Array<{
    document: string
    section_title: string
    refined_text: string
    page_number: number
    importance_rank: number
    bm25_score: number
    embedding_score: number
  }>
  subsection_analysis: Array<{
    document: string
    refined_text: string
    page_number: number
  }>
}

export interface AnalyzeChunksResponse {
  metadata: {
    input_documents: string[]
    persona: string
    job_to_be_done: string
    domain: string
    total_chunks_found: number
    chunks_analyzed: number
    gemini_model: string
    project_name: string
  }
  retrieval_results: Array<{
    document: string
    section_title: string
    content: string
    page_number: number
    hybrid_score: number
    bm25_score: number
    embedding_score: number
  }>
  gemini_analysis: Array<{
    chunk_index: number
    combined: boolean
    included_chunk_count: number
    included_sections: Array<{
      index: number
      document: string
      section_title: string
      page_number: number
      hybrid_score: number
      bm25_score: number
      embedding_score: number
    }>
    gemini_analysis: string
    analysis_timestamp: number
  }>
  summary: {
    top_insights: string[]
  }
  insight_id: string
}

export interface PodcastFromPromptResponse {
  insight_id: string
  title: string
  script: string
  analysis: string
  audio_url: string | null
  retrieved_chunk_count: number
  project_name: string
  persona: string
  prompt: string
  domain: string
}

/**
 * Generate podcast from prompt (retrieval + analysis + script + TTS)
 */
export async function podcastFromPrompt(
  projectName: string,
  prompt: string,
  k: number = 5,
  persona: string = 'Podcast Host'
): Promise<PodcastFromPromptResponse> {
  const payload = {
    project_name: projectName,
    prompt,
    k,
    persona
  }
  const response = await fetch(`${BACKEND_URL}/podcast-from-prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!response.ok) {
    const err = await response.text()
    throw new Error(`Failed to generate podcast: ${err}`)
  }
  return response.json()
}

/**
 * Upload PDFs to backend and get a cache key
 */
export async function cachePDFs(files: File[], projectName: string = ''): Promise<CachePDFsResponse> {
  const formData = new FormData()
  
  if (projectName) {
    formData.append('project_name', projectName)
  }
  
  for (const file of files) {
    formData.append('files', file)
  }

  const response = await fetch(`${BACKEND_URL}/cache-pdfs`, {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to cache PDFs: ${error}`)
  }

  return response.json()
}

/**
 * Check if the PDF cache is ready for querying
 */
export async function checkCacheStatus(cacheKey: string): Promise<CacheStatusResponse> {
  const response = await fetch(`${BACKEND_URL}/cache-status/${cacheKey}`)

  if (!response.ok) {
    throw new Error('Failed to check cache status')
  }

  return response.json()
}

/**
 * Query PDFs with a persona and task
 */
export async function queryPDFs(
  cacheKey: string,
  persona: string,
  task: string,
  k: number = 5
): Promise<QueryPDFsResponse> {
  const formData = new FormData()
  formData.append('cache_key', cacheKey)
  formData.append('persona', persona)
  formData.append('task', task)
  formData.append('k', k.toString())

  const response = await fetch(`${BACKEND_URL}/query-pdfs`, {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to query PDFs: ${error}`)
  }

  return response.json()
}

/**
 * Analyze chunks with Gemini AI
 */
export async function analyzeChunksWithGemini(
  cacheKey: string,
  persona: string,
  task: string,
  k: number = 5,
  maxChunksToAnalyze: number = 5,
  analysisPrompt?: string,
  geminiModel: string = 'gemini-2.5-flash'
): Promise<AnalyzeChunksResponse> {
  const formData = new FormData()
  formData.append('cache_key', cacheKey)
  formData.append('persona', persona)
  formData.append('task', task)
  formData.append('k', k.toString())
  formData.append('max_chunks_to_analyze', maxChunksToAnalyze.toString())
  formData.append('gemini_model', geminiModel)
  
  if (analysisPrompt) {
    formData.append('analysis_prompt', analysisPrompt)
  }

  const response = await fetch(`${BACKEND_URL}/analyze-chunks-with-gemini`, {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to analyze chunks: ${error}`)
  }

  return response.json()
}

/**
 * Poll cache status until ready, with progress callback
 */
export async function waitForCacheReadyWithProgress(
  cacheKey: string,
  onProgress?: (status: CacheStatusResponse) => void,
  maxAttempts: number = 60,
  intervalMs: number = 1000
): Promise<CacheStatusResponse> {
  for (let i = 0; i < maxAttempts; i++) {
    const status = await checkCacheStatus(cacheKey)
    
    // Call progress callback if provided
    if (onProgress) {
      onProgress(status)
    }
    
    if (status.ready) {
      return status
    }
    
    // Wait before next attempt
    await new Promise(resolve => setTimeout(resolve, intervalMs))
  }
  
  throw new Error('Cache preparation timed out')
}

export interface RemovePDFResponse {
  cache_key: string
  message: string
  removed: boolean
  remaining_pdfs: number
  remaining_chunks?: number
}

/**
 * Remove a PDF from the project and recompute embeddings
 */
export async function removePDF(
  projectName: string,
  filename: string
): Promise<RemovePDFResponse> {
  const formData = new FormData()
  formData.append('project_name', projectName)
  formData.append('filename', filename)

  const response = await fetch(`${BACKEND_URL}/remove-pdf`, {
    method: 'POST',
    body: formData
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to remove PDF: ${error}`)
  }

  return response.json()
}

/**
 * Export project cache (embeddings, chunks, meta, prompt cache)
 */
export interface ExportProjectCacheResponse {
  project_name: string
  meta: Record<string, any>
  chunks: Array<Record<string, any>>
  embeddings: {
    chunk_ids: string[]
    embeddings: number[][]
    model_name: string
  } | null
  prompt_cache: Array<{
    hash: string
    prompt: string
    response: string
    context: Record<string, any>
    metadata: Record<string, any>
    created_at: string
  }>
  export_timestamp: string
}

export async function exportProjectCache(projectName: string): Promise<ExportProjectCacheResponse> {
  const response = await fetch(`${BACKEND_URL}/export-project-cache/${encodeURIComponent(projectName)}`)

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to export project cache: ${error}`)
  }

  return response.json()
}

/**
 * Import project cache (embeddings, chunks, meta, prompt cache)
 */
export interface ImportProjectCacheRequest {
  project_name: string
  meta: Record<string, any>
  chunks: Array<Record<string, any>>
  embeddings?: {
    chunk_ids: string[]
    embeddings: number[][]
    model_name: string
  } | null
  prompt_cache?: Array<{
    hash: string
    prompt: string
    response: string
    context: Record<string, any>
    metadata: Record<string, any>
    created_at: string
  }>
}

export interface ImportProjectCacheResponse {
  cache_key: string
  project_name: string
  message: string
  chunk_count: number
  embeddings_restored: boolean
  prompt_cache_restored: number
}

export async function importProjectCache(data: ImportProjectCacheRequest): Promise<ImportProjectCacheResponse> {
  const response = await fetch(`${BACKEND_URL}/import-project-cache`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Failed to import project cache: ${error}`)
  }

  return response.json()
}

