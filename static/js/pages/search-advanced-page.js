/**
 * Advanced Search Page JavaScript - Google/YouTube-like Implementation
 * Complete overhaul with professional filtering and intelligent algorithms
 */

// Global state
const searchState = {
    query: '',
    filters: {
        fileType: [],
        categories: [],
        sources: [],
        sides: [],
        dateFrom: '',
        dateTo: '',
        status: ['Read']
    },
    options: {
        caseSensitive: false,
        wholeWord: false,
        useFuzzy: true
    },
    results: [],
    currentPage: 1,
    resultsPerPage: 20,
    totalResults: 0,
    searchTime: 0,
    suggestions: [],
    searchHistory: []
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Advanced Search page loaded - Google-like implementation');
    initializeSearch();
    loadFilterOptions();
    loadSearchHistory();
    setupEventListeners();
});

// Initialize search functionality
function initializeSearch() {
    const mainInput = document.getElementById('mainSearchInput');
    if (!mainInput) return;
    
    // Real-time search suggestions
    let suggestionTimeout;
    mainInput.addEventListener('input', function(e) {
        const query = e.target.value.trim();
        searchState.query = query;
        
        // Show/hide clear button
        const clearBtn = document.getElementById('clearSearchBtn');
        if (clearBtn) {
            clearBtn.style.display = query ? 'block' : 'none';
        }
        
        // Debounce suggestions
        clearTimeout(suggestionTimeout);
        if (query.length >= 2) {
            suggestionTimeout = setTimeout(() => {
                loadSearchSuggestions(query);
            }, 300);
        } else {
            hideSuggestions();
        }
    });
    
    // Enter key to search
    mainInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            executeAdvancedSearch();
        } else if (e.key === 'Escape') {
            hideSuggestions();
        }
    });
    
    // Clear search
    const clearBtn = document.getElementById('clearSearchBtn');
    if (clearBtn) {
        clearBtn.addEventListener('click', function() {
            mainInput.value = '';
            searchState.query = '';
            clearBtn.style.display = 'none';
            hideSuggestions();
            mainInput.focus();
        });
    }
}

// Setup event listeners
function setupEventListeners() {
    // Filter select changes
    ['fileType', 'categoriesSelect', 'sourcesSelect', 'sidesSelect'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', updateFilterChips);
        }
    });
    
    // Date changes
    ['dateFrom', 'dateTo'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', updateFilterChips);
        }
    });
    
    // Status checkboxes
    ['statusRead', 'statusUnread'].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', updateFilterChips);
        }
    });
}

// Load filter options
async function loadFilterOptions() {
    try {
        // Load categories
        const categoriesRes = await fetch('/api/categories');
        const categories = await categoriesRes.json();
        const categoriesSelect = document.getElementById('categoriesSelect');
        if (categoriesSelect && Array.isArray(categories)) {
            categoriesSelect.innerHTML = categories.map(c => 
                `<option value="${c.id}">${c.name}</option>`
            ).join('');
        }
        
        // Load sources (for both search-within and advanced filters)
        const sourcesRes = await fetch('/api/sources');
        const sources = await sourcesRes.json();
        
        // Populate search-within source dropdown
        const searchWithinSource = document.getElementById('searchWithinSource');
        if (searchWithinSource && Array.isArray(sources)) {
            searchWithinSource.innerHTML = '<option value="">{{ _("All Sources") }}</option>' + 
                sources.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
        }
        
        // Populate advanced filters source dropdown
        const sourcesSelect = document.getElementById('sourcesSelect');
        if (sourcesSelect && Array.isArray(sources)) {
            sourcesSelect.innerHTML = sources.map(s => 
                `<option value="${s.id}">${s.name}</option>`
            ).join('');
        }
        
        // Load sides (for both search-within and advanced filters)
        const sidesRes = await fetch('/api/sides');
        const sides = await sidesRes.json();
        
        // Populate search-within side dropdown
        const searchWithinSide = document.getElementById('searchWithinSide');
        if (searchWithinSide && Array.isArray(sides)) {
            searchWithinSide.innerHTML = '<option value="">{{ _("All Sides") }}</option>' + 
                sides.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
        }
        
        // Populate advanced filters side dropdown
        const sidesSelect = document.getElementById('sidesSelect');
        if (sidesSelect && Array.isArray(sides)) {
            sidesSelect.innerHTML = sides.map(s => 
                `<option value="${s.id}">${s.name}</option>`
            ).join('');
        }
        
        // Sync search-within filters with advanced filters panel
        if (searchWithinSource) {
            searchWithinSource.addEventListener('change', function() {
                syncSearchWithinToAdvancedFilters();
            });
        }
        if (searchWithinSide) {
            searchWithinSide.addEventListener('change', function() {
                syncSearchWithinToAdvancedFilters();
            });
        }
    } catch (error) {
        console.error('Error loading filter options:', error);
    }
}

