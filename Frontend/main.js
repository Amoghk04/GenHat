const { app, BrowserWindow, ipcMain, dialog } = require('electron')
const path = require('path')
const fs = require('fs')
const AdmZip = require('adm-zip')
const os = require('os')

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
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      webSecurity: true,
    },
  })

  // Maximize the window on startup (fills the screen but keeps titlebar & controls)
  win.maximize()

  win.loadFile(path.join(__dirname, 'index.html'))
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})

// IPC Handlers for File Operations
ipcMain.handle('dialog:openFile', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [{ name: 'GenHat Projects', extensions: ['genhat'] }]
  })
  if (canceled) {
    return null
  } else {
    try {
      const zip = new AdmZip(filePaths[0])
      
      // Read project.json directly from zip buffer
      const projectJsonEntry = zip.getEntry('project.json')
      if (projectJsonEntry) {
        const content = projectJsonEntry.getData().toString('utf8')
        const projectData = JSON.parse(content)
        return projectData
      }
      return null
    } catch (error) {
      console.error('Failed to read project file:', error)
      return null
    }
  }
})

ipcMain.handle('file:save', async (event, content) => {
  const { canceled, filePath } = await dialog.showSaveDialog({
    filters: [{ name: 'GenHat Projects', extensions: ['genhat'] }]
  })
  if (canceled) {
    return false
  } else {
    try {
      const zip = new AdmZip()
      
      // Add the JSON content (which now includes embedded file data)
      zip.addFile('project.json', Buffer.from(JSON.stringify(content, null, 2), 'utf8'))

      // Write zip to disk
      zip.writeZip(filePath)
      return true
    } catch (error) {
      console.error('Failed to save file:', error)
      return false
    }
  }
})

ipcMain.handle('file:read', async (event, filePath) => {
  console.log('[Main] Request to read file:', filePath)
  try {
    if (fs.existsSync(filePath)) {
      console.log('[Main] File exists, reading...')
      return await fs.promises.readFile(filePath)
    }
    console.log('[Main] File does not exist')
    return null
  } catch (error) {
    console.error('Failed to read file:', error)
    return null
  }
})
