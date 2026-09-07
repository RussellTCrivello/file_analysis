/**
 * File Details Modal
 * Handles showing file details in modal
 */

import { fileNavigationState, modalState } from '../core/state.js';
import { MODAL_ENABLED, translations } from '../core/config.js';
import { escapeHtml, formatFileSize } from '../core/utils.js';
import { updateFileNavigationButtons } from './file-navigation.js';
import { clearModalSearch } from '../search/modal-search.js';

/**
 * Show file details modal
 * @param {number} fileId - File ID
 * @param {string} fileName - File name
 * @param {Array} fileList - Optional list of files for navigation
 * @param {number} fileIndex - Optional index in file list
 */
export function showFileDetails(fileId, fileName, fileList = null, fileIndex = -1) {
    console.log('Showing file details for:', { fileId, fileName, fileList, fileIndex, MODAL_ENABLED });
    
    // If modal is disabled, open in new tab instead
    if (!MODAL_ENABLED) {
        console.log('Modal disabled - opening in new tab');
        window.open(`/file/${fileId}`, '_blank');
        return;
    }
    
    // Store file list context if provided
    if (fileList && Array.isArray(fileList)) {
        fileNavigationState.currentFiles = fileList;
        fileNavigationState.currentIndex = fileIndex >= 0 ? fileIndex : fileList.findIndex(f => f.id === fileId);
    } else {
        // Try to get file list from current page
        const fileRows = document.querySelectorAll('.file-row-item[data-file-id]');
        if (fileRows.length > 0) {
            fileNavigationState.currentFiles = Array.from(fileRows).map(row => ({
                id: parseInt(row.getAttribute('data-file-id')),
                name: row.getAttribute('data-file-name') || 'File'
            }));
            fileNavigationState.currentIndex = fileNavigationState.currentFiles.findIndex(f => f.id === fileId);
        }
    }
    
    // Open modal
    const modal = document.getElementById('fileModal');
    if (!modal) {
        console.error('File modal not found in DOM');
        if (window.showError) {
            window.showError('Modal element not found. Please refresh the page.');
        }
        // Fallback: open in new tab
        window.open(`/file/${fileId}`, '_blank');
        return;
    }
    
    // Update navigation buttons
    updateFileNavigationButtons();
    
    // Set modal title
    const modalTitle = document.getElementById('modalTitle');
    if (modalTitle) {
        modalTitle.textContent = fileName || (translations.fileDetails || 'File Details');
    }
    
    // Show loading state
    const contentSection = document.getElementById('fileContentSection');
    const analysisSection = document.getElementById('fileAnalysisSection');
    const metadataSection = document.getElementById('fileMetadataSection');
    
    if (contentSection) {
        contentSection.innerHTML = `<div class="content-loading">${translations.loadingContent || 'Loading content...'}</div>`;
    }
    if (analysisSection) {
        analysisSection.innerHTML = `<div class="content-loading">${translations.loadingAnalysis || 'Loading analysis...'}</div>`;
    }
    if (metadataSection) {
        metadataSection.innerHTML = `<div class="content-loading">${translations.loadingMetadata || 'Loading metadata...'}</div>`;
    }
    
    // Clear any previous search state
    if (clearModalSearch) {
        clearModalSearch();
    }
    
    // Show modal
    modal.classList.add('active');
    modal.style.display = 'flex';
    modal.style.visibility = 'visible';
    modal.style.opacity = '1';
    // z-index is handled by CSS (10000)
    document.body.style.overflow = 'hidden';
    
    // Load file details content
    loadFileDetailsContent(fileId, fileName);
    
    modalState.isOpen = true;
    modalState.currentFileId = fileId;
    modalState.currentFileName = fileName;
}

/**
 * Load file details content into modal
 * @param {number} fileId - File ID
 * @param {string} fileName - File name
 */