// Sync search-within filters to advanced filters panel
function syncSearchWithinToAdvancedFilters() {
    const searchWithinSource = document.getElementById('searchWithinSource');
    const searchWithinSide = document.getElementById('searchWithinSide');
    const sourcesSelect = document.getElementById('sourcesSelect');
    const sidesSelect = document.getElementById('sidesSelect');
    
    // Sync source
    if (searchWithinSource && sourcesSelect) {
        const sourceId = searchWithinSource.value;
        // Clear all selections first
        Array.from(sourcesSelect.options).forEach(opt => opt.selected = false);
        // Select the search-within source if specified
        if (sourceId) {
            const option = sourcesSelect.querySelector(`option[value="${sourceId}"]`);
            if (option) option.selected = true;
        }
    }
    
    // Sync side
    if (searchWithinSide && sidesSelect) {
        const sideId = searchWithinSide.value;
        // Clear all selections first
        Array.from(sidesSelect.options).forEach(opt => opt.selected = false);
        // Select the search-within side if specified
        if (sideId) {
            const option = sidesSelect.querySelector(`option[value="${sideId}"]`);
            if (option) option.selected = true;
        }
    }
    
    updateFilterChips();
}

// Load search suggestions
async function loadSearchSuggestions(query) {
    try {
        const response = await fetch(`/api/search/suggestions?query=${encodeURIComponent(query)}&limit=8`);
        const data = await response.json();
        
        if (data.suggestions && Array.isArray(data.suggestions)) {
            searchState.suggestions = data.suggestions;
            displaySuggestions(data.suggestions, query);
        }
    } catch (error) {
        console.error('Error loading suggestions:', error);
    }
}

// Display search suggestions
function displaySuggestions(suggestions, query) {
    const dropdown = document.getElementById('searchSuggestions');
    const list = document.getElementById('suggestionsList');
    
    if (!dropdown || !list) return;
    
    if (suggestions.length === 0) {
        hideSuggestions();
        return;
    }
    
    list.innerHTML = suggestions.map(suggestion => `
        <div class="suggestion-item" onclick="selectSuggestion('${suggestion.replace(/'/g, "\\'")}')">
            <i class="bi bi-search"></i>
            <span>${highlightMatch(suggestion, query)}</span>
        </div>
    `).join('');
    
    dropdown.classList.add('active');
}

