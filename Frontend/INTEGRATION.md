# Frontend Integration Guide

## Overview

The GenHat frontend has been enhanced with backend integration for AI-powered document analysis using Gemini API and PDF text selection capabilities.

## New Features

### 1. Backend API Integration
- Automatic PDF upload to backend on file selection
- Document caching and indexing with hybrid retrieval (BM25 + embeddings)
- Real-time chat with Gemini AI for document analysis
- Project-based session management

### 2. PDF Text Selection Analysis
- Interactive PDF viewer powered by PDF.js
- Select text in PDFs to trigger focused AI analysis
- Page navigation and zoom controls
- Text layer for seamless selection

### 3. Smart Chat Interface
- Context-aware responses based on uploaded documents
- Automatic persona and task detection
- Formatted markdown responses from Gemini
- Processing status indicators

## Setup Instructions

### Prerequisites
- Node.js 16+ and npm
- Backend server running on `http://localhost:8080`
- Environment variables set in Backend (see Backend/README.md)

### Installation

1. Install dependencies:
```bash
cd Frontend
npm install
```

2. Build TypeScript:
```bash
npm run build
```

3. Start the application:
```bash
npm start
```

For development with auto-rebuild:
```bash
npm run dev
```

## File Structure

```
Frontend/
  src/
    renderer.ts       # Main UI logic with backend integration
    api.ts           # Backend API client functions
    pdfViewer.ts     # PDF.js viewer with text selection
  index.html         # Main HTML layout
  package.json       # Dependencies and scripts
  tsconfig.json      # TypeScript configuration
```

## How It Works

### PDF Upload Flow

1. User selects PDF files via the file input
2. Files are added to the local list and displayed
3. Files are automatically sent to backend `/cache-pdfs` endpoint
4. Backend processes PDFs (extracts headings, creates chunks, builds index)
5. Frontend polls `/cache-status/{cache_key}` until ready
6. User receives confirmation when documents are ready for queries

### Chat Analysis Flow

1. User types a question in the chat input
2. Frontend checks if documents are cached and ready
3. Question is sent to `/analyze-chunks-with-gemini` endpoint
4. Backend:
   - Performs hybrid search (BM25 + embeddings)
   - Retrieves top-k relevant chunks
   - Sends aggregated context to Gemini API
   - Returns structured analysis
5. Frontend displays formatted response with insights

### Text Selection Flow

1. User opens a PDF in the viewer popup
2. PDF.js renders the document with selectable text layer
3. User selects text (minimum 10 characters)
4. Selection triggers `handlePDFTextSelection()`
5. Backend analyzes the selected text with context from the full document
6. Analysis appears in the chat with the selected text highlighted

## API Endpoints Used

### POST /cache-pdfs
Upload and cache PDF files for a project.

**Request:**
- Form-data: `project_name` (optional), `files` (multiple PDFs)

**Response:**
```json
{
  "cache_key": "uuid",
  "project_name": "GenHat_Session_123",
  "pdf_count": 3,
  "reused": false
}
```

### GET /cache-status/{cache_key}
Check if PDF cache is ready for querying.

**Response:**
```json
{
  "ready": true,
  "chunk_count": 150,
  "pdf_files": ["doc1.pdf", "doc2.pdf"],
  "domain": "general"
}
```

### POST /analyze-chunks-with-gemini
Analyze documents with Gemini AI.

**Request:**
- Form-data: `cache_key`, `persona`, `task`, `k`, `max_chunks_to_analyze`

**Response:**
```json
{
  "metadata": {
    "persona": "General User",
    "job_to_be_done": "Summarize key points",
    "chunks_analyzed": 5,
    "gemini_model": "gemini-2.5-flash"
  },
  "gemini_analysis": [{
    "gemini_analysis": "## Key Insights\n\n...",
    "included_sections": [...]
  }],
  "insight_id": "abc123"
}
```

## Configuration

### Backend URL
By default, the frontend connects to `http://localhost:8080`. To change this, modify the `BACKEND_URL` constant in `src/api.ts`:

```typescript
const BACKEND_URL = 'http://your-backend-url:port'
```

### PDF.js Worker
The PDF.js worker is loaded from a CDN. For offline use, download the worker and update `src/pdfViewer.ts`:

```typescript
pdfjsLib.GlobalWorkerOptions.workerSrc = './path/to/pdf.worker.min.js'
```

## Troubleshooting

### Backend Connection Failed
- Ensure the backend server is running: `python Backend/app.py`
- Check that port 8080 is not blocked by firewall
- Verify environment variables are set (see Backend/README.md)

### PDF Viewer Not Loading
- Check browser console for PDF.js errors
- Ensure `pdfjs-dist` is installed: `npm install pdfjs-dist`
- Verify PDF file is not corrupted

### Gemini Analysis Not Working
- Confirm `VITE_GEMINI_API_KEY` is set in backend environment
- Check backend logs for API errors
- Ensure internet connection for Gemini API access

### Text Selection Not Triggering Analysis
- Select at least 10 characters of text
- Wait for documents to finish processing
- Check that cache_key is valid and ready

## Development Tips

### Hot Reload
Use `npm run dev` to watch TypeScript files and rebuild automatically.

### Debugging
1. Open Electron DevTools: View → Toggle Developer Tools
2. Check Console tab for errors
3. Network tab shows backend API calls

### Testing Backend Integration
1. Start backend: `cd Backend && python app.py`
2. Start frontend: `cd Frontend && npm start`
3. Upload a test PDF
4. Wait for "Documents are ready!" message
5. Type a question and verify Gemini response

## Example Usage

### Basic Document Query
1. Upload PDFs (e.g., research papers)
2. Wait for processing confirmation
3. Ask: "What are the main findings?"
4. Receive structured analysis with key insights

### Text Selection Analysis
1. Open a PDF from the file list
2. Select an interesting paragraph
3. AI automatically analyzes the selection
4. View contextual explanation in chat

### Multi-document Synthesis
1. Upload multiple related documents
2. Ask: "Compare the approaches across all documents"
3. Gemini synthesizes insights from all sources
4. Results include document references and page numbers

## Future Enhancements

- [ ] Voice input for queries
- [ ] Export analysis as PDF/Markdown
- [ ] Highlight relevant sections in PDF viewer
- [ ] Save and load analysis sessions
- [ ] Multi-language support
- [ ] Offline mode with cached embeddings

## License

See the repository's top-level `LICENSE` file.
