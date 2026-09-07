/**
 * File Detail Page JavaScript
 * Extracted from file/file_detail.html
 */

// Load translations from JSON script tag
let translations = {};

// Global variables
let fileId = null;
let fileName = '';
let currentPage = 1;
let totalPages = 0;
let perPage = 10;
let totalChars = 0;
let searchQuery = '';
let caseSensitive = false;
let wholeWord = false;
let percentages = [];
let wordFrequencies = [];
let searchResults = [];
let currentSearchIndex = 0;
let chartInstances = {};
let chartsInitialized = false;

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Load translations and page data from JSON script tag
    const pageDataEl = document.getElementById('file-detail-page-data');
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            translations = data.translations || {};
            // Load page data
            if (data.fileId !== undefined) fileId = data.fileId;
            if (data.fileName) fileName = data.fileName;
            if (data.currentPage !== undefined) currentPage = data.currentPage;
            if (data.totalPages !== undefined) totalPages = data.totalPages;
            if (data.perPage !== undefined) perPage = data.perPage;
            if (data.totalChars !== undefined) totalChars = data.totalChars;
            if (data.searchQuery !== undefined) searchQuery = data.searchQuery;
            if (data.caseSensitive !== undefined) caseSensitive = data.caseSensitive;
            if (data.wholeWord !== undefined) wholeWord = data.wholeWord;
            if (data.percentages) {
                // Ensure percentages is an object/dict, not an array
                if (Array.isArray(data.percentages)) {
                    console.warn('Percentages is an array, converting to object');
                    percentages = {};
                } else {
                    percentages = data.percentages;
                }
            }
            if (data.wordFrequencies) wordFrequencies = data.wordFrequencies;
        } catch (e) {
            console.error('Error parsing file detail page data:', e);
        }
    }
    
    console.log('File detail page loaded');
    console.log(`Total chars: ${totalChars}, Total pages: ${totalPages}`);
    
    // Format content based on file type
    const contentViewer = document.getElementById('contentViewer');
    if (contentViewer) {
        const fileType = contentViewer.getAttribute('data-file-type') || '';
        const filePath = contentViewer.getAttribute('data-file-path') || '';
        const fileIdAttr = contentViewer.getAttribute('data-file-id');
        const fileId = fileIdAttr ? parseInt(fileIdAttr, 10) : null;
        const contentData = contentViewer.getAttribute('data-content') || '';
        
        // Import and apply formatter
        import('../modules/content-formatter.js').then(module => {
            const contentElement = document.getElementById('contentText');
            if (contentElement && contentData) {
                console.log('Formatting content:', {
                    fileType: fileType,
                    filePath: filePath,
                    fileId: fileId,
                    contentLength: contentData.length,
                    preview: contentData.substring(0, 200)
                });
                
                const formattedContent = module.formatContentByType(contentData, fileType, filePath, fileId);
                if (formattedContent) {
                    console.log('✅ Content formatted successfully, length:', formattedContent.length);
                    contentElement.innerHTML = formattedContent;
                    // Ensure proper styling for readability
                    contentElement.style.width = '100%';
                    contentElement.style.wordWrap = 'break-word';
                    contentElement.style.overflowWrap = 'break-word';
                    contentElement.style.whiteSpace = 'pre-wrap';
                    // Store original content for search functionality
                    contentElement.setAttribute('data-original-content', contentData);
                    
                    // Attach image error handlers after DOM insertion
                    // Use setTimeout to ensure DOM is fully updated
                    setTimeout(() => {
                        attachImageErrorHandlers(contentElement);
                    }, 10);
                } else {
                    console.warn('⚠️ Formatter returned empty result');
                    // Ensure proper styling even if formatter fails
                    contentElement.style.width = '100%';
                    contentElement.style.wordWrap = 'break-word';
                    contentElement.style.overflowWrap = 'break-word';
                    contentElement.style.whiteSpace = 'pre-wrap';
                }
            } else {
                console.warn('⚠️ Content element or data not found:', {
                    hasElement: !!contentElement,
                    hasData: !!contentData
                });
            }
        }).catch(err => {
            console.error('Error loading content formatter:', err);
        });
    }
    
    // Verify content element and store original content
    const contentElement = document.getElementById('contentText');
    if (contentElement) {
        const contentLength = contentElement.textContent.length;
        console.log(`Content element found with ${contentLength} characters`);
        
        // Store original content for search functionality (if not already stored)
        if (!contentElement.getAttribute('data-original-content')) {
            const preElement = contentElement.querySelector('pre.content-text');
            if (preElement) {
                contentElement.setAttribute('data-original-content', preElement.textContent);
            } else {
                contentElement.setAttribute('data-original-content', contentElement.textContent);
            }
        }
        
        if (contentLength === 0 && totalChars > 0) {
            console.warn('Content element empty but total_chars indicates content exists');
        }
        
        // Verify content is visible
        if (contentLength > 0) {
            console.log('✅ Content is available and visible');
            
            // Force visibility with explicit styles
            contentElement.style.display = 'block';
            contentElement.style.visibility = 'visible';
            contentElement.style.opacity = '1';
            contentElement.style.color = 'var(--text-dark)';
            contentElement.style.background = 'var(--bg-white)';
            contentElement.style.whiteSpace = 'pre-wrap';
            contentElement.style.wordWrap = 'break-word';
            contentElement.style.overflowWrap = 'break-word';
            contentElement.style.padding = '1rem';
            contentElement.style.margin = '0';
            contentElement.style.boxSizing = 'border-box';
            
            // Use scrollHeight to get actual content height and set it explicitly
            setTimeout(function() {
                const scrollHeight = contentElement.scrollHeight;
                if (scrollHeight > 0) {
                    contentElement.style.height = scrollHeight + 'px';
                    console.log('Set height from scrollHeight:', scrollHeight);
                } else {
                    // Fallback: estimate from content
                    const charCount = contentElement.textContent.length;
                    const estimatedHeight = Math.max(400, Math.ceil(charCount / 4)); // ~4 chars per pixel
                    contentElement.style.height = estimatedHeight + 'px';
                    console.log('Set estimated height:', estimatedHeight);
                }
            }, 10);
            
            // Also ensure parent is visible
            const contentViewer = document.getElementById('contentViewer');
            if (contentViewer) {
                contentViewer.style.display = 'block';
                contentViewer.style.visibility = 'visible';
                contentViewer.style.opacity = '1';
                console.log('✅ Content viewer container made visible');
            }
            
            // Check if content is actually visible
            const computedStyle = window.getComputedStyle(contentElement);
            const rect = contentElement.getBoundingClientRect();
            console.log('Content element computed styles:', {
                display: computedStyle.display,
                visibility: computedStyle.visibility,
                opacity: computedStyle.opacity,
                color: computedStyle.color,
                height: computedStyle.height,
                width: computedStyle.width,
                boundingRect: { width: rect.width, height: rect.height, top: rect.top, left: rect.left }
            });
            
            // If element has no dimensions, force them
            if (rect.height === 0 || rect.width === 0) {
                console.log('Element text content length:', contentElement.textContent.length);
                console.log('Element innerHTML length:', contentElement.innerHTML.length);
                
                // Force explicit dimensions
                contentElement.style.minHeight = '200px';
                contentElement.style.height = 'auto';
                contentElement.style.width = '100%';
                contentElement.style.position = 'relative';
                contentElement.style.whiteSpace = 'pre-wrap';
                contentElement.style.padding = '1rem';
                contentElement.style.margin = '0';
                contentElement.style.boxSizing = 'border-box';
                
                // Force parent dimensions too
                if (contentViewer) {
                    contentViewer.style.minHeight = '400px';
                    contentViewer.style.height = 'auto';
                    contentViewer.style.width = '100%';
                    contentViewer.style.position = 'relative';
                    contentViewer.style.overflow = 'visible';
                }
                
                // Try to force a reflow
                void contentElement.offsetHeight;
                
                // Check again after forcing
                setTimeout(function() {
                    const newRect = contentElement.getBoundingClientRect();
                    console.log('After forcing dimensions:', {
                        width: newRect.width,
                        height: newRect.height,
                        top: newRect.top,
                        left: newRect.left
                    });
                    
                    if (newRect.height === 0) {
                  
                        // Last resort: set explicit height based on content
                        const text = contentElement.textContent || '';
                        const lineCount = text.split('\n').length;
                        const charCount = text.length;
                        // Estimate: ~80 chars per line, ~20px per line
                        const estimatedLines = Math.max(lineCount, Math.ceil(charCount / 80));
                        const estimatedHeight = Math.max(400, estimatedLines * 20);
                        contentElement.style.height = estimatedHeight + 'px';
                        contentElement.style.overflowY = 'auto';
                        console.log('Set explicit height to:', estimatedHeight, 'px (lines:', estimatedLines, ', chars:', charCount, ')');
                        
                        // Also try setting scrollHeight if available
                        if (contentElement.scrollHeight > 0) {
                            contentElement.style.height = contentElement.scrollHeight + 'px';
                            console.log('Using scrollHeight:', contentElement.scrollHeight);
                        }
                    }
                }, 50);
            }
            
            // Last resort: try to make it absolutely visible
            setTimeout(function() {
                contentElement.scrollIntoView({ behavior: 'auto', block: 'start' });
                console.log('Attempted to scroll content into view');
            }, 100);
        } else {
            console.log('⚠️ Content element is empty');
        }
    } else {
        console.warn('Content element not found - this is expected if no content is available');
    }
    
    // Initialize search state
    restoreSearchState();
    
    // Set up tab event listeners with both Bootstrap 5 events and click fallbacks
    const analysisTab = document.getElementById('analysis-tab-btn');
    const metadataTab = document.getElementById('metadata-tab-btn');
    
    if (analysisTab) {
        // Bootstrap 5 event
        analysisTab.addEventListener('shown.bs.tab', function() {
            console.log('Analysis tab shown');
            if (!chartsInitialized) {
                setTimeout(initializeCharts, 100); // Small delay to ensure DOM is ready
            }
        });
        
        // Click fallback for compatibility
        analysisTab.addEventListener('click', function() {
            setTimeout(function() {
                const analysisPane = document.getElementById('tabAnalysis');
                if (analysisPane && analysisPane.classList.contains('active')) {
                    if (!chartsInitialized) {
                        initializeCharts();
                    }
                }
            }, 200);
        });
    }
    
    if (metadataTab) {
        // Bootstrap 5 event
        metadataTab.addEventListener('shown.bs.tab', ensureMetadataVisible);
        
        // Click fallback for compatibility
        metadataTab.addEventListener('click', function() {
            setTimeout(ensureMetadataVisible, 200);
        });
    }
});

