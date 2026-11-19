/**
 * OGK CHILD PORTAL - CLIENT JAVASCRIPT
 * Xử lý: Đếm giờ thời gian thực, Lọc tìm kiếm ứng dụng, In-App Safe Browser,
 * In-Page Lock Overlay (KHÔNG CAN THIỆP FULLSCREEN OS), và WebSocket Realtime Sync.
 */

// --- 1. BIẾN TRẠNG THÁI TOÀN CỤC ---
let childId = Number(window.location.pathname?.match(/^\/child\/(\d+)\/?$/)?.[1]) || 1;
let waitingForSetup = true;
let manuallyLocked = false;
let usageSyncPending = false;
let remainingSeconds = 120 * 60; // Mặc định 120 phút
let totalSeconds = 120 * 60;
let isLocked = false;
let isTimeExpired = false; // Trạng thái hết hạn sử dụng
let timeExpiredNotified = false; // Đã gửi cảnh báo hết giờ tới phụ huynh chưa
let currentPolicy = null;
let ws = null;
let currentCategory = 'all';
const childChatMessageIds = new Set();
let configuredParentPin = ""; // Bắt buộc lấy chính xác từ Server / Policy của Phụ huynh

// Danh sách ứng dụng cài sẵn và phân loại (Đã loại bỏ hoàn toàn các ứng dụng lỗi Zing MP3, Duolingo)
const APPS = [
  { id: 'google_search', name: 'Google Tìm Kiếm', category: 'study', icon: '🔍',
    desc: 'Tìm kiếm với SafeSearch', url: 'https://www.google.com/search?safe=active&igu=1',
    type: 'web', allowed: true }
];

// Danh sách domain bị chặn mặc định (Mạng xã hội, video giải trí độc hại, web cờ bạc/đen, game cấm)
const DEFAULT_BLOCKED_DOMAINS = [
  'youtube.com', 'youtu.be',
  'facebook.com', 'fb.com', 'messenger.com',
  'tiktok.com', 'instagram.com', 'twitter.com', 'x.com',
  'discord.com', 'telegram.org',
  'roblox.com', 'steamcommunity.com',
  'bet', 'casino', 'poker', 'porn', 'xxx', '18plus'
];

// Danh mục từ khóa bị hạn chế / cấm tìm kiếm trên máy con (Nội dung người lớn, cờ bạc cá cược, chất cấm/bạo lực)
const RESTRICTED_KEYWORDS = [
  // 1. Nhóm nội dung không phù hợp lứa tuổi / đồi trụy (Adult/Explicit content)
  'sex', 'porn', 'xxx', '18+', '18plus', 'hentai', 'lon', 'buoi', 'dam', 'khoa than',
  'khong che', 'phim nguoi lon', 'gai goi', 'kich duc', 'tinh duc', 'thu dam', 'lam tinh',
  'jav', 'nude', 'erotic', 'lo hang', 'clip nong', 'do trui', 'khieu dam',

  // 2. Nhóm cờ bạc, cá cược trực tuyến, nhà cái, game bài đổi thưởng
  'bet', '88bet', 'f8bet', 'kubet', 'shbet', 'hi88', '789bet', 'jun88', 'new88', 'w88',
  'casino', 'nha cai', 'tai xiu', 'lo de', 'so de', 'danh bac', 'co bac', 'ca do', 'ca cuoc',
  'game bai', 'ban ca doi thuong', 'nohu', 'no hu', 'slot game', 'baccarat', 'roulette',
  'poker', 'xoc dia', 'xocdia', 'quay hu', 'keo nha cai',

  // 3. Nhóm bạo lực, chất gây nghiện, nguy hiểm
  'tu tu', 'tu sat', 'thuoc phien', 'ma tuy', 'ke', 'can sa', 'thuoc lac', 'bong cuoi',
  'chat gay nghien', 'vu khi', 'mua sung', 'dao kiem', 'danh nhau', 'bao luc'
];

/**
 * Chuẩn hóa chuỗi tìm kiếm và loại bỏ dấu tiếng Việt để đối chiếu toàn diện
 */
function normalizeQuery(str) {
  if (!str) return '';
  return str.toLowerCase().trim();
}

function removeVietnameseTones(str) {
  if (!str) return '';
  return str
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D');
}

/**
 * Kiểm tra xem chuỗi tìm kiếm có chứa từ khóa hạn chế hay không
 * Trả về { isRestricted: boolean, matchedKeyword: string }
 */
function checkRestrictedKeyword(query) {
  if (!query) return { isRestricted: false, matchedKeyword: '' };
  
  const rawNorm = normalizeQuery(query);
  const noToneNorm = normalizeQuery(removeVietnameseTones(query));

  // Kiểm tra từng từ khóa hạn chế
  for (const kw of RESTRICTED_KEYWORDS) {
    const kwNorm = normalizeQuery(kw);
    const kwNoTone = normalizeQuery(removeVietnameseTones(kw));

    // Với từ khóa ngắn (<= 3 ký tự, ví dụ: 'sex', 'xxx', 'bet', 'lon', 'ke'): dùng regex ranh giới từ hoặc so khớp độc lập
    if (kwNorm.length <= 3) {
      const wordRegex = new RegExp(`(^|\\b|\\s|_|\\W)${kwNorm}($|\\b|\\s|_|\\W)`, 'i');
      const wordRegexNoTone = new RegExp(`(^|\\b|\\s|_|\\W)${kwNoTone}($|\\b|\\s|_|\\W)`, 'i');
      if (wordRegex.test(rawNorm) || wordRegexNoTone.test(noToneNorm)) {
        return { isRestricted: true, matchedKeyword: kw };
      }
    } else {
      // Với từ khóa >= 4 ký tự (ví dụ: 'casino', 'hentai', '88bet', 'tai xiu', 'lo de'): kiểm tra includes
      if (rawNorm.includes(kwNorm) || noToneNorm.includes(kwNoTone)) {
        return { isRestricted: true, matchedKeyword: kw };
      }
    }
  }

  return { isRestricted: false, matchedKeyword: '' };
}

// --- 2. KHỞI CHẠY KHI TẢI TRANG ---
document.addEventListener('DOMContentLoaded', async () => {
  renderApps();
  setupEventListeners();
  await checkInitializationStatus();
  await loadInitialPolicy();
  connectWebSocket();
  startClockTicker();
  syncUsage();
  setInterval(() => syncUsage(), 5000);
});