// Highlight match in suggestion
function highlightMatch(text, query) {
    if (!query) return text;
    const regex = new RegExp(`(${query})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
}

// Select suggestion
function selectSuggestion(suggestion) {
    document.getElementById('mainSearchInput').value = suggestion;
    searchState.query = suggestion;
    hideSuggestions();
    executeAdvancedSearch();
}

// Hide suggestions
function hideSuggestions() {
    const dropdown = document.getElementById('searchSuggestions');
    if (dropdown) {
        dropdown.classList.remove('active');
    }
}

// Update filter chips
function updateFilterChips() {
    const chips = [];
    
    // File types
    const fileTypes = Array.from(document.getElementById('fileType').selectedOptions).map(o => o.value);
    if (fileTypes.length > 0) {
        fileTypes.forEach(type => {
            if (type) chips.push({ type: 'fileType', label: 'File Type', value: type });
        });
    }
    
    // Categories
    const categories = Array.from(document.getElementById('categoriesSelect').selectedOptions).map(o => o.value);
    if (categories.length > 0) {
        categories.forEach(catId => {
            const option = document.getElementById('categoriesSelect').querySelector(`option[value="${catId}"]`);
            if (option) {
                chips.push({ type: 'category', label: 'Category', value: option.textContent, id: catId });
            }
        });
    }
    
    // Sources
    const sources = Array.from(document.getElementById('sourcesSelect').selectedOptions).map(o => o.value);
    if (sources.length > 0) {
        sources.forEach(sourceId => {
            const option = document.getElementById('sourcesSelect').querySelector(`option[value="${sourceId}"]`);
            if (option) {
                chips.push({ type: 'source', label: 'Source', value: option.textContent, id: sourceId });
            }
        });
    }
    
    // Sides
    const sides = Array.from(document.getElementById('sidesSelect').selectedOptions).map(o => o.value);
    if (sides.length > 0) {
        sides.forEach(sideId => {
            const option = document.getElementById('sidesSelect').querySelector(`option[value="${sideId}"]`);
            if (option) {
                chips.push({ type: 'side', label: 'Side', value: option.textContent, id: sideId });
            }
        });
    }
    
    // Date range
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;
    if (dateFrom) {
        chips.push({ type: 'dateFrom', label: 'From', value: dateFrom });
    }
    if (dateTo) {
        chips.push({ type: 'dateTo', label: 'To', value: dateTo });
    }
    
    // Status
    const statusRead = document.getElementById('statusRead').checked;
    const statusUnread = document.getElementById('statusUnread').checked;
    if (statusRead && !statusUnread) {
        chips.push({ type: 'status', label: 'Status', value: 'Analyzed' });
    } else if (!statusRead && statusUnread) {
        chips.push({ type: 'status', label: 'Status', value: 'Pending' });
    }
    
    // Display chips
    displayFilterChips(chips);
    
    // Update active filters count
    const countEl = document.getElementById('activeFiltersCount');
    if (countEl) {
        countEl.textContent = chips.length;
    }
}

// Display filter chips
function displayFilterChips(chips) {
    const container = document.getElementById('filtersChipsContainer');
    const chipsEl = document.getElementById('filtersChips');
    
    if (!container || !chipsEl) return;
    
    if (chips.length === 0) {
        container.style.display = 'none';
        return;
    }
    
    container.style.display = 'block';
    chipsEl.innerHTML = chips.map((chip, index) => {
        const chipClass = chip.priority ? 'filter-chip priority-chip' : 'filter-chip';
        return `
            <div class="${chipClass}">
                <span class="chip-label">${chip.label}:</span>
                <span class="chip-value">${chip.value}</span>
                <button type="button" class="chip-remove" onclick="removeFilterChip(${index}, '${chip.type}', '${chip.id || ''}', ${chip.priority || false})">
                    <i class="bi bi-x"></i>
                </button>
            </div>
        `;
    }).join('');
}

// Remove filter chip
function removeFilterChip(index, type, id, isPriority = false) {
    if (isPriority) {
        // Handle search-within filters
        if (type === 'source') {
            document.getElementById('searchWithinSource').value = '';
            // Also clear from advanced filters
            const sourceSelect = document.getElementById('sourcesSelect');
            Array.from(sourceSelect.options).forEach(opt => opt.selected = false);
        } else if (type === 'side') {
            document.getElementById('searchWithinSide').value = '';
            // Also clear from advanced filters
            const sideSelect = document.getElementById('sidesSelect');
            Array.from(sideSelect.options).forEach(opt => opt.selected = false);
        }
    } else {
        // Handle regular filters
        switch (type) {
            case 'fileType':
                const fileTypeSelect = document.getElementById('fileType');
                const fileTypeOption = fileTypeSelect.querySelector(`option[value="${id}"]`);
                if (fileTypeOption) fileTypeOption.selected = false;
                break;
            case 'category':
                const categorySelect = document.getElementById('categoriesSelect');
                const categoryOption = categorySelect.querySelector(`option[value="${id}"]`);
                if (categoryOption) categoryOption.selected = false;
                break;
            case 'source':
                const sourceSelect = document.getElementById('sourcesSelect');
                const sourceOption = sourceSelect.querySelector(`option[value="${id}"]`);
                if (sourceOption) sourceOption.selected = false;
                // Also clear search-within if it matches
                const searchWithinSource = document.getElementById('searchWithinSource');
                if (searchWithinSource && searchWithinSource.value === id) {
                    searchWithinSource.value = '';
                }
                break;
            case 'side':
                const sideSelect = document.getElementById('sidesSelect');
                const sideOption = sideSelect.querySelector(`option[value="${id}"]`);
                if (sideOption) sideOption.selected = false;
                // Also clear search-within if it matches
                const searchWithinSide = document.getElementById('searchWithinSide');
                if (searchWithinSide && searchWithinSide.value === id) {
                    searchWithinSide.value = '';
                }
                break;
            case 'dateFrom':
                document.getElementById('dateFrom').value = '';
                break;
            case 'dateTo':
                document.getElementById('dateTo').value = '';
                break;
            case 'status':
                document.getElementById('statusRead').checked = true;
                document.getElementById('statusUnread').checked = false;
                break;
        }
    }
    updateFilterChips();
}

// Clear all filters
function clearAllFilters() {
    document.getElementById('fileType').selectedIndex = -1;
    document.getElementById('categoriesSelect').selectedIndex = -1;
    document.getElementById('sourcesSelect').selectedIndex = -1;
    document.getElementById('sidesSelect').selectedIndex = -1;
    document.getElementById('dateFrom').value = '';
    document.getElementById('dateTo').value = '';
    document.getElementById('statusRead').checked = true;
    document.getElementById('statusUnread').checked = false;
    updateFilterChips();
}

// Toggle filters panel
function toggleFiltersPanel() {
    const content = document.getElementById('filtersPanelContent');
    const icon = document.getElementById('filtersToggleIcon');
    
    if (content && icon) {
        content.classList.toggle('active');
        icon.classList.toggle('bi-chevron-down');
        icon.classList.toggle('bi-chevron-up');
    }
}

// Execute advanced search
async function executeAdvancedSearch() {
    const startTime = performance.now();
    const query = document.getElementById('mainSearchInput').value.trim();
    
    if (!query && getActiveFiltersCount() === 0) {
        alert('Please enter a search query or select filters');
        return;
    }
    
    // Hide suggestions
    hideSuggestions();
    
    // Show loading
    showLoading();
    
    // Collect filters - prioritize search-within filters for database optimization
    const searchWithinSource = document.getElementById('searchWithinSource')?.value;
    const searchWithinSide = document.getElementById('searchWithinSide')?.value;
    
    // Get source/side from search-within OR advanced filters (search-within takes priority)
    const sourceIds = searchWithinSource ? [parseInt(searchWithinSource)] : 
                      Array.from(document.getElementById('sourcesSelect').selectedOptions).map(o => parseInt(o.value));
    const sideIds = searchWithinSide ? [parseInt(searchWithinSide)] : 
                    Array.from(document.getElementById('sidesSelect').selectedOptions).map(o => parseInt(o.value));
    
    const filters = {
        file_type: Array.from(document.getElementById('fileType').selectedOptions).map(o => o.value).filter(v => v),
        category_id: Array.from(document.getElementById('categoriesSelect').selectedOptions).map(o => parseInt(o.value)),
        source_id: sourceIds.filter(id => !isNaN(id)),
        side_id: sideIds.filter(id => !isNaN(id)),
        date_from: document.getElementById('dateFrom').value || null,
        date_to: document.getElementById('dateTo').value || null,
        status: []
    };
    
    if (document.getElementById('statusRead').checked) filters.status.push('Read');
    if (document.getElementById('statusUnread').checked) filters.status.push('Unread');
    
    // Show warning if searching without source/side filter (for large databases)
    if (!filters.source_id.length && !filters.side_id.length && !query) {
        const confirmSearch = confirm('Searching without source/side filter may be slow on large databases. Continue?');
        if (!confirmSearch) return;
    }
    
    // Search options
    const options = {
        case_sensitive: document.getElementById('caseSensitive').checked,
        whole_word: document.getElementById('wholeWord').checked,
        use_fuzzy: document.getElementById('useFuzzy').checked
    };
    
    try {
        // Use advanced search API
        const params = new URLSearchParams({
            query: query || '',
            page: searchState.currentPage,
            per_page: searchState.resultsPerPage,
            use_advanced: 'true',
            use_bm25: 'true',
            use_expansion: 'true',
            use_fuzzy: options.use_fuzzy ? 'true' : 'false',
            sort_by: document.getElementById('sortBy').value || 'relevance',
            sort_order: 'desc'
        });
        
        // Add filters
        if (filters.file_type.length > 0) {
            filters.file_type.forEach(type => params.append('file_type', type));
        }
        if (filters.category_id.length > 0) {
            filters.category_id.forEach(id => params.append('category_id', id));
        }
        if (filters.source_id.length > 0) {
            filters.source_id.forEach(id => params.append('source_id', id));
        }
        if (filters.side_id.length > 0) {
            filters.side_id.forEach(id => params.append('side_id', id));
        }
        if (filters.date_from) params.append('date_from', filters.date_from);
        if (filters.date_to) params.append('date_to', filters.date_to);
        
        const response = await fetch(`/api/search?${params.toString()}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        const endTime = performance.now();
        searchState.searchTime = ((endTime - startTime) / 1000).toFixed(2);
        
        // Process results
        if (data.results && Array.isArray(data.results)) {
            searchState.results = data.results;
            searchState.totalResults = data.pagination?.total || data.results.length;
            displayResults(data.results, data.pagination);
        } else {
            searchState.results = [];
            searchState.totalResults = 0;
            displayResults([], null);
        }
        
        // Note: Search history is already saved by the API endpoint
        // This is a backup save (optional, won't cause errors if it fails)
        if (query) {
            // Only save if API didn't already save it (check response)
            // For now, skip to avoid duplicate saves - API already handles it
            // saveToSearchHistory(query, filters);
        }
        
    } catch (error) {
        console.error('Search error:', error);
        alert('Search error: ' + error.message);
        searchState.results = [];
        displayResults([], null);
    } finally {
        hideLoading();
    }
}