// ==================== SEARCH FUNCTIONALITY ====================

function restoreSearchState() {
    try {
        const q = searchQuery;
        const cs = caseSensitive;
        const ww = wholeWord;
        const input = document.getElementById('searchInput');
        const csEl = document.getElementById('caseSensitive');
        const wwEl = document.getElementById('wholeWord');
        if (typeof q === 'string' && q.length > 0 && input) {
            input.value = q;
            if (csEl) csEl.checked = cs;
            if (wwEl) wwEl.checked = ww;
            setTimeout(performSearch, 50);
        }
    } catch (error) {
        console.error('Error restoring search state:', error);
    }
}

function performSearch() {
    const query = document.getElementById('searchInput').value.trim();
    if (!query) {
        clearSearch();
        return;
    }
    
    const caseSensitive = document.getElementById('caseSensitive').checked;
    const wholeWord = document.getElementById('wholeWord').checked;
    
    const contentElement = document.getElementById('contentText');
    if (!contentElement) return;
    
    const content = contentElement.textContent;
    searchResults = [];
    currentSearchIndex = 0;
    
    let pattern = query;
    if (wholeWord) {
        pattern = `\\b${pattern}\\b`;
    }
    
    const flags = caseSensitive ? 'g' : 'gi';
    const regex = new RegExp(pattern, flags);
    
    let match;
    while ((match = regex.exec(content)) !== null) {
        searchResults.push({ 
            index: match.index, 
            length: match[0].length,
            text: match[0]
        });
    }
    
    updateSearchUI();
    highlightMatches();
    document.getElementById('searchResults').style.display = 'block';
    
    if (searchResults.length > 0) {
        scrollToMatch(searchResults[0]);
    }
}

