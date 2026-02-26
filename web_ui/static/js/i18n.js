/**
 * SAR Scanner Internationalization (i18n) Module
 * 
 * Provides translation support for the web UI.
 * Supports English (en), Polish (pl), and German (de).
 */

const I18n = (function() {
    // Available languages
    const SUPPORTED_LANGUAGES = ['en', 'pl', 'de'];
    const DEFAULT_LANGUAGE = 'en';
    const STORAGE_KEY = 'sarscanner_language';

    // Cached translations
    let translations = {};
    let currentLanguage = DEFAULT_LANGUAGE;
    let isLoaded = false;

    /**
     * Get nested property from object using dot notation
     * @param {Object} obj - The object to search
     * @param {string} path - Dot-separated path (e.g., 'dashboard.status.title')
     * @returns {string|undefined} The value at path or undefined
     */
    function getNestedValue(obj, path) {
        return path.split('.').reduce((current, key) => {
            return current && current[key] !== undefined ? current[key] : undefined;
        }, obj);
    }

    /**
     * Load translation file for a specific language
     * @param {string} lang - Language code (en, pl, de)
     * @returns {Promise<Object>} Translation object
     */
    async function loadTranslation(lang) {
        try {
            const response = await fetch(`/static/i18n/${lang}.json`);
            if (!response.ok) {
                throw new Error(`Failed to load ${lang}.json: ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`Error loading translation for ${lang}:`, error);
            return null;
        }
    }

    /**
     * Initialize the i18n system
     * @returns {Promise<void>}
     */
    async function init() {
        // Get saved language preference
        const savedLang = localStorage.getItem(STORAGE_KEY);
        if (savedLang && SUPPORTED_LANGUAGES.includes(savedLang)) {
            currentLanguage = savedLang;
        } else {
            // Try to detect from browser
            const browserLang = navigator.language.split('-')[0];
            if (SUPPORTED_LANGUAGES.includes(browserLang)) {
                currentLanguage = browserLang;
            }
        }

        // Load all translations in parallel
        const loadPromises = SUPPORTED_LANGUAGES.map(async (lang) => {
            const data = await loadTranslation(lang);
            if (data) {
                translations[lang] = data;
            }
        });

        await Promise.all(loadPromises);
        isLoaded = true;

        // Apply translations to current page
        applyTranslations();

        return currentLanguage;
    }

    /**
     * Get translation for a key
     * @param {string} key - Translation key (dot notation, e.g., 'dashboard.status.title')
     * @param {Object} params - Optional parameters for interpolation
     * @returns {string} Translated string or key if not found
     */
    function t(key, params = {}) {
        if (!isLoaded) {
            console.warn('I18n not loaded yet, returning key:', key);
            return key;
        }

        // Try current language first
        let value = getNestedValue(translations[currentLanguage], key);

        // Fallback to English
        if (value === undefined && currentLanguage !== 'en') {
            value = getNestedValue(translations['en'], key);
        }

        // Return key if not found
        if (value === undefined) {
            console.warn('Translation not found:', key);
            return key;
        }

        // Simple parameter interpolation: {{param}}
        if (typeof value === 'string' && Object.keys(params).length > 0) {
            Object.keys(params).forEach(param => {
                value = value.replace(new RegExp(`{{${param}}}`, 'g'), params[param]);
            });
        }

        return value;
    }

    /**
     * Apply translations to all elements with data-i18n attribute
     */
    function applyTranslations() {
        if (!isLoaded) return;

        // Update page title if it has data-i18n-title attribute on html/head
        const titleElement = document.querySelector('title[data-i18n]');
        if (titleElement) {
            const key = titleElement.getAttribute('data-i18n');
            titleElement.textContent = t(key);
        }

        // Update all elements with data-i18n attribute
        document.querySelectorAll('[data-i18n]').forEach(element => {
            const key = element.getAttribute('data-i18n');
            if (key) {
                // Handle different element types
                if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
                    // For inputs, check for placeholder
                    if (element.hasAttribute('placeholder')) {
                        element.placeholder = t(key);
                    } else {
                        element.value = t(key);
                    }
                } else if (element.tagName === 'TITLE') {
                    element.textContent = t(key);
                } else {
                    element.textContent = t(key);
                }
            }
        });

        // Update elements with data-i18n-placeholder attribute
        document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
            const key = element.getAttribute('data-i18n-placeholder');
            if (key) {
                element.placeholder = t(key);
            }
        });

        // Update elements with data-i18n-title attribute (for tooltips)
        document.querySelectorAll('[data-i18n-title]').forEach(element => {
            const key = element.getAttribute('data-i18n-title');
            if (key) {
                element.title = t(key);
            }
        });

        // Update html lang attribute
        document.documentElement.lang = currentLanguage;

        // Dispatch event for custom handlers
        document.dispatchEvent(new CustomEvent('languageChanged', {
            detail: { language: currentLanguage }
        }));
    }

    /**
     * Change the current language
     * @param {string} lang - Language code (en, pl, de)
     * @returns {boolean} True if language was changed
     */
    function setLanguage(lang) {
        if (!SUPPORTED_LANGUAGES.includes(lang)) {
            console.error('Unsupported language:', lang);
            return false;
        }

        if (lang === currentLanguage) {
            return true;
        }

        currentLanguage = lang;
        localStorage.setItem(STORAGE_KEY, lang);
        applyTranslations();

        return true;
    }

    /**
     * Get current language
     * @returns {string} Current language code
     */
    function getLanguage() {
        return currentLanguage;
    }

    /**
     * Get list of supported languages
     * @returns {string[]} Array of language codes
     */
    function getSupportedLanguages() {
        return [...SUPPORTED_LANGUAGES];
    }

    /**
     * Check if translations are loaded
     * @returns {boolean}
     */
    function isReady() {
        return isLoaded;
    }

    // Public API
    return {
        init,
        t,
        setLanguage,
        getLanguage,
        getSupportedLanguages,
        applyTranslations,
        isReady
    };
})();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => I18n.init());
} else {
    I18n.init();
}
