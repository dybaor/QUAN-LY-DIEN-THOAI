const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const { googleNavigation, googleSearch } = require('../desktop/google.cjs');

test('desktop Google verification returns only to filtered search', () => {
    const search = googleSearch('pythagorean theorem');
    const challenge = new URL('/sorry/index', search.origin);
    challenge.searchParams.set('continue', search.href);
    assert.equal(googleNavigation(challenge.href)?.href, challenge.href);
    challenge.searchParams.set('continue', 'https://example.com/search?safe=active&udm=14');
    assert.equal(googleNavigation(challenge.href), null);
    assert.equal(googleNavigation('https://www.google.com/url?q=https://example.com'), null);
    assert.equal(googleNavigation('https://example.com/'), null);
    assert.equal(googleNavigation('https://www.google.com/search?q=test&safe=off')?.searchParams.get('safe'), 'active');
});

const root = path.resolve(__dirname, '..');
const parentHtml = fs.readFileSync(path.join(root, 'server/templates/dashboard.html'), 'utf8');
const childHtml = fs.readFileSync(path.join(root, 'server/templates/child_portal.html'), 'utf8');
const parentScript = [...parentHtml.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
    .map(match => match[1]).sort((a, b) => b.length - a.length)[0];
const childScript = fs.readFileSync(path.join(root, 'server/static/js/child.js'), 'utf8');

// These DOM doubles exercise the production handlers without browser dependencies.
class Element {
    constructor(tag = 'div') {
        this.tagName = tag;
        this.value = '';
        this.innerText = '';
        this.innerHTML = '';
        this.className = '';
        this.style = {};
        this.dataset = {};
        this.children = [];
        this.listeners = {};
        this.attributes = {};
        this.disabled = false;
        this.classList = {
            add: (...names) => { this.className = [...new Set([...this.className.split(' '), ...names])].join(' '); },
            remove: (...names) => { this.className = this.className.split(' ').filter(name => !names.includes(name)).join(' '); },
            contains: name => this.className.split(' ').includes(name),
        };
    }
    appendChild(child) { this.children.push(child); }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
    querySelector(selector) {
        if (selector === '.launch-btn') return this.launchButton ||= new Element('button');
        return null;
    }
    click() { for (const listener of this.listeners.click || []) listener({ detail: 0, stopPropagation() {} }); }
    reportValidity() {
        return this.value !== '' && Number.isInteger(Number(this.value)) && Number(this.value) >= 0 && Number(this.value) <= 1440;
    }
    getContext() { return {}; }
}

function runtime(script, html, extra = {}) {
    const nodes = new Map();
    for (const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
        const element = new Element(match[1]);
        element.value = /\bvalue="([^"]*)"/.exec(match[2])?.[1] || '';
        element.className = /\bclass="([^"]*)"/.exec(match[2])?.[1] || '';
        nodes.set(match[3], element);
    }
    const errors = [];
    const context = vm.createContext({
        document: {
            getElementById: id => nodes.get(id) || null,
            createElement: tag => new Element(tag),
            addEventListener() {},
            querySelector: selector => selector === '.usage-card' ? nodes.get('overview') : null,
            querySelectorAll: () => [],
        },
        window: { addEventListener() {}, location: { protocol: 'http:', host: 'localhost', pathname: '/child/1' } },
        console: { log() {}, warn() {}, error: (...args) => errors.push(args) },
        setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {},
        Chart: class { destroy() {} },
        URL, URLSearchParams, Blob, Date, Option: class {},
        sessionStorage: { getItem: () => null, setItem() {} },
        fetch: async () => ({ ok: false, json: async () => ({}) }),
        ...extra,
    });
    vm.runInContext(fs.readFileSync(path.join(root, "server/static/js/time-timeline.js"), "utf8"), context);
    vm.runInContext(script, context);
    vm.runInContext('showToast = (...args) => { testToasts.push(args); }', Object.assign(context, { testToasts: [] }));
    return {
        nodes, errors, context,
        run: code => vm.runInContext(code, context),
        selectedDays(days) {
            context.document.querySelectorAll = selector => selector.includes('scheduleDay') ? days.map(day => ({ value: String(day) })) : [];
        },
        setPolicy(policy) {
            context.fetch = async () => ({ ok: true, json: async () => policy });
        },
    };
}

function parent() {
    const app = runtime(parentScript, parentHtml);
    app.run("currentChildId = 1; currentPolicy = { version: 1, blocked_domains: '', blocked_categories: 'games', daily_quota_weekday_min: 120, daily_quota_weekend_min: 180, schedule_matrix: '1'.repeat(336) }; selectedCategories = ['games'];");
    app.nodes.get('rangeStart').value = '44'; // 22:00 (khung 30 phút)
    app.nodes.get('rangeEnd').value = '12';   // 06:00
    app.nodes.get('rangeState').value = '0';
    return app;
}

