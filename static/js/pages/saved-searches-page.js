/**
 * Saved Searches Page JavaScript
 * Extracted from Search/saved_searches.html
 */

// Load translations from JSON script tag
let translations = {};

document.addEventListener('DOMContentLoaded', function() {
    // Load translations from JSON script tag
    const pageDataEl = document.getElementById('saved-searches-page-data');
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            translations = data.translations || {};
        } catch (e) {
            console.error('Error parsing saved searches page data:', e);
        }
    }
    
    console.log('Saved searches page loaded');
});

// Filter saved searches
function filterSavedSearches() {
    const searchTerm = document.getElementById('searchSaved').value.toLowerCase();
    const cards = document.querySelectorAll('.search-card');
    
    cards.forEach(card => {
        const name = card.dataset.name;
        card.style.display = name.includes(searchTerm) ? '' : 'none';
    });
}


// Run saved search
async function runSearch(searchId) {
    try {
        const response = await fetch(`/search/run/${searchId}`);
        const results = await response.json();
        
        // Redirect to results page
        window.location.href = `/search/results?search_id=${searchId}`;
    } catch (error) {
        alert(translations.errorRunningSearch + ': ' + error.message);
    }
}

// Edit search
function editSearch(searchId) {
    window.location.href = `/search/edit/${searchId}`;
}

// Toggle alert
function toggleAlert(searchId) {
    document.getElementById('alertSearchId').value = searchId;
    new bootstrap.Modal(document.getElementById('alertModal')).show();
}

// Save alert configuration
async function saveAlert() {
    const searchId = document.getElementById('alertSearchId').value;
    const frequency = document.getElementById('alertFrequency').value;
    const emailEnabled = document.getElementById('alertEmail').checked;
    const inAppEnabled = document.getElementById('alertInApp').checked;
    const minDocs = document.getElementById('alertMinDocs').value;
    const active = document.getElementById('alertActive').checked;
    
    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        const response = await fetch('/search/alert/configure', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                search_id: searchId,
                frequency: frequency,
                email_enabled: emailEnabled,
                in_app_enabled: inAppEnabled,
                min_docs: minDocs,
                active: active
            })
        });
        
        if (response.ok) {
            bootstrap.Modal.getInstance(document.getElementById('alertModal')).hide();
            alert(translations.alertConfigurationSaved);
            // ✅ Complete page reload with cache-busting
            window.location.href = window.location.pathname + '?t=' + Date.now();
        } else {
            throw new Error('Failed to save alert');
        }
    } catch (error) {
        alert(translations.error + ': ' + error.message);
    }
}

// Delete search
async function deleteSearch(searchId) {
    if (!confirm(translations.deleteSearchConfirm)) {
        return;
    }
    
    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        const response = await fetch(`/search/delete/${searchId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        });
        
        if (response.ok) {
            alert(translations.searchDeletedSuccessfully);
            // ✅ Complete page reload with cache-busting
            window.location.href = window.location.pathname + '?t=' + Date.now();
        } else {
            throw new Error('Failed to delete search');
        }
    } catch (error) {
        alert(translations.error + ': ' + error.message);
    }
}