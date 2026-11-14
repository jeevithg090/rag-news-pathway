/**
 * Live AI News - main web UI.
 *
 * Plain JavaScript, no build step. Sections (feed, chat, compare) are switched with the URL
 * hash so the browser back button and deep links work. All server text is escaped before it
 * is inserted into the page.
 */

const API_BASE = '/api';
const USER_ID_KEY = 'news_ai_user_id';
const THEME_KEY = 'news_ai_theme';
const SECTIONS = ['feed', 'chat', 'compare'];
const SECTION_TITLES = { feed: 'Feed', chat: 'AI Chat', compare: 'Compare' };
const DEFAULT_FETCH_CATEGORY = 'Technology';

const state = {
    articles: [],
    personalized: false,
    feedLoaded: false,
    llmConfigured: true,
    currentArticle: null,
    youtubeVideos: [],
    lastFocused: null,
    ws: null,
    feedReloadTimer: null,
};

const userId = getOrCreateUserId();
const $ = (id) => document.getElementById(id);

// ============ Icons ============

const ICONS = {
    news: '<svg aria-hidden="true" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8M15 18h-5M10 6h8v4h-8z"/></svg>',
    search: '<svg aria-hidden="true" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>',
    alert: '<svg aria-hidden="true" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4M12 17h.01"/></svg>',
    spinner: '<svg class="spin" aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>',
    bolt: '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>',
    external: '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>',
    video: '<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>',
};

// ============ Identity & theme ============