// Kiểm tra trạng thái khởi tạo từ phụ huynh (Waiting State)
async function checkInitializationStatus() {
  try {
    const res = await fetch(`/api/auth/status/${childId}?t=${Date.now()}`);
    if (res.ok) {
      const data = await res.json();
      if (data.child_name) {
        const nameEl = document.getElementById('childNameDisplay');
        if (nameEl) nameEl.innerText = data.child_name;
        document.title = `Người Bạn Đồng Hành — Trạm Học Tập (${data.child_name})`;
      }
      if (data.lock_pin) {
        configuredParentPin = String(data.lock_pin).trim();
      }
      // TRƯỜNG HỢP A: Hệ thống chưa có Tên bé hoặc chưa có PIN -> GIỮ NGUYÊN MÀN HÌNH CHỜ
      if (!data.is_initialized || !data.has_pin || !data.child_name || !data.child_name.trim()) {
        showWaitingScreen();
      } else {
        // TRƯỜNG HỢP B: Đã có tên bé và PIN
        hideWaitingScreen();
      }
    }
  } catch (e) {
    showWaitingScreen();
  }
}

function hideWaitingScreen() {
  waitingForSetup = false;
  const waitingEl = document.getElementById('waitingScreenState');
  if (waitingEl) {
    waitingEl.style.opacity = '0';
    waitingEl.style.pointerEvents = 'none';
    setTimeout(() => {
      waitingEl.style.display = 'none';
    }, 700);
  }
}

function showWaitingScreen() {
  waitingForSetup = true;
  const waitingEl = document.getElementById('waitingScreenState');
  if (waitingEl) {
    waitingEl.style.display = 'flex';
    waitingEl.style.opacity = '1';
    waitingEl.style.pointerEvents = 'auto';
  }
}

// --- 3. ĐỒNG HỒ & ĐẾM LÙI THỜI GIAN ---
function startClockTicker() {
  setInterval(() => {
    // 1. Cập nhật giờ số trên thanh tiêu đề và màn hình khóa
    const now = new Date();
    const hours = now.getHours();
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    const timeFormatted = `${displayHours}:${minutes} ${ampm}`;
    
    const clockEl = document.getElementById('digitalClock');
    if (clockEl) {
      clockEl.innerText = timeFormatted;
    }
    const lockClockEl = document.getElementById('lockOverlayClock');
    if (lockClockEl) {
      lockClockEl.innerText = timeFormatted;
    }

    updateTimeDisplay();
  }, 1000);
}

async function syncUsage(record = true) {
  if (usageSyncPending) return;
  usageSyncPending = true;
  try {
    const active = record && !waitingForSetup && !isLocked && (!document.hidden || window.ogkDesktop);
    const response = await fetch(`/web-usage/${childId}`, { method: active ? 'POST' : 'GET' });
    if (!response.ok) return;
    const usage = await response.json();
    remainingSeconds = usage.remaining_seconds;
    totalSeconds = usage.quota_minutes * 60;
    if (!waitingForSetup) {
      if (usage.lock_reason && !manuallyLocked) {
        manuallyLocked = true;
        showLockOverlay(usage.lock_reason);
      } else if (usage.lock_reason === null && manuallyLocked) {
        hideLockOverlay();
      }
      if (remainingSeconds === 0 && !isTimeExpired) {
        handleTimeExpired();
      } else if (remainingSeconds > 0 && isTimeExpired) {
        isTimeExpired = false;
        timeExpiredNotified = false;
        if (!manuallyLocked) hideLockOverlay();
      }
    }
    updateTimeDisplay();
  } catch (err) {
    console.warn("Không thể đồng bộ thời gian:", err);
  } finally {
    usageSyncPending = false;
  }
}

// Xử lý khi hết giờ sử dụng trong ngày (Khóa tuyệt đối, đóng toàn bộ app và báo cho phụ huynh)
function handleTimeExpired() {
  isTimeExpired = true;
  disableAppInteractions();
  showLockOverlay("Đã hết thời gian sử dụng hôm nay. Toàn bộ ứng dụng đã bị khóa!");
  
  if (!timeExpiredNotified) {
    timeExpiredNotified = true;
    notifyParentTimeExpired();
  }
}

// Gửi thông báo thời gian thực về Phụ huynh khi trẻ hết giờ
function notifyParentTimeExpired() {
  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')} ${String(now.getDate()).padStart(2, '0')}/${String(now.getMonth()+1).padStart(2, '0')}/${now.getFullYear()}`;
  const childName = document.getElementById('childNameDisplay')?.innerText || "Bé yêu";

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      action: 'time_expired_alert',
      child_name: childName,
      timestamp: timeStr
    }));
  }
}

// Vô hiệu hóa toàn bộ tương tác trên giao diện máy con khi bị khóa/hết giờ
function disableAppInteractions() {
  const grid = document.getElementById('appGrid');
  const search = document.getElementById('searchAppInput');
  const btnSearch = document.getElementById('btnSearchGoogle');
  const pills = document.querySelectorAll('.folder-pill');
  if (grid) {
    grid.style.pointerEvents = 'none';
    grid.style.opacity = '0.4';
    grid.style.filter = 'grayscale(60%)';
  }
  if (search) {
    search.style.pointerEvents = 'none';
    search.disabled = true;
    search.style.opacity = '0.5';
  }
  if (btnSearch) {
    btnSearch.style.pointerEvents = 'none';
    btnSearch.disabled = true;
    btnSearch.style.opacity = '0.5';
  }
  pills.forEach(p => {
    p.style.pointerEvents = 'none';
    p.style.opacity = '0.5';
  });
}

// Kích hoạt lại tương tác khi được mở khóa
function enableAppInteractions() {
  const grid = document.getElementById('appGrid');
  const search = document.getElementById('searchAppInput');
  const btnSearch = document.getElementById('btnSearchGoogle');
  const pills = document.querySelectorAll('.folder-pill');
  if (grid) {
    grid.style.pointerEvents = 'auto';
    grid.style.opacity = '1';
    grid.style.filter = 'none';
  }
  if (search) {
    search.style.pointerEvents = 'auto';
    search.disabled = false;
    search.style.opacity = '1';
  }
  if (btnSearch) {
    btnSearch.style.pointerEvents = 'auto';
    btnSearch.disabled = false;
    btnSearch.style.opacity = '1';
  }
  pills.forEach(p => {
    p.style.pointerEvents = 'auto';
    p.style.opacity = '1';
  });
}

let displayedTimelineMinute;

