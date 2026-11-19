const { app, BrowserWindow, Menu, ipcMain, session, desktopCapturer } = require('electron');
const path = require('node:path');
const { googleSearch, googleNavigation } = require('./google.cjs');

const childMode = process.argv.includes('--child') || /ogkchild/i.test(path.basename(process.execPath));
const server = new URL(process.env.OGK_SERVER_URL || 'http://127.0.0.1:8000');
if (server.protocol !== 'https:' && server.origin !== 'http://127.0.0.1:8000') {
    throw new Error('OGK_SERVER_URL must use HTTPS for a remote server.');
}
const origin = server.origin;
const wsOrigin = origin.replace(/^http/, 'ws');
const entry = origin + (childMode ? '/child' : '/');
let mainWindow;
let googleWindow;
let approvedSearch;

function configureGoogle() {
    const isolated = session.fromPartition('ogk-google');
    isolated.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
    isolated.setPermissionCheckHandler(() => false);
    isolated.on('will-download', event => event.preventDefault());
    isolated.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, done) => {
        if (details.resourceType === 'mainFrame') {
            const allowed = googleNavigation(details.url);
            if (!allowed) return done({ cancel: true });
            const query = allowed.searchParams.get('q') ?? '';
            if (query !== approvedSearch) {
                done({ cancel: true });
                if (query && mainWindow && !mainWindow.isDestroyed()) {
                    mainWindow.webContents.send('ogk:google-search-attempt', query);
                }
                return;
            }
            return done(allowed.href === details.url ? {} : { redirectURL: allowed.href });
        }
        const url = new URL(details.url);
        const assets = ['www.google.com', 'www.gstatic.com', 'fonts.gstatic.com', 'fonts.googleapis.com'];
        return done({ cancel: url.protocol !== 'https:' || !assets.includes(url.hostname) });
    });
    return isolated;
}

function openGoogle(query, isolated) {
    if (!googleWindow || googleWindow.isDestroyed()) {
        googleWindow = new BrowserWindow({
            parent: mainWindow,
            title: 'OGK · Google Tìm kiếm',
            width: 1024,
            height: 700,
            minimizable: false,
            webPreferences: { session: isolated, sandbox: true, devTools: false },
        });
        googleWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
        googleWindow.on('closed', () => { googleWindow = null; });
    }
    approvedSearch = query;
    googleWindow.loadURL(googleSearch(query).href).catch(() => {});
}

app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    const childSession = childMode ? session.fromPartition('ogk-child') : null;
    mainWindow = new BrowserWindow({
        title: childMode ? 'OGK Trẻ em' : 'OGK Phụ huynh',
        width: 1280,
        height: 850,
        kiosk: childMode,
        webPreferences: {
            sandbox: true,
            contextIsolation: true,
            devTools: !childMode,
            ...(childMode ? {
                session: childSession,
                preload: path.join(__dirname, 'preload.cjs'),
            } : {}),
        },
    });
    mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    mainWindow.webContents.on('will-navigate', (event, url) => {
        if (url !== entry) event.preventDefault();
    });
    mainWindow.webContents.on('will-redirect', (event, url) => {
        if (url !== entry) event.preventDefault();
    });

    if (childMode) {
        const isolated = configureGoogle();
        const trusted = event => event.sender === mainWindow.webContents &&
            event.senderFrame === mainWindow.webContents.mainFrame &&
            event.senderFrame.url === entry;
        ipcMain.on('ogk:google-search', (event, query) => {
            if (trusted(event) && typeof query === 'string' && query.length <= 500) openGoogle(query, isolated);
        });
        ipcMain.on('ogk:google-close', event => {
            if (trusted(event) && googleWindow && !googleWindow.isDestroyed()) googleWindow.close();
        });
        childSession.on('will-download', event => event.preventDefault());
        childSession.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, done) => {
            const url = new URL(details.url);
            const localPage = url.origin === origin && (
                url.pathname === '/child' || url.pathname.startsWith('/static/') ||
                /^\/(?:policy|web-usage|api\/auth\/status)\/\d+$/.test(url.pathname) ||
                ['/api/access-log', '/events/', '/api/settings/verify-pin', '/requests/'].includes(url.pathname)
            );
            const childSocket = url.origin === wsOrigin && url.pathname.startsWith('/ws/child/');
            const styles = url.origin === 'https://cdn.tailwindcss.com' && details.resourceType === 'script';
            done({ cancel: !(localPage || childSocket || styles) });
        });
        childSession.setDisplayMediaRequestHandler(async (request, callback) => {
            try {
                if (request.frame !== mainWindow.webContents.mainFrame || !request.userGesture) {
                    return callback({});
                }
                const sources = await desktopCapturer.getSources({ types: ['window'] });
                const source = sources.find(item => item.id === mainWindow.getMediaSourceId());
                callback(source ? { video: source } : {});
            } catch (_) {
                callback({});
            }
        });
    }

    mainWindow.loadURL(entry).catch(() => {
        mainWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(
            '<h2>OGK chưa kết nối được với server</h2><p>Hãy khởi động server OGK rồi mở lại ứng dụng.</p>'
        ));
    });
});

app.on('window-all-closed', () => app.quit());