// Expose functions to global scope for onclick handlers
window.performSearch = performSearch;
window.clearSearch = clearSearch;
window.findNext = findNext;
window.findPrevious = findPrevious;
window.goToPage = goToPage;
window.changePageSize = changePageSize;
window.jumpToPage = jumpToPage;
window.copyContent = copyContent;
window.downloadContent = downloadContent;
window.saveMetadata = saveMetadata;
window.toggleFullscreen = toggleFullscreen;
window.shareFile = shareFile;
window.exportFile = exportFile;

function updateSearchUI() {
    const resultCount = document.getElementById('resultCount');
    const currentMatch = document.getElementById('currentMatch');
    
    if (searchResults.length === 0) {
        resultCount.textContent = '0 results';
        resultCount.className = 'badge bg-secondary';
        currentMatch.textContent = translations.noMatches;
        currentMatch.className = 'badge bg-secondary';
    } else {
        resultCount.textContent = `${searchResults.length} result${searchResults.length > 1 ? 's' : ''}`;
        resultCount.className = 'badge bg-primary';
        currentMatch.textContent = `Match ${currentSearchIndex + 1} of ${searchResults.length}`;
        currentMatch.className = 'badge bg-info';
    }
}

function highlightMatches() {
    const contentElement = document.getElementById('contentText');
    if (!contentElement || searchResults.length === 0) {
        if (contentElement) {
            const originalContent = contentElement.getAttribute('data-original-content');
            if (originalContent !== null) {
                contentElement.innerHTML = originalContent;
            }
        }
        return;
    }
    
    if (!contentElement.getAttribute('data-original-content')) {
        contentElement.setAttribute('data-original-content', contentElement.innerHTML);
    }
    
    const content = contentElement.textContent;
    let highlightedContent = '';
    let lastIndex = 0;
    
    // Sort matches by index in ascending order for proper insertion
    const sortedMatches = [...searchResults].sort((a, b) => a.index - b.index);
    
    sortedMatches.forEach((match, index) => {
        // Add text before match
        highlightedContent += escapeHtml(content.substring(lastIndex, match.index));
        
        // Add highlighted match
        const matchText = content.substring(match.index, match.index + match.length);
        const highlightClass = index === currentSearchIndex ? 'search-highlight current-match' : 'search-highlight';
        highlightedContent += `<span class="${highlightClass}">${escapeHtml(matchText)}</span>`;
        
        lastIndex = match.index + match.length;
    });
    
    // Add remaining text
    highlightedContent += escapeHtml(content.substring(lastIndex));
    
    contentElement.innerHTML = highlightedContent;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function findNext() {
    if (searchResults.length === 0) return;
    currentSearchIndex = (currentSearchIndex + 1) % searchResults.length;
    scrollToMatch(searchResults[currentSearchIndex]);
    updateSearchUI();
    highlightMatches();
}

function findPrevious() {
    if (searchResults.length === 0) return;
    currentSearchIndex = (currentSearchIndex - 1 + searchResults.length) % searchResults.length;
    scrollToMatch(searchResults[currentSearchIndex]);
    updateSearchUI();
    highlightMatches();
}

function scrollToMatch(result) {
    const highlights = document.querySelectorAll('.search-highlight');
    if (highlights.length > currentSearchIndex) {
        highlights[currentSearchIndex].scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center'
        });
    }
}