function policy(matrix = '1'.repeat(336)) {
    return { version: 3, daily_quota_weekday_min: 120, daily_quota_weekend_min: 180, schedule_matrix: matrix, blocked_apps: '', blocked_domains: '', blocked_categories: 'games' };
}

test('weekly grid renders 336 keyboard-accessible half-hour slots and seven summaries', () => {
    const app = parent();
    app.run('initScheduleGrid()');
    const rows = app.nodes.get('scheduleMatrixGrid').children;
    assert.equal(rows.length, 7);
    assert.equal(rows.flatMap(row => row.children[1].children).length, 336);
    assert.match(rows[0].children[1].children[1].title, /00:30–01:00/);
    const cell = rows[0].children[1].children[0];
    assert.equal(cell.type, 'button');
    assert.equal(cell.attributes['aria-pressed'], 'true');
    cell.click();
    assert.equal(app.run('scheduleMatrixArray[0]'), '0');
    assert.equal(cell.attributes['aria-pressed'], 'false');
    assert.equal(app.run('scheduleDirty'), true);
    assert.match(app.nodes.get('scheduleSummary').innerHTML, /Giờ nghỉ/);
});

test('summary merges adjacent slots including 24:00', () => {
    const app = parent();
    app.run("scheduleMatrixArray = Array(336).fill('0'); renderScheduleSummary();");
    assert.equal((app.nodes.get('scheduleSummary').innerHTML.match(/00:00–24:00/g) || []).length, 7);
    assert.equal((app.nodes.get('scheduleSummary').innerHTML.match(/schedule-range rest/g) || []).length, 7);
});

test('daytime range changes only the selected days and hours', () => {
    const app = parent();
    app.selectedDays([0, 2]);
    app.nodes.get('rangeStart').value = '17'; // 08:30
    app.nodes.get('rangeEnd').value = '22';   // 11:00
    app.run('applyScheduleRange()');
    const actual = app.run("scheduleMatrixArray.map((state, index) => state === '0' ? index : -1).filter(index => index >= 0).join(',')");
    assert.equal(actual, '17,18,19,20,21,113,114,115,116,117');
});

test('overnight range extends to the next day', () => {
    const app = parent();
    app.selectedDays([0]);
    app.run('applyScheduleRange()');
    assert.equal(app.run("scheduleMatrixArray.slice(0, 12).join('')"), '1'.repeat(12));
    assert.equal(app.run("scheduleMatrixArray.slice(44, 60).join('')"), '0'.repeat(16));
    assert.equal(app.run('scheduleMatrixArray[60]'), '1');
});

test('Sunday overnight range wraps to Monday', () => {
    const app = parent();
    app.selectedDays([6]);
    app.run('applyScheduleRange()');
    assert.equal(app.run("scheduleMatrixArray.slice(332).join('')"), '0000');
    assert.equal(app.run("scheduleMatrixArray.slice(0, 12).join('')"), '0'.repeat(12));
    assert.equal(app.run("scheduleMatrixArray.slice(288, 300).join('')"), '1'.repeat(12));
});

test('range supports midnight to 24:00 for a full day', () => {
    const app = parent();
    app.selectedDays([3]);
    app.nodes.get('rangeStart').value = '0';
    app.nodes.get('rangeEnd').value = '48';
    app.run('applyScheduleRange()');
    assert.equal(app.run("scheduleMatrixArray.filter(state => state === '0').length"), 48);
});

test('range rejects an empty selection and equal endpoints', () => {
    const app = parent();
    app.selectedDays([]);
    app.run('applyScheduleRange()');
    app.selectedDays([0]);
    app.nodes.get('rangeEnd').value = '44';
    app.run('applyScheduleRange()');
    assert.equal(app.run('scheduleDirty'), false);
    assert.equal(app.context.testToasts.length, 2);
});

test('restoring allowed time keeps other restrictions intact', () => {
    const app = parent();
    app.run("scheduleMatrixArray.fill('0')");
    app.selectedDays([1]);
    app.nodes.get('rangeStart').value = '18';
    app.nodes.get('rangeEnd').value = '19';
    app.nodes.get('rangeState').value = '1';
    app.run('applyScheduleRange()');
    assert.equal(app.run("scheduleMatrixArray.filter(state => state === '1').length"), 1);
    assert.equal(app.run('scheduleMatrixArray[66]'), '1');
});

