/**
 * Language Switcher - Seamless language switching with instant UI updates
 * Handles language changes via AJAX for smooth, fast transitions
 */

class LanguageSwitcher {
    constructor() {
        this.isChanging = false;
        this.init();
    }

    init() {
        // Setup dropdown handler
        this.setupDropdownHandler();
        
        // Setup top bar quick language menu (event delegation)
        document.addEventListener('click', (e) => {
            const item = e.target.closest('[data-language-switch]');
            if (item && !this.isChanging) {
                e.preventDefault();
                this.changeLanguage(item.getAttribute('data-language-switch'));
            }
        });
        
        // Listen for system setting changes
        document.addEventListener('systemSettingChanged', (e) => {
            if (e.detail.key === 'language') {
                this.handleLanguageChange(e.detail.value, false);
            }
        });
    }

    /**
     * Setup dropdown change handler
     */
    setupDropdownHandler() {
        const languageSelect = document.getElementById('sidebarLanguageSelect');
        if (languageSelect) {
            languageSelect.addEventListener('change', (e) => {
                const selectedLanguage = e.target.value;
                if (selectedLanguage && !this.isChanging) {
                    this.changeLanguage(selectedLanguage);
                }
            });
        }
    }

    /**
     * Change language seamlessly with retry logic and comprehensive error handling
     * @param {string} languageCode - Language code to switch to
     * @param {number} retryCount - Internal retry counter
     */
    async changeLanguage(languageCode, retryCount = 0) {
        if (this.isChanging) {
            console.warn('Language change already in progress, ignoring duplicate request');
            return;
        }

        // Validate language code
        if (!languageCode || typeof languageCode !== 'string') {
            console.error('Invalid language code:', languageCode);
            this.showError(window.t ? window.t('Invalid language code') : 'Invalid language code');
            return;
        }

        this.isChanging = true;
        const languageSelect = document.getElementById('sidebarLanguageSelect');
        const originalValue = languageSelect ? languageSelect.value : null;
        const maxRetries = 2;

        try {
            // Show loading state
            this.showLoadingState(languageSelect);

            // Step 1: Apply RTL/LTR immediately for instant visual feedback
            if (window.RTLManager) {
                try {
                    window.RTLManager.applyDirection(languageCode);
                } catch (rtlError) {
                    console.warn('RTL Manager error (non-critical):', rtlError);
                    // Continue even if RTL fails
                }
            } else {
                // Fallback: Apply direction directly if RTLManager not available
                const htmlElement = document.documentElement;
                const isRTL = ['ar', 'fa', 'he', 'ur'].includes(languageCode);
                htmlElement.setAttribute('dir', isRTL ? 'rtl' : 'ltr');
                htmlElement.setAttribute('lang', languageCode);
            }

            // Step 2: Update language via API with retry logic
            let response;
            let data;
            let apiSuccess = false;

            for (let attempt = 0; attempt <= maxRetries; attempt++) {
                try {
                    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
                    
                    response = await fetch(`/api/settings/system/language`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                            'Accept': 'application/json',
                            'X-CSRFToken': csrfToken
                        },
                        credentials: 'same-origin',
                        body: JSON.stringify({ value: languageCode }),
                        cache: 'no-store' // Prevent caching
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    data = await response.json();

                    if (data.success) {
                        apiSuccess = true;
                        break; // Success, exit retry loop
                    } else {
                        throw new Error(data.error || (window.t ? window.t('Failed to change language') : 'Failed to change language'));
                    }
                } catch (apiError) {
                    console.warn(`Language change API attempt ${attempt + 1} failed:`, apiError);
                    
                    if (attempt < maxRetries) {
                        // Wait before retry (exponential backoff)
                        await new Promise(resolve => setTimeout(resolve, 300 * (attempt + 1)));
                        continue;
                    } else {
                        throw apiError; // All retries failed
                    }
                }
            }

            if (!apiSuccess) {
                throw new Error(window.t ? window.t('Failed to change language') : 'Failed to change language');
            }

            // Step 3: Update dropdown to reflect change
            if (languageSelect) {
                languageSelect.value = languageCode;
            }

            // Step 4: Store in sessionStorage as backup and update Language Persistence
            try {
                sessionStorage.setItem('userLanguage', languageCode);
                sessionStorage.setItem('languageChangeTime', Date.now().toString());
                sessionStorage.setItem('userExplicitLanguage', 'true'); // Mark as user explicit
                
                // Update Language Persistence Manager if available (mark as user explicit)
                if (window.LanguagePersistence) {
                    window.LanguagePersistence.updateLanguage(languageCode, false, true);
                }
            } catch (e) {
                console.warn('Could not store language in sessionStorage:', e);
            }

            // Step 5: Reload translations if available
            if (window.translations && typeof window.reloadTranslations === 'function') {
                try {
                    await window.reloadTranslations(languageCode);
                } catch (e) {
                    console.warn('Could not reload translations dynamically:', e);
                    // Non-critical, continue with page reload
                }
            }

            // Step 6: Dispatch event for other components
            document.dispatchEvent(new CustomEvent('languageChanged', {
                detail: { language: languageCode, success: true }
            }));

            // Step 6.5: Ensure Language Persistence Manager knows this is explicit
            // This prevents any response headers from overriding the user's choice
            if (window.LanguagePersistence) {
                // Force update with explicit flag
                window.LanguagePersistence.userExplicitlySetLanguage = true;
                window.LanguagePersistence.currentLanguage = languageCode;
            }

            // Step 7: Smooth page reload with fade transition
            this.reloadPageSmoothly();
        } catch (error) {
            console.error('Error changing language:', error);
            
            // Revert dropdown if error
            if (languageSelect && originalValue) {
                languageSelect.value = originalValue;
            }

            // Revert RTL/LTR if error
            if (window.RTLManager && originalValue) {
                try {
                    window.RTLManager.applyDirection(originalValue);
                } catch (rtlError) {
                    console.warn('Could not revert RTL direction:', rtlError);
                }
            } else if (originalValue) {
                // Fallback revert
                const htmlElement = document.documentElement;
                const isRTL = ['ar', 'fa', 'he', 'ur'].includes(originalValue);
                htmlElement.setAttribute('dir', isRTL ? 'rtl' : 'ltr');
                htmlElement.setAttribute('lang', originalValue);
            }

            // Show error message
            this.showError(error.message || (window.t ? window.t('Failed to change language') : 'Failed to change language. Please try again.'));
            
            this.isChanging = false;
        }
    }