function updateTimeDisplay() {
  const minute = Math.floor(Date.now() / 60000);
  if (minute !== displayedTimelineMinute) {
    displayedTimelineMinute = minute;
    OgkTimeline.render("todayTimeline", currentPolicy?.schedule_matrix);
  }
  const remMinutes = Math.ceil(remainingSeconds / 60);
  const totMinutes = Math.floor(totalSeconds / 60);
  const percent = totalSeconds > 0 ? Math.min(100, Math.max(0, (remainingSeconds / totalSeconds) * 100)) : 0;

  const remEl = document.getElementById('remainingMinutes');
  const totEl = document.getElementById('totalMinutes');
  const barEl = document.getElementById('timeProgressBar');

  if (remEl) remEl.innerText = `${remMinutes} phút`;
  if (totEl) totEl.innerText = `${totMinutes} phút`;
  if (barEl) {
    barEl.style.width = `${percent}%`;
    if (percent <= 15) {
      barEl.style.background = '#f43f5e'; // Đỏ cảnh báo
    } else if (percent <= 40) {
      barEl.style.background = '#f59e0b'; // Vàng
    } else {
      barEl.style.background = '#0f766e';
    }
  }

  // Cập nhật trạng thái thời gian trên màn hình khóa (nếu đang hiển thị)
  const lockStatusEl = document.getElementById('lockOverlayTimeStatus');
  if (lockStatusEl) {
    if (remainingSeconds <= 0) {
      lockStatusEl.innerText = 'Đã hết thời gian trong ngày';
      lockStatusEl.className = 'text-rose-400 font-bold';
    } else {
      lockStatusEl.innerText = `Còn ${remMinutes} phút sử dụng`;
      lockStatusEl.className = 'text-cyan-400 font-bold';
    }
  }
}

// --- 4. TẢI CHÍNH SÁCH TỪ SERVER ---
async function loadInitialPolicy() {
  try {
    const res = await fetch(`/policy/${childId}`);
    if (res.ok) {
      const policy = await res.json();
      if (policy.version < currentPolicy?.version) return;
      currentPolicy = policy;
      applyPolicy(currentPolicy);
    }
  } catch (err) {
    console.warn("Không thể tải chính sách từ server, dùng thiết lập mặc định:", err);
  }
}

function applyPolicy(policy) {
  if (!policy) return;

  const now = new Date();
  const isWeekend = now.getDay() === 0 || now.getDay() === 6;

  // Cập nhật chế độ hiển thị
  const modeBadge = document.getElementById('modeBadge');
  if (modeBadge) {
    if (isWeekend) {
      modeBadge.innerText = '🎮 Chế độ: Giải trí cuối tuần';
      modeBadge.className = 'badge-status badge-mode';
    } else {
      modeBadge.innerText = '📚 Chế độ: Giờ học tập tích cực';
      modeBadge.className = 'badge-status badge-mode';
    }
  }

  // Cập nhật tên của trẻ
  if (policy.child_name) {
    const nameEl = document.getElementById('childNameDisplay');
    if (nameEl) nameEl.innerText = policy.child_name;
    document.title = `Người Bạn Đồng Hành — Trạm Học Tập (${policy.child_name})`;
  }

  // Cập nhật mã PIN phụ huynh
  if (policy.lock_pin) {
    configuredParentPin = String(policy.lock_pin).trim();
  }

  APPS[0].allowed = !isDomainBlocked('www.google.com');
  APPS[0].blockReason = APPS[0].allowed ? '' : 'Google đã bị phụ huynh chặn';

  renderApps();
  displayedTimelineMinute = undefined;
  updateTimeDisplay();
}

// --- 5. RENDER DANH SÁCH ỨNG DỤNG & LỌC TÌM KIẾM CỤC BỘ ---
function filterApps() {
  renderApps();
  const searchInput = document.getElementById('searchAppInput');
  const clearBtn = document.getElementById('btnClearSearch');
  if (clearBtn) {
    if (searchInput && searchInput.value.trim()) {
      clearBtn.classList.remove('hidden');
    } else {
      clearBtn.classList.add('hidden');
    }
  }
}

function clearSearchInput() {
  const searchInput = document.getElementById('searchAppInput');
  if (searchInput) {
    searchInput.value = '';
    searchInput.focus();
  }
  filterApps();
}

