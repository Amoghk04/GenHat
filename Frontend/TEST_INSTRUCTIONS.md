# Testing Instructions for GenHat

## The Issue That Was Fixed

The problem was a **timing issue** with ES modules:
- ES modules load asynchronously
- By the time the module loaded, `DOMContentLoaded` event had already fired
- This meant the event listeners were never attached
- Result: Chat input and file uploads didn't work

## The Solution

Changed the code to check `document.readyState`:
- If DOM is still loading → wait for `DOMContentLoaded`
- If DOM is already loaded → run initialization immediately

This ensures the app always initializes correctly regardless of module loading timing.

## How to Test

### 1. **Backend Must Be Running**
```bash
cd /home/amogh/Documents/7thsem/genAI/GenHat/Backend
python3 app.py
```
Verify it's running: Open browser to http://localhost:8080/api/ → should see `{"message":"DocumInt Backend API"}`

### 2. **Start Frontend** (Already running)
The app should already be open. If not:
```bash
cd /home/amogh/Documents/7thsem/genAI/GenHat/Frontend
./node_modules/.bin/electron .
```

### 3. **Test File Upload**
1. Click the **+** button in the Files sidebar
2. Select one or more PDF files
3. You should see messages in the chat:
   - ✅ "📄 Uploaded X file(s) successfully!"
   - ✅ "📤 Sending PDFs to backend for processing..."
   - ✅ "⏳ Building document index..."
   - ✅ "✅ Documents are ready!"
4. Files should appear in the sidebar with thumbnails

### 4. **Test Chat**
1. Type a question in the chat input box (e.g., "Summarize the main topics")
2. Press Enter or click Send
3. You should see:
   - Your message appears on the right (blue bubble)
   - "🤔 Analyzing your documents..." appears
   - AI response appears on the left (gray bubble)
   - Metadata about analysis appears

### 5. **Test PDF Viewer**
1. Click on a file card in the sidebar
2. PDF should open in a popup modal
3. Try selecting text in the PDF
4. Selected text should trigger AI analysis

### 6. **Check Console** (Open DevTools with Ctrl+Shift+I)
You should see:
```
🎩 GenHat renderer starting...
✅ All DOM elements found
```

If you see errors, they will appear here.

## Common Issues

### "Missing script: start" Error
**Solution:** Use the direct electron command:
```bash
cd /home/amogh/Documents/7thsem/genAI/GenHat/Frontend
./node_modules/.bin/electron .
```

### Backend Connection Failed
**Solution:** Make sure backend is running on port 8080:
```bash
cd Backend
python3 app.py
```

### Chat Not Responding
1. Open DevTools (Ctrl+Shift+I)
2. Check Console for errors
3. Check Network tab to see if API calls are being made
4. Verify backend is responding: `curl http://localhost:8080/api/`

### Files Not Uploading
1. Check console for "📄 Uploaded..." message
2. If you see "⚠️ Failed to process PDFs" → backend issue
3. Check backend logs for errors
4. Make sure you set GEMINI_API_KEY in Backend/.env

## What Changed in the Code

**Frontend/src/renderer.ts:**
```typescript
// BEFORE (didn't work reliably):
document.addEventListener('DOMContentLoaded', () => {
  // initialization code
})

// AFTER (works every time):
function initializeApp() {
  // initialization code
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeApp)
} else {
  initializeApp() // Run immediately if DOM already loaded
}
```

This ensures the initialization runs whether the DOM is ready or still loading.

## Expected Behavior

✅ **Working:**
- File upload button responds
- Chat input accepts text
- Send button works
- Backend processes PDFs
- AI responds to queries
- PDF viewer opens when clicking files

❌ **Not Working (Expected):**
- Mind Map feature (not implemented yet)
- Podcast feature (not implemented yet)
- More menu (not implemented yet)

## Next Steps After Verification

Once you confirm everything is working:

1. **Remove DevTools auto-open** (optional, for production)
   Edit `main.js`, remove this line:
   ```javascript
   mainWindow.webContents.openDevTools()
   ```

2. **Test full workflow:**
   - Upload multiple PDFs
   - Ask various questions
   - Select text in different PDFs
   - Verify responses are accurate

3. **Set up Gemini API key** (if not done):
   ```bash
   cd Backend
   echo "GEMINI_API_KEY=your_api_key_here" >> .env
   ```

4. **Check backend logs** for any errors or warnings

## Debugging Commands

```bash
# Check if backend is running
curl http://localhost:8080/api/

# Check for Electron processes
ps aux | grep electron

# View backend logs (if running in terminal)
cd Backend && python3 app.py

# Rebuild frontend TypeScript
cd Frontend && npm run build

# Check compiled JavaScript
ls -lh Frontend/dist/
```