test('bedtime and school presets preserve restrictions in other periods', () => {
    const app = parent();
    app.run("scheduleMatrixArray[24] = '0'; setSchedulePreset('bedtime_lock'); setSchedulePreset('school_lock');");
    assert.equal(app.run('scheduleMatrixArray[24]'), '0');
    assert.equal(app.run('scheduleMatrixArray[16]'), '0');
    assert.equal(app.run('scheduleMatrixArray[5 * 48 + 16]'), '1');
    assert.equal(app.run('scheduleMatrixArray[6 * 48 + 47]'), '0');
});

test('policy load expands legacy hourly schedules to half-hour slots', async () => {
    const app = parent();
    app.setPolicy(policy('10'.repeat(84)));
    await app.run('loadPolicy()');
    assert.equal(app.errors.length, 0);
    assert.equal(app.run('scheduleMatrixArray.length'), 336);
    assert.equal(app.run("scheduleMatrixArray.slice(0, 8).join('')"), '11001100');
    assert.equal(app.nodes.get('weekdaySlider').disabled, false);
    assert.match(app.nodes.get('weekdayQuotaDisplay').innerText, /120/);
});

test('background policy reload preserves unsaved schedule and app edits', async () => {
    const app = parent();
    app.run("scheduleMatrixArray[2] = '0'; blockedAppsList = [{name: 'Game', hash: 'a'.repeat(64)}]; markScheduleDirty();");
    app.setPolicy(policy());
    await app.run('loadPolicy()');
    assert.equal(app.run('scheduleMatrixArray[2]'), '0');
    assert.equal(app.run('blockedAppsList[0].name'), 'Game');
});

test('saving sends the existing API schema and clears dirty state', async () => {
    const app = parent();
    const sent = [];
    app.context.fetch = async (url, options = {}) => {
        if (options.method === 'PUT') sent.push(JSON.parse(options.body));
        return { ok: true, json: async () => policy(sent[0]?.schedule_matrix) };
    };
    app.run("scheduleMatrixArray[1] = '0'; markScheduleDirty();");
    await app.run('saveScheduleMatrixOnly()');
    assert.equal(sent.length, 1);
    assert.equal(sent[0].schedule_matrix.length, 336);
    assert.equal(sent[0].schedule_matrix[1], '0');
    assert.equal(sent[0].child_id, 1);
    assert.equal(sent[0].blocked_categories, 'games');
    assert.equal(sent[0].daily_quota_weekday_min, 120);
    assert.equal(app.run('scheduleDirty'), false);
    assert.equal(app.nodes.get('saveScheduleButton').disabled, false);
    assert.equal(app.errors.length, 0);
});

test('failed save retains edits and can be retried', async () => {
    const app = parent();
    app.context.fetch = async () => { throw new Error('offline'); };
    app.run("scheduleMatrixArray[1] = '0'; markScheduleDirty();");
    await app.run('saveScheduleMatrixOnly()');
    assert.equal(app.run('scheduleDirty'), true);
    assert.equal(app.run('scheduleMatrixArray[1]'), '0');
    assert.equal(app.run('scheduleSaving'), false);
    assert.equal(app.nodes.get('saveScheduleButton').disabled, false);
    app.context.fetch = async () => ({ ok: true, json: async () => policy() });
    await app.run('saveScheduleMatrixOnly()');
    assert.equal(app.run('scheduleDirty'), false);
});

test('HTTP save failures retain dirty state', async () => {
    const app = parent();
    app.context.fetch = async () => ({ ok: false });
    app.run('markScheduleDirty()');
    await app.run('saveScheduleMatrixOnly()');
    assert.equal(app.run('scheduleDirty'), true);
    assert.equal(app.context.testToasts.at(-1)[1], 'error');
});

test('edits during an in-flight save survive the returned policy', async () => {
    const app = parent();
    let finish;
    app.context.fetch = (url, options = {}) => options.method === 'PUT'
        ? new Promise(resolve => { finish = resolve; })
        : Promise.resolve({ ok: true, json: async () => policy() });
    app.run('markScheduleDirty()');
    const saving = app.run('saveScheduleMatrixOnly()');
    app.run("scheduleMatrixArray[5] = '0'; markScheduleDirty();");
    finish({ ok: true });
    await saving;
    assert.equal(app.run('scheduleDirty'), true);
    assert.equal(app.run('scheduleMatrixArray[5]'), '0');
});