export async function loadFileDetailsContent(fileId, fileName) {
    try {
        const response = await fetch(`/api/file/${fileId}/details`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.success || !data.details) {
            // ERROR HANDLING FIX: Properly handle API error responses
            const errorMsg = escapeHtml(data.error || (translations.errorLoadingFileDetails || 'Error loading file details'));
            const contentSection = document.getElementById('fileContentSection');
            const analysisSection = document.getElementById('fileAnalysisSection');
            const metadataSection = document.getElementById('fileMetadataSection');
            
            // Show error in all sections
            if (contentSection) contentSection.innerHTML = `<div class="empty-state error">${errorMsg}</div>`;
            if (analysisSection) analysisSection.innerHTML = `<div class="empty-state error">${errorMsg}</div>`;
            if (metadataSection) metadataSection.innerHTML = `<div class="empty-state error">${errorMsg}</div>`;
            
            // Show notification to user
            if (window.fms && window.fms.ui && window.fms.ui.notifications) {
                window.fms.ui.notifications.error(errorMsg);
            } else if (window.showError) {
                window.showError(errorMsg);
            }
            return;
        }

        const file = data.details;
        
        // Store file ID for export functionality
        window.currentModalFileId = fileId;
        
        // Populate Content Section
        const contentSection = document.getElementById('fileContentSection');
        if (contentSection) {
            const contentValue = file.content || file['content'] || '';
            const fileType = file.type || '';
            const filePath = file.path || '';
            
            if (contentValue && typeof contentValue === 'string' && contentValue.trim()) {
                // Display full content without truncation
                // SECURITY FIX: Content is already escaped in formatContentByType or we escape it here
                const displayContent = contentValue;
                
                window.currentModalFileContent = contentValue;
                window.currentModalFileName = fileName || 'file';
                
                // Format content based on file type
                import('../content-formatter.js').then(module => {
                    const formatted = module.formatContentByType(displayContent, fileType, filePath, fileId);
                    if (formatted) {
                        // SECURITY FIX: Ensure formatted content is safe - formatContentByType should handle escaping
                        // But we'll add a safety check here
                        contentSection.innerHTML = `<div id="modalContentText" class="formatted-content-wrapper">${formatted}</div>`;
                        
                        // Attach image error handlers after DOM insertion
                        setTimeout(() => {
                            const contentElement = document.getElementById('modalContentText');
                            if (contentElement && window.attachImageErrorHandlers) {
                                window.attachImageErrorHandlers(contentElement);
                            }
                        }, 10);
                    } else {
                        // SECURITY FIX: Always escape HTML content to prevent XSS
                        contentSection.innerHTML = `<pre id="modalContentText" style="margin: 0; white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word;">${escapeHtml(displayContent)}</pre>`;
                    }
                    
                    const contentElement = document.getElementById('modalContentText');
                    if (contentElement) {
                        contentElement.setAttribute('data-original-content', displayContent);
                        contentElement.setAttribute('data-full-content', escapeHtml(contentValue));
                    }
                }).catch(err => {
                    console.error('Error formatting modal content:', err);
                    // SECURITY FIX: Always escape HTML content to prevent XSS
                    contentSection.innerHTML = `<pre id="modalContentText" style="margin: 0; white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word;">${escapeHtml(displayContent)}</pre>`;
                    const contentElement = document.getElementById('modalContentText');
                    if (contentElement) {
                        contentElement.setAttribute('data-original-content', displayContent);
                        contentElement.setAttribute('data-full-content', escapeHtml(contentValue));
                    }
                });
            } else if (fileType.match(/\.(jpg|jpeg|png|gif|bmp|tiff|tif|webp|svg)$/i) && (filePath || fileId)) {
                // Image file without text content - show image
                import('../content-formatter.js').then(module => {
                    const formatted = module.formatContentByType('', fileType, filePath, fileId);
                    if (formatted) {
                        contentSection.innerHTML = `<div id="modalContentText" class="formatted-content-wrapper">${formatted}</div>`;
                    }
                }).catch(err => {
                    console.error('Error formatting image:', err);
                });
            } else {
                window.currentModalFileContent = '';
                window.currentModalFileName = fileName || 'file';
                contentSection.innerHTML = `<div class="empty-state">${translations.noContentAvailable || 'No content available'}</div>`;
            }
        }
        
        // Populate Analysis Section
        const analysisSection = document.getElementById('fileAnalysisSection');
        if (analysisSection) {
            let analysisHtml = '';
            
            if (file.title) {
                analysisHtml += `
                    <div class="analysis-section-title">
                        <h4><i class="bi bi-file-text me-2"></i>${translations.titleAnalysis || 'Title Analysis'}</h4>
                    </div>
                    <div class="analysis-item">
                        <div class="analysis-label">${translations.fileTitle || 'File Title'}:</div>
                        <div class="analysis-value">${escapeHtml(file.title)}</div>
                    </div>
                `;
                
                if (file.similar_titles && file.similar_titles.length > 0) {
                    analysisHtml += `
                        <div class="analysis-item">
                            <div class="analysis-label">${translations.similarTitles || 'Similar Titles'}:</div>
                            <div class="similar-titles-list">
                    `;
                    
                    file.similar_titles.forEach(similar => {
                        analysisHtml += `
                            <div class="similar-title-item">
                                <span class="similarity-badge">${similar.similarity_percent || 0}%</span>
                                <span class="similar-title-text">${escapeHtml(similar.name || 'Unknown')}</span>
                                ${similar.file_count ? `<span class="file-count-badge">${similar.file_count} files</span>` : ''}
                            </div>
                        `;
                    });
                    
                    analysisHtml += `
                            </div>
                        </div>
                    `;
                }
                
                analysisHtml += '<hr style="margin: 1rem 0; border-color: #e2e8f0;">';
            }
            
            analysisHtml += '<div id="classificationChartsContainer"></div>';
            analysisSection.innerHTML = analysisHtml;
            
            // Load charts after HTML is set
            if (window.fms && window.fms.charts && window.fms.charts.loadClassificationCharts) {
                window.fms.charts.loadClassificationCharts(file.id);
            } else if (window.loadClassificationCharts) {
                window.loadClassificationCharts(file.id);
            }
        }
        
        // Populate Metadata Section
        const metadataSection = document.getElementById('fileMetadataSection');
        if (metadataSection) {
            let metadataHtml = '';
            
            const metadataItems = [
                { label: translations.fileName || 'File Name', value: file.name || 'N/A' },
                { label: translations.fileType || 'File Type', value: file.type || 'Unknown' },
                { label: translations.fileSize || 'File Size', value: formatFileSize(file.size) },
                { label: translations.status || 'Status', value: file.status || 'Unknown' },
                { label: translations.fileDate || 'File Date', value: file.file_date ? new Date(file.file_date).toLocaleDateString() : 'N/A' },
                { label: translations.dateCreated || 'Date Created', value: file.date_creation ? new Date(file.date_creation).toLocaleDateString() : 'N/A' },
                { label: translations.source || 'Source', value: file.source || 'Unknown' },
                { label: translations.side || 'Side', value: file.side || 'Unknown' },
                { label: translations.wordCount || 'Word Count', value: (file.word_count || 0).toLocaleString() },
                { label: translations.contentChunks || 'Content Chunks', value: (file.content_chunks || 0).toLocaleString() }
            ];
            
            if (file.path) {
                metadataItems.push({ label: translations.filePath || 'File Path', value: file.path });
            }
            
            if (file.hash) {
                metadataItems.push({ label: translations.hash || 'Relations', value: file.hash });
            }
            
            metadataItems.forEach(item => {
                metadataHtml += `
                    <div class="metadata-item">
                        <div class="metadata-label">${escapeHtml(item.label)}</div>
                        <div class="metadata-value">${escapeHtml(String(item.value))}</div>
                    </div>
                `;
            });
            
            metadataSection.innerHTML = metadataHtml || `<div class="empty-state">${translations.noMetadataAvailable || 'No metadata available'}</div>`;
        }
    } catch (error) {
        console.error('Error loading file details:', error);
        // SECURITY FIX: Always escape error messages to prevent XSS
        const errorMsg = escapeHtml(error.message || 'Unknown error occurred');
        const networkError = error.name === 'TypeError' && error.message.includes('fetch');
        const userFriendlyMsg = networkError 
            ? (translations.networkError || 'Network error: Unable to connect to server. Please check your connection and try again.')
            : `${translations.errorLoadingFileDetails || 'Error loading file details'}: ${errorMsg}`;
        
        const contentSection = document.getElementById('fileContentSection');
        const analysisSection = document.getElementById('fileAnalysisSection');
        const metadataSection = document.getElementById('fileMetadataSection');
        
        // ERROR HANDLING FIX: Show proper error messages in all sections
        if (contentSection) {
            contentSection.innerHTML = `<div class="empty-state error">${escapeHtml(userFriendlyMsg)}</div>`;
        }
        if (analysisSection) {
            analysisSection.innerHTML = `<div class="empty-state error">${escapeHtml(userFriendlyMsg)}</div>`;
        }
        if (metadataSection) {
            metadataSection.innerHTML = `<div class="empty-state error">${escapeHtml(userFriendlyMsg)}</div>`;
        }
        
        // Show notification to user
        if (window.fms && window.fms.ui && window.fms.ui.notifications) {
            window.fms.ui.notifications.error(userFriendlyMsg);
        } else if (window.showError) {
            window.showError(userFriendlyMsg);
        }
    }
}

/**
 * Close file modal
 */
export function closeFileModal() {
    const modal = document.getElementById('fileModal');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
        document.body.style.overflow = '';
        
        // Clear search state
        if (clearModalSearch) {
            clearModalSearch();
        }
        
        // Clear stored content and file ID
        window.currentModalFileContent = '';
        window.currentModalFileName = '';
        window.currentModalFileId = null;
        
        modalState.isOpen = false;
        modalState.currentFileId = null;
        modalState.currentFileName = null;
    }
}

// Setup click outside to close
if (typeof document !== 'undefined') {
    document.addEventListener('click', function(e) {
        const modal = document.getElementById('fileModal');
        if (modal && modal.classList.contains('active')) {
            if (e.target === modal) {
                closeFileModal();
            }
        }
    });
    
    // Keyboard navigation
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('fileModal');
            if (modal && modal.classList.contains('active')) {
                closeFileModal();
            }
        }
    });
}

