# Frontend (Electron)

This is a small, intentionally simple Electron frontend scaffold for the GenHat project.

How to run

1. Open a terminal and change into the `Frontend` folder:

```powershell
cd Frontend
```

2. Install dependencies (one-time):

```powershell
npm install
```

3. Start the Electron app:

```powershell
npm start
```

What you get

- An Electron main process (`main.js`) that creates a BrowserWindow and opens devtools.
- A renderer page (`index.html`) and a small renderer script (`index.js`) with a demo button.

Next steps (suggestions)

- Add IPC handlers to communicate between main and renderer.
- Replace `nodeIntegration: true` + `contextIsolation: false` with a secure preload script and enable `contextIsolation` for production.
- Add bundling (Vite/webpack) and hot reload for faster development.