test('concurrent save clicks share one write', async () => {
    const app = parent();
    let finish;
    let writes = 0;
    app.context.fetch = (url, options = {}) => {
        if (options.method !== 'PUT') return Promise.resolve({ ok: true, json: async () => policy() });
        writes++;
        return new Promise(resolve => { finish = resolve; });
    };
    const first = app.run('saveScheduleMatrixOnly()');
    await app.run('applyAllPolicies()');
    assert.equal(writes, 1);
    finish({ ok: true });
    await first;
});

test('quota validation accepts 0 and 1440 and rejects empty, decimal, negative and over-limit values', () => {
    const app = parent();
    for (const value of ['0', '1440']) {
        app.nodes.get('weekdaySlider').value = value;
        assert.equal(app.run('validateQuotaInputs()'), true);
    }
    for (const value of ['', '-1', '1441', '1.5']) {
        app.nodes.get('weekdaySlider').value = value;
        assert.equal(app.run('validateQuotaInputs()'), false);
    }
});

test('unloaded policy cannot write an assumed schedule', async () => {
    const app = parent();
    app.run('currentPolicy = null');
    let writes = 0;
    app.context.fetch = async () => { writes++; return { ok: false }; };
    await app.run('saveScheduleMatrixOnly()');
    app.selectedDays([0]);
    app.run('applyScheduleRange()');
    assert.equal(writes, 0);
    assert.equal(app.run('scheduleDirty'), false);
});

test('usage card shows remaining minutes, including exhausted and zero quota', async () => {
    const app = parent();
    for (const [used, quota, remaining, level] of [[75, 120, 45, 'normal'], [110, 120, 10, 'low'], [140, 120, 0, 'empty'], [0, 0, 0, 'empty']]) {
        app.context.fetch = async () => ({ ok: true, json: async () => ({ today_minutes: used, quota_minutes: quota, weekly_labels: [], weekly_usage: [] }) });
        await app.run('loadDashboardStats()');
        assert.match(app.nodes.get('remainingTimeText').innerHTML, new RegExp(`^${remaining}<span>`));
        assert.equal(app.nodes.get('overview').dataset.level, level);
    }
    assert.equal(app.errors.length, 0);
});

test('monitor transitions preserve compact idle and expanded live state', () => {
    const app = parent();
    app.run('recordStartMonitoringSession = () => {}; setMonitorState("pending")');
    assert.equal(app.nodes.get('device').dataset.state, 'pending');
    app.run('setMonitorState("live")');
    assert.equal(app.nodes.get('liveScreenImg').classList.contains('hidden'), false);
    app.run('setMonitorState("idle")');
    assert.equal(app.nodes.get('device').dataset.state, 'idle');
    assert.equal(app.nodes.get('liveScreenImg').classList.contains('hidden'), true);
});

test('child portal has no Google app card: the app section stays hidden until an app is added', () => {
    const app = runtime(childScript, childHtml);
    assert.equal(app.run('APPS.length'), 0);
    app.run('renderApps()');
    assert.equal(app.nodes.get('appsSection').hidden, true);
    assert.equal(app.nodes.get('appGrid').children.length, 0);
    assert.doesNotMatch(childHtml, /Google Tìm kiếm\s*<\/h3>/);
    assert.doesNotMatch(childHtml, /Xin mở 15p/);
});

test('future apps still render, escape unmatched text and respect locking', () => {
    const app = runtime(childScript, childHtml);
    app.run("APPS.push({ id: 'demo', name: 'Máy tính', category: 'study', icon: '🧮', desc: 'Tính toán', url: 'https://example.org', type: 'web', allowed: true });");
    app.run('renderApps()');
    assert.equal(app.nodes.get('appsSection').hidden, false);
    assert.equal(app.nodes.get('appGrid').children[0].attributes['data-id'], 'demo');
    app.nodes.get('searchAppInput').value = '<img src=x onerror=alert(1)>';
    app.run('renderApps()');
    assert.doesNotMatch(app.nodes.get('appGrid').innerHTML, /<img/);
    assert.match(app.nodes.get('appGrid').innerHTML, /&lt;img/);
    app.nodes.get('searchAppInput').value = '';
    app.run('renderApps(); isLocked = true;');
    const card = app.nodes.get('appGrid').children[0];
    assert.match(card.launchButton.attributes['aria-label'], /Mở Máy tính/);
    card.launchButton.click();
    assert.match(app.context.testToasts.at(-1)[0], /đang bị khóa/);
    app.run('isLocked = false; isTimeExpired = true;');
    card.launchButton.click();
    assert.match(app.context.testToasts.at(-1)[0], /hết thời gian/);
});

