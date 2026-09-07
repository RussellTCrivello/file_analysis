/**
 * Translations Loader
 * Loads translations from API and JSON script tag, sets up window.translations
 * Centralized translation system for the entire application
 */

import { getPageData } from './pages/data-helper.js';

let translationsLoaded = false;
let currentLocale = 'en';

/**
 * Load translations from API
 */
async function loadTranslationsFromAPI(locale = null) {
    try {
        const url = locale 
            ? `/api/translations?locale=${locale}`
            : '/api/translations';
        
        const response = await fetch(url);
        if (!response.ok) {
            console.warn('Failed to load translations from API');
            return {};
        }
        
        const data = await response.json();
        if (data.success && data.translations) {
            currentLocale = data.locale || 'en';
            return data.translations;
        }
        return {};
    } catch (error) {
        console.warn('Error loading translations from API:', error);
        return {};
    }
}

/**
 * Get current locale from API
 */
async function getCurrentLocale() {
    try {
        const response = await fetch('/api/translations/locale');
        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                return data.locale || 'en';
            }
        }
    } catch (error) {
        console.warn('Error getting current locale:', error);
    }
    return 'en';
}

/**
 * Load all translations (from API and page data)
 */
export async function loadTranslations(forceReload = false) {
    if (translationsLoaded && !forceReload) {
        return;
    }
    
    // Initialize translations object
    window.translations = window.translations || {};
    window.appTranslations = window.appTranslations || {};
    
    // Get current locale
    currentLocale = await getCurrentLocale();
    window.currentLocale = currentLocale;
    
    // Load translations from API (centralized)
    const apiTranslations = await loadTranslationsFromAPI(currentLocale);
    if (apiTranslations && Object.keys(apiTranslations).length > 0) {
        Object.assign(window.translations, apiTranslations);
        Object.assign(window.appTranslations, apiTranslations);
    }
    
    // Get translations from JSON script tag (page-specific)
    const pageTranslations = getPageData('translations');
    if (pageTranslations && Object.keys(pageTranslations).length > 0) {
        Object.assign(window.translations, pageTranslations);
        Object.assign(window.appTranslations, pageTranslations);
    }
    
    // Merge with existing appTranslations from base.html if present
    if (window.appTranslations && Object.keys(window.appTranslations).length > 0) {
        Object.assign(window.translations, window.appTranslations);
    }
    
    translationsLoaded = true;
    
    // Dispatch event that translations are loaded
    window.dispatchEvent(new CustomEvent('translationsLoaded', {
        detail: { locale: currentLocale, translations: window.translations }
    }));
    
    console.log(`✅ Translations loaded for locale: ${currentLocale}`);
}

/**
 * Reload translations for a specific locale
 */
export async function reloadTranslations(locale) {
    translationsLoaded = false;
    await loadTranslations(true);
}

/**
 * Get translation for a key
 */
export function getTranslation(key, defaultValue = null) {
    if (!window.translations) {
        return defaultValue || key;
    }
    return window.translations[key] || defaultValue || key;
}

// Load translations when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => loadTranslations());
} else {
    loadTranslations();
}

// Export for use in other modules
export { currentLocale };