function renderApps() {
  const grid = document.getElementById('appGrid');
  if (!grid) return;

  const rawKeyword = (document.getElementById('searchAppInput')?.value || '').trim().toLowerCase();
  const noToneKeyword = removeVietnameseTones(rawKeyword);
  grid.innerHTML = '';

  const filtered = APPS.filter(app => {
    const matchCategory = currentCategory === 'all' || app.category === currentCategory;
    if (!matchCategory) return false;

    if (!rawKeyword) return true;
    const nameLower = app.name.toLowerCase();
    const nameNoTone = removeVietnameseTones(nameLower);
    const descLower = (app.desc || '').toLowerCase();
    const descNoTone = removeVietnameseTones(descLower);

    return nameLower.includes(rawKeyword) || 
           nameNoTone.includes(noToneKeyword) ||
           descLower.includes(rawKeyword) ||
           descNoTone.includes(noToneKeyword);
  });

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-muted);">
        <p style="font-size: 2rem; margin-bottom: 8px;">🔍</p>
        <p style="font-weight: 600;">Không tìm thấy ứng dụng phù hợp với từ khóa "${escapeHtml(rawKeyword)}"</p>
        <p style="font-size: 0.85rem; margin-top: 4px;">Hãy thử tìm kiếm với tên khác hoặc chọn thư mục "Tất cả".</p>
      </div>
    `;
    return;
  }

  filtered.forEach(app => {
    const card = document.createElement('div');
    card.className = `app-card ${app.allowed ? '' : 'disabled'}`;
    card.setAttribute('data-id', app.id);
    card.setAttribute('role', 'group');
    card.setAttribute('aria-label', app.name);

    const badgeHtml = app.allowed 
      ? ''
      : `<span class="badge-status badge-blocked">✕ Đang bị khóa</span>`;

    card.innerHTML = `
      <div>
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="app-icon">${app.icon}</div>
          ${badgeHtml}
        </div>
        <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 6px; color: var(--text-main);">${app.name}</h3>
        <p style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.4;">${app.desc}</p>
      </div>
      <div style="margin-top: 16px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 0.75rem; color: #64748b; font-weight: 600;">${getCategoryName(app.category)}</span>
        <button class="launch-btn" style="
          padding: 6px 14px;
          border-radius: 10px;
          border: none;
          background: ${app.allowed ? '#0f766e' : '#64748b'};
          color: white;
          font-size: 0.8rem;
          font-weight: 700;
          cursor: ${app.allowed ? 'pointer' : 'not-allowed'};
          transition: all 0.2s;
        ">
          ${app.allowed ? 'Mở ứng dụng ↗' : 'Đã khóa 🔒'}
        </button>
      </div>
    `;

    const launchButton = card.querySelector('.launch-btn');
    launchButton.setAttribute('aria-label', `${app.allowed ? 'Mở' : 'Xem giới hạn của'} ${app.name}`);
    launchButton.addEventListener('click', event => event.stopPropagation());
    launchButton.addEventListener('click', () => card.click());
    card.addEventListener('click', () => {
      // 1. Chặn toàn diện nếu đã hết thời gian sử dụng
      if (isTimeExpired || remainingSeconds <= 0) {
        showToast("⌛ Đã hết thời gian sử dụng! Toàn bộ ứng dụng đã bị khóa.");
        return false;
      }

      // 2. Chặn nếu phiên đang bị phụ huynh tạm khóa
      if (isLocked) {
        showToast("⚠️ Phiên làm việc đang bị khóa, không thể mở ứng dụng.");
        return false;
      }

      // BƯỚC 1: KIỂM TRA TÊN APP / DANH MỤC CỤC BỘ (Local App Verification)
      if (!app.allowed) {
        showViolationBlockModal(app.name, "app");
        triggerViolationAlert(app.name, "app", "Ứng dụng cấm");
        logAccess(app.name, "Ứng dụng", "blocked");
        showToast("🛑 Nội dung hoặc tên miền này đã bị ba mẹ hạn chế truy cập!");
        return false;
      }

      // Nếu là Desktop App -> Mở trong Mock App Modal nội bộ
      if (app.type === 'desktop') {
        logAccess(app.name, "Ứng dụng", "allowed");
        openMockApp(app.name, app.icon);
        return;
      }

      // BƯỚC 2: KIỂM TRA TÊN MIỀN (Domain Blacklist Checking)
      const domain = extractDomain(app.url);
      const kwCheck = checkRestrictedKeyword(domain);
      if (kwCheck.isRestricted || isDomainBlocked(domain)) {
        showViolationBlockModal(app.name || domain, "web");
        triggerViolationAlert(app.name || domain, "web", "Tên miền cấm");
        logAccess(app.name || domain, "Trang web", "blocked");
        showToast("🛑 Nội dung hoặc tên miền này đã bị ba mẹ hạn chế truy cập!");
        return false;
      }

      // Domain hợp lệ -> Mở trực tiếp trong In-App Safe Browser
      logAccess(app.name || domain, "Trang web", "allowed");
      openInAppBrowser(app.url, app.name);
    });

    grid.appendChild(card);
  });
}

// Mô phỏng ứng dụng đơn giản (Mock App Modal - Không can thiệp hệ điều hành)
function openMockApp(name, icon) {
  if (isTimeExpired || remainingSeconds <= 0) {
    showToast("⌛ Đã hết thời gian sử dụng! Toàn bộ ứng dụng đã bị khóa.");
    return;
  }
  if (isLocked) {
    showToast("⚠️ Phiên làm việc đang bị khóa, không thể mở ứng dụng.");
    return;
  }

  const modal = document.getElementById('mockAppModal');
  const hIcon = document.getElementById('mockAppHeaderIcon');
  const hTitle = document.getElementById('mockAppHeaderTitle');
  const cIcon = document.getElementById('mockAppCenterIcon');
  const status = document.getElementById('mockAppStatusText');

  if (hIcon) hIcon.innerText = icon || '📱';
  if (hTitle) hTitle.innerText = name;
  if (cIcon) cIcon.innerText = icon || '📱';
  if (status) status.innerText = `Đang mở app ${name}...`;

  if (modal) {
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }
}

function closeMockAppModal() {
  const modal = document.getElementById('mockAppModal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}

function getCategoryName(cat) {
  switch (cat) {
    case 'study': return '📚 Học tập';
    case 'creative': return '🎨 Sáng tạo';
    case 'entertainment': return '🎮 Giải trí';
    default: return 'Ứng dụng';
  }
}

// --- 6. IN-APP SAFE BROWSER (KIỂM DUYỆT TÊN MIỀN & MỞ NỘI BỘ AN TOÀN) ---

// Trích xuất hostname / tên miền sạch từ URL hoặc chuỗi
function extractDomain(url) {
  if (!url) return '';
  let str = String(url).trim();
  if (!str.startsWith('http://') && !str.startsWith('https://')) {
    str = 'https://' + str;
  }
  try {
    let hostname = new URL(str).hostname.toLowerCase();
    if (hostname.startsWith('www.')) {
      hostname = hostname.substring(4);
    }
    return hostname;
  } catch (e) {
    let clean = str.replace(/https?:\/\//i, '').split('/')[0].split('?')[0].toLowerCase();
    if (clean.startsWith('www.')) clean = clean.substring(4);
    return clean;
  }
}

// Đối chiếu domain với danh sách tên miền bị hạn chế (Chính sách Phụ huynh + Mặc định)
function isDomainBlocked(domain) {
  if (!domain) return false;
  const cleanDomain = domain.toLowerCase().trim();

  // 1. Đọc blocked_domains từ policy (nếu có)
  let policyBlocked = [];
  if (currentPolicy && currentPolicy.blocked_domains) {
    const raw = currentPolicy.blocked_domains;
    if (typeof raw === 'string') {
      try {
        if (raw.trim().startsWith('[')) {
          policyBlocked = JSON.parse(raw);
        } else {
          policyBlocked = raw.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
        }
      } catch (e) {
        policyBlocked = raw.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
      }
    } else if (Array.isArray(raw)) {
      policyBlocked = raw.map(s => String(s).trim().toLowerCase()).filter(Boolean);
    }
  }

  // 2. Hợp nhất danh sách mặc định và chính sách phụ huynh
  const allBlocked = new Set([...DEFAULT_BLOCKED_DOMAINS, ...policyBlocked]);

  // 3. So khớp domain chính xác, đuôi tên miền hoặc từ khóa cấm
  for (let b of allBlocked) {
    let bClean = b.trim().toLowerCase();
    if (bClean.startsWith('www.')) bClean = bClean.substring(4);
    if (!bClean) continue;
    if (cleanDomain === bClean || cleanDomain.endsWith('.' + bClean) || (bClean.length > 3 && cleanDomain.includes(bClean))) {
      return true;
    }
  }

  return false;
}

/**
 * Quy trình mở Web & Kiểm duyệt 2 bước chuẩn đồ án:
 * - Bước 1: Trích xuất tên miền (extractDomain)
 * - Bước 2: So khớp Policy tên miền (isDomainBlocked)
 *   + Nếu vi phạm: Không mở iframe/modal, hiển thị thông báo: "Trang web / Ứng dụng này đã bị ba mẹ chặn truy cập!"
 *     hoặc "Nội dung tìm kiếm chứa từ khóa không phù hợp với quy định của phụ huynh!", bắn WebSocket violation_alert (query_filter/web).
 *   + Nếu hợp lệ: Nạp trực tiếp URL thật vào khung iframe nội bộ, thanh tiêu đề có tên trang và nút Đóng [✕].
 *   + Cấu hình Google SafeSearch tham chiếu: https://www.google.com/search?q=&safe=active&ssui=on&igu=1
 */
function handleGoogleOrDomainSearch() {
  if (isTimeExpired || remainingSeconds <= 0 || isLocked) {
    showToast("⌛ Đã hết thời gian sử dụng hoặc máy đang khóa! Toàn bộ ứng dụng đã bị khóa.");
    return;
  }
  if (isLocked) {
    showToast("⚠️ Phiên làm việc đang bị khóa, không thể mở ứng dụng.");
    return;
  }

  const searchInput = document.getElementById('searchAppInput');
  const rawQuery = (searchInput?.value || '').trim();
  if (!rawQuery) {
    filterApps();
    return;
  }

  // 1. KIỂM DUYỆT TỪ KHÓA TÌM KIẾM ĐẦU VÀO (KEYWORD MODERATION)
  const kwCheck = checkRestrictedKeyword(rawQuery);
  if (kwCheck.isRestricted) {
    showViolationBlockModal(rawQuery, "keyword");
    triggerViolationAlert(rawQuery, "keyword", "Từ khóa cấm");
    logAccess(rawQuery, "Tìm kiếm", "blocked");
    showToast("🛑 Nội dung hoặc tên miền này đã bị ba mẹ hạn chế truy cập!");
    return;
  }

  const looksLikeAddress = /^https?:|^[^\s/]+\.[a-z]{2,}(?:[/?#:]|$)/i.test(rawQuery);
  if (looksLikeAddress) {
    const target = extractDomain(rawQuery.includes('://') ? rawQuery : "https://" + rawQuery);
    if (target !== 'google.com' && target !== 'www.google.com') {
      showViolationBlockModal(target || rawQuery, "web");
      triggerViolationAlert(target || rawQuery, "web", "Chỉ cho phép Google Tìm kiếm");
      logAccess(target || rawQuery, "Trang web", "blocked");
      return;
    }
  }

  const google = new URL("https://www.google.com/search");
  google.search = new URLSearchParams({q: rawQuery, safe: 'active', igu: '1', udm: '14'});
  openInAppBrowser(google.href, "Google Tìm kiếm");
}

function openInAppBrowser(url, title) {
  if (waitingForSetup || isTimeExpired || remainingSeconds <= 0 || isLocked) return;

  let search;
  try {
    search = new URL(url);
  } catch (_) {
    return;
  }
  if (search.origin !== 'https://www.google.com' || search.pathname !== '/search' ||
      isDomainBlocked(search.hostname)) {
    showViolationBlockModal(search.hostname, 'web');
    triggerViolationAlert(search.hostname, 'web');
    return;
  }

  search.searchParams.set('safe', 'active');
  search.searchParams.set('udm', '14');
  logAccess(search.searchParams.get('q') || title, 'Tìm kiếm', 'allowed');
  if (window.ogkDesktop) {
    const showSearchError = () => showToast("Google Tìm kiếm chưa tải được. Hãy thử lại sau.");
    Promise.resolve(window.ogkDesktop.searchGoogle(search.searchParams.get('q') || ''))
      .then(opened => { if (opened === false) showSearchError(); })
      .catch(showSearchError);
    return;
  }

  const modal = document.getElementById('inAppBrowserModal');
  const frame = document.getElementById('internalBrowserFrame');
  if (!modal || !frame) return;
  document.getElementById('browserTitleDisplay').innerText = title;
  document.getElementById('browserUrlDisplay').innerText = search.origin;
  frame.src = search.href;
  modal.classList.add('active');
}

function closeInAppBrowser() {
  window.ogkDesktop?.closeGoogle();
  const modal = document.getElementById('inAppBrowserModal');
  const frame = document.getElementById('internalBrowserFrame');
  if (modal) modal.classList.remove('active');
  if (frame) frame.src = 'about:blank';
}

// Modal cảnh báo nội dung hạn chế trên máy con
function showViolationBlockModal(targetName, targetType) {
  const modal = document.getElementById('violationBlockModal');
  const textEl = document.getElementById('violationBlockTargetText');
  let msg = `Trang web / Ứng dụng "${targetName}" đã bị ba mẹ chặn truy cập!`;
  if (targetType === 'app') {
    msg = `Ứng dụng "${targetName}" đã bị ba mẹ chặn truy cập!`;
  } else if (targetType === 'web') {
    msg = `Trang web "${targetName}" đã bị ba mẹ chặn truy cập!`;
  }

  if (textEl) {
    textEl.innerText = msg;
  }
  if (modal) {
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }
}

function closeViolationBlockModal() {
  const modal = document.getElementById('violationBlockModal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}

// Ghi nhận nhật ký truy cập vào cơ sở dữ liệu
function logAccess(targetName, targetType, status) {
  try {
    fetch('/api/access-log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        child_id: childId,
        device_id: 'CHILD-PC',
        target_name: String(targetName || 'Không xác định'),
        target_type: String(targetType || 'Trang web'),
        status: String(status || 'allowed')
      })
    }).catch(() => {});
  } catch (e) {}
}

// Bắn sự kiện cảnh báo vi phạm thời gian thực về Phụ huynh qua WebSocket
function triggerViolationAlert(targetName, targetType, violationType = "Từ khóa / Tên miền cấm") {
  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')} ${String(now.getDate()).padStart(2, '0')}/${String(now.getMonth()+1).padStart(2, '0')}/${now.getFullYear()}`;

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      action: 'violation_alert',
      target_name: targetName,
      target_type: targetType || 'web',
      violation_type: violationType,
      timestamp: timeStr
    }));
  }

  // Ghi nhận sự kiện vào database thông qua API
  try {
    let eventType = 'blocked_domain';
    if (targetType === 'app') eventType = 'blocked_app';
    else if (targetType === 'query_filter' || targetType === 'keyword') eventType = 'query_filter';

    fetch('/events/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ts: new Date().toISOString(),
        device_id: 'CHILD-PC',
        child_id: childId,
        type: eventType,
        subject: targetName,
        duration_sec: 0,
        policy_id: currentPolicy?.id || 1
      })
    }).catch(() => {});
  } catch (e) {}
}