test('search bar: forbidden keyword is blocked and reported to the parent, safe query opens SafeSearch', () => {
    const app = runtime(childScript, childHtml);
    const sent = [], opened = [], fetches = [];
    app.context.WebSocket = { OPEN: 1 };
    app.context.fetch = async url => { fetches.push(url); return { ok: true, json: async () => ({}) }; };
    app.run("childId = 1; waitingForSetup = false; remainingSeconds = 3600;");
    app.run("ws = { readyState: 1, send: data => sent.push(JSON.parse(data)) }; openInAppBrowser = (url, title) => opened.push(url);");
    app.context.sent = sent; app.context.opened = opened;
    const input = app.nodes.get('searchAppInput');
    input.value = 'phim sex';
    app.run('handleGoogleOrDomainSearch()');
    assert.deepEqual(opened, []);
    assert.equal(sent.length, 1);
    assert.equal(sent[0].action, 'violation_alert');
    assert.equal(sent[0].target_name, 'phim sex');
    assert.deepEqual(fetches, ['/api/child/access-log']);
    input.value = 'bài tập toán lớp 5';
    app.run('handleGoogleOrDomainSearch()');
    const url = new URL(opened[0]);
    assert.equal(url.origin + url.pathname, 'https://www.google.com/search');
    assert.equal(url.searchParams.get('safe'), 'active');
    assert.equal(url.searchParams.get('q'), 'bài tập toán lớp 5');
    assert.equal(sent.length, 1, 'tìm kiếm hợp lệ không được báo vi phạm');
});

test('search bar: names of domains the parent blocked count as forbidden keywords', () => {
    const app = runtime(childScript, childHtml);
    const sent = [], opened = [];
    app.context.WebSocket = { OPEN: 1 };
    app.context.fetch = async () => ({ ok: true, json: async () => ({}) });
    app.run("childId = 1; waitingForSetup = false; remainingSeconds = 3600; currentPolicy = { blocked_domains: 'tiktok.com, vi-du-game.com' };");
    app.run("ws = { readyState: 1, send: data => sent.push(JSON.parse(data)) }; openInAppBrowser = (url) => opened.push(url);");
    app.context.sent = sent; app.context.opened = opened;
    const input = app.nodes.get('searchAppInput');
    for (const query of ['xem tiktok', 'TikTok video', 'tải vi-du-game.com']) {
        input.value = query; app.run('handleGoogleOrDomainSearch()');
    }
    assert.equal(sent.length, 3);
    assert.deepEqual(opened, []);
    input.value = 'tik tok cho trẻ em'; // chỉ chứa từ rời, không phải tên miền đã chặn
    app.run('handleGoogleOrDomainSearch()');
    assert.equal(opened.length, 1);
});

test('child remaining-time display uses consistent warning colors', () => {
    const app = runtime(childScript, childHtml);
    for (const [seconds, color] of [[6000, '#0f766e'], [2000, '#f59e0b'], [300, '#f43f5e']]) {
        app.run(`remainingSeconds = ${seconds}; totalSeconds = 7200; updateTimeDisplay()`);
        assert.equal(app.nodes.get('timeProgressBar').style.background, color);
    }
});

test('blocked-app form adds, prevents duplicates, removes and marks edits', () => {
    const app = parent();
    app.nodes.get('appNameInput').value = 'Roblox';
    app.nodes.get('appHashInput').value = 'a'.repeat(64);
    app.run('addBlockedApp()');
    assert.equal(app.run('blockedAppsList.length'), 1);
    assert.equal(app.run('scheduleDirty'), true);
    assert.equal(app.nodes.get('exeFileInput').value, '');
    app.nodes.get('appHashInput').value = 'a'.repeat(64);
    app.run('addBlockedApp()');
    assert.equal(app.run('blockedAppsList.length'), 1);
    app.run('removeBlockedApp(0)');
    assert.equal(app.run('blockedAppsList.length'), 0);
    assert.match(app.nodes.get('blockedAppsTableBody').innerHTML, /Chưa có ứng dụng/);
});

test('saving a modified block list sends its name and hash', async () => {
    const app = parent();
    let payload;
    app.context.fetch = async (url, options = {}) => {
        if (options.method === 'PUT') payload = JSON.parse(options.body);
        return { ok: true, json: async () => ({ ...policy(), blocked_apps: payload?.blocked_apps || '' }) };
    };
    app.nodes.get('appNameInput').value = 'Game';
    app.nodes.get('appHashInput').value = 'b'.repeat(64);
    app.run('addBlockedApp()');
    await app.run('applyAllPolicies()');
    assert.deepEqual(JSON.parse(payload.blocked_apps), [{ name: 'Game', hash: 'b'.repeat(64) }]);
    assert.equal(app.run('scheduleDirty'), false);
});