    /**
     * Handle language change (called from settings page or other sources)
     * @param {string} languageCode - Language code
     * @param {boolean} showLoading - Whether to show loading state
     */
    async handleLanguageChange(languageCode, showLoading = true) {
        if (this.isChanging) {
            return;
        }

        this.isChanging = true;

        try {
            const languageSelect = document.getElementById('sidebarLanguageSelect');
            
            if (showLoading) {
                this.showLoadingState(languageSelect);
            }

            // Apply RTL/LTR immediately
            if (window.RTLManager) {
                window.RTLManager.applyDirection(languageCode);
            }

            // Update dropdown if exists
            if (languageSelect) {
                languageSelect.value = languageCode;
            }

            // Reload translations if available
            if (window.translations && typeof window.reloadTranslations === 'function') {
                try {
                    await window.reloadTranslations(languageCode);
                } catch (e) {
                    console.warn('Could not reload translations dynamically:', e);
                }
            }

            // Smooth reload
            this.reloadPageSmoothly();
        } catch (error) {
            console.error('Error handling language change:', error);
            this.isChanging = false;
        }
    }

    /**
     * Show loading state on dropdown
     * @param {HTMLElement} selectElement - Select element
     */
    showLoadingState(selectElement) {
        if (!selectElement) return;

        selectElement.disabled = true;
        selectElement.style.opacity = '0.6';
        selectElement.style.cursor = 'wait';

        // Add loading spinner if not exists
        const container = selectElement.closest('.language-switcher');
        if (container && !container.querySelector('.language-loading')) {
            const spinner = document.createElement('div');
            spinner.className = 'language-loading';
            spinner.className += ' sidebar-lang-loading';
            spinner.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i>';
            spinner.style.cssText = 'position: absolute; inset-inline-end: 0.7rem; top: 50%; transform: translateY(-50%); pointer-events: none; color: inherit;';
            selectElement.style.position = 'relative';
            container.style.position = 'relative';
            container.appendChild(spinner);
        }
    }

    /**
     * Remove loading state
     */
    removeLoadingState() {
        const languageSelect = document.getElementById('sidebarLanguageSelect');
        if (languageSelect) {
            languageSelect.disabled = false;
            languageSelect.style.opacity = '1';
            languageSelect.style.cursor = 'pointer';
        }

        const loadingSpinner = document.querySelector('.language-loading');
        if (loadingSpinner) {
            loadingSpinner.remove();
        }
    }

    /**
     * Reload page smoothly with fade transition
     */
    reloadPageSmoothly() {
        // Add fade-out class to body
        document.body.style.transition = 'opacity 0.2s ease-out';
        document.body.style.opacity = '0.7';

        // Small delay for smooth transition, then reload
        setTimeout(() => {
            window.location.reload();
        }, 150);
    }
    
    /**
     * Static method to reload page (can be called from outside)
     */
    static reloadPageSmoothly() {
        // Add fade-out class to body
        document.body.style.transition = 'opacity 0.2s ease-out';
        document.body.style.opacity = '0.7';

        // Small delay for smooth transition, then reload
        setTimeout(() => {
            window.location.reload();
        }, 150);
    }

    /**
     * Show error message
     * @param {string} message - Error message
     */
    showError(message) {
        this.removeLoadingState();

        // Use notification system if available
        if (window.notifications && typeof window.notifications.error === 'function') {
            window.notifications.error(message, { duration: 3000 });
        } else if (window.MessageSystem && typeof window.MessageSystem.show === 'function') {
            window.MessageSystem.show(message, 'error');
        } else {
            // Fallback to alert
            alert(message);
        }
    }
}

// Initialize Language Switcher
let languageSwitcher = null;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        languageSwitcher = new LanguageSwitcher();
        window.LanguageSwitcher = languageSwitcher;
    });
} else {
    languageSwitcher = new LanguageSwitcher();
    window.LanguageSwitcher = languageSwitcher;
}

export default LanguageSwitcher;

