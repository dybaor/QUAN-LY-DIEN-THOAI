/**
 * ==============================================================================
 * OGK SYSTEM - PARENT DASHBOARD AUTH & PIN VERIFICATION (app.js)
 * ==============================================================================
 */

async function submitPinAuth(event) {
    if (event && event.preventDefault) {
        event.preventDefault();
    }
    const pinInputElement = document.getElementById('authPinInput') || document.getElementById('onboardingLockPin');
    const pinInput = (pinInputElement ? pinInputElement.value : '').trim();

    if (!pinInput) {
        const errorEl = document.getElementById('onboardingErrorText');
        if (errorEl) {
            errorEl.innerText = "Vui lòng nhập mã PIN bảo mật!";
            errorEl.classList.remove('hidden');
        }
        if (typeof showToast === 'function') {
            showToast("Vui lòng nhập mã PIN bảo mật!", "error");
        }
        return;
    }

    try {
        const res = await fetch('/api/auth/verify-pin', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ pin: pinInput })
        });
        const data = await res.json();
        if (data.success || data.valid || data.verified || data.status === 'success') {
            // Đóng modal xác thực ngay lập tức
            const authModal = document.getElementById('authModal') || document.getElementById('onboardingModal');
            if (authModal) {
                authModal.classList.add('hidden');
                authModal.classList.remove('flex');
            }
            // Mở khóa tương tác Dashboard
            document.body.classList.remove('modal-open');
            sessionStorage.setItem('ogk_parent_auth', 'true');
            sessionStorage.setItem('ogk_parent_unlocked', '1');

            // Đồng bộ tên bé lên Header
            if (data.child_name) {
                const childHeader = document.getElementById('childNameHeader');
                if (childHeader) childHeader.innerText = data.child_name;
                const parentChildDisplay = document.getElementById('parentChildNameDisplay');
                if (parentChildDisplay) parentChildDisplay.innerText = data.child_name;
                if (typeof updateChildNameDisplay === 'function') {
                    updateChildNameDisplay(data.child_name);
                }
            }

            if (typeof showToast === 'function') {
                showToast("Đăng nhập thành công!", "success");
            }

            // Bắn tín hiệu WebSocket phụ huynh đã xác thực
            if (window.parentWs && window.parentWs.readyState === WebSocket.OPEN) {
                try {
                    window.parentWs.send(JSON.stringify({
                        action: 'parent_authenticated',
                        child_id: 1
                    }));
                } catch (err) {}
            }
        } else {
            const errorEl = document.getElementById('onboardingErrorText');
            if (errorEl) {
                errorEl.innerText = data.message || "Mã PIN không chính xác. Vui lòng thử lại!";
                errorEl.classList.remove('hidden');
            }
            if (typeof showToast === 'function') {
                showToast(data.message || "Mã PIN không chính xác. Vui lòng thử lại!", "error");
            }
        }
    } catch (e) {
        console.error("Lỗi xác thực PIN:", e);
        if (typeof showToast === 'function') {
            showToast("Lỗi kết nối máy chủ khi xác thực PIN!", "error");
        }
    }
}

// Gắn ra window scope để gọi được từ inline onclick hoặc event listener
window.submitPinAuth = submitPinAuth;