test('legacy comma-separated blocked-app hashes still render', async () => {
    const app = parent();
    app.setPolicy({ ...policy(), blocked_apps: `${'a'.repeat(64)},${'b'.repeat(64)}` });
    await app.run('loadPolicy()');
    assert.equal(app.run('blockedAppsList.length'), 2);
    assert.match(app.nodes.get('blockedAppsTableBody').innerHTML, /aaaaaaaaaaaaaaaa/);
    assert.equal(app.errors.length, 0);
});

test('failed initial policy load leaves a useful connection status', async () => {
    const app = parent();
    app.run('currentPolicy = null');
    app.context.fetch = async () => ({ ok: false });
    await app.run('loadPolicy()');
    assert.equal(app.run('currentPolicy'), null);
    assert.match(app.nodes.get('scheduleSaveStatus').innerText, /Mất kết nối/);
});

test('pending requests show their reason and exclude completed requests', async () => {
    const app = parent();
    app.context.fetch = async () => ({ ok: true, json: async () => [
        { id: 1, status: 'pending', requested_minutes: 15, reason: '<b>Hoàn thành bài Toán</b>' },
        { id: 2, status: 'approved', requested_minutes: 30, reason: 'Đã duyệt trước đó' },
    ] });
    await app.run('loadRequests()');
    assert.equal(app.nodes.get('pendingRequestCountBadge').innerText, '1 chờ duyệt');
    assert.match(app.nodes.get('requestContainer').innerHTML, /&lt;b&gt;Hoàn thành bài Toán/);
    assert.doesNotMatch(app.nodes.get('requestContainer').innerHTML, /Đã duyệt trước đó/);
});

test('approval keeps the existing duration payload and refreshes the UI', async () => {
    const app = parent();
    let write;
    app.context.refreshes = [];
    app.run(`loadRequests = () => refreshes.push('requests');
        loadPolicy = () => refreshes.push('policy');
        loadDashboardStats = () => refreshes.push('stats');`);
    app.context.fetch = async (url, options) => {
        write = { url, method: options.method, body: JSON.parse(options.body) };
        return { ok: true, json: async () => ({ status: 'success' }) };
    };
    await app.run('approveRequest(7, 15)');
    assert.deepEqual(write, { url: '/requests/7/approve', method: 'POST', body: { duration_min: 15 } });
    assert.equal(app.context.refreshes.join(','), 'requests,policy,stats');
});

test('rejected requests refresh the request list', async () => {
    const app = parent();
    let requestedUrl;
    app.context.refreshCount = 0;
    app.run('loadRequests = () => { refreshCount++; };');
    app.context.fetch = async url => {
        requestedUrl = url;
        return { ok: true, json: async () => ({ status: 'success' }) };
    };
    await app.run('rejectRequest(7)');
    assert.equal(requestedUrl, '/requests/7/reject');
    assert.equal(app.context.refreshCount, 1);
});

test('child only opens filtered Google search and blocks external domains', () => {
    const app = runtime(childScript, childHtml);
    const searches = [];
    app.context.window.ogkDesktop = { searchGoogle: q => searches.push(q), closeGoogle() {} };
    const input = app.nodes.get('searchAppInput');
    app.run('waitingForSetup = false;');
    input.value = 'https://adult-content-sample.com';
    app.run('handleGoogleOrDomainSearch()');
    input.value = 'phim người lớn';
    app.run('handleGoogleOrDomainSearch()');
    assert.deepEqual(searches, []);
    input.value = 'bài tập toán lớp 5';
    app.run('handleGoogleOrDomainSearch()');
    assert.deepEqual(searches, ['bài tập toán lớp 5']);
});

test('parent immediately refreshes new requests and stops monitoring on child signal', () => {
    const app = parent();
    const sockets = [];
    app.context.WebSocket = class {
        constructor() { sockets.push(this); }
    };
    app.context.refreshCount = 0;
    app.run('loadRequests = () => refreshCount++; recordStartMonitoringSession = () => {}; recordStopMonitoringSession = () => {}; initParentWebSocket(); setMonitorState("live");');
    sockets[0].onmessage({ data: '{"cmd":"new_time_request","child_id":1}' });
    sockets[0].onmessage({ data: '{"cmd":"screen_share_stopped"}' });
    assert.equal(app.context.refreshCount, 1);
    assert.equal(app.nodes.get('device').dataset.state, 'idle');
    assert.equal(app.errors.length, 0);
});

