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

function runtime(script, html) {
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
    app.run("currentPolicy = { version: 1, blocked_domains: '', daily_quota_weekday_min: 120, daily_quota_weekend_min: 180, schedule_matrix: '1'.repeat(168) };");
    app.nodes.get('rangeStart').value = '22';
    app.nodes.get('rangeEnd').value = '6';
    app.nodes.get('rangeState').value = '0';
    return app;
}

function policy(matrix = '1'.repeat(168)) {
    return { version: 3, daily_quota_weekday_min: 120, daily_quota_weekend_min: 180, schedule_matrix: matrix, blocked_apps: '', blocked_domains: '' };
}

test('both parent entry templates stay identical', () => {
    assert.equal(parentHtml, fs.readFileSync(path.join(root, 'server/templates/index.html'), 'utf8'));
});

test('weekly grid renders 168 keyboard-accessible slots and seven summaries', () => {
    const app = parent();
    app.run('initScheduleGrid()');
    const rows = app.nodes.get('scheduleMatrixGrid').children;
    assert.equal(rows.length, 7);
    assert.equal(rows.flatMap(row => row.children[1].children).length, 168);
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
    app.run("scheduleMatrixArray = Array(168).fill('0'); renderScheduleSummary();");
    assert.equal((app.nodes.get('scheduleSummary').innerHTML.match(/00:00–24:00/g) || []).length, 7);
    assert.equal((app.nodes.get('scheduleSummary').innerHTML.match(/schedule-range rest/g) || []).length, 7);
});

test('daytime range changes only the selected days and hours', () => {
    const app = parent();
    app.selectedDays([0, 2]);
    app.nodes.get('rangeStart').value = '8';
    app.nodes.get('rangeEnd').value = '11';
    app.run('applyScheduleRange()');
    const actual = app.run("scheduleMatrixArray.map((state, index) => state === '0' ? index : -1).filter(index => index >= 0).join(',')");
    assert.equal(actual, '8,9,10,56,57,58');
});

test('overnight range extends to the next day', () => {
    const app = parent();
    app.selectedDays([0]);
    app.run('applyScheduleRange()');
    assert.equal(app.run("scheduleMatrixArray.slice(0, 6).join('')"), '111111');
    assert.equal(app.run("scheduleMatrixArray.slice(22, 30).join('')"), '00000000');
    assert.equal(app.run('scheduleMatrixArray[30]'), '1');
});

test('Sunday overnight range wraps to Monday', () => {
    const app = parent();
    app.selectedDays([6]);
    app.run('applyScheduleRange()');
    assert.equal(app.run("scheduleMatrixArray.slice(166).join('')"), '00');
    assert.equal(app.run("scheduleMatrixArray.slice(0, 6).join('')"), '000000');
    assert.equal(app.run("scheduleMatrixArray.slice(144, 150).join('')"), '111111');
});

test('range supports midnight to 24:00 for a full day', () => {
    const app = parent();
    app.selectedDays([3]);
    app.nodes.get('rangeStart').value = '0';
    app.nodes.get('rangeEnd').value = '24';
    app.run('applyScheduleRange()');
    assert.equal(app.run("scheduleMatrixArray.filter(state => state === '0').length"), 24);
});

test('range rejects an empty selection and equal endpoints', () => {
    const app = parent();
    app.selectedDays([]);
    app.run('applyScheduleRange()');
    app.selectedDays([0]);
    app.nodes.get('rangeEnd').value = '22';
    app.run('applyScheduleRange()');
    assert.equal(app.run('scheduleDirty'), false);
    assert.equal(app.context.testToasts.length, 2);
});

test('restoring allowed time keeps other restrictions intact', () => {
    const app = parent();
    app.run("scheduleMatrixArray.fill('0')");
    app.selectedDays([1]);
    app.nodes.get('rangeStart').value = '9';
    app.nodes.get('rangeEnd').value = '10';
    app.nodes.get('rangeState').value = '1';
    app.run('applyScheduleRange()');
    assert.equal(app.run("scheduleMatrixArray.filter(state => state === '1').length"), 1);
    assert.equal(app.run('scheduleMatrixArray[33]'), '1');
});

test('bedtime and school presets preserve restrictions in other periods', () => {
    const app = parent();
    app.run("scheduleMatrixArray[12] = '0'; setSchedulePreset('bedtime_lock'); setSchedulePreset('school_lock');");
    assert.equal(app.run('scheduleMatrixArray[12]'), '0');
    assert.equal(app.run('scheduleMatrixArray[8]'), '0');
    assert.equal(app.run('scheduleMatrixArray[5 * 24 + 8]'), '1');
    assert.equal(app.run('scheduleMatrixArray[6 * 24 + 23]'), '0');
});

test('policy load handles legacy 336-slot schedules conservatively', async () => {
    const app = parent();
    app.setPolicy(policy('10'.repeat(168)));
    await app.run('loadPolicy()');
    assert.equal(app.errors.length, 0);
    assert.equal(app.run('scheduleMatrixArray.length'), 168);
    assert.equal(app.run("scheduleMatrixArray.every(state => state === '0')"), true);
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
    assert.equal(sent[0].schedule_matrix.length, 168);
    assert.equal(sent[0].schedule_matrix[1], '0');
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

test('child catalogue only has Google and escapes unmatched text', () => {
    const app = runtime(childScript, childHtml);
    app.nodes.get('searchAppInput').value = 'tim kiem';
    app.run('renderApps()');
    assert.equal(app.nodes.get('appGrid').children.length, 1);
    assert.equal(app.nodes.get('appGrid').children[0].attributes['data-id'], 'google_search');
    app.nodes.get('searchAppInput').value = '<img src=x onerror=alert(1)>';
    app.run('renderApps()');
    assert.doesNotMatch(app.nodes.get('appGrid').innerHTML, /<img/);
    assert.match(app.nodes.get('appGrid').innerHTML, /&lt;img/);
});

test('child launch button has an accessible label and respects locking', () => {
    const app = runtime(childScript, childHtml);
    app.run('renderApps(); isLocked = true;');
    const card = app.nodes.get('appGrid').children[0];
    assert.match(card.launchButton.attributes['aria-label'], /Mở Google Tìm Kiếm/);
    card.launchButton.click();
    assert.match(app.context.testToasts.at(-1)[0], /đang bị khóa/);
    app.run('isLocked = false; isTimeExpired = true;');
    card.launchButton.click();
    assert.match(app.context.testToasts.at(-1)[0], /hết thời gian/);
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
    app.run(`scheduleMatrixArray[8] = '0'; renderScheduleSummary();`);
    const preview = app.nodes.get('schedulePreview');
    assert.equal(preview.hidden, false);
    assert.match(preview.innerHTML, /1 khung giờ thay đổi trong tuần/);
    assert.match(app.nodes.get('scheduleSummary').innerHTML, /08:00–09:00<\/b> · Đã sửa/);
    app.run(`scheduleMatrixArray[8] = '1'; renderScheduleSummary();`);
    assert.equal(preview.hidden, true);
});

test('weekly summary reports recorded duration and active days', () => {
    const app = parent();
    assert.match(app.run('OgkTimeline.weeklySummary([0, 25, 0, 0, 50, 0, 0])'), /1 giờ 15 phút.*2\/7 ngày/);
    assert.match(app.run('OgkTimeline.weeklySummary(Array(7).fill(0))'), /Chưa ghi nhận/);
});