function clearSearch() {
    searchResults = [];
    currentSearchIndex = 0;
    
    const searchInput = document.getElementById('searchInput');
    const caseSensitive = document.getElementById('caseSensitive');
    const wholeWord = document.getElementById('wholeWord');
    const searchResultsDiv = document.getElementById('searchResults');
    
    if (searchInput) searchInput.value = '';
    if (caseSensitive) caseSensitive.checked = false;
    if (wholeWord) wholeWord.checked = false;
    if (searchResultsDiv) searchResultsDiv.style.display = 'none';
    
    // Restore original content
    const contentElement = document.getElementById('contentText');
    if (contentElement) {
        const originalContent = contentElement.getAttribute('data-original-content');
        if (originalContent !== null) {
            contentElement.innerHTML = originalContent;
        } else {
            // Fallback: remove highlights
            const highlightedContent = contentElement.innerHTML;
            const cleanContent = highlightedContent.replace(/<span class="search-highlight[^"]*">([^<]*)<\/span>/g, '$1');
            contentElement.innerHTML = cleanContent;
        }
    }
}

// ==================== PAGINATION ====================

function goToPage(page) {
    if (page < 1 || page > totalPages) return;
    const url = new URL(window.location);
    url.searchParams.set('page', page);
    url.searchParams.set('per_page', perPage);
    window.location.href = url.toString();
}

function changePageSize(newPerPage) {
    const url = new URL(window.location);
    url.searchParams.set('page', 1);
    url.searchParams.set('per_page', newPerPage);
    window.location.href = url.toString();
}