for (const role of ['child', 'parent']) {
    test(`${role} chat renders a sent message once when the server echoes it`, async () => {
        const app = role === 'child' ? runtime(childScript, childHtml) : parent();
        const sockets = [];
        app.context.WebSocket = class {
            static OPEN = 1;
            constructor() { this.readyState = 1; this.sent = []; sockets.push(this); }
            send(data) { this.sent.push(JSON.parse(data)); }
        };
        app.run(role === 'child' ? 'connectWebSocket()' : 'initParentWebSocket()');
        const socket = sockets[0];
        const input = app.nodes.get(role === 'child' ? 'childChatInput' : 'parentChatInput');
        const list = app.nodes.get(role === 'child' ? 'childChatMessageList' : 'parentChatMessageList');
        app.run(role === 'child' ? 'sendQuickChildMsg("alo")' : 'sendQuickParentMsg("alo")');
        assert.equal(socket.sent.length, 1);
        assert.equal(socket.sent[0].text, 'alo');
        assert.equal(list.children.length, 1);
        const payload = { ...socket.sent[0], cmd: 'chat_message' };
        await socket.onmessage({ data: JSON.stringify(payload) });
        await socket.onmessage({ data: JSON.stringify(payload) });
        assert.equal(list.children.length, 1);
        assert.equal(app.context.testToasts.length, 0);
        input.value = 'alo';
        app.run(role === 'child' ? 'sendChildChatMessage()' : 'sendParentChatMessage()');
        assert.equal(list.children.length, 2);
        assert.notEqual(socket.sent[0].message_id, socket.sent[1].message_id);
        assert.equal(app.errors.length, 0);
    });

    test(`${role} chat deduplicates incoming deliveries before unread notifications`, async () => {
        const app = role === 'child' ? runtime(childScript, childHtml) : parent();
        let socket;
        app.context.WebSocket = class {
            static OPEN = 1;
            constructor() { this.readyState = 1; socket = this; }
        };
        app.run(role === 'child' ? 'connectWebSocket()' : 'initParentWebSocket()');
        const list = app.nodes.get(role === 'child' ? 'childChatMessageList' : 'parentChatMessageList');
        const message = { cmd: 'chat_message', sender: role === 'child' ? 'parent' : 'child', message_id: 'test-1', text: 'alo', timestamp: '23:00' };
        await socket.onmessage({ data: JSON.stringify(message) });
        await socket.onmessage({ data: JSON.stringify(message) });
        assert.equal(list.children.length, 1);
        assert.equal(app.context.testToasts.length, 1);
        await socket.onmessage({ data: JSON.stringify({ ...message, message_id: 'test-2' }) });
        assert.equal(list.children.length, 2);
        assert.equal(app.errors.length, 0);
    });
}

for (const role of ['child', 'parent']) {
    test(`${role} repeated initialization opens only one socket and repeated send consumes the input once`, () => {
        const app = role === 'child' ? runtime(childScript, childHtml) : parent();
        const sockets = [];
        app.context.WebSocket = class {
            static OPEN = 1;
            constructor() { this.readyState = 0; this.sent = []; sockets.push(this); }
            send(data) { this.sent.push(JSON.parse(data)); }
        };
        const initialize = role === 'child' ? 'connectWebSocket()' : 'initParentWebSocket()';
        app.run(initialize);
        app.run(initialize);
        assert.equal(sockets.length, 1);
        sockets[0].readyState = 1;
        app.run(initialize);
        assert.equal(sockets.length, 1);
        app.nodes.get(role === 'child' ? 'childChatInput' : 'parentChatInput').value = 'alo';
        const send = role === 'child' ? 'sendChildChatMessage()' : 'sendParentChatMessage()';
        app.run(send);
        app.run(send);
        assert.equal(sockets[0].sent.length, 1);
        const list = app.nodes.get(role === 'child' ? 'childChatMessageList' : 'parentChatMessageList');
        assert.equal(list.children.length, 1);
    });
}

test('timeline shows the next access change across midnight', () => {
    const app = parent();
    app.run(`OgkTimeline.render('todayTimeline', '1'.repeat(22) + '00' + '0'.repeat(6) + '1'.repeat(138), null,
        new Date(2026, 10, 16, 23, 30))`);
    const timeline = app.nodes.get('todayTimeline');
    assert.equal(timeline.hidden, false);
    assert.match(timeline.innerHTML, /Được dùng lại lúc 06:00 ngày mai/);
});