function getOrCreateUserId() {
    try {
        let id = localStorage.getItem(USER_ID_KEY);
        if (!id) {
            id = `user_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
            localStorage.setItem(USER_ID_KEY, id);
        }
        return id;
    } catch (_) {
        return null; // storage unavailable (private mode); personalisation is skipped
    }
}

function withUser(params = {}) {
    const query = new URLSearchParams(params);
    if (userId) query.set('user_id', userId);
    return query.toString();
}

const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');

function resolvedTheme() {
    const explicit = document.documentElement.dataset.theme;
    if (explicit === 'light' || explicit === 'dark') return explicit;
    return darkQuery.matches ? 'dark' : 'light';
}

function applyThemeState() {
    const theme = resolvedTheme();
    document.documentElement.dataset.themeResolved = theme;
    const toggle = $('theme-toggle');
    if (toggle) toggle.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
}

function toggleTheme() {
    const next = resolvedTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(THEME_KEY, next); } catch (_) { /* not persisted */ }
    applyThemeState();
}

// ============ Initialisation ============

document.addEventListener('DOMContentLoaded', () => {
    applyThemeState();
    darkQuery.addEventListener('change', applyThemeState);
    bindEvents();
    showSection(sectionFromHash(), { focus: false });
    loadNewsFeed();
    loadStats();
    connectWebSocket();
});

function bindEvents() {
    $('theme-toggle').addEventListener('click', toggleTheme);
    $('fetch-news-btn').addEventListener('click', fetchNews);
    window.addEventListener('hashchange', () => showSection(sectionFromHash(), { focus: true }));

    $('search-input').addEventListener('input', debounce(applyFilters, 200));
    $('category-filter').addEventListener('change', applyFilters);

    $('chat-form').addEventListener('submit', (e) => { e.preventDefault(); sendChatMessage(); });
    $('chat-input').addEventListener('input', () => setFieldError('chat-input', 'chat-error', ''));
    document.querySelectorAll('.hint').forEach(hint => {
        hint.addEventListener('click', () => {
            $('chat-input').value = hint.dataset.query;
            sendChatMessage();
        });
    });

    $('article-chat-form').addEventListener('submit', (e) => { e.preventDefault(); sendArticleChatMessage(); });

    $('compare-form').addEventListener('submit', (e) => { e.preventDefault(); compareArticles(); });
    $('compare-select-1').addEventListener('change', updateComparePreview);
    $('compare-select-2').addEventListener('change', updateComparePreview);

    document.querySelectorAll('[data-close-modal]').forEach(el => el.addEventListener('click', closeModal));
    $('fetch-youtube-btn').addEventListener('click', fetchYouTubeVideos);
    document.addEventListener('keydown', onGlobalKeydown);
}

function debounce(fn, wait) {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn(...args), wait);
    };
}

// ============ Routing ============

function sectionFromHash() {
    const name = window.location.hash.replace(/^#/, '');
    return SECTIONS.includes(name) ? name : 'feed';
}

function showSection(section, { focus }) {
    document.querySelectorAll('.nav-btn').forEach(link => {
        if (link.dataset.section === section) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
    });
    document.querySelectorAll('.section').forEach(sec => {
        sec.hidden = sec.id !== `${section}-section`;
    });
    document.title = section === 'feed'
        ? 'Live AI News | Real-time news with AI chat'
        : `${SECTION_TITLES[section]} | Live AI News`;
    if (focus) {
        const heading = document.querySelector(`#${section}-section h1`);
        if (heading) {
            heading.setAttribute('tabindex', '-1');
            heading.focus({ preventScroll: true });
        }
        window.scrollTo({ top: 0 });
    }
}

function goTo(section) {
    if (sectionFromHash() === section && window.location.hash) showSection(section, { focus: true });
    else window.location.hash = section;
}

// ============ API ============

async function fetchAPI(endpoint, options = {}) {
    let response;
    try {
        response = await fetch(`${API_BASE}${endpoint}`, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...options.headers },
        });
    } catch (_) {
        const error = new Error('Could not reach the server. Check that the backend is running.');
        error.status = 0;
        throw error;
    }

    if (!response.ok) {
        let detail = `Request failed (HTTP ${response.status})`;
        try {
            const body = await response.json();
            if (typeof body.detail === 'string') detail = body.detail;
            else if (Array.isArray(body.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
        } catch (_) { /* non-JSON error body */ }
        const error = new Error(detail);
        error.status = response.status;
        throw error;
    }
    return response.json();
}

// ============ Stats ============

async function loadStats() {
    try {
        const stats = await fetchAPI('/stats');
        const count = stats.rag_engine.indexed_documents;
        state.llmConfigured = Boolean(stats.rag_engine.llm_configured);
        $('indexed-count').textContent = `${plural(count, 'article')} indexed`;
        $('article-count').textContent = plural(count, 'article');
        renderLlmNotice();
    } catch (_) {
        /* the feed shows its own error state */
    }
}

function renderLlmNotice() {
    const existing = document.getElementById('llm-notice');
    if (state.llmConfigured) {
        if (existing) existing.remove();
        return;
    }
    if (existing) return;
    const notice = document.createElement('div');
    notice.id = 'llm-notice';
    notice.className = 'message assistant';
    notice.innerHTML = `
        <div class="message-avatar" aria-hidden="true">i</div>
        <div class="message-content">
            <p><strong>AI answers are switched off.</strong> No language model key is configured on the server
            (<code>OPENROUTER_API_KEY</code>). You can still ask questions: you'll get the most relevant articles as sources.</p>
        </div>`;
    $('chat-messages').appendChild(notice);
}

// ============ Feed ============

function feedSkeleton(count = 6) {
    return Array.from({ length: count }, () =>
        '<div class="news-card skeleton" aria-hidden="true"><span></span><span></span><span></span></div>').join('');
}

async function loadNewsFeed() {
    const feed = $('news-feed');
    feed.setAttribute('aria-busy', 'true');
    if (!state.articles.length) feed.innerHTML = feedSkeleton();

    try {
        const data = await fetchAPI(`/news/feed?${withUser({ limit: 30 })}`);
        state.articles = data.articles || [];
        state.personalized = Boolean(data.personalized);
        state.feedLoaded = true;
        applyFilters();
        updateCompareDropdowns();
        $('article-count').textContent = plural(state.articles.length, 'article');
        $('last-update').textContent = `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } catch (error) {
        $('feed-summary').textContent = '';
        feed.innerHTML = emptyState({
            icon: ICONS.alert,
            title: "Couldn't load the feed",
            body: escapeHtml(error.message),
            actions: '<button type="button" class="btn btn-primary" data-action="retry-feed">Try again</button>',
            error: true,
        });
        feed.querySelector('[data-action="retry-feed"]').addEventListener('click', loadNewsFeed);
    } finally {
        feed.setAttribute('aria-busy', 'false');
    }
}

function emptyState({ icon, title, body, actions = '', error = false }) {
    return `
        <div class="empty-state${error ? ' is-error' : ''}">
            <div class="empty-icon">${icon}</div>
            <h2>${title}</h2>
            <p>${body}</p>
            ${actions ? `<div class="empty-actions">${actions}</div>` : ''}
        </div>`;
}

function applyFilters() {
    const term = $('search-input').value.trim().toLowerCase();
    const category = $('category-filter').value;
    let filtered = state.articles;
    if (term) {
        filtered = filtered.filter(a =>
            (a.title || '').toLowerCase().includes(term) ||
            (a.description || '').toLowerCase().includes(term) ||
            (a.topics || []).some(t => t.toLowerCase().includes(term)));
    }
    if (category) filtered = filtered.filter(a => a.category === category);
    renderArticles(filtered, { filtered: Boolean(term || category) });
}

function renderArticles(list, { filtered }) {
    const feed = $('news-feed');
    const summary = $('feed-summary');

    if (!state.articles.length) {
        summary.textContent = '';
        feed.innerHTML = emptyState({
            icon: ICONS.news,
            title: 'No articles yet',
            body: 'Fetch the latest stories to fill your feed. New articles also appear here automatically while the server is streaming news. No API keys? Start the server with <code>python app.py --demo</code> to explore with sample articles.',
            actions: '<button type="button" class="btn btn-primary" data-action="fetch">Fetch news</button><a class="btn btn-secondary" href="/onboarding/">Personalise first</a>',
        });
        feed.querySelector('[data-action="fetch"]').addEventListener('click', fetchNews);
        return;
    }

    if (!list.length) {
        summary.textContent = 'No matching articles';
        feed.innerHTML = emptyState({
            icon: ICONS.search,
            title: 'No articles match your filters',
            body: 'Try a different search term or category.',
            actions: '<button type="button" class="btn btn-secondary" data-action="clear-filters">Clear filters</button>',
        });
        feed.querySelector('[data-action="clear-filters"]').addEventListener('click', () => {
            $('search-input').value = '';
            $('category-filter').value = '';
            applyFilters();
            $('search-input').focus();
        });
        return;
    }

    const shown = filtered ? `${list.length} of ${plural(state.articles.length, 'article')}` : plural(list.length, 'article');
    const ranked = state.personalized && state.articles.some(personalReason);
    summary.textContent = `${shown} · ${ranked ? 'ranked by your interests' : 'newest first'}`;
    feed.innerHTML = list.map((article, index) => createNewsCard(article, index)).join('');
    feed.querySelectorAll('.card-link').forEach(button => {
        button.addEventListener('click', () => openArticle(button.dataset.articleId));
    });
}

function createNewsCard(article, index) {
    const topics = (article.topics || []).slice(0, 3)
        .map(t => `<span class="topic-tag">${escapeHtml(t)}</span>`).join('');
    const when = relativeTime(article.publish_date);
    const reason = personalReason(article);

    return `
        <article class="news-card" style="animation-delay:${Math.min(index, 8) * 30}ms">
            <div class="news-card-meta">
                <span class="news-category">${escapeHtml(article.category || 'News')}</span>
                ${article.source ? `<span>${escapeHtml(article.source)}</span>` : ''}
                ${when ? `<span aria-hidden="true">·</span><time datetime="${escapeHtml(article.publish_date)}">${when}</time>` : ''}
            </div>
            <h2 class="news-card-title"><button type="button" class="card-link" data-article-id="${escapeHtml(article.article_id)}">${escapeHtml(article.title || 'Untitled')}</button></h2>
            ${article.description ? `<p class="news-card-desc">${escapeHtml(article.description)}</p>` : ''}
            <div class="news-card-footer">
                ${topics ? `<div class="news-topics" aria-label="Topics">${topics}</div>` : '<span></span>'}
                ${reason ? `<span class="relevance-score">${ICONS.bolt}${escapeHtml(truncate(reason, 40))}</span>` : ''}
            </div>
        </article>`;
}

// Only reasons based on the reader's own interests count as personalisation
// ("Fresh news" applies to everyone, so it isn't shown as a match).
function personalReason(article) {
    return (article.reasons || []).find(r => /^(Interested in|Matches interests)/.test(r)) || '';
}

async function fetchNews() {
    const btn = $('fetch-news-btn');
    if (btn.disabled) return;
    const category = $('category-filter').value || DEFAULT_FETCH_CATEGORY;
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    btn.innerHTML = `${ICONS.spinner}<span class="btn-label">Fetching…</span>`;

    try {
        const params = new URLSearchParams({ category, num_results: 5 });
        const result = await fetchAPI(`/news/fetch?${params}`, { method: 'POST' });
        showToast(result.count > 0
            ? `Added ${plural(result.count, 'new article')} from ${category}.`
            : `No new ${category} articles right now. Try again later.`, result.count > 0 ? 'success' : 'warning');
        await Promise.all([loadNewsFeed(), loadStats()]);
    } catch (error) {
        showToast(`Couldn't fetch news: ${error.message}`, 'error');
    } finally {
        btn.innerHTML = original;
        btn.disabled = false;
        btn.removeAttribute('aria-busy');
    }
}

// ============ Article dialog ============

async function openArticle(articleId) {
    const modal = $('article-modal');
    const content = $('modal-article-content');
    state.lastFocused = document.activeElement;
    state.currentArticle = null;

    resetYouTubeSection();
    $('article-chat-messages').innerHTML = '';
    $('article-chat-input').value = '';
    $('comparison-suggestion').hidden = true;
    content.innerHTML = '<h2 id="modal-title" class="sr-only">Loading article</h2><div class="loading" role="status">Loading article…</div>';

    modal.hidden = false;
    document.body.classList.add('modal-open');
    modal.querySelector('.modal-container').scrollTop = 0;
    modal.querySelector('.modal-close').focus();

    try {
        const data = await fetchAPI(`/news/article/${encodeURIComponent(articleId)}?${withUser()}`);
        const article = data.article;
        state.currentArticle = article;
        const date = article.publish_date ? new Date(article.publish_date) : null;
        const dateText = date && !Number.isNaN(date.getTime())
            ? date.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' }) : '';

        content.innerHTML = `
            <span class="news-category">${escapeHtml(article.category || 'News')}</span>
            <h2 id="modal-title">${escapeHtml(article.title || 'Untitled')}</h2>
            <p class="article-meta">${[escapeHtml(article.source || 'Unknown source'), escapeHtml(article.author || ''), dateText].filter(Boolean).join(' · ')}</p>
            <div class="article-content">${escapeHtml(article.content || 'No content available for this article.')}</div>
            ${safeUrl(article.url) ? `<a class="article-link" href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">Read the original article ${ICONS.external}<span class="sr-only">(opens in a new tab)</span></a>` : ''}`;

        renderComparisonSuggestion(data.comparison_suggestion);
    } catch (error) {
        content.innerHTML = `<h2 id="modal-title" class="sr-only">Article unavailable</h2>${emptyState({
            icon: ICONS.alert,
            title: "Couldn't open this article",
            body: escapeHtml(error.status === 404 ? 'It may have been removed from the index.' : error.message),
            error: true,
        })}`;
    }
}

function renderComparisonSuggestion(suggestion) {
    const box = $('comparison-suggestion');
    if (!suggestion || !suggestion.article_ids || suggestion.article_ids.length < 2) {
        box.hidden = true;
        return;
    }
    box.innerHTML = `
        <div>
            <p><strong>Compare with a related story</strong></p>
            <p>${escapeHtml(truncate(suggestion.titles[1], 110))}</p>
        </div>
        <button type="button" class="btn btn-primary btn-sm">Compare articles</button>`;
    box.querySelector('button').addEventListener('click', () =>
        startComparison(suggestion.article_ids[0], suggestion.article_ids[1]));
    box.hidden = false;
}

function closeModal() {
    const modal = $('article-modal');
    if (modal.hidden) return;
    modal.hidden = true;
    document.body.classList.remove('modal-open');
    state.currentArticle = null;
    if (state.lastFocused && document.body.contains(state.lastFocused)) state.lastFocused.focus();
}

function onGlobalKeydown(event) {
    const modal = $('article-modal');
    if (modal.hidden) return;
    if (event.key === 'Escape') {
        event.preventDefault();
        closeModal();
        return;
    }
    if (event.key === 'Tab') trapFocus(event, modal.querySelector('.modal-container'));
}

function trapFocus(event, container) {
    const focusable = [...container.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select, textarea, summary, [tabindex]:not([tabindex="-1"])')]
        .filter(el => el.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
}

// ============ Chat ============

function setFieldError(inputId, errorId, message) {
    $(errorId).textContent = message;
    if (message) $(inputId).setAttribute('aria-invalid', 'true');
    else $(inputId).removeAttribute('aria-invalid');
}

function appendMessage(container, role, html) {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${role}`;
    wrapper.innerHTML = `
        <div class="message-avatar" aria-hidden="true">${role === 'user' ? 'You' : 'AI'}</div>
        <div class="message-content">${html}</div>`;
    container.appendChild(wrapper);
    container.scrollTop = container.scrollHeight;
    return wrapper.querySelector('.message-content');
}

const TYPING = '<span class="typing" role="status" aria-label="Thinking"><span></span><span></span><span></span></span>';

async function runChat({ container, input, button, endpoint, body }) {
    const query = input.value.trim();
    input.value = '';
    appendMessage(container, 'user', `<p>${escapeHtml(query)}</p>`);
    const reply = appendMessage(container, 'assistant', TYPING);
    button.disabled = true;

    try {
        const result = await fetchAPI(endpoint, { method: 'POST', body: JSON.stringify({ query, ...body }) });
        reply.innerHTML = `${formatResponse(result.response)}${renderSources(result)}`;
    } catch (error) {
        reply.classList.add('is-error');
        reply.innerHTML = `<p>Sorry, that didn't work: ${escapeHtml(error.message)}</p>`;
    } finally {
        button.disabled = false;
        container.scrollTop = container.scrollHeight;
        input.focus();
    }
}

async function sendChatMessage() {
    const input = $('chat-input');
    if (!input.value.trim()) {
        setFieldError('chat-input', 'chat-error', 'Type a question first, or pick one of the suggestions.');
        input.focus();
        return;
    }
    setFieldError('chat-input', 'chat-error', '');
    if ($('send-chat-btn').disabled) return;
    await runChat({
        container: $('chat-messages'),
        input,
        button: $('send-chat-btn'),
        endpoint: '/chat/query',
        body: { user_id: userId },
    });
}

async function sendArticleChatMessage() {
    const input = $('article-chat-input');
    if (!state.currentArticle || !input.value.trim() || $('send-article-chat-btn').disabled) {
        input.focus();
        return;
    }
    await runChat({
        container: $('article-chat-messages'),
        input,
        button: $('send-article-chat-btn'),
        endpoint: `/chat/article/${encodeURIComponent(state.currentArticle.article_id)}`,
        body: { expand_context: true, user_id: userId },
    });
}

// ============ Compare ============

function updateCompareDropdowns() {
    const selects = [$('compare-select-1'), $('compare-select-2')];
    const options = state.articles.map(a =>
        `<option value="${escapeHtml(a.article_id)}">${escapeHtml(truncate(a.title, 70))}</option>`).join('');
    const placeholder = state.articles.length ? 'Select an article…' : 'No articles yet: fetch news first';
    selects.forEach(select => {
        const previous = select.value;
        select.innerHTML = `<option value="">${placeholder}</option>${options}`;
        if (state.articles.some(a => a.article_id === previous)) select.value = previous;
    });
    updateComparePreview();
}

function updateComparePreview() {
    [1, 2].forEach(n => {
        const id = $(`compare-select-${n}`).value;
        const preview = $(`compare-preview-${n}`);
        const article = state.articles.find(a => a.article_id === id);
        preview.classList.toggle('has-article', Boolean(article));
        preview.innerHTML = article
            ? `<span class="news-category">${escapeHtml(article.category || 'News')}</span><div>${escapeHtml(truncate(article.title, 120))}</div>`
            : 'No article selected';
    });
    $('compare-error').textContent = '';
}

function startComparison(id1, id2) {
    closeModal();
    goTo('compare');
    $('compare-select-1').value = id1;
    $('compare-select-2').value = id2;
    updateComparePreview();
    $('compare-query').focus();
}

async function compareArticles() {
    const id1 = $('compare-select-1').value;
    const id2 = $('compare-select-2').value;
    const error = $('compare-error');
    if (!id1 || !id2) {
        error.textContent = 'Choose two articles to compare.';
        $(!id1 ? 'compare-select-1' : 'compare-select-2').focus();
        return;
    }
    if (id1 === id2) {
        error.textContent = 'Pick two different articles.';
        $('compare-select-2').focus();
        return;
    }
    error.textContent = '';

    const btn = $('compare-btn');
    if (btn.disabled) return;
    const query = $('compare-query').value.trim() || 'Compare these two articles in detail';
    const resultDiv = $('compare-result');
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `${ICONS.spinner}<span class="btn-label">Comparing…</span>`;
    resultDiv.innerHTML = '<div class="card result-card"><div class="loading" role="status">Analysing both articles…</div></div>';

    try {
        const result = await fetchAPI('/chat/compare', {
            method: 'POST',
            body: JSON.stringify({ article_ids: [id1, id2], query, user_id: userId }),
        });
        resultDiv.innerHTML = `<div class="card result-card"><h2>Comparison</h2>${formatResponse(result.response)}${renderSources(result)}</div>`;
    } catch (err) {
        resultDiv.innerHTML = `<div class="card result-card">${emptyState({
            icon: ICONS.alert, title: "Couldn't compare these articles", body: escapeHtml(err.message), error: true,
        })}</div>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = original;
    }
}

// ============ Live updates (WebSocket) ============

function setConnection(status) {
    const labels = { connected: 'Live updates on', connecting: 'Connecting…', offline: 'Live updates offline' };
    $('connection-status').textContent = labels[status];
    $('status-dot').classList.toggle('connected', status === 'connected');
    const live = $('live-indicator');
    live.classList.toggle('is-live', status === 'connected');
    live.title = labels[status];
    live.querySelector('.live-label').textContent = status === 'connected' ? 'Live' : 'Offline';
}

function connectWebSocket() {
    setConnection('connecting');
    try {
        const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        state.ws = new WebSocket(`${scheme}://${window.location.host}/ws/feed`);
    } catch (_) {
        setConnection('offline');
        return;
    }
    state.ws.onopen = () => setConnection('connected');
    state.ws.onmessage = (event) => {
        if (event.data === 'pong') return;
        let data;
        try { data = JSON.parse(event.data); } catch (_) { return; }
        if (data.type === 'new_article') {
            // Coalesce bursts of new articles into a single refresh.
            clearTimeout(state.feedReloadTimer);
            state.feedReloadTimer = setTimeout(() => { loadNewsFeed(); loadStats(); }, 1000);
        }
    };
    state.ws.onclose = () => {
        setConnection('offline');
        setTimeout(connectWebSocket, 5000);
    };
}

setInterval(() => {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send('ping');
}, 30000);

// ============ YouTube analysis ============

async function fetchYouTubeVideos() {
    const btn = $('fetch-youtube-btn');
    const list = $('youtube-videos-list');
    const article = state.currentArticle;
    if (!article || btn.disabled) return;

    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `${ICONS.spinner}<span class="btn-label">Searching…</span>`;
    $('youtube-analysis-result').hidden = true;
    $('youtube-analysis-loading').hidden = true;
    list.hidden = false;
    list.innerHTML = '<div class="loading" role="status">Searching YouTube…</div>';

    try {
        const data = await fetchAPI('/youtube/search', {
            method: 'POST',
            body: JSON.stringify({ query: article.title, num_results: 5 }),
        });
        state.youtubeVideos = data.videos || [];
        if (!state.youtubeVideos.length) {
            list.innerHTML = '<p class="muted">No related videos found for this article.</p>';
        } else {
            list.innerHTML = state.youtubeVideos.map((video, index) => `
                <div class="youtube-video-card">
                    <div class="video-thumbnail">${video.thumbnail && safeUrl(video.thumbnail)
                        ? `<img src="${escapeHtml(video.thumbnail)}" alt="" loading="lazy" referrerpolicy="no-referrer" width="96" height="54">`
                        : ICONS.video}</div>
                    <div class="video-info">
                        <h4>${escapeHtml(video.title)}</h4>
                        <div class="video-channel">${escapeHtml(video.channel || '')}${video.duration ? ` · ${escapeHtml(video.duration)}` : ''}</div>
                    </div>
                    <button type="button" class="btn btn-secondary btn-sm" data-index="${index}">
                        Analyse<span class="sr-only"> video: ${escapeHtml(video.title)}</span>
                    </button>
                </div>`).join('');
            list.querySelectorAll('button[data-index]').forEach(button => {
                button.addEventListener('click', () => {
                    const video = state.youtubeVideos[Number(button.dataset.index)];
                    if (video) analyzeYouTubeVideo(video);
                });
            });
            list.querySelectorAll('.video-thumbnail img').forEach(img => {
                img.addEventListener('error', () => img.remove(), { once: true });
            });
        }
    } catch (error) {
        list.innerHTML = `<p class="field-error">Couldn't search videos: ${escapeHtml(error.message)}</p>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = original;
    }
}

async function analyzeYouTubeVideo(video) {
    const article = state.currentArticle;
    if (!article) return;
    $('youtube-videos-list').hidden = true;
    $('youtube-analysis-loading').hidden = false;
    $('youtube-analysis-result').hidden = true;

    try {
        const data = await fetchAPI('/youtube/analyze', {
            method: 'POST',
            body: JSON.stringify({
                video_url: video.url,
                video_title: video.title,
                article_title: article.title,
                article_content: (article.content || '').slice(0, 500),
            }),
        });
        displayYouTubeAnalysis(data);
    } catch (error) {
        $('youtube-analysis-loading').hidden = true;
        $('youtube-videos-list').hidden = false;
        showToast(`Video analysis failed: ${error.message}`, 'error');
    }
}

function displayYouTubeAnalysis(data) {
    $('youtube-analysis-loading').hidden = true;
    $('youtube-analysis-result').hidden = false;
    const sentiment = ['positive', 'negative', 'neutral'].includes(data.sentiment) ? data.sentiment : 'neutral';
    const badge = $('video-sentiment');
    badge.textContent = `${sentiment} tone`;
    badge.className = `badge ${sentiment}`;
    $('video-key-points').innerHTML = (data.key_points || []).length
        ? `<ul>${data.key_points.map(p => `<li>${escapeHtml(p)}</li>`).join('')}</ul>` : '';
    $('video-analysis-text').textContent = data.analysis || 'No analysis available.';
    $('video-transcript').textContent = data.transcript || 'No transcript available.';
    showToast('Video analysis complete.');
}

function resetYouTubeSection() {
    ['youtube-videos-list', 'youtube-analysis-loading', 'youtube-analysis-result'].forEach(id => { $(id).hidden = true; });
    $('youtube-videos-list').innerHTML = '';
    state.youtubeVideos = [];
}

// ============ Utilities ============

function renderSources(result) {
    const docs = (result && result.context && result.context.documents) || [];
    if (!docs.length) return '';
    const items = docs.map(doc => {
        const title = escapeHtml(truncate(doc.title || 'Untitled', 90));
        const source = doc.source ? ` <span>(${escapeHtml(doc.source)})</span>` : '';
        return safeUrl(doc.url)
            ? `<li><a href="${escapeHtml(doc.url)}" target="_blank" rel="noopener noreferrer">${title}</a>${source}</li>`
            : `<li>${title}${source}</li>`;
    }).join('');
    return `<div class="message-sources"><strong>Sources</strong><ul>${items}</ul></div>`;
}

function safeUrl(url) {
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'https:' || parsed.protocol === 'http:';
    } catch (_) {
        return false;
    }
}

const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

// Safe for both element content and quoted attribute values.
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text).replace(/[&<>"']/g, ch => HTML_ESCAPES[ch]);
}

function truncate(text, length) {
    if (!text) return '';
    return text.length > length ? `${text.substring(0, length).trimEnd()}…` : text;
}

function plural(count, noun) {
    return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

function relativeTime(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const seconds = Math.round((date.getTime() - Date.now()) / 1000);
    const units = [['year', 31536000], ['month', 2592000], ['week', 604800], ['day', 86400], ['hour', 3600], ['minute', 60]];
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
    for (const [unit, size] of units) {
        if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
    }
    return 'just now';
}

/**
 * Render model output as paragraphs. Text is escaped first; then a small, safe subset of
 * Markdown is applied: **bold**, "- " / "* " bullet lists and "1. " numbered lists.
 */
function formatResponse(text) {
    if (!text) return '';
    const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return escapeHtml(text).split(/\n{2,}/).map(block => {
        const lines = block.split('\n');
        if (lines.every(l => /^\s*[-*]\s+/.test(l))) {
            return `<ul>${lines.map(l => `<li>${inline(l.replace(/^\s*[-*]\s+/, ''))}</li>`).join('')}</ul>`;
        }
        if (lines.every(l => /^\s*\d+\.\s+/.test(l))) {
            return `<ol>${lines.map(l => `<li>${inline(l.replace(/^\s*\d+\.\s+/, ''))}</li>`).join('')}</ol>`;
        }
        return `<p>${inline(lines.join('<br>'))}</p>`;
    }).join('');
}

function showToast(message, type = 'success') {
    const region = $('toast-region');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toast.textContent = message;
    region.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('is-leaving');
        setTimeout(() => toast.remove(), 250);
    }, type === 'error' ? 6000 : 3500);
}
