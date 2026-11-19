const googleOrigin = 'https://www.google.com';

function googleSearch(query) {
    const url = new URL('/search', googleOrigin);
    url.search = new URLSearchParams({ q: query, safe: 'active', udm: '14' });
    return url;
}

function googleNavigation(rawUrl) {
    const url = new URL(rawUrl);
    if (url.origin !== googleOrigin || url.pathname !== '/search') return null;
    url.searchParams.set('safe', 'active');
    url.searchParams.set('udm', '14');
    return url;
}

module.exports = { googleSearch, googleNavigation };
