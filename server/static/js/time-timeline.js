const OgkTimeline = (() => {
    const SLOTS = 48; // Mỗi ngày 48 khung 30 phút
    const WEEK = 7 * SLOTS;

    function normalize(matrix) {
        if (typeof matrix !== 'string' || !/^[01]+$/.test(matrix)) return '';
        if (matrix.length === WEEK) return matrix;
        if (matrix.length !== 168) return '';
        return [...matrix].map(slot => slot + slot).join(''); // Lịch theo giờ cũ: mỗi giờ thành 2 khung
    }

    function timeLabel(slot) {
        const minute = (slot * 30) % 1440;
        return `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;
    }

    function render(id, policyMatrix, draft, now = new Date()) {
        const element = document.getElementById(id);
        const saved = normalize(policyMatrix);
        if (!element || !saved) {
            if (element) element.hidden = true;
            return;
        }
        const day = (now.getDay() + 6) % 7;
        const matrix = draft ? normalize(draft) : saved;
        const first = day * SLOTS;
        const changed = draft ? [...saved].filter((slot, index) => slot !== matrix[index]).length : 0;
        const position = (now.getHours() * 60 + now.getMinutes()) / 14.4;
        const current = first + now.getHours() * 2 + (now.getMinutes() >= 30 ? 1 : 0);
        const allowed = matrix[current] === '1';
        let next = current + 1;
        while (next < current + WEEK && matrix[next % WEEK] === matrix[current]) next++;
        const dayOffset = Math.floor(next / SLOTS) - day;
        const dayLabel = dayOffset === 0 ? '' : dayOffset === 1 ? ' ngày mai' :
            ` ${['thứ Hai', 'thứ Ba', 'thứ Tư', 'thứ Năm', 'thứ Sáu', 'thứ Bảy', 'Chủ nhật'][Math.floor(next / SLOTS) % 7]}`;
        const summary = next === current + WEEK
            ? (allowed ? 'Cả tuần được dùng theo hạn mức' : 'Cả tuần là giờ nghỉ')
            : `${allowed ? 'Giờ nghỉ' : 'Được dùng lại'} lúc ${timeLabel(next)}${dayLabel}`;
        const slots = [...matrix.slice(first, first + SLOTS)];
        const track = slots.map((slot, index) => {
            const isChanged = slot !== saved[first + index];
            return `<span class="${slot === '1' ? 'is-allowed' : 'is-rest'}${isChanged ? ' is-changed' : ''}"
                title="${timeLabel(index)} · ${slot === '1' ? 'Được dùng' : 'Giờ nghỉ'}${isChanged ? ' · Thay đổi' : ''}"></span>`;
        }).join('');
        const heading = draft ? 'Xem trước lịch hôm nay' : 'Lịch hôm nay';
        const draftNotice = changed ? ` · ${changed} khung 30 phút thay đổi trong tuần` : '';
        element.innerHTML = `
            <div class="ogk-timeline-caption"><strong>${heading}</strong><span>${summary}${draftNotice}</span></div>
            <div class="ogk-timeline-track" aria-hidden="true">${track}<i style="left:${position}%"></i></div>
            <div class="ogk-timeline-axis" aria-hidden="true"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div>
            <p class="ogk-timeline-key"><span><i class="is-allowed"></i>Được dùng</span><span><i class="is-rest"></i>Giờ nghỉ</span><span>│ Hiện tại</span>${changed ? '<span><i class="is-changed"></i>Thay đổi</span>' : ''}</p>`;
        element.hidden = false;
    }

    function weeklySummary(values) {
        if (!Array.isArray(values) || !values.length || !values.every(Number.isFinite)) return '';
        const total = values.reduce((sum, minutes) => sum + minutes, 0);
        if (!total) return 'Chưa ghi nhận thời gian sử dụng trong 7 ngày qua.';
        const days = values.filter(minutes => minutes > 0).length;
        const duration = total < 60 ? `${total} phút` :
            `${Math.floor(total / 60)} giờ${total % 60 ? ` ${total % 60} phút` : ''}`;
        return `Đã dùng ${duration} thiết bị trong ${days}/${values.length} ngày qua.`;
    }

    return { render, normalize, weeklySummary, SLOTS };
})();