// --- 7. CƠ CHẾ IN-PAGE LOCK OVERLAY (SỬA DỨT ĐIỂM FULLSCREEN BUG) ---
/**
 * TUYỆT ĐỐI KHÔNG KÍCH HOẠT CHẾ ĐỘ TOÀN MÀN HÌNH HOẶC WINDOWS OS API
 * Cửa sổ giữ nguyên kích thước của người dùng.
 */
function showLockOverlay(reason = "Đã hết thời gian sử dụng hoặc ba mẹ tạm khóa cửa sổ") {
  isLocked = true;
  const overlay = document.getElementById('lockOverlay');
  const reasonEl = document.getElementById('lockReasonText');

  if (reasonEl) {
    reasonEl.innerText = `Lý do: ${reason}`;
  }

  if (overlay) {
    overlay.classList.add('active');
  }

  // Khóa toàn bộ tương tác bề mặt app
  disableAppInteractions();

  // Đóng toàn bộ các cửa sổ nội bộ và modal đang mở
  closeInAppBrowser();
  closeMockAppModal();
  closeViolationBlockModal();
  closeRequestTimeModal();

  showToast("🔒 Cửa sổ học tập đã được tạm khóa bảo vệ.");
}

function hideLockOverlay() {
  manuallyLocked = false;
  if (remainingSeconds <= 0) {
    if (!isTimeExpired) handleTimeExpired();
    return;
  }
  isLocked = false;
  if (remainingSeconds > 0) {
    isTimeExpired = false;
    timeExpiredNotified = false;
    enableAppInteractions();
  }
  const overlay = document.getElementById('lockOverlay');
  if (overlay) {
    overlay.classList.remove('active');
  }
  const pinInput = document.getElementById('parentPinInput');
  if (pinInput) pinInput.value = '';
  showToast("🔓 Đã mở khóa cửa sổ thành công! Chúc con học vui vẻ.");
}

