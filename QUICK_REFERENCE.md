# GenHat Quick Reference

## 🚀 Quick Start

```bash
# First time setup
./setup.sh

# Edit Backend/.env with your API keys
# VITE_GEMINI_API_KEY=your_key_here

# Run both (requires tmux)
./run.sh both

# Or run separately in two terminals:
./run.sh backend   # Terminal 1
./run.sh frontend  # Terminal 2
```

## 📋 Common Commands

### Backend
```bash
cd Backend
source .venv/bin/activate
python app.py                           # Start server
uvicorn app:app --reload --port 8080   # Dev mode with reload
```

### Frontend
```bash
cd Frontend
npm install          # Install dependencies
npm run build        # Compile TypeScript
npm start            # Start Electron app
npm run dev          # Watch mode for TS
```

## 🔑 Environment Variables

Create `Backend/.env`:
```env
DOCUMINT_DATA_DIR=./data/projects
VITE_GEMINI_API_KEY=your_gemini_api_key
SPEECH_API_KEY=your_azure_key         # Optional
SPEECH_REGION=your_azure_region       # Optional
```

## 🎯 Features Overview

| Feature | Description | How to Use |
|---------|-------------|------------|
| **Upload PDFs** | Add documents to analyze | Click "+" button, select PDFs |
| **AI Chat** | Ask questions about docs | Type in chat, press Enter |
| **Text Selection** | Analyze specific text | Open PDF, select text |
| **Page Navigation** | Browse PDF pages | Use ◀ ▶ buttons |
| **Zoom** | Adjust PDF view | Use + − buttons |

## 🌐 API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/cache-pdfs` | POST | Upload and cache PDFs |
| `/cache-status/{key}` | GET | Check processing status |
| `/analyze-chunks-with-gemini` | POST | AI analysis |
| `/query-pdfs` | POST | Query documents |
| `/generate-podcast` | POST | Generate audio |

## 💡 Example Queries

```
"Summarize the key findings"
"What are the main recommendations?"
"Compare approaches across documents"
"Explain [topic] in simple terms"
"What did the authors conclude?"
```

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Backend won't start | Check Python version (3.10+), install dependencies |
| Frontend won't start | Run `npm install`, check Node version (16+) |
| No AI responses | Verify VITE_GEMINI_API_KEY in .env |
| PDF won't open | Check file is valid PDF, not corrupted |
| Text selection fails | Select more text (10+ chars), wait for processing |
| Connection refused | Ensure backend is running on port 8080 |

## 📊 Status Messages

| Message | Meaning |
|---------|---------|
| 📄 Uploaded N file(s) | Files added to list |
| 📤 Sending PDFs... | Uploading to backend |
| ⏳ Building index... | Creating search index |
| ✅ Documents ready! | Ready for queries |
| 🤔 Analyzing... | Processing request |
| ❌ Error: ... | Something failed |
| ⚠️ Warning: ... | Non-critical issue |

## 🔄 Workflow

```
1. Upload PDFs → 2. Wait for "Ready" → 3. Ask questions
                                      ↓
                              4. Open PDF viewer
                                      ↓
                              5. Select text
                                      ↓
                              6. Get AI insights
```

## 📂 Project Structure

```
GenHat/
├── Backend/          # FastAPI server
│   ├── app.py       # Main API
│   └── src/         # Processing modules
├── Frontend/        # Electron app
│   ├── src/         # TypeScript source
│   └── dist/        # Compiled JS
├── setup.sh         # Setup script
└── run.sh          # Run script
```

## 🔧 Configuration

**Change Backend URL** (Frontend/src/api.ts):
```typescript
const BACKEND_URL = 'http://localhost:8080'
```

**Change PDF Worker** (Frontend/src/pdfViewer.ts):
```typescript
workerSrc = './local/path/pdf.worker.min.js'
```

## 📖 Documentation

- `README.md` - Main documentation
- `Backend/README.md` - Backend API reference
- `Frontend/INTEGRATION.md` - Integration guide
- `IMPLEMENTATION_SUMMARY.md` - Technical details

## 🆘 Getting Help

1. Check documentation files
2. Review error messages in chat
3. Check backend logs (terminal)
4. Open browser DevTools (View → Toggle Developer Tools)
5. Review GitHub issues

## 💻 Development Tips

- Use `npm run dev` for hot reload
- Check Console tab in DevTools for errors
- Backend logs show detailed API activity
- Test with small PDFs first
- Keep backend and frontend logs visible

## 🎨 UI Elements

- **Sidebar**: File list with cards
- **Chat**: Main interaction area
- **Radial Menu**: Access features (top-right)
- **Popup**: Modal for PDF viewer and options

## ⌨️ Keyboard Shortcuts

- `Enter` - Send chat message
- `Esc` - Close popup (when focused)

## 📊 Performance

- **Upload Speed**: ~1-2 sec per MB
- **Index Build**: ~5-10 sec for 100 pages
- **Analysis Time**: ~3-5 sec per query
- **PDF Render**: Near instant for normal docs

## 🔒 Security Notes

- API keys stored server-side only
- Files processed locally, not sent to third parties
- Gemini API calls from backend only
- No data persistence by default

## 📱 Platform Support

- ✅ Linux
- ✅ Windows (with WSL or native)
- ✅ macOS

---

**Last Updated**: November 18, 2025
**Version**: 1.0.0
