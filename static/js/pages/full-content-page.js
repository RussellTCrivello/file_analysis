/**
 * Full Content Page JavaScript
 * Extracted from file/full_content.html
 */

// --- State ---
let fileId = null;
let fileName = '';
let totalChars = 0;
let buffer = []; // array of { offset, data }
let fetching = false;
let eof = false;
let wrap = true;
let fontPx = 14;
let themeDark = false;

// DOM elements (will be initialized after DOM loads)
let elReader, elContent, elSentinel, elStatus, elQ, elPrev, elNext, elClear;
let elWrap, elCopy, elDownload, elPrint, elFontInc, elFontDec, elTheme;
let elRange, elChunkSize, optCase, optWhole;

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    console.log('Full content page loaded');
    
    // Load page data from JSON script tag
    const pageDataEl = document.getElementById('full-content-page-data');
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            fileId = data.fileId;
            fileName = data.fileName || '';
            totalChars = data.totalChars || 0;
        } catch (e) {
            console.error('Error parsing full content page data:', e);
        }
    }
    
    // Initialize DOM elements
    elReader = document.getElementById('reader');
    elContent = document.getElementById('content');
    elSentinel = document.getElementById('sentinel');
    elStatus = document.getElementById('status');
    elQ = document.getElementById('q');
    elPrev = document.getElementById('btnPrev');
    elNext = document.getElementById('btnNext');
    elClear = document.getElementById('btnClear');
    elWrap = document.getElementById('btnWrap');
    elCopy = document.getElementById('btnCopy');
    elDownload = document.getElementById('btnDownload');
    elPrint = document.getElementById('btnPrint');
    elFontInc = document.getElementById('btnFontInc');
    elFontDec = document.getElementById('btnFontDec');
    elTheme = document.getElementById('btnTheme');
    elRange = document.getElementById('rangeJump');
    elChunkSize = document.getElementById('chunkSize');
    optCase = document.getElementById('optCase');
    optWhole = document.getElementById('optWhole');
    
    if (!fileId) {
        console.error('File ID not found');
        if (elStatus) elStatus.textContent = 'Error: File ID not found';
        return;
    }
    
    // Initialize all functionality
    initializeReader();
});

// --- Utilities ---
const escapeHtml = t => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
function setStatus(s) {
    if (elStatus) elStatus.textContent = s;
}

// --- Rendering ---
async function renderBuffer() {
    if (!elContent) return;
    buffer.sort((a, b) => a.offset - b.offset);
    const text = buffer.map(c => c.data).join('');
    
    // Format content based on file type
    const reader = document.getElementById('reader');
    if (reader) {
        const fileType = reader.getAttribute('data-file-type') || '';
        const filePath = reader.getAttribute('data-file-path') || '';
        const fileIdAttr = reader.getAttribute('data-file-id');
        const fileId = fileIdAttr ? parseInt(fileIdAttr, 10) : null;
        
        try {
            const formatter = await import('../modules/content-formatter.js');
            const formatted = formatter.formatContentByType(text, fileType, filePath, fileId);
            if (formatted) {
                elContent.innerHTML = formatted;
                // Ensure proper styling for readability
                elContent.style.width = '100%';
                elContent.style.wordWrap = 'break-word';
                elContent.style.overflowWrap = 'break-word';
                elContent.style.whiteSpace = 'pre-wrap';
                // Attach image error handlers after DOM insertion
                setTimeout(() => {
                    if (window.attachImageErrorHandlers && elContent) {
                        window.attachImageErrorHandlers(elContent);
                    }
                }, 10);
                applyHighlights();
                return;
            }
        } catch (err) {
            console.error('Error formatting content:', err);
        }
    }
    
    // Fallback to plain text with proper formatting
    elContent.innerHTML = escapeHtml(text);
    elContent.style.width = '100%';
    elContent.style.wordWrap = 'break-word';
    elContent.style.overflowWrap = 'break-word';
    elContent.style.whiteSpace = 'pre-wrap';
    applyHighlights();
}

// --- Fetching ---
async function fetchChunk(offset, limit) {
    if (!fileId) throw new Error('File ID not set');
    const url = new URL(window.location.origin + `/file/${fileId}/content`);
    url.searchParams.set('offset', offset);
    url.searchParams.set('limit', limit);
    const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
    if (!res.ok) throw new Error('Fetch failed');
    return res.json();
}

