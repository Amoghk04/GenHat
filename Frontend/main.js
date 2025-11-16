const { app, BrowserWindow } = require('electron')
const path = require('path')

function createWindow() {
  const win = new BrowserWindow({
    width: 900,
    height: 640,
    // Start maximized instead of true fullscreen so window controls remain visible
    // and the user can still resize the window. On macOS `fullscreenable: false`
    // prevents entering native fullscreen when the green traffic light is clicked.
    fullscreenable: false,
    resizable: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  })

  // Maximize the window on startup (fills the screen but keeps titlebar & controls)
  win.maximize()

  win.loadFile(path.join(__dirname, 'index.html'))
  // Open devtools for initial development. Remove in production.
  win.webContents.openDevTools()
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})
