/**
 * Import Export Page JavaScript
 * Extracted from ImportExport/import_export.html
 */

// Load translations from JSON script tag
let translations = {};

document.addEventListener('DOMContentLoaded', function() {
    // Load translations from JSON script tag
    const pageDataEl = document.getElementById('import-export-page-data');
    if (pageDataEl) {
        try {
            const data = JSON.parse(pageDataEl.textContent);
            translations = data.translations || {};
            // Also make available on window for backward compatibility
            window.translations = window.translations || {};
            Object.assign(window.translations, translations);
        } catch (e) {
            console.error('Error parsing import export page data:', e);
        }
    }
    
    console.log('Import export page loaded');
});

   // Switch import method
    document.getElementById('importMethod').addEventListener('change', function() {
        const method = this.value;
        document.getElementById('pathsMethod').style.display = method === 'paths' ? 'block' : 'none';
        document.getElementById('csvMethod').style.display = method === 'csv' ? 'block' : 'none';
    });

    // Batch import
    async function handleBatchImport() {
        const method = document.getElementById('importMethod').value;
        const sourceId = document.getElementById('importSourceId').value;
        const sideId = document.getElementById('importSideId').value;

        if (!sourceId || !sideId) {
            alert(translations.pleaseEnterSourceAndSideId || 'Please enter Source ID and Side ID');
            return;
        }

        const progressDiv = document.getElementById('importProgress');
        const resultsDiv = document.getElementById('importResults');
        progressDiv.style.display = 'block';
        resultsDiv.innerHTML = '';

        try {
            let response;
            const formData = new FormData();

            if (method === 'paths') {
                const paths = document.getElementById('filePaths').value.split('\n').filter(p => p.trim());
                if (paths.length === 0) {
                    alert(translations.pleaseEnterAtLeastOneFilePath || 'Please enter at least one file path');
                    return;
                }

                response = await fetch('/api/import-export/batch-import', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    },
                    body: JSON.stringify({
                        file_paths: paths,
                        source_id: parseInt(sourceId),
                        side_id: parseInt(sideId)
                    })
                });
            } else {
                const file = document.getElementById('csvFile').files[0];
                if (!file) {
                    alert(translations.pleaseSelectCsvFile || 'Please select a CSV file');
                    return;
                }

                formData.append('file', file);
                formData.append('source_id', sourceId);
                formData.append('side_id', sideId);

                response = await fetch('/api/import-export/batch-import/csv', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    },
                    body: formData
                });
            }

            const data = await response.json();
            
            if (data.success) {
                resultsDiv.innerHTML = `
                    <div class="alert alert-success">
                        <strong>${translations.importComplete || 'Import Complete'}</strong><br>
                        ${translations.total || 'Total'}: ${data.results.total}<br>
                        ${translations.successful || 'Successful'}: ${data.results.successful}<br>
                        ${translations.failed || 'Failed'}: ${data.results.failed}
                    </div>
                `;
            } else {
                resultsDiv.innerHTML = `<div class="alert alert-danger">${data.error || (translations.importFailed || 'Import failed')}</div>`;
            }

        } catch (error) {
            console.error('Import error:', error);
            resultsDiv.innerHTML = `<div class="alert alert-danger">${translations.error || 'Error'}: ${error.message}</div>`;
        } finally {
            progressDiv.style.display = 'none';
        }
    }

    // Export database backup
    async function exportDatabaseBackup() {
        const includeData = document.getElementById('includeData').checked;
        
        try {
            const response = await fetch(`/api/import-export/backup/export?include_data=${includeData}`);
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `database_backup_${new Date().toISOString().split('T')[0]}.zip`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Export error:', error);
            alert((translations.errorExportingBackup || 'Error exporting backup') + ': ' + error.message);
        }
    }

    // Import database backup
    async function importDatabaseBackup(file) {
        if (!file) return;

        const resultsDiv = document.getElementById('backupResults');
        resultsDiv.innerHTML = '<div class="text-center"><div class="spinner-border"></div></div>';

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/import-export/backup/import', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: formData
            });

            const data = await response.json();
            
            if (data.success) {
                resultsDiv.innerHTML = `
                    <div class="alert alert-success">
                        <strong>${translations.backupValid || 'Backup Valid'}</strong><br>
                        ${translations.tables || 'Tables'}: ${data.results.table_count}<br>
                        ${data.results.warnings && data.results.warnings.length > 0 ? 
                            '<small>' + data.results.warnings.join('<br>') + '</small>' : ''}
                    </div>
                `;
            } else {
                resultsDiv.innerHTML = `<div class="alert alert-danger">${data.results.error || (translations.invalidBackup || 'Invalid backup')}</div>`;
            }

        } catch (error) {
            console.error('Import error:', error);
            resultsDiv.innerHTML = `<div class="alert alert-danger">${translations.error || 'Error'}: ${error.message}</div>`;
        }
    }

    // Export settings (exposed globally)
    window.exportSettings = async function exportSettings() {
        try {
            const response = await fetch('/api/settings/export');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `settings_${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Export error:', error);
            alert((translations.errorExportingSettings || 'Error exporting settings') + ': ' + error.message);
        }
    }

    // Import settings (exposed globally)
    window.importSettings = async function importSettings(file) {
        if (!file) return;

        const resultsDiv = document.getElementById('settingsResults');
        resultsDiv.innerHTML = '<div class="text-center"><div class="spinner-border"></div></div>';

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/settings/import', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: formData
            });

            const data = await response.json();
            
            if (data.success) {
                resultsDiv.innerHTML = `
                    <div class="alert alert-success">
                        <strong>${translations.settingsValid || 'Settings Valid'}</strong><br>
                        <small>${translations.noteUseSettingsPage || 'Note: Use Settings page to apply imported settings'}</small>
                    </div>
                `;
            } else {
                resultsDiv.innerHTML = `<div class="alert alert-danger">${data.error || (translations.invalidSettingsFile || 'Invalid settings file')}</div>`;
            }

        } catch (error) {
            console.error('Import error:', error);
            resultsDiv.innerHTML = `<div class="alert alert-danger">${translations.error || 'Error'}: ${error.message}</div>`;
        }
    }