function jumpToPage() {
    const pageInput = document.getElementById('pageJump');
    const page = parseInt(pageInput.value);
    
    if (page >= 1 && page <= totalPages) {
        goToPage(page);
    } else {
        alert(`Please enter a page number between 1 and ${totalPages}`);
        pageInput.value = currentPage;
    }
}

// ==================== CHARTS ====================

function initializeCharts() {
    // Prevent multiple initializations
    if (chartsInitialized) {
        console.log('Charts already initialized, skipping...');
        return;
    }
    
    console.log('Initializing charts...');
    
    if (typeof Chart === 'undefined') {
        console.error('Chart.js not loaded!');
        setTimeout(() => {
            if (typeof Chart !== 'undefined') {
                initializeCharts();
            }
        }, 500);
        return;
    }
    
    Object.values(chartInstances).forEach(chart => {
        if (chart && typeof chart.destroy === 'function') {
            try {
                chart.destroy();
            } catch (e) {
                console.log('Error destroying chart:', e);
            }
        }
    });
    chartInstances = {};
    
    createClassificationChart();
    createFrequencyChart();
    
    // Mark as initialized
    chartsInitialized = true;
    console.log('Charts initialized successfully');
}

function createClassificationChart() {
    const ctx = document.getElementById('classificationChart');
    if (!ctx) {
        console.warn('Classification chart canvas not found');
        return;
    }
    
    if (typeof Chart === 'undefined') {
        ctx.parentElement.innerHTML = `<div class="text-center py-5"><i class="bi bi-exclamation-circle display-4 text-danger"></i><p class="text-danger mt-3">${translations.chartLibraryNotLoaded}</p></div>`;
        return;
    }
    
    const chartPercentages = percentages;
    console.log('Classification percentages data:', chartPercentages);
    
    if (!chartPercentages || Object.keys(chartPercentages).length === 0) {
        console.warn('No classification data available for chart');
        ctx.parentElement.innerHTML = `<div class="text-center py-5"><i class="bi bi-graph-down display-4 text-muted"></i><p class="text-muted mt-3">${translations.noDataAvailable}</p></div>`;
        return;
    }
    
    try {
        const chartLabels = Object.keys(chartPercentages);
        const chartData = Object.values(chartPercentages).map(p => {
            if (typeof p === 'object' && p !== null && 'percentage' in p) {
                return p.percentage || 0;
            }
            return p || 0;
        });
        const colors = generateColors(chartLabels.length);
        
        chartInstances.classification = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: chartLabels,
                datasets: [{
                    data: chartData,
                    backgroundColor: colors,
                    borderColor: colors.map(c => adjustBrightness(c, -20)),
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 10,
                            usePointStyle: true,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => context.label + ': ' + context.parsed.toFixed(1) + '%'
                        }
                    }
                }
            }
        });
        
        // Attach chart controls
        if (window.ChartExport) {
            const chartContainer = ctx.closest('.chart-container, .section-card');
            if (chartContainer) {
                setTimeout(() => {
                    window.ChartExport.attachExportButtonsToCharts(chartContainer);
                }, 100);
            }
        }
    } catch (error) {
        console.error('Error creating classification chart:', error);
        ctx.parentElement.innerHTML = '<div class="text-center py-5"><i class="bi bi-exclamation-circle display-4 text-danger"></i><p class="text-danger mt-3">Error: ' + error.message + '</p></div>';
    }
}

