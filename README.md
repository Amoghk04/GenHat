# 🎩 GenHat - Document Intelligence Platform

A powerful AI-driven document intelligence engine that combines PDF analysis, hybrid retrieval (BM25 + embeddings), Gemini AI insights, and interactive PDF text selection for comprehensive document understanding.

## 🌟 Features

### Backend (FastAPI + Python)
- **PDF Processing**: Automatic outline extraction, heading detection, and content chunking
- **Hybrid Retrieval**: BM25 + sentence embeddings for accurate document search
- **Domain-Aware**: Optimized parameters for travel, research, business, culinary, and general domains
- **Gemini Integration**: AI-powered document analysis with context-aware insights
- **Podcast Generation**: Text-to-speech with Azure Cognitive Services
- **Project Persistence**: Multi-PDF project caching with deduplication
- **RESTful API**: Comprehensive endpoints for all document operations

### Frontend (Electron + TypeScript)
- **Interactive Chat**: Natural language queries powered by Gemini AI
- **PDF Viewer**: Full-featured viewer with text selection support
- **Text Selection Analysis**: Select text in PDFs to get instant AI analysis
- **File Management**: Upload multiple PDFs with visual cards
- **Real-time Processing**: Live status updates during document indexing
- **Responsive UI**: Dark theme with modern design

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 16+
- npm
- Gemini API key (for AI features)
- Azure Speech API key (optional, for podcasts)

### Installation

1. **Clone and setup:**
```bash
git clone https://github.com/Amoghk04/GenHat.git
cd GenHat
./setup.sh
```

2. **Configure environment variables:**
Edit `Backend/.env` and add your API keys:
```env
VITE_GEMINI_API_KEY=your_gemini_api_key
SPEECH_API_KEY=your_azure_speech_key
SPEECH_REGION=your_azure_region
```

3. **Run the application:**

**Option A: Both together (requires tmux)**
```bash
./run.sh both
```

**Option B: Separate terminals**

Terminal 1 (Backend):
```bash
./run.sh backend
```

Terminal 2 (Frontend):
```bash
./run.sh frontend
```

## 📖 Usage

### Basic Workflow

1. **Upload PDFs**: Click the "+" button in the sidebar to upload documents
2. **Wait for Processing**: Documents are automatically sent to backend and indexed
3. **Ask Questions**: Type natural language queries in the chat
4. **Get AI Insights**: Receive structured analysis from Gemini AI
5. **Select Text**: Open PDFs and select text to get focused explanations

### Example Queries

- "Summarize the key findings from all documents"
- "What are the main recommendations?"
- "Compare the methodologies across papers"
- "Explain the technical approach in simple terms"

### Text Selection Feature

1. Click any PDF file card to open the viewer
2. Use mouse to select text (minimum 10 characters)
3. AI automatically analyzes the selection with full document context
4. View insights in the chat window

## 🏗️ Architecture

```
┌─────────────────┐         ┌──────────────────┐
│   Frontend      │         │   Backend        │
│   (Electron)    │◄────────┤   (FastAPI)      │
│                 │  HTTP   │                  │
│  - PDF Viewer   │         │  - PDF Parser    │
│  - Chat UI      │         │  - Hybrid Search │
│  - File Manager │         │  - Gemini API    │
└─────────────────┘         └──────────────────┘
                                     │
                            ┌────────┴────────┐
                            │                 │
                      ┌─────▼────┐     ┌─────▼─────┐
                      │  Gemini  │     │   Azure   │
                      │   API    │     │  Speech   │
                      └──────────┘     └───────────┘
```

## 📁 Project Structure

```
GenHat/
├── Backend/
│   ├── app.py                    # FastAPI application
│   ├── pdf_extractor.py          # PDF outline extraction
│   ├── requirements.txt          # Python dependencies
│   ├── src/
│   │   ├── extract/              # Heading & chunking
│   │   ├── retrieval/            # Hybrid BM25+embeddings
│   │   ├── output/               # Formatters
│   │   └── utils/                # Utilities
│   └── README.md                 # Backend documentation
│
├── Frontend/
│   ├── src/
│   │   ├── renderer.ts           # Main UI logic
│   │   ├── api.ts                # Backend client
│   │   └── pdfViewer.ts          # PDF.js integration
│   ├── index.html                # Main HTML
│   ├── package.json              # Node dependencies
│   └── INTEGRATION.md            # Integration guide
│
├── setup.sh                      # Setup script
├── run.sh                        # Run script
└── README.md                     # This file
```

## 🔧 Configuration

### Backend Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DOCUMINT_DATA_DIR` | Base directory for persisted projects | No (default: `./data/projects`) |
| `DOCUMINT_FRONTEND_DIST` | Path to built frontend | No |
| `VITE_GEMINI_API_KEY` | Google Gemini API key | Yes (for AI) |
| `SPEECH_API_KEY` | Azure Speech API key | No (for podcasts) |
| `SPEECH_REGION` | Azure Speech region | No (for podcasts) |

### Frontend Configuration

Change backend URL in `Frontend/src/api.ts`:
```typescript
const BACKEND_URL = 'http://localhost:8080'
```

## 📚 Documentation

- **Backend API**: See [Backend/README.md](Backend/README.md)
- **Frontend Integration**: See [Frontend/INTEGRATION.md](Frontend/INTEGRATION.md)

## 🔌 API Endpoints

### Core Endpoints

- `POST /cache-pdfs` - Upload and cache PDFs
- `GET /cache-status/{cache_key}` - Check processing status
- `POST /query-pdfs` - Query documents with persona/task
- `POST /analyze-chunks-with-gemini` - AI analysis
- `POST /generate-podcast` - Generate podcast from insights
- `GET /projects/{project}/insights` - List saved insights

See Backend README for complete API documentation.

## 🛠️ Development

### Backend Development
```bash
cd Backend
source .venv/bin/activate
uvicorn app:app --reload --port 8080
```

### Frontend Development
```bash
cd Frontend
npm run dev  # Watch mode for TypeScript
npm start    # Run Electron app
```

### Building for Production
```bash
cd Frontend
npm run build
npm start
```

## 🐛 Troubleshooting

### Backend Connection Failed
- Ensure backend is running: `./run.sh backend`
- Check port 8080 is available
- Verify firewall settings

### PDF Viewer Not Working
- Install dependencies: `cd Frontend && npm install`
- Check browser console for errors
- Ensure PDF files are valid

### Gemini Analysis Fails
- Verify `VITE_GEMINI_API_KEY` is set correctly
- Check internet connection
- Review backend logs for API errors

### Text Selection Not Responding
- Select at least 10 characters
- Wait for "Documents are ready!" message
- Check that cache_key is valid

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

See [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **PDF.js** - Mozilla's PDF rendering library
- **FastAPI** - Modern Python web framework
- **Gemini API** - Google's generative AI
- **Sentence Transformers** - Embedding models
- **Azure Cognitive Services** - Text-to-speech

## 📧 Contact

For questions or support, please open an issue on GitHub.

---

**Note**: This is a mimic of Notebook LM with enhanced speed and features for GenAI Laboratory use.
