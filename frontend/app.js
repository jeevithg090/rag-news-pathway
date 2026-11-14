/**
 * Live AI News Platform - Frontend JavaScript
 * Premium Interactive Experience
 */

const API_BASE = '/api';
const USER_ID_KEY = 'news_ai_user_id';
let wsConnection = null;
let feedReloadTimer = null;
let currentArticleId = null;
let articles = [];
const userId = getOrCreateUserId();

function getOrCreateUserId() {
    try {
        let id = localStorage.getItem(USER_ID_KEY);
        if (!id) {
            id = `user_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
            localStorage.setItem(USER_ID_KEY, id);
        }
        return id;
    } catch (error) {
        return null; // storage unavailable (private mode); personalisation is skipped
    }
}

function withUser(params = {}) {
    const query = new URLSearchParams(params);
    if (userId) query.set('user_id', userId);
    return query.toString();
}

// ============ Initialization ============

document.addEventListener('DOMContentLoaded', () => {
    initializeNavigation();
    initializeEventListeners();
    loadNewsFeed();
    loadStats();
    connectWebSocket();
});

function initializeNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const section = e.currentTarget.dataset.section;
            switchSection(section);
        });
    });
}

function switchSection(section) {
    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.section === section);
    });

    // Update sections
    document.querySelectorAll('.section').forEach(sec => {
        sec.classList.toggle('active', sec.id === `${section}-section`);
    });
}

function initializeEventListeners() {
    // Fetch news button
    document.getElementById('fetch-news-btn').addEventListener('click', fetchNews);

    // Search
    document.getElementById('search-input').addEventListener('input', debounce(filterArticles, 300));
    document.getElementById('category-filter').addEventListener('change', filterArticles);

    // Chat
    document.getElementById('send-chat-btn').addEventListener('click', sendChatMessage);
    document.getElementById('chat-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendChatMessage();
    });

    // Article modal chat
    document.getElementById('send-article-chat-btn').addEventListener('click', sendArticleChatMessage);
    document.getElementById('article-chat-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendArticleChatMessage();
    });

    // Comparison
    document.getElementById('compare-btn').addEventListener('click', compareArticles);
    document.getElementById('compare-select-1').addEventListener('change', updateComparePreview);
    document.getElementById('compare-select-2').addEventListener('change', updateComparePreview);
    document.getElementById('compare-query').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') compareArticles();
    });
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// ============ API Functions ============

async function fetchAPI(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        if (!response.ok) {
            let detail = `HTTP ${response.status}`;
            try {
                const body = await response.json();
                if (typeof body.detail === 'string') detail = body.detail;
            } catch (_) { /* non-JSON error body */ }
            const error = new Error(detail);
            error.status = response.status;
            throw error;
        }

        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        throw error;
    }
}

// ============ Stats ============

async function loadStats() {
    try {
        const stats = await fetchAPI('/stats');
        document.getElementById('indexed-count').textContent = `${stats.rag_engine.indexed_documents} articles indexed`;
        document.getElementById('article-count').textContent = `${stats.rag_engine.indexed_documents} articles`;
    } catch (error) {
        console.error('Failed to load stats');
    }
}

// ============ News Feed ============

async function loadNewsFeed() {
    const feedContainer = document.getElementById('news-feed');
    feedContainer.setAttribute('aria-busy', 'true');
    if (!articles.length) feedContainer.innerHTML = '<div class="loading">Loading articles</div>';

    try {
        const data = await fetchAPI(`/news/feed?${withUser({ limit: 30 })}`);
        articles = data.articles || [];

        renderArticles(articles);
        feedContainer.setAttribute('aria-busy', 'false');
        updateCompareDropdowns();
        updateStats();

    } catch (error) {
        feedContainer.setAttribute('aria-busy', 'false');
        feedContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <h3>Unable to load articles</h3>
                <p>Make sure the backend is running and try again</p>
            </div>
        `;
    }
}

function renderArticles(articlesToRender) {
    const feedContainer = document.getElementById('news-feed');

    if (articlesToRender.length === 0) {
        feedContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📰</div>
                <h3>No articles yet</h3>
                <p>Click "Fetch News" to load the latest articles</p>
            </div>
        `;
        return;
    }

    feedContainer.innerHTML = articlesToRender.map(article => createNewsCard(article)).join('');
    feedContainer.querySelectorAll('.news-card').forEach(card => {
        const open = () => openArticle(card.dataset.articleId);
        card.addEventListener('click', open);
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                open();
            }
        });
    });
}

function createNewsCard(article) {
    const topics = article.topics || [];
    const topicTags = topics.slice(0, 4).map(t => `<span class="topic-tag">${escapeHtml(t)}</span>`).join('');
    const score = article.relevance_score || article.score || 0;

    return `
        <article class="news-card" role="button" tabindex="0" data-article-id="${escapeHtml(article.article_id)}"
            aria-label="Open article: ${escapeHtml(article.title || 'Untitled')}">
            <div class="news-card-content">
                <div class="news-card-meta">
                    <span class="news-category">${escapeHtml(article.category || 'News')}</span>
                    <span class="news-source">${escapeHtml(article.source || '')}</span>
                </div>
                <h3>${escapeHtml(article.title || 'Untitled')}</h3>
                ${topicTags ? `<div class="news-topics">${topicTags}</div>` : ''}
                ${score > 0.5 ? `
                    <div class="relevance-score">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M13 10V3L4 14h7v7l9-11h-7z"/>
                        </svg>
                        <span>${Math.round(score * 100)}% relevant for you</span>
                    </div>
                ` : ''}
            </div>
        </article>
    `;
}

function filterArticles() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    const category = document.getElementById('category-filter').value;

    let filtered = articles;

    if (searchTerm) {
        filtered = filtered.filter(a =>
            (a.title || '').toLowerCase().includes(searchTerm) ||
            (a.topics || []).some(t => t.toLowerCase().includes(searchTerm))
        );
    }

    if (category) {
        filtered = filtered.filter(a => a.category === category);
    }

    renderArticles(filtered);
}

function updateStats() {
    document.getElementById('article-count').textContent = `${articles.length} articles`;
    document.getElementById('indexed-count').textContent = `${articles.length} articles indexed`;
    document.getElementById('last-update').textContent = `Updated ${new Date().toLocaleTimeString()}`;
}

async function fetchNews() {
    const btn = document.getElementById('fetch-news-btn');
    const originalContent = btn.innerHTML;

    btn.innerHTML = `
        <svg class="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
        <span>Fetching...</span>
    `;
    btn.disabled = true;

    try {
        // Fetch from Technology category for speed
        const result = await fetchAPI('/news/fetch?category=Technology&num_results=5', { method: 'POST' });

        if (result.count > 0) {
            showNotification(`✅ Fetched ${result.count} new articles`);
        } else {
            showNotification('No new articles found');
        }

        await loadNewsFeed();
        await loadStats();

    } catch (error) {
        showNotification(`Could not fetch news: ${error.message}`, 'error');
    }

    btn.innerHTML = originalContent;
    btn.disabled = false;
}

let lastFocusedElement = null;

// ============ Article Modal ============

async function openArticle(articleId) {
    currentArticleId = articleId;
    const modal = document.getElementById('article-modal');
    const content = document.getElementById('modal-article-content');

    lastFocusedElement = document.activeElement;
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
    content.innerHTML = '<div class="loading">Loading article</div>';
    resetYouTubeSection();
    modal.querySelector('.modal-close').focus();

    try {
        const data = await fetchAPI(`/news/article/${encodeURIComponent(articleId)}?${withUser()}`);
        const article = data.article;

        content.innerHTML = `
            <span class="news-category">${escapeHtml(article.category || 'News')}</span>
            <h2>${escapeHtml(article.title)}</h2>
            <div style="color: var(--text-secondary); margin-bottom: 1.5rem; font-size: 0.9rem;">
                ${escapeHtml(article.source || 'Unknown source')} • ${article.publish_date ? new Date(article.publish_date).toLocaleDateString() : 'Recent'}
            </div>
            <div class="article-content">${escapeHtml(article.content || 'No content available')}</div>
            ${safeUrl(article.url) ? `<p><a href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">Read the original article</a></p>` : ''}
        `;

        // Show comparison suggestion
        const suggestionDiv = document.getElementById('comparison-suggestion');
        if (data.comparison_suggestion) {
            const s = data.comparison_suggestion;
            suggestionDiv.innerHTML = `
                <p><strong>💡 Want to compare?</strong></p>
                <p style="margin: 0.5rem 0; color: var(--text-secondary);">Similar article: "${escapeHtml(s.titles[1])}"</p>
                <button class="btn-primary" style="margin-top: 0.5rem" data-a="${escapeHtml(s.article_ids[0])}" data-b="${escapeHtml(s.article_ids[1])}" onclick="startComparison(this.dataset.a, this.dataset.b)">
                    Compare Articles
                </button>
            `;
            suggestionDiv.style.display = 'block';
        } else {
            suggestionDiv.style.display = 'none';
        }

        document.getElementById('article-chat-messages').innerHTML = '';

    } catch (error) {
        content.innerHTML = '<div class="empty-state"><p>Error loading article</p></div>';
    }
}

function closeModal() {
    const modal = document.getElementById('article-modal');
    if (!modal.classList.contains('active')) return;
    modal.classList.remove('active');
    modal.setAttribute('aria-hidden', 'true');
    currentArticleId = null;
    if (lastFocusedElement && document.body.contains(lastFocusedElement)) lastFocusedElement.focus();
}

// Close modal on escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

// ============ Chat Functions ============

function setQuery(query) {
    document.getElementById('chat-input').value = query;
    document.getElementById('chat-input').focus();
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const query = input.value.trim();

    if (!query) return;

    input.value = '';
    const messagesDiv = document.getElementById('chat-messages');

    // Add user message
    messagesDiv.innerHTML += `
        <div class="message user">
            <div class="message-avatar">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                </svg>
            </div>
            <div class="message-content"><p>${escapeHtml(query)}</p></div>
        </div>
    `;
    scrollToBottom(messagesDiv);

    // Add loading message
    const loadingId = `loading-${Date.now()}`;
    messagesDiv.innerHTML += `
        <div class="message assistant" id="${loadingId}">
            <div class="message-avatar">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <circle cx="12" cy="12" r="10"/>
                </svg>
            </div>
            <div class="message-content"><div class="loading">Thinking</div></div>
        </div>
    `;
    scrollToBottom(messagesDiv);

    try {
        const result = await fetchAPI('/chat/query', {
            method: 'POST',
            body: JSON.stringify({ query, user_id: userId })
        });

        document.getElementById(loadingId).querySelector('.message-content').innerHTML =
            `<p>${formatResponse(result.response)}</p>${renderSources(result)}`;

    } catch (error) {
        document.getElementById(loadingId).querySelector('.message-content').innerHTML =
            `<p class="error-text">Sorry, something went wrong: ${escapeHtml(error.message)}</p>`;
    }

    scrollToBottom(messagesDiv);
}

async function sendArticleChatMessage() {
    if (!currentArticleId) return;

    const input = document.getElementById('article-chat-input');
    const query = input.value.trim();

    if (!query) return;

    input.value = '';
    const messagesDiv = document.getElementById('article-chat-messages');

    messagesDiv.innerHTML += `<div class="message user"><div class="message-content"><p>${escapeHtml(query)}</p></div></div>`;

    const loadingId = `loading-${Date.now()}`;
    messagesDiv.innerHTML += `<div class="message assistant" id="${loadingId}"><div class="message-content"><div class="loading">Thinking</div></div></div>`;

    try {
        const result = await fetchAPI(`/chat/article/${currentArticleId}`, {
            method: 'POST',
            body: JSON.stringify({ query, expand_context: true, user_id: userId })
        });

        document.getElementById(loadingId).querySelector('.message-content').innerHTML =
            `<p>${formatResponse(result.response)}</p>${renderSources(result)}`;

    } catch (error) {
        document.getElementById(loadingId).querySelector('.message-content').innerHTML =
            `<p class="error-text">Sorry, something went wrong: ${escapeHtml(error.message)}</p>`;
    }

    scrollToBottom(messagesDiv);
}

// ============ Comparison Functions ============

function updateCompareDropdowns() {
    const select1 = document.getElementById('compare-select-1');
    const select2 = document.getElementById('compare-select-2');

    const options = articles.map(a =>
        `<option value="${escapeHtml(a.article_id)}">${escapeHtml(truncate(a.title, 60))}</option>`
    ).join('');

    select1.innerHTML = `<option value="">Select an article...</option>${options}`;
    select2.innerHTML = `<option value="">Select an article...</option>${options}`;
}

function updateComparePreview() {
    const id1 = document.getElementById('compare-select-1').value;
    const id2 = document.getElementById('compare-select-2').value;

    const preview1 = document.getElementById('compare-preview-1');
    const preview2 = document.getElementById('compare-preview-2');

    const article1 = articles.find(a => a.article_id === id1);
    const article2 = articles.find(a => a.article_id === id2);

    preview1.innerHTML = article1 ? `<strong>${escapeHtml(article1.category || 'News')}</strong><br>${escapeHtml(truncate(article1.title, 80))}` : 'No article selected';
    preview2.innerHTML = article2 ? `<strong>${escapeHtml(article2.category || 'News')}</strong><br>${escapeHtml(truncate(article2.title, 80))}` : 'No article selected';
}

function startComparison(id1, id2) {
    closeModal();
    switchSection('compare');

    document.getElementById('compare-select-1').value = id1;
    document.getElementById('compare-select-2').value = id2;
    updateComparePreview();
}

async function compareArticles() {
    const id1 = document.getElementById('compare-select-1').value;
    const id2 = document.getElementById('compare-select-2').value;
    const query = document.getElementById('compare-query').value.trim() || 'Compare these two articles in detail';

    if (!id1 || !id2 || id1 === id2) {
        showNotification('Please select two different articles to compare', 'warning');
        return;
    }

    const resultDiv = document.getElementById('compare-result');
    resultDiv.innerHTML = '<div class="loading">Analyzing articles</div>';

    try {
        const result = await fetchAPI('/chat/compare', {
            method: 'POST',
            body: JSON.stringify({
                article_ids: [id1, id2],
                query,
                user_id: userId
            })
        });

        resultDiv.innerHTML = `<p>${formatResponse(result.response)}</p>`;

    } catch (error) {
        resultDiv.innerHTML = `<p class="error-text">Error comparing articles: ${escapeHtml(error.message)}</p>`;
    }
}

// ============ WebSocket ============

function connectWebSocket() {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('connection-status');

    try {
        const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        wsConnection = new WebSocket(`${scheme}://${window.location.host}/ws/feed`);

        wsConnection.onopen = () => {
            statusDot.classList.add('connected');
            statusText.textContent = 'Connected';
        };

        wsConnection.onmessage = (event) => {
            if (event.data !== 'pong') {
                const data = JSON.parse(event.data);
                if (data.type === 'new_article') {
                    // Coalesce bursts of new articles into a single refresh.
                    clearTimeout(feedReloadTimer);
                    feedReloadTimer = setTimeout(() => { loadNewsFeed(); loadStats(); }, 1000);
                }
            }
        };

        wsConnection.onclose = () => {
            statusDot.classList.remove('connected');
            statusText.textContent = 'Disconnected';
            setTimeout(connectWebSocket, 5000);
        };

        wsConnection.onerror = () => {
            statusDot.classList.remove('connected');
            statusText.textContent = 'Connection error';
        };

    } catch (error) {
        statusText.textContent = 'WebSocket unavailable';
    }
}

// Keep WebSocket alive
setInterval(() => {
    if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
        wsConnection.send('ping');
    }
}, 30000);