function createFrequencyChart() {
    const ctx = document.getElementById('frequencyChart');
    if (!ctx) {
        console.warn('Frequency chart canvas not found');
        return;
    }
    
    if (typeof Chart === 'undefined') {
        console.error('Chart.js not loaded');
        ctx.parentElement.innerHTML = `<div class="text-center py-5"><i class="bi bi-exclamation-circle display-4 text-danger"></i><p class="text-danger mt-3">${translations.chartLibraryNotLoaded}</p></div>`;
        return;
    }
    
    const wordFreqData = wordFrequencies;
    console.log('Word frequency data:', wordFreqData);
    
    if (!wordFreqData || (Array.isArray(wordFreqData) && wordFreqData.length === 0)) {
        console.log('No word frequency data available');
        ctx.parentElement.innerHTML = `<div class="text-center py-5"><i class="bi bi-graph-down display-4 text-muted"></i><p class="text-muted mt-3">${translations.noFrequencyDataAvailable}</p></div>`;
        return;
    }
    
    try {
        // Handle multiple data formats flexibly
        let topWords = [];
        
        if (Array.isArray(wordFreqData)) {
            topWords = wordFreqData.slice(0, 15);
        } else if (wordFreqData && typeof wordFreqData === 'object') {
            // Convert object to array format
            topWords = Object.entries(wordFreqData)
                .map(([word, count]) => [word, count])
                .sort((a, b) => (b[1] || 0) - (a[1] || 0))
                .slice(0, 15);
        } else {
            console.warn('Unexpected word frequency data format:', typeof wordFreqData);
            ctx.parentElement.innerHTML = `<div class="text-center py-5"><i class="bi bi-graph-down display-4 text-muted"></i><p class="text-muted mt-3">${translations.invalidDataFormat}</p></div>`;
            return;
        }
        
        const freqLabels = topWords.map(w => {
            if (Array.isArray(w)) {
                return String(w[0] || w.word || '');
            }
            if (w && typeof w === 'object') {
                return String(w.word || w.text || w.keyword || '');
            }
            return String(w || '');
        }).filter(label => label.length > 0);
        
        const freqData = topWords.map(w => {
            if (Array.isArray(w)) {
                return Number(w[1] || w.count || w.frequency || 0);
            }
            if (w && typeof w === 'object') {
                return Number(w.count || w.frequency || w.word_count || w.occurrences || 0);
            }
            return Number(w) || 0;
        }).filter(val => !isNaN(val) && val > 0);
        
        if (freqLabels.length === 0 || freqData.length === 0) {
            console.warn('No valid frequency data extracted');
            ctx.parentElement.innerHTML = `<div class="text-center py-5"><i class="bi bi-graph-down display-4 text-muted"></i><p class="text-muted mt-3">${translations.noValidFrequencyData}</p></div>`;
            return;
        }
        
        // Ensure arrays have same length
        const minLength = Math.min(freqLabels.length, freqData.length);
        const finalLabels = freqLabels.slice(0, minLength);
        const finalData = freqData.slice(0, minLength);
        
        console.log(`Creating frequency chart with ${finalLabels.length} items`);
        
        // Create gradient using theme colors
        const chartCtx = ctx.getContext('2d');
        const gradient = chartCtx.createLinearGradient(0, 0, 0, 400);
        const primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--primary-color').trim() || '#4f46e5';
        const secondaryColor = getComputedStyle(document.documentElement).getPropertyValue('--secondary-color').trim() || '#06b6d4';
        gradient.addColorStop(0, primaryColor);
        gradient.addColorStop(1, secondaryColor);
        
        chartInstances.frequency = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: finalLabels,
                datasets: [{
                    label: 'Occurrences',
                    data: finalData,
                    backgroundColor: gradient,
                    borderColor: primaryColor,
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (context) => 'Count: ' + context.parsed.y
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { precision: 0 }
                    },
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                }
            }
        });
        
        // Attach chart controls
        if (window.ChartExport) {
            const chartContainer = ctx.closest('.chart-container, .section-card');
            if (chartContainer) {
                setTimeout(() => {
                    window.ChartExport.attachExportButtonsToCharts(chartContainer);
                }, 100);
            }
        }
        
        console.log('✅ Frequency chart created successfully');
    } catch (error) {
        console.error('Error creating frequency chart:', error);
        console.error('Error stack:', error.stack);
        ctx.parentElement.innerHTML = '<div class="text-center py-5"><i class="bi bi-exclamation-circle display-4 text-danger"></i><p class="text-danger mt-3">Error: ' + (error.message || 'Unknown error') + '</p></div>';
    }
}

// ==================== UTILITY FUNCTIONS ====================

function generateColors(count) {
    const colors = [];
    const hueStep = 360 / count;
    for (let i = 0; i < count; i++) {
        colors.push(`hsl(${i * hueStep}, 70%, 60%)`);
    }
    return colors;
}

function adjustBrightness(color, amount) {
    const usePound = color[0] === '#';
    const col = usePound ? color.slice(1) : color;
    const num = parseInt(col, 16);
    let r = (num >> 16) + amount;
    let g = (num >> 8 & 0x00FF) + amount;
    let b = (num & 0x0000FF) + amount;
    
    r = r > 255 ? 255 : r < 0 ? 0 : r;
    g = g > 255 ? 255 : g < 0 ? 0 : g;
    b = b > 255 ? 255 : b < 0 ? 0 : b;
    
    return (usePound ? '#' : '') + (r << 16 | g << 8 | b).toString(16);
}