async function ensureNext() {
    if (fetching || eof) return;
    fetching = true;
    const limit = parseInt(elChunkSize ? elChunkSize.value : '50000', 10);
    const nextOffset = buffer.length ? buffer[buffer.length - 1].offset + buffer[buffer.length - 1].data.length : 0;
    if (totalChars && nextOffset >= totalChars) {
        eof = true;
        setStatus('All loaded');
        fetching = false;
        return;
    }
    try {
        setStatus(`Loading ${nextOffset}…`);
        const j = await fetchChunk(nextOffset, limit);
        buffer.push({ offset: j.offset, data: j.content || '' });
        totalChars = j.total_length || totalChars;
        if (!j.has_more) {
            eof = true;
        }
        renderBuffer();
        setStatus(`Loaded ${Math.min(nextOffset + (j.content ? j.content.length : 0), totalChars)} / ${totalChars}`);
    } catch (e) {
        setStatus('Error loading');
        console.error(e);
    } finally {
        fetching = false;
    }
}

// Infinite scroll via IntersectionObserver
let io = null;
if (elReader && elSentinel) {
    io = new IntersectionObserver((entries) => {
        for (const e of entries) {
            if (e.isIntersecting) {
                ensureNext();
            }
        }
    }, { root: elReader, threshold: 0.1 });
    io.observe(elSentinel);
}

// Initialize reader
function initializeReader() {
    // Load initial content from page data
    const pageDataEl = document.getElementById('full-content-page-data');
    let initialContent = '';
    let startChar = 0;
    
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            initialContent = data.initialContent || '';
            startChar = (data.startChar || 1) - 1;
        } catch (e) {
            console.error('Error parsing initial content:', e);
        }
    }
    
    // Bootstrap initial content
    if (initialContent && initialContent.length) {
        buffer.push({ offset: startChar, data: initialContent });
        renderBuffer();
    }
    
    const chunkSize = parseInt(elChunkSize ? elChunkSize.value : '50000', 10);
    if (!initialContent || initialContent.length < chunkSize) {
        ensureNext();
    }
    
    // Setup event listeners
    setupEventListeners();
}

// --- Search ---
let matchPositions = [];
let currentMatch = -1;

function buildRegex(q) {
    if (!q) return null;
    const w = optWhole && optWhole.checked ? `\\b${q}\\b` : q;
    return new RegExp(w, optCase && optCase.checked ? 'g' : 'gi');
}

function computeMatches() {
    if (!elContent || !elQ) return;
    const text = elContent.textContent || '';
    const rx = buildRegex(elQ.value.trim());
    matchPositions = [];
    if (!rx) return;
    let m;
    while ((m = rx.exec(text)) !== null) {
        matchPositions.push({ start: m.index, end: m.index + m[0].length });
        if (m[0].length === 0) rx.lastIndex++;
    }
}

function applyHighlights() {
    if (!elContent || !elQ) return;
    const q = elQ.value.trim();
    if (!q) {
        return;
    }
    computeMatches();
    if (matchPositions.length === 0) {
        return;
    }
    const text = elContent.textContent;
    let out = '';
    let last = 0;
    matchPositions.forEach((p, i) => {
        out += escapeHtml(text.slice(last, p.start));
        out += `<span class="hl${i === currentMatch ? ' current' : ''}">` + escapeHtml(text.slice(p.start, p.end)) + `</span>`;
        last = p.end;
    });
    out += escapeHtml(text.slice(last));
    elContent.innerHTML = out;
}