// ============ YouTube Analysis Functions ============

let currentYouTubeVideos = [];
let currentArticleTitle = '';
let currentArticleContent = '';

async function fetchYouTubeVideos() {
    const btn = document.getElementById('fetch-youtube-btn');
    const listDiv = document.getElementById('youtube-videos-list');
    const loadingDiv = document.getElementById('youtube-analysis-loading');
    const resultDiv = document.getElementById('youtube-analysis-result');

    // Get article title from modal
    const modalContent = document.getElementById('modal-article-content');
    const titleElement = modalContent.querySelector('h2');
    currentArticleTitle = titleElement ? titleElement.textContent : '';
    const contentElement = modalContent.querySelector('.article-content');
    currentArticleContent = contentElement ? contentElement.textContent.substring(0, 500) : '';

    if (!currentArticleTitle) {
        showNotification('No article loaded', 'error');
        return;
    }

    // Update button state
    btn.disabled = true;
    btn.innerHTML = `
        <svg class="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
        <span>Searching...</span>
    `;

    // Hide previous results
    resultDiv.style.display = 'none';
    loadingDiv.style.display = 'none';

    try {
        const data = await fetchAPI('/youtube/search', {
            method: 'POST',
            body: JSON.stringify({
                query: currentArticleTitle,
                num_results: 5
            })
        });

        currentYouTubeVideos = data.videos || [];

        if (currentYouTubeVideos.length === 0) {
            listDiv.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 1rem;">No related YouTube videos found</p>';
        } else {
            listDiv.innerHTML = currentYouTubeVideos.map((video, index) => `
                <div class="youtube-video-card" data-index="${index}">
                    <div class="video-thumbnail">
                        ${video.thumbnail
                    ? `<img src="${escapeHtml(video.thumbnail)}" alt="" loading="lazy" referrerpolicy="no-referrer"/>`
                    : `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>`
                }
                    </div>
                    <div class="video-info">
                        <h4>${escapeHtml(video.title)}</h4>
                        <div class="video-channel">${escapeHtml(video.channel)}</div>
                        ${video.duration ? `<div class="video-duration">${escapeHtml(video.duration)}</div>` : ''}
                    </div>
                    <button type="button" class="video-analyze-btn" data-index="${index}" aria-label="Analyze video: ${escapeHtml(video.title)}">
                        Analyze
                    </button>
                </div>
            `).join('');
            listDiv.querySelectorAll('.youtube-video-card').forEach(card => {
                card.addEventListener('click', () => selectVideo(Number(card.dataset.index)));
            });
            listDiv.querySelectorAll('.video-analyze-btn').forEach(button => {
                button.addEventListener('click', (event) => {
                    event.stopPropagation();
                    const video = currentYouTubeVideos[Number(button.dataset.index)];
                    if (video) analyzeYouTubeVideo(video.url, video.title);
                });
            });
            listDiv.querySelectorAll('.video-thumbnail img').forEach(img => {
                img.addEventListener('error', () => img.remove(), { once: true });
            });
        }

        listDiv.style.display = 'flex';

    } catch (error) {
        console.error('YouTube search error:', error);
        listDiv.innerHTML = `<p class="error-text" style="text-align: center; padding: 1rem;">Error searching YouTube: ${escapeHtml(error.message)}</p>`;
        listDiv.style.display = 'flex';
    }

    // Reset button
    btn.disabled = false;
    btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="23 7 16 12 23 17 23 7"/>
            <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
        </svg>
        <span>Find Related Videos</span>
    `;
}

function selectVideo(index) {
    // Highlight selected video
    document.querySelectorAll('.youtube-video-card').forEach((card, i) => {
        card.classList.toggle('selected', i === index);
    });
}

async function analyzeYouTubeVideo(videoUrl, videoTitle) {
    const listDiv = document.getElementById('youtube-videos-list');
    const loadingDiv = document.getElementById('youtube-analysis-loading');
    const resultDiv = document.getElementById('youtube-analysis-result');

    // Show loading
    listDiv.style.display = 'none';
    loadingDiv.style.display = 'block';
    resultDiv.style.display = 'none';

    try {
        const data = await fetchAPI('/youtube/analyze', {
            method: 'POST',
            body: JSON.stringify({
                video_url: videoUrl,
                article_title: currentArticleTitle,
                article_content: currentArticleContent,
                video_title: videoTitle
            })
        });

        // Display results
        displayYouTubeAnalysis(data);

    } catch (error) {
        console.error('YouTube analysis error:', error);
        loadingDiv.style.display = 'none';
        listDiv.style.display = 'flex';
        showNotification(`Video analysis failed: ${error.message}`, 'error');
    }
}

function displayYouTubeAnalysis(data) {
    const loadingDiv = document.getElementById('youtube-analysis-loading');
    const resultDiv = document.getElementById('youtube-analysis-result');

    loadingDiv.style.display = 'none';
    resultDiv.style.display = 'block';

    // Set sentiment badge
    const sentimentBadge = document.getElementById('video-sentiment');
    sentimentBadge.textContent = data.sentiment || 'neutral';
    sentimentBadge.className = `sentiment-badge ${data.sentiment || 'neutral'}`;

    // Set key points
    const keyPointsDiv = document.getElementById('video-key-points');
    if (data.key_points && data.key_points.length > 0) {
        keyPointsDiv.innerHTML = `
            <ul>
                ${data.key_points.map(point => `<li>${escapeHtml(point)}</li>`).join('')}
            </ul>
        `;
    } else {
        keyPointsDiv.innerHTML = '';
    }

    // Set analysis text
    const analysisText = document.getElementById('video-analysis-text');
    analysisText.textContent = data.analysis || 'No analysis available.';

    // Set transcript
    const transcriptDiv = document.getElementById('video-transcript');
    transcriptDiv.textContent = data.transcript || 'No transcript available.';

    showNotification('✅ Video analysis complete!');
}

function resetYouTubeSection() {
    ['youtube-videos-list', 'youtube-analysis-loading', 'youtube-analysis-result'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    const list = document.getElementById('youtube-videos-list');
    if (list) list.innerHTML = '';
    currentYouTubeVideos = [];
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
    return text.length > length ? text.substring(0, length) + '...' : text;
}

function formatResponse(text) {
    if (!text) return '';
    // Convert line breaks to <br> and escape HTML
    return escapeHtml(text).replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>');
}

function scrollToBottom(element) {
    element.scrollTop = element.scrollHeight;
}

function showNotification(message, type = 'success') {
    // Create notification element
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 90px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'error' ? 'var(--accent-danger)' : type === 'warning' ? 'var(--accent-warning)' : 'var(--accent-success)'};
        color: white;
        border-radius: 10px;
        font-size: 0.9rem;
        font-weight: 500;
        z-index: 1001;
        animation: slideIn 0.3s ease;
        box-shadow: var(--shadow-lg);
    `;
    notification.setAttribute('role', type === 'error' ? 'alert' : 'status');
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'fadeOut 0.3s ease forwards';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add CSS for spin animation
const style = document.createElement('style');
style.textContent = `
    .spin { animation: spin 1s linear infinite; }
    @keyframes fadeOut { to { opacity: 0; transform: translateX(20px); } }
`;
document.head.appendChild(style);