test('schedule preview marks draft ranges separately from the active timeline', () => {
    const app = parent();
    app.run(`scheduleMatrixArray[16] = '0'; scheduleMatrixArray[17] = '0'; renderScheduleSummary();`);
    const preview = app.nodes.get('schedulePreview');
    assert.equal(preview.hidden, false);
    assert.match(preview.innerHTML, /2 khung 30 phút thay đổi trong tuần/);
    assert.match(app.nodes.get('scheduleSummary').innerHTML, /08:00–09:00<\/b> · Đã sửa/);
    app.run(`scheduleMatrixArray[16] = '1'; scheduleMatrixArray[17] = '1'; renderScheduleSummary();`);
    assert.equal(preview.hidden, true);
});

test('weekly summary reports recorded duration and active days', () => {
    const app = parent();
    assert.match(app.run('OgkTimeline.weeklySummary([0, 25, 0, 0, 50, 0, 0])'), /1 giờ 15 phút.*2\/7 ngày/);
    assert.match(app.run('OgkTimeline.weeklySummary(Array(7).fill(0))'), /Chưa ghi nhận/);
});

test('child portal warns at 10/5/1 minutes and grants a 60-second grace before locking', async () => {
    const app = runtime(childScript, childHtml);
    const events = [];
    app.context.fetch = async (url, options = {}) => {
        if (url === '/api/child/events') events.push(JSON.parse(options.body)[0].type);
        return { ok: true, json: async () => ({ remaining_seconds: app.context.remaining, quota_minutes: 60, lock_reason: null, paused_until: null }) };
    };
    app.run("childId = 1; waitingForSetup = false;");
    for (const seconds of [590, 290, 50]) {
        app.context.remaining = seconds;
        await app.run('syncUsage(false)');
    }
    assert.deepEqual(events, ['quota_warning', 'quota_warning', 'quota_warning']);
    app.context.remaining = 0;
    await app.run('syncUsage(false)');
    assert.equal(app.run('isTimeExpired'), false);
    assert.equal(app.nodes.get('graceBanner').hidden, false);
    app.run('graceDeadline = Date.now() - 1; tickGracePeriod();');
    assert.equal(app.run('isTimeExpired'), true);
});

test('child portal locks immediately when opened after the quota is used up', async () => {
    const app = runtime(childScript, childHtml);
    app.context.fetch = async () => ({ ok: true, json: async () => ({ remaining_seconds: 0, quota_minutes: 60, lock_reason: null, paused_until: null }) });
    app.run("childId = 1; waitingForSetup = false;");
    await app.run('syncUsage(false)');
    assert.equal(app.run('isTimeExpired'), true);
});

test('parent writes carry the CSRF token through the fetch wrapper', async () => {
    const calls = [];
    const nativeFetch = async (url, options) => { calls.push(options); return { status: 200, ok: true, json: async () => ({}) }; };
    const window = { addEventListener() {}, location: { protocol: 'http:', host: 'localhost', pathname: '/' }, fetch: nativeFetch };
    const app = runtime(parentScript, parentHtml, { window, Headers });
    app.run("csrfToken = 'abc';");
    await app.run("window.fetch('/policy/update', { method: 'PUT' })");
    assert.equal(calls[0].headers.get('X-CSRF-Token'), 'abc');
    assert.equal(calls[0].credentials, 'same-origin');
});

test('child portal shows the rest-hour overlay outside the weekly schedule and releases it afterwards', async () => {
    const app = runtime(childScript, childHtml);
    let blocked = true;
    app.context.fetch = async () => ({ ok: true, json: async () => ({ remaining_seconds: 3600, quota_minutes: 120, lock_reason: null, paused_until: null, schedule_blocked: blocked }) });
    app.run("childId = 1; waitingForSetup = false;");
    await app.run('syncUsage(false)');
    assert.equal(app.nodes.get('lockOverlay').classList.contains('active'), true);
    assert.match(app.nodes.get('lockReasonText').innerText, /giờ nghỉ/);
    app.run('hideLockOverlay()');
    assert.equal(app.nodes.get('lockOverlay').classList.contains('active'), true, 'PIN không mở được giờ nghỉ theo lịch');
    blocked = false;
    await app.run('syncUsage(false)');
    assert.equal(app.nodes.get('lockOverlay').classList.contains('active'), false);
});

test('a blocked search produces one block record, not two', async () => {
    const app = runtime(childScript, childHtml);
    const calls = [];
    app.context.fetch = async url => { calls.push(url); return { ok: true, json: async () => ({}) }; };
    app.run("childId = 1; waitingForSetup = false; ws = null;");
    app.run("triggerViolationAlert('phim sex', 'keyword'); logAccess('phim sex', 'Tìm kiếm', 'blocked');");
    assert.deepEqual(calls, ['/api/child/access-log']);
});