async function verifyParentPin() {
  const pinInput = document.getElementById('parentPinInput');
  const pin = (pinInput?.value || '').trim();
  if (!pin) {
    showToast("⚠️ Vui lòng nhập mã PIN phụ huynh.");
    return;
  }

  try {
    const res = await fetch('/api/settings/verify-pin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ child_id: childId, pin: pin, unlock_window: true })
    });
    if (res.ok) {
      const data = await res.json();
      if (data.valid) {
        if (pin) configuredParentPin = pin;
        hideLockOverlay();
        return;
      }
    }
  } catch (e) {
    console.error("Lỗi xác thực PIN từ server:", e);
  }

  showToast("❌ Mã PIN không chính xác. Vui lòng thử lại!");
  if (pinInput) {
    pinInput.value = '';
    pinInput.focus();
  }
}

// --- 8. XIN THÊM GIỜ (REQUEST TIME EXTENSION) ---
function openRequestTimeModal() {
  const modal = document.getElementById('requestTimeModal');
  if (modal) modal.style.display = 'flex';
}

function closeRequestTimeModal() {
  const modal = document.getElementById('requestTimeModal');
  if (modal) modal.style.display = 'none';
}

async function submitTimeRequest(minutes, reasonText) {
  try {
    const res = await fetch('/requests/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        child_id: childId,
        requested_minutes: minutes,
        reason: reasonText || `Bé xin thêm ${minutes} phút học tập`
      })
    });

    if (res.ok) {
      closeRequestTimeModal();
      showToast(`✓ Đã gửi yêu cầu xin thêm ${minutes} phút tới Ba Mẹ!`);
    } else {
      showToast("❌ Không thể gửi yêu cầu, vui lòng thử lại sau.");
    }
  } catch (err) {
    showToast("❌ Lỗi kết nối tới máy chủ phụ huynh.");
  }
}

// --- 9. WEBSOCKET REALTIME SYNC (CHUYÊN BIỆT CHO TRẺ) ---
function connectWebSocket() {
  if (ws && (ws.readyState === 0 || ws.readyState === 1)) return;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  const clientGuid = `child_web_${Math.random().toString(36).substring(2, 8)}`;
  const wsUrl = `${protocol}//${host}/ws/child/${clientGuid}`;

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("[WS] Kết nối WebSocket Child Portal thành công:", wsUrl);
      const wsBadge = document.getElementById('wsStatusBadge');
      if (wsBadge) {
        wsBadge.innerText = '🟢 Trực tuyến';
        wsBadge.className = 'badge-status badge-online';
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log("[WS Message Received]:", data);

        const cmd = data.cmd || data.action;
        const reason = data.reason || 'Lệnh từ phụ huynh';

        // 1. Lệnh KHÓA CỬA SỔ (< 1s)
        if (cmd === 'lock' || cmd === 'lock_window' || cmd === 'lock_now') {
          if (data.child_id != null && data.child_id !== childId) return;
          manuallyLocked = true;
          showLockOverlay(reason);
        }
        // 2. Lệnh MỞ KHÓA CỬA SỔ
        else if (cmd === 'unlock' || cmd === 'unlock_window') {
          if (data.child_id != null && data.child_id !== childId) return;
          hideLockOverlay();
        }
        // 3. Phụ huynh TRỪ GIỜ THỜI GIAN THỰC
        else if (cmd === 'time_deducted' || cmd === 'deduct_time') {
          if (data.child_id != null && data.child_id !== childId) return;
          syncUsage(false);
          const deducted = data.deduct_min ?? data.minutes;
          if (deducted > 0) showToast(`⚡ Ba mẹ đã trừ bớt ${deducted} phút (${reason})`);
        }
        // 4. Phụ huynh DUYỆT THÊM GIỜ
        else if (cmd === 'extend_time') {
          if (data.child_id != null && data.child_id !== childId) return;
          syncUsage(false);
          if (data.granted_minutes) {
            showToast(`🎉 Ba Mẹ đã duyệt thêm cho con +${data.granted_minutes} phút!`);
          }
        }
        // 5. Cập nhật chính sách mới
        else if (cmd === 'sync_policy') {
          loadInitialPolicy();
          syncUsage(false);
        }
        // 6. Phụ huynh yêu cầu xem màn hình trẻ (Cần sự đồng thuận)
        else if (cmd === 'request_screen_consent' || cmd === 'request_screen') {
          handleScreenConsentRequest();
        }
        // 7. Phụ huynh yêu cầu dừng chia sẻ màn hình
        else if (cmd === 'stop_screen_share') {
          stopScreenShare();
        }
        // 8. Tín hiệu Phụ huynh HOÀN TẤT KHỞI TẠO BAN ĐẦU (Tên & PIN)
        else if (cmd === 'init_completed') {
          const newName = data.child_name || 'Bé yêu';
          const nameEl = document.getElementById('childNameDisplay');
          if (nameEl) nameEl.innerText = newName;
          document.title = `Người Bạn Đồng Hành — Trạm Học Tập (${newName})`;
          if (data.lock_pin) {
            configuredParentPin = String(data.lock_pin).trim();
          }
          hideWaitingScreen();
          showToast(`🎉 Ba mẹ đã hoàn tất thiết lập! Chào mừng ${newName} đến với Trạm Học Tập!`);
        }
        // 9. Phụ huynh cập nhật tên bé hoặc mã PIN bảo mật
        else if (cmd === 'settings_updated') {
          if (data.child_name) {
            const nameEl = document.getElementById('childNameDisplay');
            if (nameEl) nameEl.innerText = data.child_name;
            document.title = `Người Bạn Đồng Hành — Trạm Học Tập (${data.child_name})`;
            showToast(`🔔 Ba Mẹ đã cập nhật: Tên của con là "${data.child_name}"`);
          }
          if (data.lock_pin) {
            configuredParentPin = String(data.lock_pin).trim();
          }
        }
        // 10. Tin nhắn Chat thời gian thực từ Phụ huynh (Hoạt động cả khi máy con bị khóa)
        else if (cmd === 'chat_message') {
          const sender = data.sender || 'parent';
          const text = data.text || '';
          const time = data.timestamp ? data.timestamp.split(' ')[0] : '';
          if (sender === 'child' && !data.message_id) return;
          if (!appendChatMessage(sender, text, time, data.message_id)) return;

          const widget = document.getElementById('floatingChatWindow') || document.getElementById('childChatWidget');
          const isWidgetHidden = !widget || widget.classList.contains('hidden');
          if (isWidgetHidden) {
            childChatUnreadCount++;
            const badge = document.getElementById('childChatUnreadBadge');
            if (badge) {
              badge.innerText = childChatUnreadCount;
              badge.classList.remove('hidden');
            }
          }
          showToast(`💬 Ba Mẹ: "${text}"`);
        }
        // 11. Cảnh báo vi phạm nội bộ (100% In-Page Toast)
        else if (cmd === 'violation_toast') {
          showToast(`🛑 ${data.message || 'Phát hiện ứng dụng/tên miền bị chặn'}`);
        }
      } catch (err) {
        console.error("Lỗi phân tích WebSocket message:", err);
      }
    };

    ws.onclose = () => {
      stopScreenShare();
      console.warn("[WS] Mất kết nối WebSocket, đang thử kết nối lại sau 3s...");
      const wsBadge = document.getElementById('wsStatusBadge');
      if (wsBadge) {
        wsBadge.innerText = '🟡 Đang kết nối lại...';
        wsBadge.className = 'badge-status badge-mode';
      }
      setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = (err) => {
      console.error("[WS Error]:", err);
    };

  } catch (err) {
    console.error("Không thể khởi tạo WebSocket:", err);
  }
}