function gotoMatch(idx) {
    if (matchPositions.length === 0) return;
    currentMatch = (idx + matchPositions.length) % matchPositions.length;
    applyHighlights();
    const spans = elContent ? elContent.querySelectorAll('.hl') : [];
    if (spans[currentMatch]) {
        spans[currentMatch].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    setStatus(`Match ${currentMatch + 1}/${matchPositions.length}`);
}

// Setup event listeners
function setupEventListeners() {
    if (elQ) {
        elQ.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                currentMatch = -1;
                computeMatches();
                gotoMatch(0);
            }
        });
    }
    
    if (elNext) elNext.addEventListener('click', () => gotoMatch(currentMatch + 1));
    if (elPrev) elPrev.addEventListener('click', () => gotoMatch(currentMatch - 1));
    if (elClear) {
        elClear.addEventListener('click', () => {
            if (elQ) elQ.value = '';
            currentMatch = -1;
            matchPositions = [];
            setStatus('Search cleared');
            renderBuffer();
        });
    }
    if (optCase) optCase.addEventListener('change', () => { currentMatch = -1; renderBuffer(); });
    if (optWhole) optWhole.addEventListener('change', () => { currentMatch = -1; renderBuffer(); });
    
    // --- Controls ---
    if (elWrap) {
        elWrap.addEventListener('click', () => {
            wrap = !wrap;
            if (elContent) {
                elContent.classList.toggle('pre-wrap', wrap);
                elContent.classList.toggle('pre', !wrap);
            }
        });
    }
    if (elFontInc) {
        elFontInc.addEventListener('click', () => {
            fontPx = Math.min(24, fontPx + 1);
            if (elContent) elContent.style.fontSize = fontPx + 'px';
        });
    }
    if (elFontDec) {
        elFontDec.addEventListener('click', () => {
            fontPx = Math.max(10, fontPx - 1);
            if (elContent) elContent.style.fontSize = fontPx + 'px';
        });
    }
    if (elTheme) {
        elTheme.addEventListener('click', () => {
            themeDark = !themeDark;
            document.body.classList.toggle('dark', themeDark);
            elTheme.innerHTML = themeDark 
                ? '<i class="bi bi-brightness-high me-1"></i>Light' 
                : '<i class="bi bi-moon me-1"></i>Dark';
        });
    }
    
    const btnTop = document.getElementById('btnTop');
    if (btnTop && elReader) {
        btnTop.addEventListener('click', () => elReader.scrollTo({ top: 0, behavior: 'smooth' }));
    }
    
    const btnBottom = document.getElementById('btnBottom');
    if (btnBottom && elReader) {
        btnBottom.addEventListener('click', () => elReader.scrollTo({ top: elReader.scrollHeight, behavior: 'smooth' }));
    }
    
    if (elRange && elChunkSize) {
        elRange.addEventListener('input', async (e) => {
            const target = parseInt(e.target.value || '0', 10);
            buffer = [];
            eof = false;
            fetching = false;
            setStatus('Jumping…');
            if (elContent) elContent.innerHTML = '';
            const j = await fetchChunk(target, parseInt(elChunkSize.value, 10) || 50000);
            buffer.push({ offset: j.offset, data: j.content || '' });
            totalChars = j.total_length || totalChars;
            eof = !j.has_more;
            renderBuffer();
            if (elReader) elReader.scrollTop = 0;
        });
    }
    
    // Copy/Download/Print
    if (elCopy) {
        elCopy.addEventListener('click', async () => {
            setStatus('Fetching all for copy…');
            await fetchAll();
            if (elContent) {
                navigator.clipboard.writeText(elContent.textContent || '');
            }
            setStatus('Copied to clipboard');
        });
    }
    
    if (elDownload) {
        elDownload.addEventListener('click', async () => {
            setStatus('Preparing download…');
            const text = await getFullText();
            const blob = new Blob([text], { type: 'text/plain' });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = `${encodeURIComponent(fileName || 'file')}.txt`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setStatus('Download started');
        });
    }
    
    if (elPrint) {
        elPrint.addEventListener('click', async () => {
            const text = await getFullText();
            const w = window.open('', '_blank');
            if (!w) return;
            w.document.write(`<pre style="white-space:pre-wrap;font-family:monospace;">${escapeHtml(text)}</pre>`);
            w.document.close();
            w.focus();
            w.print();
        });
    }
}

async function fetchAll() {
    const limit = 100000;
    let offset = 0;
    const parts = [];
    while (!totalChars || offset < totalChars) {
        const j = await fetchChunk(offset, limit);
        parts.push(j.content || '');
        offset += (j.content ? j.content.length : 0);
        totalChars = j.total_length || totalChars;
        if (!j.has_more) break;
    }
    buffer = [{ offset: 0, data: parts.join('') }];
    eof = true;
    renderBuffer();
}

async function getFullText() {
    if (!eof) {
        await fetchAll();
    }
    return elContent ? elContent.textContent || '' : '';
}