// Display results
function displayResults(results, pagination) {
    const section = document.getElementById('searchResultsSection');
    const container = document.getElementById('resultsContainer');
    const countEl = document.getElementById('resultsCount');
    const timeEl = document.getElementById('searchTime');
    
    if (!section || !container) return;
    
    section.style.display = 'block';
    
    if (countEl) {
        countEl.textContent = searchState.totalResults.toLocaleString();
    }
    
    if (timeEl) {
        const pageDataEl = document.getElementById('search-advanced-page-data');
        let timeText = `in ${searchState.searchTime} seconds`;
        if (pageDataEl) {
            try {
                const data = JSON.parse(pageDataEl.textContent);
                timeText = data.translations?.inSeconds?.replace('{seconds}', searchState.searchTime) || timeText;
            } catch (e) {}
        }
        timeEl.textContent = timeText;
    }
    
    if (results.length === 0) {
        container.innerHTML = `
            <div class="text-center py-5">
                <i class="bi bi-search display-4 text-muted d-block mb-3"></i>
                <p class="text-muted">No results found matching your criteria</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = results.map(result => {
        const snippet = result.snippet || result.file_name || '';
        const highlightedSnippet = highlightQueryTerms(snippet, searchState.query);
        
        return `
            <div class="result-item" onclick="window.location.href='/file/${result.id}'">
                <div class="result-title">
                    <i class="bi bi-file-earmark"></i>
                    ${result.file_name || 'Untitled'}
                    ${result.relevance_score ? `<span class="relevance-badge">${Math.round(result.relevance_score * 100)}% match</span>` : ''}
                </div>
                ${snippet ? `<div class="result-snippet">${highlightedSnippet}</div>` : ''}
                <div class="result-meta">
                    <span class="result-meta-item">
                        <i class="bi bi-building"></i>
                        ${result.source_name || 'Unknown'}
                    </span>
                    <span class="result-meta-item">
                        <i class="bi bi-calendar"></i>
                        ${result.file_date ? new Date(result.file_date).toLocaleDateString() : 'N/A'}
                    </span>
                    <span class="result-meta-item">
                        <i class="bi bi-filetype-${result.file_type?.toLowerCase() || 'file'}"></i>
                        ${result.file_type || 'Unknown'}
                    </span>
                    ${result.file_size ? `
                        <span class="result-meta-item">
                            <i class="bi bi-hdd"></i>
                            ${formatFileSize(result.file_size)}
                        </span>
                    ` : ''}
                </div>
                ${result.categories && result.categories.length > 0 ? `
                    <div class="result-badges">
                        ${result.categories.map(cat => `<span class="badge bg-secondary">${cat}</span>`).join('')}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
    
    // Update pagination
    if (pagination && pagination.total_pages > 1) {
        updatePagination(pagination);
    } else {
        const paginationEl = document.getElementById('pagination');
        if (paginationEl) paginationEl.innerHTML = '';
    }
}

// Highlight query terms in text
function highlightQueryTerms(text, query) {
    if (!query || !text) return text;
    
    // Parse query for terms (handle quotes, AND, OR, NOT)
    const terms = parseQueryTerms(query);
    
    let highlighted = text;
    terms.forEach(term => {
        const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        highlighted = highlighted.replace(regex, '<mark>$1</mark>');
    });
    
    return highlighted;
}

// Parse query terms (handle quotes, operators)
function parseQueryTerms(query) {
    const terms = [];
    const quoted = query.match(/"([^"]+)"/g);
    const unquoted = query.replace(/"([^"]+)"/g, '').trim();
    
    if (quoted) {
        quoted.forEach(q => terms.push(q.replace(/"/g, '')));
    }
    
    if (unquoted) {
        unquoted.split(/\s+(?:AND|OR|NOT)\s+/i).forEach(term => {
            const cleanTerm = term.trim().replace(/\b(AND|OR|NOT)\b/gi, '').trim();
            if (cleanTerm) terms.push(cleanTerm);
        });
    }
    
    return terms.length > 0 ? terms : [query];
}

// Update pagination
function updatePagination(pagination) {
    const paginationEl = document.getElementById('pagination');
    if (!paginationEl) return;
    
    import('../modules/rendering/unified-pagination.js').then(module => {
        module.renderUnifiedPagination({
            currentPage: pagination.page,
            totalPages: pagination.total_pages,
            containerId: 'pagination',
            onPageChange: (page) => {
                searchState.currentPage = page;
                executeAdvancedSearch();
            },
            urlParams: {},
            showInfo: true,
            showJump: pagination.total_pages > 5
        });
    }).catch(err => {
        console.error('Error loading pagination:', err);
    });
}

// Show loading
function showLoading() {
    const overlay = document.getElementById('searchLoadingOverlay');
    if (overlay) overlay.style.display = 'flex';
}

// Hide loading
function hideLoading() {
    const overlay = document.getElementById('searchLoadingOverlay');
    if (overlay) overlay.style.display = 'none';
}

// Get active filters count
function getActiveFiltersCount() {
    let count = 0;
    count += document.getElementById('fileType').selectedOptions.length;
    count += document.getElementById('categoriesSelect').selectedOptions.length;
    count += document.getElementById('sourcesSelect').selectedOptions.length;
    count += document.getElementById('sidesSelect').selectedOptions.length;
    if (document.getElementById('dateFrom').value) count++;
    if (document.getElementById('dateTo').value) count++;
    if (!document.getElementById('statusRead').checked || document.getElementById('statusUnread').checked) count++;
    return count;
}

// Reset all filters
function resetAllFilters() {
    document.getElementById('mainSearchInput').value = '';
    searchState.query = '';
    clearAllFilters();
    document.getElementById('caseSensitive').checked = false;
    document.getElementById('wholeWord').checked = false;
    document.getElementById('useFuzzy').checked = true;
    document.getElementById('searchResultsSection').style.display = 'none';
    updateFilterChips();
}

// Feeling lucky (get first result)
async function feelingLucky() {
    searchState.resultsPerPage = 1;
    await executeAdvancedSearch();
    if (searchState.results.length > 0) {
        window.location.href = `/file/${searchState.results[0].id}`;
    }
    searchState.resultsPerPage = 20;
}

// Load search history
async function loadSearchHistory() {
    try {
        const response = await fetch('/api/search/history?limit=10');
        const data = await response.json();
        if (data.history) {
            searchState.searchHistory = data.history;
        }
    } catch (error) {
        console.error('Error loading search history:', error);
    }
}

// Save to search history
async function saveToSearchHistory(query, filters) {
    if (!query || !query.trim()) return; // Don't save empty queries
    
    try {
        const response = await fetch('/api/search/history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                query: query.trim(),
                filters: filters || {},
                result_count: searchState.totalResults || 0
            })
        });
        
        if (!response.ok) {
            // Don't show error to user, just log it
            const errorData = await response.json().catch(() => ({}));
            console.warn('Could not save search history:', errorData.error || 'Unknown error');
        }
    } catch (error) {
        // Silently fail - history saving is not critical
        console.warn('Error saving search history:', error);
    }
}

// Sort results
function sortResults() {
    const sortBy = document.getElementById('sortBy').value;
    searchState.currentPage = 1;
    executeAdvancedSearch();
}

// Export results in various formats
function exportResults(format = 'csv') {
    if (searchState.results.length === 0) {
        alert('No results to export');
        return;
    }
    
    const timestamp = new Date().toISOString().split('T')[0];
    const query = document.getElementById('mainSearchInput')?.value || 'search';
    
    switch (format) {
        case 'csv':
            exportAsCSV(timestamp, query);
            break;
        case 'excel':
            exportAsExcel(timestamp, query);
            break;
        case 'json':
            exportAsJSON(timestamp, query);
            break;
        default:
            exportAsCSV(timestamp, query);
    }
}

// Export as CSV with all details
function exportAsCSV(timestamp, query) {
    // CSV header with all available fields
    const headers = [
        'File ID',
        'File Name',
        'File Path',
        'File Type',
        'File Size (bytes)',
        'File Size (formatted)',
        'File Date',
        'File Status',
        'Source Name',
        'Source ID',
        'Side Name',
        'Side ID',
        'Relevance Score',
        'Categories',
        'Date Created',
        'Snippet'
    ];
    
    const csvRows = [headers.join(',')];
    
    searchState.results.forEach(result => {
        const row = [
            escapeCSV(result.id || ''),
            escapeCSV(result.file_name || ''),
            escapeCSV(result.file_path || ''),
            escapeCSV(result.file_type || ''),
            result.file_size || 0,
            escapeCSV(formatFileSize(result.file_size || 0)),
            escapeCSV(result.file_date ? new Date(result.file_date).toLocaleDateString() : ''),
            escapeCSV(result.file_status || ''),
            escapeCSV(result.source_name || ''),
            result.source_id || '',
            escapeCSV(result.side_name || ''),
            result.side_id || '',
            (result.relevance_score || 0).toFixed(2),
            escapeCSV(Array.isArray(result.categories) ? result.categories.join('; ') : ''),
            escapeCSV(result.date_creation ? new Date(result.date_creation).toLocaleDateString() : ''),
            escapeCSV(result.snippet || '')
        ];
        csvRows.push(row.join(','));
    });
    
    const csv = csvRows.join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    downloadBlob(blob, `search_results_${sanitizeFilename(query)}_${timestamp}.csv`);
}

// Export as Excel (CSV format with .xlsx extension, or use a library)
function exportAsExcel(timestamp, query) {
    // For now, export as CSV with Excel-compatible format
    // In production, you might want to use a library like SheetJS
    exportAsCSV(timestamp, query);
    
    // Alternative: Use server-side Excel generation
    // fetch('/api/search/export', {
    //     method: 'POST',
    //     headers: { 'Content-Type': 'application/json' },
    //     body: JSON.stringify({ results: searchState.results, format: 'excel' })
    // }).then(response => response.blob())
    //   .then(blob => downloadBlob(blob, `search_results_${query}_${timestamp}.xlsx`));
}

// Export as JSON
function exportAsJSON(timestamp, query) {
    const exportData = {
        query: query,
        timestamp: new Date().toISOString(),
        total_results: searchState.totalResults,
        search_time: searchState.searchTime,
        filters: {
            source_id: Array.from(document.getElementById('sourcesSelect')?.selectedOptions || []).map(o => parseInt(o.value)),
            side_id: Array.from(document.getElementById('sidesSelect')?.selectedOptions || []).map(o => parseInt(o.value)),
            categories: Array.from(document.getElementById('categoriesSelect')?.selectedOptions || []).map(o => parseInt(o.value)),
            file_type: Array.from(document.getElementById('fileType')?.selectedOptions || []).map(o => o.value),
            date_from: document.getElementById('dateFrom')?.value || null,
            date_to: document.getElementById('dateTo')?.value || null
        },
        results: searchState.results.map(result => ({
            id: result.id,
            file_name: result.file_name,
            file_path: result.file_path,
            file_type: result.file_type,
            file_size: result.file_size,
            file_size_formatted: formatFileSize(result.file_size || 0),
            file_date: result.file_date,
            file_status: result.file_status,
            source_name: result.source_name,
            source_id: result.source_id,
            side_name: result.side_name,
            side_id: result.side_id,
            relevance_score: result.relevance_score,
            categories: result.categories || [],
            date_creation: result.date_creation,
            snippet: result.snippet
        }))
    };
    
    const json = JSON.stringify(exportData, null, 2);
    const blob = new Blob([json], { type: 'application/json;charset=utf-8;' });
    downloadBlob(blob, `search_results_${sanitizeFilename(query)}_${timestamp}.json`);
}

// Print results
function printResults() {
    if (searchState.results.length === 0) {
        alert('No results to print');
        return;
    }
    
    const query = document.getElementById('mainSearchInput')?.value || 'Search Results';
    const printWindow = window.open('', '_blank');
    
    const printContent = `
<!DOCTYPE html>
<html>
<head>
    <title>Search Results - ${query}</title>
    <style>
        @media print {
            @page { margin: 1cm; }
            body { font-family: Arial, sans-serif; font-size: 10pt; }
            h1 { font-size: 18pt; margin-bottom: 10pt; }
            h2 { font-size: 14pt; margin-top: 15pt; margin-bottom: 8pt; }
            table { width: 100%; border-collapse: collapse; margin-top: 10pt; }
            th, td { border: 1px solid #ddd; padding: 6pt; text-align: left; }
            th { background-color: #f2f2f2; font-weight: bold; }
            tr:nth-child(even) { background-color: #f9f9f9; }
            .header-info { margin-bottom: 15pt; }
            .header-info p { margin: 3pt 0; }
            .no-print { display: none; }
        }
        body { font-family: Arial, sans-serif; font-size: 10pt; padding: 20px; }
        h1 { font-size: 18pt; margin-bottom: 10pt; }
        h2 { font-size: 14pt; margin-top: 15pt; margin-bottom: 8pt; }
        table { width: 100%; border-collapse: collapse; margin-top: 10pt; }
        th, td { border: 1px solid #ddd; padding: 6pt; text-align: left; }
        th { background-color: #f2f2f2; font-weight: bold; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        .header-info { margin-bottom: 15pt; }
        .header-info p { margin: 3pt 0; }
    </style>
</head>
<body>
    <h1>Search Results: ${escapeHtml(query)}</h1>
    <div class="header-info">
        <p><strong>Total Results:</strong> ${searchState.totalResults.toLocaleString()}</p>
        <p><strong>Search Time:</strong> ${searchState.searchTime} seconds</p>
        <p><strong>Date:</strong> ${new Date().toLocaleString()}</p>
    </div>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>File Name</th>
                <th>File Path</th>
                <th>Type</th>
                <th>Size</th>
                <th>Date</th>
                <th>Source</th>
                <th>Side</th>
                <th>Relevance</th>
            </tr>
        </thead>
        <tbody>
            ${searchState.results.map((result, index) => `
                <tr>
                    <td>${index + 1}</td>
                    <td>${escapeHtml(result.file_name || 'N/A')}</td>
                    <td>${escapeHtml(result.file_path || 'N/A')}</td>
                    <td>${escapeHtml(result.file_type || 'N/A')}</td>
                    <td>${formatFileSize(result.file_size || 0)}</td>
                    <td>${result.file_date ? new Date(result.file_date).toLocaleDateString() : 'N/A'}</td>
                    <td>${escapeHtml(result.source_name || 'N/A')}</td>
                    <td>${escapeHtml(result.side_name || 'N/A')}</td>
                    <td>${result.relevance_score ? (result.relevance_score * 100).toFixed(1) + '%' : 'N/A'}</td>
                </tr>
            `).join('')}
        </tbody>
    </table>
    <script>
        window.onload = function() {
            window.print();
        };
    </script>
</body>
</html>`;
    
    printWindow.document.write(printContent);
    printWindow.document.close();
}

// Helper function to escape CSV values
function escapeCSV(value) {
    if (value === null || value === undefined) return '""';
    const stringValue = String(value);
    if (stringValue.includes(',') || stringValue.includes('"') || stringValue.includes('\n')) {
        return `"${stringValue.replace(/"/g, '""')}"`;
    }
    return stringValue;
}

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Helper function to download blob
function downloadBlob(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// Format file size (keep for backward compatibility)
function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

// Helper function to sanitize filename
function sanitizeFilename(filename) {
    return filename.replace(/[^a-z0-9]/gi, '_').toLowerCase().substring(0, 50);
}

// Expose functions globally
if (typeof window !== 'undefined') {
    window.executeAdvancedSearch = executeAdvancedSearch;
    window.resetAllFilters = resetAllFilters;
    window.clearAllFilters = clearAllFilters;
    window.toggleFiltersPanel = toggleFiltersPanel;
    window.removeFilterChip = removeFilterChip;
    window.selectSuggestion = selectSuggestion;
    window.feelingLucky = feelingLucky;
    window.sortResults = sortResults;
    window.exportResults = exportResults;
    window.printResults = printResults;
    console.log('Advanced Search functions exposed globally');
}