// --- 10. TIỆN ÍCH & EVENT LISTENERS ---
function setupEventListeners() {
  // Lắng nghe tìm kiếm ứng dụng cục bộ (Realtime client-side filter)
  const searchInput = document.getElementById('searchAppInput');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      filterApps();
    });
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleGoogleOrDomainSearch();
      }
    });
  }

  // Lắng nghe nút chuyển thư mục category
  document.querySelectorAll('.folder-pill').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.folder-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentCategory = btn.getAttribute('data-cat') || 'all';
      renderApps();
    });
  });

  // Nút mở khóa bằng PIN
  const unlockBtn = document.getElementById('btnUnlockPin');
  if (unlockBtn) {
    unlockBtn.addEventListener('click', verifyParentPin);
  }

  const pinInput = document.getElementById('parentPinInput');
  if (pinInput) {
    pinInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') verifyParentPin();
    });
  }
}

let childToastTimeout = null;
function showToast(msg) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  // Singleton Toast Pattern: Xóa thông báo cũ và timer ngay lập tức
  if (childToastTimeout) {
    clearTimeout(childToastTimeout);
    childToastTimeout = null;
  }
  container.innerHTML = '';

  const item = document.createElement('div');
  item.className = 'toast-item';
  item.innerText = msg;

  container.appendChild(item);
  childToastTimeout = setTimeout(() => {
    item.style.opacity = '0';
    item.style.transform = 'translateY(-10px)';
    item.style.transition = 'all 0.3s ease';
    setTimeout(() => {
      if (item.parentNode) item.remove();
    }, 300);
    childToastTimeout = null;
  }, 2500);
}

// --- 11. XỬ LÝ CHIA SẺ MÀN HÌNH REALTIME ĐỒNG THUẬN (CONSENT-BASED SCREEN SHARE) ---
let screenStream = null;
let screenCaptureInterval = null;
let isSharingScreenActive = false;

function handleScreenConsentRequest() {
  const modal = document.getElementById('screenConsentModal');
  if (modal) modal.style.display = 'flex';
}

async function respondScreenConsent(approved) {
  const modal = document.getElementById('screenConsentModal');
  if (modal) modal.style.display = 'none';

  if (!approved) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'consent_response',
        approved: false,
        reason: 'Trẻ em đã từ chối yêu cầu chia sẻ màn hình.'
      }));
    }
    showToast("Đã từ chối chia sẻ màn hình.");
    return;
  }

  if (isSharingScreenActive || !ws || ws.readyState !== WebSocket.OPEN) return;
  const consentSocket = ws;
  try {
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        displaySurface: "browser",
        cursor: "always",
        frameRate: { ideal: 30, max: 30 }
      },
      audio: false,
      preferCurrentTab: true,
      selfBrowserSurface: "include",
      systemAudio: "exclude"
    });

    if (ws !== consentSocket || consentSocket.readyState !== WebSocket.OPEN || isSharingScreenActive) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    screenStream = stream;
    isSharingScreenActive = true;

    // Thông báo cho server là đã đồng ý
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'consent_response',
        approved: true
      }));
    }

    // Hiển thị badge đang chia sẻ
    const badge = document.getElementById('screenShareIndicator');
    if (badge) badge.style.display = 'flex';

    // Bắt đầu chụp frame gửi về websocket
    const video = document.createElement('video');
    video.srcObject = screenStream;
    await video.play();
    if (screenStream !== stream) return;

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    // Chụp frame nhị phân tốc độ cao 15 - 30 FPS (canvas.toBlob JPEG 0.5, downscale max width 800px)
    // Kiểm soát lưu lượng chặt chẽ (Backpressure): bufferedAmount === 0 để không tắc nghẽn queue WebSocket
    let isCapturingFrame = false;
    let lastFrameTimestamp = 0;
    screenCaptureInterval = setInterval(() => {
      if (!screenStream || !screenStream.active) {
        if (isSharingScreenActive) {
          stopScreenShare();
        }
        return;
      }
      // Tự hồi phục nếu tác vụ toBlob bị treo quá 1s
      if (isCapturingFrame && Date.now() - lastFrameTimestamp > 1000) {
        isCapturingFrame = false;
      }
      if (isCapturingFrame) return; // Tránh dồn hàng đợi frame
      if (!ws || ws.readyState !== WebSocket.OPEN || ws.bufferedAmount > 0) return; // Flow Control: buffer rỗng

      try {
        if (video.videoWidth > 0 && video.videoHeight > 0) {
          isCapturingFrame = true;
          lastFrameTimestamp = Date.now();

          // Downscale chiều ngang tối đa 800px để tối ưu băng thông & CPU
          const maxW = 800;
          const scale = video.videoWidth > maxW ? (maxW / video.videoWidth) : 1;
          const width = Math.round(video.videoWidth * scale);
          const height = Math.round(video.videoHeight * scale);

          if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
          }
          ctx.drawImage(video, 0, 0, width, height);

          // Xuất Binary Blob JPEG 0.5 và gửi thẳng qua WebSocket
          canvas.toBlob((blob) => {
            try {
              if (screenStream === stream && blob && consentSocket.readyState === WebSocket.OPEN && consentSocket.bufferedAmount === 0) {
                consentSocket.send(blob);
              }
            } catch (sendErr) {
              console.warn("Lỗi gửi binary frame:", sendErr);
            } finally {
              isCapturingFrame = false;
            }
          }, 'image/jpeg', 0.5);
        }
      } catch (e) {
        console.error("Lỗi capture frame:", e);
        isCapturingFrame = false;
      }
    }, 33); // Tần suất ~30 FPS, điều tiết qua ws.bufferedAmount === 0

    // Bắt sự kiện khi trẻ bấm "Stop sharing" trên thanh công cụ của trình duyệt
    screenStream.getVideoTracks()[0].onended = () => {
      if (isSharingScreenActive) {
        stopScreenShare();
      }
    };

    showToast("✓ Đang chia sẻ màn hình trực tiếp với Ba Mẹ.");
  } catch (err) {
    console.error("Không thể chia sẻ màn hình:", err);
    if (ws !== consentSocket || consentSocket.readyState !== WebSocket.OPEN) return;
    stopScreenShare();
    if (consentSocket.readyState === WebSocket.OPEN) {
      consentSocket.send(JSON.stringify({
        type: 'consent_response',
        approved: false,
        reason: 'Không thể truy cập màn hình: ' + err.message
      }));
    }
    showToast("⚠️ Không thể kích hoạt chia sẻ màn hình.");
  }
}

