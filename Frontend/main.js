const { app, BrowserWindow } = require('electron')
const path = require('path')

function createWindow() {
  const win = new BrowserWindow({
    width: 900,
    height: 640,
    icon: path.join(__dirname, 'assets/outline-1.ico'), // Add your icon file here
    // Start maximized instead of true fullscreen so window controls remain visible
    // and the user can still resize the window. On macOS `fullscreenable: false`
    // prevents entering native fullscreen when the green traffic light is clicked.
    fullscreenable: false,
    resizable: true,
    autoHideMenuBar: true, // Hide the menu bar (File, Edit, View, etc.)
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      webSecurity: true,
    },
  })

  // Maximize the window on startup (fills the screen but keeps titlebar & controls)
  win.maximize()

  // Open DevTools for debugging
  win.webContents.openDevTools()

  win.loadFile(path.join(__dirname, 'index.html'))
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})
