const googleOrigin = 'https://www.google.com';

function googleSearch(query) {
    const url = new URL('/search', googleOrigin);
    url.search = new URLSearchParams({ q: query, safe: 'active', udm: '14' });
    return url;
}

function googleNavigation(rawUrl) {
    const url = new URL(rawUrl);
    if (url.origin !== googleOrigin) return null;
    if (url.pathname === '/sorry/index') {
        try {
            const next = new URL(url.searchParams.get('continue'));
            if (next.origin === googleOrigin && next.pathname === '/search' &&
                next.searchParams.get('safe') === 'active' && next.searchParams.get('udm') === '14') {
                return url;
            }
        } catch (_) {
            // A verification page must have a Google Search destination.
        }
        return null;
    }
    if (url.pathname !== '/search') return null;
    url.searchParams.set('safe', 'active');
    url.searchParams.set('udm', '14');
    return url;
}

module.exports = { googleSearch, googleNavigation };