function stopScreenShare() {
  if (!isSharingScreenActive && !screenStream && !screenCaptureInterval) {
    return;
  }
  isSharingScreenActive = false;
  if (screenCaptureInterval) {
    clearInterval(screenCaptureInterval);
    screenCaptureInterval = null;
  }
  if (screenStream) {
    screenStream.getTracks().forEach(t => t.stop());
    screenStream = null;
  }
  const badge = document.getElementById('screenShareIndicator');
  if (badge) badge.style.display = 'none';

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'stop_screen_share'
    }));
  }
  showToast("Đã dừng chia sẻ màn hình.");
}

// --- 12. LOGIC WIDGET CHAT REALTIME 2 CHIỀU (DARK GLASSMORPHISM) ---
let childChatUnreadCount = 0;
function toggleChildChat() {
  const widget = document.getElementById('floatingChatWindow') || document.getElementById('childChatWidget');
  const badge = document.getElementById('childChatUnreadBadge');
  if (!widget) return;

  if (widget.classList.contains('hidden')) {
    widget.classList.remove('hidden');
    widget.classList.add('flex');
    childChatUnreadCount = 0;
    if (badge) {
      badge.innerText = '0';
      badge.classList.add('hidden');
    }
    const input = document.getElementById('childChatInput');
    if (input) input.focus();
    scrollChildChatToBottom();
  } else {
    widget.classList.add('hidden');
    widget.classList.remove('flex');
  }
}

function closeFloatingChat() {
  const widget = document.getElementById('floatingChatWindow') || document.getElementById('childChatWidget');
  if (widget) {
    widget.classList.add('hidden');
    widget.classList.remove('flex');
  }
}

function openChildChatBox() {
  toggleChildChat();
}

function scrollChildChatToBottom() {
  const list = document.getElementById('childChatMessageList');
  if (list) {
    setTimeout(() => {
      list.scrollTop = list.scrollHeight;
    }, 50);
  }
}

function sendQuickChildMsg(text) {
  const input = document.getElementById('childChatInput');
  if (input) input.value = text;
  sendChildChatMessage();
}

function sendChildChatMessage() {
  const input = document.getElementById('childChatInput');
  const text = (input?.value || '').trim();
  if (!text) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    showToast('Chưa kết nối được với Ba Mẹ. Con hãy thử gửi lại khi kết nối trở lại.');
    return;
  }
  input.value = '';

  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  const fullTs = `${timeStr} ${String(now.getDate()).padStart(2, '0')}/${String(now.getMonth()+1).padStart(2, '0')}/${now.getFullYear()}`;

  const messageId = `child-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  // 1. Thêm tin nhắn của trẻ vào danh sách hiển thị
  appendChatMessage('child', text, timeStr, messageId);
  if (input) input.value = '';

  // 2. Gửi tin nhắn qua WebSocket tới Phụ huynh
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      action: 'chat_message',
      message_id: messageId,
      sender: 'child',
      text: text,
      timestamp: fullTs
    }));
  } else {
    showToast("⚠️ WebSocket đang kết nối lại, tin nhắn sẽ sớm gửi đến Ba Mẹ.");
  }
}

function appendChatMessage(sender, text, timeStr, messageId) {
  const list = document.getElementById('childChatMessageList');
  if (!list) return;

  if (messageId && childChatMessageIds.has(messageId)) return false;
  if (messageId) {
    childChatMessageIds.add(messageId);
    if (childChatMessageIds.size > 500) childChatMessageIds.delete(childChatMessageIds.values().next().value);
  }

  const isChild = sender === 'child';
  const msgDiv = document.createElement('div');
  msgDiv.className = `flex flex-col ${isChild ? 'items-end' : 'items-start'} mb-2`;

  msgDiv.innerHTML = `
    <div class="ogk-chat-bubble ${isChild ? 'ogk-chat-sent' : ''}">
      ${escapeHtml(text)}
    </div>
    <span class="ogk-chat-time">
      ${isChild ? 'Con' : 'Ba Mẹ'} • ${timeStr || ''}
    </span>
  `;
  list.appendChild(msgDiv);
  scrollChildChatToBottom();
  return true;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// --- 13. XỬ LÝ ĐÓNG MODAL QUA PHÍM ESCAPE & BACKDROP CLICK ---
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' || e.key === 'Esc') {
    closeFloatingChat();
    closeInAppBrowser();
    closeRequestTimeModal();
    closeMockAppModal();
    closeViolationBlockModal();
    const consentModal = document.getElementById('screenConsentModal');
    if (consentModal && consentModal.style.display !== 'none' && !consentModal.classList.contains('hidden')) {
      respondScreenConsent(false);
    }
  }
});

document.addEventListener('click', (e) => {
  if (e.target.id === 'inAppBrowserModal') closeInAppBrowser();
  if (e.target.id === 'requestTimeModal') closeRequestTimeModal();
  if (e.target.id === 'mockAppModal') closeMockAppModal();
  if (e.target.id === 'violationBlockModal') closeViolationBlockModal();
  if (e.target.id === 'screenConsentModal') respondScreenConsent(false);
});