// ==================== CONTENT ACTIONS ====================

function copyContent() {
    const content = document.getElementById('contentText').textContent;
    navigator.clipboard.writeText(content).then(() => {
        alert(translations.contentCopiedToClipboard);
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

function downloadContent() {
    const content = document.getElementById('contentText').textContent;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${fileName}_page_${currentPage}_of_${totalPages}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// ==================== METADATA ACTIONS ====================

function saveMetadata() {
    const name = document.getElementById('metaName').value.trim();
    const notes = document.getElementById('metaNotes').value.trim();
    console.log('Saving metadata:', { name, notes });
    alert(translations.metadataSavedSuccessfully);
}

// ==================== FULLSCREEN & SHARE ====================

function toggleFullscreen() {
    const elem = document.documentElement;
    if (!document.fullscreenElement) {
        elem.requestFullscreen().catch(err => {
            alert(translations.error + ': ' + err.message);
        });
    } else {
        document.exitFullscreen();
    }
}

function shareFile() {
    const shareLink = `${window.location.origin}/file/${fileId}/share`;
    const shareText = `Check out this document: ${fileName}`;
    
    if (navigator.share) {
        navigator.share({
            title: fileName,
            text: shareText,
            url: shareLink
        }).catch(err => console.log('Error sharing:', err));
    } else {
        navigator.clipboard.writeText(shareLink).then(() => {
            alert(translations.shareLinkCopiedToClipboard);
        });
    }
}

function exportFile() {
    window.location.href = `/file/${fileId}/export?format=pdf`;
}

function ensureMetadataVisible() {
    const metadataPane = document.getElementById('tabMetadata');
    if (metadataPane) {
        // Force visibility
        metadataPane.style.display = 'block';
        metadataPane.style.visibility = 'visible';
        metadataPane.style.opacity = '1';
        metadataPane.classList.add('show', 'active');
        
        // Remove any conflicting classes
        const allTabPanes = document.querySelectorAll('.tab-pane');
        allTabPanes.forEach(pane => {
            if (pane.id !== 'metadata') {
                pane.classList.remove('show', 'active');
            }
        });
        
        console.log('✅ Metadata tab made visible');
    } else {
        console.warn('Metadata pane element not found');
    }
}

/**
 * Attach image error handlers to all images in the content
 * Global function so it can be used from other modules
 * @param {HTMLElement} container - Container element with images
 */
window.attachImageErrorHandlers = function attachImageErrorHandlers(container) {
    if (!container) return;
    
    const images = container.querySelectorAll('.formatted-image');
    images.forEach(img => {
        const errorDiv = img.nextElementSibling;
        if (!errorDiv || !errorDiv.classList.contains('image-load-error')) return;
        
        const fileId = img.getAttribute('data-file-id') || null;
        const filePath = img.getAttribute('data-file-path') || null;
        const fallbackSources = img.getAttribute('data-fallback-sources');
        
        // Image load success handler
        img.addEventListener('load', function() {
            if (errorDiv) {
                errorDiv.style.display = 'none';
            }
        });
        
        // Image error handler
        img.addEventListener('error', function() {
            let currentIndex = parseInt(img.getAttribute('data-current-source-index') || '0');
            
            // Try fallback sources
            if (fallbackSources) {
                try {
                    const sources = JSON.parse(fallbackSources);
                    if (currentIndex < sources.length - 1) {
                        // Try next fallback source
                        currentIndex++;
                        img.setAttribute('data-current-source-index', currentIndex.toString());
                        img.src = sources[currentIndex];
                        return; // Don't show error yet, try next source
                    }
                } catch (e) {
                    console.error('Error parsing fallback sources:', e);
                }
            }
            
            // All sources failed, show error
            img.style.display = 'none';
            if (errorDiv) {
                errorDiv.style.display = 'block';
                const errorMsg = errorDiv.querySelector('.error-message');
                if (errorMsg) {
                    if (filePath) {
                        errorMsg.innerHTML = 'Image could not be loaded from: ' + filePath + '<br><small>Please ensure the file exists and is accessible.</small>';
                    } else {
                        errorMsg.innerHTML = 'Image could not be loaded. Please ensure the file exists and is accessible.';
                    }
                }
            }
        });
    });
};