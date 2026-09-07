/**
 * Content Formatter Module
 * Comprehensive file content formatter with language detection and RTL/LTR support
 * Formats file content based on file type for accurate original-format display
 * 
 * Features:
 * - Language detection and automatic RTL/LTR direction
 * - Support for all file types (Word, Excel, PDF, PowerPoint, Email, Images, etc.)
 * - Organized storage format parsing
 * - Realistic table display with borders and frames
 * - Original format preservation
 * - Spatial order preservation: Content is displayed in the same order as it appears
 *   in the original document (top-to-bottom, left-to-right)
 * - Element ordering: Tables, paragraphs, images, and other elements maintain their
 *   original spatial relationships from the source document
 */

/**
 * Detect text direction (RTL/LTR) based on language
 * @param {string} text - Text to analyze
 * @returns {string} - 'rtl' or 'ltr'
 */
function detectTextDirection(text) {
    if (!text || typeof text !== 'string') return 'ltr';
    
    // RTL language patterns (Arabic, Hebrew, Persian, Urdu, etc.)
    const rtlPatterns = [
        /[\u0590-\u05FF]/, // Hebrew
        /[\u0600-\u06FF]/, // Arabic
        /[\u06A0-\u06FF]/, // Arabic Supplement
        /[\u0700-\u074F]/, // Syriac
        /[\u0750-\u077F]/, // Arabic Supplement
        /[\u08A0-\u08FF]/, // Arabic Extended-A
        /[\uFB50-\uFDFF]/, // Arabic Presentation Forms-A
        /[\uFE70-\uFEFF]/  // Arabic Presentation Forms-B
    ];
    
    // Check for RTL characters
    for (const pattern of rtlPatterns) {
        if (pattern.test(text)) {
            return 'rtl';
        }
    }
    
    // Default to LTR
    return 'ltr';
}

/**
 * Detect language from text content
 * @param {string} text - Text to analyze
 * @returns {string} - Language code (e.g., 'ar', 'he', 'en')
 */
function detectLanguage(text) {
    if (!text || typeof text !== 'string') return 'en';
    
    // Simple language detection based on character ranges
    if (/[\u0590-\u05FF]/.test(text)) return 'he'; // Hebrew
    if (/[\u0600-\u06FF]/.test(text)) return 'ar'; // Arabic
    if (/[\u4E00-\u9FFF]/.test(text)) return 'zh'; // Chinese
    if (/[\u3040-\u309F\u30A0-\u30FF]/.test(text)) return 'ja'; // Japanese
    if (/[\uAC00-\uD7AF]/.test(text)) return 'ko'; // Korean
    
    return 'en'; // Default to English
}

/**
 * Detect if a line is a table header (from storage format)
 * @param {string} line - Line to check
 * @returns {Object|null} - Table info or null
 */
function detectTableHeader(line) {
    if (!line || typeof line !== 'string') return null;
    
    // Pattern: "Table N" or "Table N | Caption: ..." (case-insensitive)
    // Also match "table N" (lowercase)
    const tableMatch = line.match(/^[Tt]able\s+(\d+)(?:\s*\|\s*(.+))?$/i);
    if (tableMatch) {
        const result = {
            type: 'table',
            number: parseInt(tableMatch[1]),
            caption: tableMatch[2] ? tableMatch[2].replace(/^Caption:\s*/i, '').trim() : null
        };
        console.log('detectTableHeader: Found table header:', result);
        return result;
    }
    
    // Pattern: "Sheet: SheetName | Rows: X | Columns: Y"
    const sheetMatch = line.match(/^Sheet:\s*([^|]+)(?:\s*\|\s*(.+))?$/i);
    if (sheetMatch) {
        const metadata = sheetMatch[2] || '';
        const rowsMatch = metadata.match(/Rows:\s*(\d+)/i);
        const colsMatch = metadata.match(/Columns:\s*(\d+)/i);
        return {
            type: 'sheet',
            name: sheetMatch[1].trim(),
            rows: rowsMatch ? parseInt(rowsMatch[1]) : null,
            columns: colsMatch ? parseInt(colsMatch[1]) : null
        };
    }
    
    return null;
}

/**
 * Check if a line is explanatory/metadata text that should be hidden
 * @param {string} line - Line to check
 * @returns {boolean} - True if line is explanatory text
 */
function isExplanatoryText(line) {
    if (!line || typeof line !== 'string') return false;
    
    const trimmed = line.trim();
    
    // Page markers: "Page N", "Page N | Method: ...", etc.
    if (/^Page\s+\d+(\s*\|\s*.*)?$/i.test(trimmed)) {
        return true;
    }
    
    // Slide markers: "Slide N", "Slide N | ..."
    if (/^Slide\s+\d+(\s*\|\s*.*)?$/i.test(trimmed)) {
        return true;
    }
    
    // Table markers: "Table N", "Table N | Caption: ..."
    if (/^Table\s+\d+(\s*\|\s*(Caption|Title):\s*.*)?$/i.test(trimmed)) {
        return true;
    }
    
    // Sheet markers: "Sheet: ... | Rows: ... | Columns: ..."
    if (/^Sheet:\s*[^|]+(\s*\|\s*(Rows|Columns):\s*\d+.*)?$/i.test(trimmed)) {
        return true;
    }
    
    // Style markers: "[Style: ...]"
    if (/^\[Style:\s*[^\]]+\]\s*$/.test(trimmed)) {
        return true;
    }
    
    // Metadata lines: "Method: ...", "Length: ...", "Rows: ...", "Columns: ..."
    if (/^(Method|Length|Rows|Columns|Total\s+(Pages|Slides|Sheets)):\s*.*$/i.test(trimmed)) {
        return true;
    }
    
    // PDF metadata: "Total Pages: ...", "OCR Used: ...", etc.
    if (/^(Total\s+(Pages|Slides|Sheets)|OCR\s+Used|OCR\s+Languages|Encrypted|Title|Author|Subject|Creator|Producer):\s*.*$/i.test(trimmed)) {
        return true;
    }
    
    // Slides metadata: "Total Slides: ..."
    if (/^Total\s+Slides:\s*\d+$/i.test(trimmed)) {
        return true;
    }
    
    // Image metadata: "Width: ...", "Height: ...", "Format: ...", "GPS: ..."
    if (/^(Width|Height|Format|Mode|GPS|Maps):\s*.*$/i.test(trimmed)) {
        return true;
    }
    
    // Chapter markers: "Chapter ID: ...", "Chapter N"
    if (/^Chapter\s+(ID|Number)?:?\s*.*$/i.test(trimmed)) {
        return true;
    }
    
    // Database metadata: "SQLite Version: ...", "Tables: ..."
    if (/^(SQLite\s+Version|Tables|Table\s+Count):\s*.*$/i.test(trimmed)) {
        return true;
    }
    
    return false;
}

/**
 * Remove explanatory text from a line while preserving actual content
 * @param {string} line - Line to process
 * @returns {string} - Line with explanatory text removed
 */
function removeExplanatoryText(line) {
    if (!line || typeof line !== 'string') return line;
    
    // If entire line is explanatory, return empty
    if (isExplanatoryText(line.trim())) {
        return '';
    }
    
    // Remove style markers from beginning: "[Style: ...] actual text"
    const styleMatch = line.match(/^\[Style:\s*[^\]]+\]\s*(.+)$/);
    if (styleMatch) {
        return styleMatch[1];
    }
    
    // Remove metadata from pipe-separated format: "Page N | Method: ... | actual content"
    // Keep only the actual content part
    if (line.includes('|')) {
        const parts = line.split('|').map(p => p.trim());
        const contentParts = parts.filter(part => {
            // Keep parts that don't match explanatory patterns
            return !isExplanatoryText(part);
        });
        
        if (contentParts.length > 0) {
            return contentParts.join(' | ');
        }
    }
    
    return line;
}

/**
 * Detect if content contains table-like structures
 * @param {string} content - Content to analyze
 * @returns {boolean} - True if content appears to contain tables
 */
function detectTableStructure(content) {
    if (!content || typeof content !== 'string') return false;
    
    const lines = content.split('\n').filter(line => line.trim());
    if (lines.length < 2) return false;
    
    // Check for storage format table headers
    for (const line of lines) {
        const header = detectTableHeader(line);
        if (header) return true;
    }
    
    // Check for tab-separated values (common in Word/Excel exports)
    const tabSeparatedLines = lines.filter(line => line.includes('\t')).length;
    if (tabSeparatedLines >= lines.length * 0.3) return true;
    
    // Check for consistent column counts (pipe, comma, or multiple spaces)
    const columnCounts = lines.map(line => {
        if (line.includes('|')) {
            return line.split('|').filter(c => c.trim()).length;
        } else if (line.includes(',')) {
            return line.split(',').filter(c => c.trim()).length;
        } else {
            // Count multiple spaces as column separators
            return line.split(/\s{2,}/).filter(c => c.trim()).length;
        }
    }).filter(count => count > 1);
    
    if (columnCounts.length < 2) return false;
    
    // Check if most lines have similar column counts
    const avgColumns = columnCounts.reduce((a, b) => a + b, 0) / columnCounts.length;
    const consistentLines = columnCounts.filter(count => 
        Math.abs(count - avgColumns) <= 1
    ).length;
    
    return consistentLines >= columnCounts.length * 0.7;
}

/**
 * Parse content into table structure (handles storage format)
 * @param {string} content - Content to parse
 * @param {Object} headerInfo - Optional header info from detectTableHeader
 * @returns {Array<Array<string>>} - Array of rows, each row is an array of cells
 */
function parseTableContent(content, headerInfo = null) {
    if (!content || typeof content !== 'string') return [];
    
    const lines = content.split('\n').filter(line => line.trim());
    if (lines.length === 0) return [];
    
    const rows = [];
    let skipHeader = false;
    let expectedColumns = null;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        
        // Skip table/sheet header lines
        if (detectTableHeader(line)) {
            skipHeader = true;
            continue;
        }
        
        // Skip metadata lines (Rows:, Columns:, etc.)
        if (line.match(/^(Rows|Columns|Sheet):/i)) {
            // Extract column count if available
            const colsMatch = line.match(/Columns:\s*(\d+)/i);
            if (colsMatch) {
                expectedColumns = parseInt(colsMatch[1]);
            }
            continue;
        }
        
        // Skip empty lines after headers
        if (skipHeader && !line.trim()) {
            continue;
        }
        skipHeader = false;
        
        let cells = [];
        
        // Try tab-separated first (most common in Word/Excel storage format)
        if (line.includes('\t')) {
            cells = line.split('\t').map(cell => cell.trim()).filter(cell => cell !== '');
        }
        // Try pipe-separated (but not if it's metadata)
        else if (line.includes('|') && !line.match(/^(Table|Sheet|Rows|Columns):/i)) {
            cells = line.split('|').map(cell => cell.trim()).filter(cell => cell);
        }
        // Try comma-separated (CSV-like)
        else if (line.includes(',') && line.split(',').length > 2) {
            cells = line.split(',').map(cell => cell.trim());
        }
        // Try multiple spaces (common in storage format where cells are space-separated)
        else {
            // For space-separated, we need to be smarter
            // Look for patterns of 2+ spaces that likely separate columns
            // But preserve single spaces within cell content
            
            // First, try splitting on 3+ spaces (more reliable for column separation)
            const tripleSpaceSplit = line.split(/\s{3,}/).map(cell => cell.trim()).filter(cell => cell);
            
            if (tripleSpaceSplit.length > 1) {
                cells = tripleSpaceSplit;
            } else {
                // Try 2+ spaces
                const doubleSpaceSplit = line.split(/\s{2,}/).map(cell => cell.trim()).filter(cell => cell);
                
                if (doubleSpaceSplit.length > 1) {
                    // Check if this looks like a table row vs. regular text
                    // Table rows typically have consistent column counts
                    if (expectedColumns && doubleSpaceSplit.length === expectedColumns) {
                        cells = doubleSpaceSplit;
                    } else if (rows.length > 0) {
                        // Compare with previous row - if similar column count, likely a table row
                        const prevCols = rows[rows.length - 1].length;
                        if (Math.abs(doubleSpaceSplit.length - prevCols) <= 1 && doubleSpaceSplit.length >= 2) {
                            cells = doubleSpaceSplit;
                        }
                    } else if (doubleSpaceSplit.length >= 2) {
                        // First row with 2+ columns - likely a table header
                        cells = doubleSpaceSplit;
                        expectedColumns = doubleSpaceSplit.length;
                    }
                }
            }
        }
        
        // Add row if we have cells
        if (cells.length > 1) {
            // Normalize column count - pad or trim to match expected
            if (expectedColumns && cells.length !== expectedColumns) {
                if (cells.length < expectedColumns) {
                    // Pad with empty cells
                    while (cells.length < expectedColumns) {
                        cells.push('');
                    }
                } else if (cells.length > expectedColumns) {
                    // Merge excess cells into last column
                    const excess = cells.slice(expectedColumns).join(' ');
                    cells = cells.slice(0, expectedColumns);
                    cells[expectedColumns - 1] = (cells[expectedColumns - 1] || '') + ' ' + excess;
                }
            }
            rows.push(cells);
            // Update expected columns from first row
            if (!expectedColumns && rows.length === 1) {
                expectedColumns = cells.length;
            }
        } else if (cells.length === 1 && cells[0] && headerInfo) {
            // Single cell row in a table context
            rows.push(cells);
        }
    }
    
    return rows;
}

/**
 * Parse a table row intelligently, handling space-separated cells
 * Enhanced version that better handles storage format where cells are space-separated
 * @param {string} line - Line to parse
 * @param {number} expectedColumns - Expected number of columns (if known)
 * @param {Array<Array<string>>} previousRows - Previous rows for pattern analysis
 * @returns {Array<string>} - Array of cell values
 */
function parseTableRow(line, expectedColumns = null, previousRows = []) {
    if (!line || !line.trim()) return [];
    
    // If we have tab-separated values, use that (most reliable)
    if (line.includes('\t')) {
        const cells = line.split('\t').map(c => c.trim());
        // Normalize to expected columns if provided
        if (expectedColumns && cells.length !== expectedColumns) {
            if (cells.length < expectedColumns) {
                while (cells.length < expectedColumns) {
                    cells.push('');
                }
            } else {
                const excess = cells.slice(expectedColumns).join(' ');
                cells.splice(expectedColumns);
                cells[expectedColumns - 1] = (cells[expectedColumns - 1] || '') + ' ' + excess;
            }
        }
        return cells;
    }
    
    // If we have pipe-separated values (but not metadata), use that
    if (line.includes('|') && !line.match(/^(Table|Sheet|Rows|Columns|Page|Slide|Chapter):/i)) {
        const cells = line.split('|').map(c => c.trim()).filter(c => c);
        if (cells.length > 1) {
            // Normalize to expected columns if provided
            if (expectedColumns && cells.length !== expectedColumns) {
                if (cells.length < expectedColumns) {
                    while (cells.length < expectedColumns) {
                        cells.push('');
                    }
                } else {
                    const excess = cells.slice(expectedColumns).join(' ');
                    cells.splice(expectedColumns);
                    cells[expectedColumns - 1] = (cells[expectedColumns - 1] || '') + ' ' + excess;
                }
            }
            return cells;
        }
    }
    
    // For space-separated values, use intelligent parsing
    // Strategy 1: Look for multiple consecutive spaces (3+ spaces = very likely column separator)
    const tripleSpaceSplit = line.split(/\s{3,}/).map(c => c.trim()).filter(c => c);
    if (tripleSpaceSplit.length > 1) {
        // Normalize to expected columns
        if (expectedColumns && tripleSpaceSplit.length !== expectedColumns) {
            if (tripleSpaceSplit.length < expectedColumns) {
                while (tripleSpaceSplit.length < expectedColumns) {
                    tripleSpaceSplit.push('');
                }
            } else {
                const excess = tripleSpaceSplit.slice(expectedColumns).join(' ');
                tripleSpaceSplit.splice(expectedColumns);
                tripleSpaceSplit[expectedColumns - 1] = (tripleSpaceSplit[expectedColumns - 1] || '') + ' ' + excess;
            }
        }
        return tripleSpaceSplit;
    }
    
    // Strategy 2: Look for 2+ spaces (moderate confidence)
    const doubleSpaceSplit = line.split(/\s{2,}/).map(c => c.trim()).filter(c => c);
    if (doubleSpaceSplit.length > 1) {
        // Use previous rows to validate if this looks like a table row
        if (previousRows.length > 0) {
            const prevCols = previousRows[previousRows.length - 1].length;
            // If column count matches previous rows, likely a table row
            if (Math.abs(doubleSpaceSplit.length - prevCols) <= 1) {
                expectedColumns = prevCols;
            }
        }
        
        // Normalize to expected columns
        if (expectedColumns && doubleSpaceSplit.length !== expectedColumns) {
            if (doubleSpaceSplit.length < expectedColumns) {
                while (doubleSpaceSplit.length < expectedColumns) {
                    doubleSpaceSplit.push('');
                }
            } else {
                const excess = doubleSpaceSplit.slice(expectedColumns).join(' ');
                doubleSpaceSplit.splice(expectedColumns);
                doubleSpaceSplit[expectedColumns - 1] = (doubleSpaceSplit[expectedColumns - 1] || '') + ' ' + excess;
            }
        }
        return doubleSpaceSplit;
    }
    
    // Strategy 3: If we know expected columns, try intelligent token distribution
    if (expectedColumns && expectedColumns > 1) {
        const tokens = line.split(/\s+/);
        
        if (tokens.length >= expectedColumns) {
            // Analyze previous rows to find column boundaries
            if (previousRows.length > 0) {
                // Calculate average token distribution from previous rows
                const avgTokensPerCol = previousRows.map(row => {
                    const rowText = row.join(' ');
                    return rowText.split(/\s+/).length / row.length;
                }).reduce((a, b) => a + b, 0) / previousRows.length;
                
                // Distribute tokens based on average
                const cells = [];
                let tokenIndex = 0;
                for (let col = 0; col < expectedColumns; col++) {
                    const tokensForThisCol = Math.round(avgTokensPerCol);
                    const endIndex = Math.min(tokenIndex + tokensForThisCol, tokens.length);
                    cells.push(tokens.slice(tokenIndex, endIndex).join(' '));
                    tokenIndex = endIndex;
                }
                
                // Add any remaining tokens to last column
                if (tokenIndex < tokens.length) {
                    cells[expectedColumns - 1] = (cells[expectedColumns - 1] || '') + ' ' + tokens.slice(tokenIndex).join(' ');
                }
                
                return cells;
            } else {
                // First row - distribute evenly
                const tokensPerColumn = Math.ceil(tokens.length / expectedColumns);
                const cells = [];
                for (let i = 0; i < expectedColumns; i++) {
                    const start = i * tokensPerColumn;
                    const end = Math.min(start + tokensPerColumn, tokens.length);
                    cells.push(tokens.slice(start, end).join(' '));
                }
                return cells;
            }
        }
    }
    
    // Strategy 4: Single cell (not a table row)
    return [line.trim()];
}

/**
 * Format content as HTML table with proper borders and frames
 * Enhanced version with realistic table appearance
 * @param {Array<Array<string>>} rows - Table rows (data rows, excluding header)
 * @param {Object} headerInfo - Optional header info with number, caption, name, etc.
 * @param {Array<string>} headerRow - Optional explicit header row
 * @param {boolean} isNested - Whether this is a nested table (for Word documents)
 * @returns {string} - HTML table string
 */
function formatAsTable(rows, headerInfo = null, headerRow = null, isNested = false) {
    // Determine if we have headers
    const hasExplicitHeader = headerRow && headerRow.length > 0;
    const hasDataRows = rows && rows.length > 0;
    
    if (!hasExplicitHeader && !hasDataRows) return '';
    
    // Determine column count
    let columnCount = 0;
    if (hasExplicitHeader) {
        columnCount = headerRow.length;
    } else if (hasDataRows && rows[0]) {
        columnCount = rows[0].length;
    } else {
        return '';
    }
    
    // Normalize all rows to have the same column count
    const normalizedRows = [];
    if (hasDataRows) {
        rows.forEach(row => {
            const normalizedRow = [];
            for (let i = 0; i < columnCount; i++) {
                normalizedRow.push(row && row[i] !== undefined ? String(row[i]).trim() : '');
            }
            normalizedRows.push(normalizedRow);
        });
    }
    
    // Normalize header row
    const normalizedHeader = [];
    if (hasExplicitHeader) {
        for (let i = 0; i < columnCount; i++) {
            normalizedHeader.push(headerRow[i] !== undefined ? String(headerRow[i]).trim() : '');
        }
    }
    
    // Detect language and direction for table
    const tableText = rows.flat().join(' ') + (headerRow ? headerRow.join(' ') : '');
    const direction = detectTextDirection(tableText);
    const lang = detectLanguage(tableText);
    
    const containerClass = isNested ? 'formatted-table-container nested-table' : 'formatted-table-container';
    let html = `<div class="${containerClass}" dir="${direction}" lang="${lang}">`;
    
    // Don't display table/sheet header - it's just explanatory metadata
    // Table numbers and sheet names are used internally for ordering only
    // The headerInfo is still used to track table structure but not displayed
    
    html += '<table class="formatted-content-table">';
    
    // Add header row if available
    if (hasExplicitHeader && normalizedHeader.length > 0) {
        html += '<thead><tr>';
        normalizedHeader.forEach((cell, cellIndex) => {
            html += `<th>${escapeHtml(cell || '')}</th>`;
        });
        html += '</tr></thead>';
    }
    
    // Add data rows
    if (hasDataRows && normalizedRows.length > 0) {
        html += '<tbody>';
        normalizedRows.forEach((row, rowIndex) => {
            html += '<tr>';
            row.forEach((cell, cellIndex) => {
                // Check if cell contains nested table markers
                const cellContent = escapeHtml(cell || '');
                html += `<td>${cellContent}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody>';
    }
    
    html += '</table></div>';
    return html;
}

/**
 * Format Word document content (handles storage format with tables and styles)
 * Enhanced version with better table detection, nested table support, and language detection
 * @param {string} content - Content text
 * @returns {string} - Formatted HTML
 */
function formatWordContent(content) {
    if (!content || typeof content !== 'string') {
        console.log('formatWordContent: No content provided');
        return '';
    }
    
    // Detect language and direction
    const direction = detectTextDirection(content);
    const lang = detectLanguage(content);
    
    console.log('formatWordContent: Processing content, length:', content.length);
    const lines = content.split('\n');
    console.log('formatWordContent: Total lines:', lines.length);
    let html = `<div class="formatted-word-content" dir="${direction}" lang="${lang}">`;
    let currentTable = [];
    let currentTableHeader = null;
    let inTable = false;
    let currentParagraph = [];
    let expectedColumns = null;
    let tableRows = []; // Track previous rows for pattern analysis
    let lastElementType = null; // Track last element type to preserve order
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();
        
        if (!trimmedLine) {
            // Empty line - end current section if we have enough data
            if (inTable && currentTable.length > 0) {
                // Check if next non-empty line is also a table row
                let nextNonEmpty = null;
                for (let j = i + 1; j < lines.length; j++) {
                    if (lines[j].trim()) {
                        nextNonEmpty = lines[j].trim();
                        break;
                    }
                }
                
                // If next line is not a table row or table header, end current table
                if (!nextNonEmpty || (!detectTableHeader(nextNonEmpty) && !isLikelyTableRow(nextNonEmpty, expectedColumns, currentTable))) {
                    html += formatAsTable(currentTable, currentTableHeader);
                    currentTable = [];
                    currentTableHeader = null;
                    tableRows = [];
                    inTable = false;
                    expectedColumns = null;
                }
            } else if (currentParagraph.length > 0) {
                const paraText = currentParagraph.join(' ');
                if (paraText.trim()) {
                    html += formatParagraph(paraText);
                }
                currentParagraph = [];
            }
            continue;
        }
        
        // Skip explanatory text lines (metadata markers)
        if (isExplanatoryText(trimmedLine)) {
            // These are organizational markers - skip them but preserve structure
            continue;
        }
        
        // Check for table header (storage format)
        // Support both "Table N" and "word_table" markers for new ordered format
        const tableHeader = detectTableHeader(trimmedLine);
        const isWordTableMarker = trimmedLine.match(/^word_table/i);
        
        if ((tableHeader && tableHeader.type === 'table') || isWordTableMarker) {
            console.log('formatWordContent: Found table header at line', i, ':', tableHeader || 'word_table marker');
            
            // End any current paragraph to preserve order
            if (currentParagraph.length > 0) {
                html += formatParagraph(currentParagraph.join(' '));
                currentParagraph = [];
                lastElementType = 'paragraph';
            }
            
            // End previous table if any
            if (currentTable.length > 0) {
                html += formatAsTable(currentTable, currentTableHeader);
                currentTable = [];
                tableRows = [];
            }
            
            // Start new table
            if (tableHeader && tableHeader.type === 'table') {
                currentTableHeader = {
                    number: tableHeader.number,
                    caption: tableHeader.caption
                };
            } else {
                // Extract table number from word_table marker if available
                const tableNumMatch = trimmedLine.match(/table\s+(\d+)/i);
                currentTableHeader = {
                    number: tableNumMatch ? parseInt(tableNumMatch[1]) : null,
                    caption: null
                };
            }
            inTable = true;
            expectedColumns = null; // Reset column count for new table
            lastElementType = 'table';
            continue;
        }
        
        // Check for word_paragraph marker (new ordered format)
        if (trimmedLine.match(/^word_paragraph/i)) {
            // End any current table
            if (inTable && currentTable.length > 0) {
                html += formatAsTable(currentTable, currentTableHeader);
                currentTable = [];
                tableRows = [];
                currentTableHeader = null;
                inTable = false;
                expectedColumns = null;
            }
            // Continue to process as paragraph (skip the marker line)
            lastElementType = 'paragraph';
            continue;
        }
        
        // Check if we're in a table section
        if (inTable) {
            // Parse row using enhanced parser with previous rows context
            const cells = parseTableRow(trimmedLine, expectedColumns, currentTable);
            
            // Determine if this is a table row
            const isTableRow = cells.length > 1 || (cells.length === 1 && cells[0].length > 0 && expectedColumns === 1);
            
            if (isTableRow) {
                // Update expected columns from first row
                if (expectedColumns === null && currentTable.length === 0) {
                    expectedColumns = cells.length;
                    console.log('Table first row detected with', expectedColumns, 'columns');
                }
                
                // Normalize column count if we have expected columns
                if (expectedColumns && cells.length !== expectedColumns) {
                    if (cells.length < expectedColumns) {
                        // Pad with empty cells
                        while (cells.length < expectedColumns) {
                            cells.push('');
                        }
                    } else {
                        // Merge excess into last column
                        const excess = cells.slice(expectedColumns).join(' ');
                        cells.splice(expectedColumns);
                        cells[expectedColumns - 1] = (cells[expectedColumns - 1] || '') + ' ' + excess;
                    }
                }
                
                currentTable.push(cells);
                tableRows.push(cells);
                continue;
            } else if (currentTable.length > 0) {
                // End of table - format it
                console.log('Ending table with', currentTable.length, 'rows');
                html += formatAsTable(currentTable, currentTableHeader);
                currentTable = [];
                currentTableHeader = null;
                tableRows = [];
                expectedColumns = null;
                inTable = false;
                // Continue processing this line as regular text
            }
        }
        
        // Handle paragraph text (may include style info)
        // Remove style markers and explanatory text
        const cleanedLine = removeExplanatoryText(trimmedLine);
        
        if (cleanedLine && cleanedLine !== trimmedLine) {
            // Line had style marker or other metadata - use cleaned version
            if (trimmedLine.match(/^\[Style:\s*([^\]]+)\]/)) {
                const styleMatch = trimmedLine.match(/^\[Style:\s*([^\]]+)\]\s*(.+)$/);
                if (styleMatch && styleMatch[2].trim()) {
                    const style = styleMatch[1];
                    const text = styleMatch[2].trim();
                    html += formatParagraph(text, style);
                }
            } else if (cleanedLine.trim()) {
                currentParagraph.push(cleanedLine.trim());
            }
        } else if (cleanedLine && cleanedLine.trim()) {
            // Regular paragraph text
            currentParagraph.push(cleanedLine.trim());
        }
    }
    
    // Close any remaining sections
    if (inTable && currentTable.length > 0) {
        console.log('Closing remaining table with', currentTable.length, 'rows');
        html += formatAsTable(currentTable, currentTableHeader);
    }
    if (currentParagraph.length > 0) {
        html += formatParagraph(currentParagraph.join(' '));
    }
    
    html += '</div>';
    console.log('formatWordContent: Final HTML length:', html.length);
    return html;
}

/**
 * Check if a line is likely a table row
 * @param {string} line - Line to check
 * @param {number} expectedColumns - Expected number of columns
 * @param {Array<Array<string>>} previousRows - Previous rows for comparison
 * @returns {boolean} - True if line looks like a table row
 */
function isLikelyTableRow(line, expectedColumns, previousRows) {
    if (!line || !line.trim()) return false;
    
    // Check for tab-separated values
    if (line.includes('\t')) {
        const cells = line.split('\t').filter(c => c.trim());
        return cells.length > 1;
    }
    
    // Check for multiple spaces (column separators)
    const tripleSpace = line.split(/\s{3,}/).filter(c => c.trim());
    if (tripleSpace.length > 1) return true;
    
    const doubleSpace = line.split(/\s{2,}/).filter(c => c.trim());
    if (doubleSpace.length > 1) {
        // If we have expected columns, check if it matches
        if (expectedColumns) {
            return Math.abs(doubleSpace.length - expectedColumns) <= 1;
        }
        // If we have previous rows, check if column count matches
        if (previousRows.length > 0) {
            const prevCols = previousRows[previousRows.length - 1].length;
            return Math.abs(doubleSpace.length - prevCols) <= 1;
        }
        return true;
    }
    
    return false;
}

/**
 * Format a paragraph with optional style and language detection
 * @param {string} text - Paragraph text
 * @param {string} style - Optional style name
 * @returns {string} - Formatted HTML
 */
function formatParagraph(text, style = null) {
    if (!text || !text.trim()) return '';
    
    // Detect language and direction
    const direction = detectTextDirection(text);
    const lang = detectLanguage(text);
    
    let className = 'formatted-paragraph';
    let styleAttr = '';
    
    // Apply style-based formatting
    if (style) {
        const styleLower = style.toLowerCase();
        if (styleLower.includes('heading') || styleLower.includes('title')) {
            className += ' formatted-heading';
            if (styleLower.includes('heading 1') || styleLower.includes('title')) {
                className += ' formatted-h1';
            } else if (styleLower.includes('heading 2')) {
                className += ' formatted-h2';
            } else if (styleLower.includes('heading 3')) {
                className += ' formatted-h3';
            }
        }
    }
    
    return `<p class="${className}" dir="${direction}" lang="${lang}"${styleAttr}>${escapeHtml(text.trim())}</p>`;
}

/**
 * Format Excel content as table (handles storage format with sheets)
 * Enhanced version with better parsing, display, and language detection
 * @param {string} content - Content text
 * @returns {string} - Formatted HTML table
 */
/**
 * Format Excel/Spreadsheet content
 * Preserves original sheet order and row/column spatial relationships
 * Content is already in spatial order from database storage
 * @param {string} content - Content text (already in spatial order)
 * @returns {string} - Formatted HTML
 */
function formatExcelContent(content) {
    if (!content || typeof content !== 'string') {
        console.log('formatExcelContent: No content provided');
        return '';
    }
    
    // Detect language and direction
    const direction = detectTextDirection(content);
    const lang = detectLanguage(content);
    
    console.log('formatExcelContent: Processing content, length:', content.length);
    const lines = content.split('\n');
    console.log('formatExcelContent: Total lines:', lines.length);
    let html = `<div class="formatted-excel-content" dir="${direction}" lang="${lang}">`;
    let currentSheet = null;
    let currentTable = [];
    let headerRow = null;
    let inSheet = false;
    let sheetColumnCount = null;
    let sheetRowCount = null;
    let isFirstDataRow = true;
    let tableRows = []; // Track previous rows for pattern analysis
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();
        
        if (!trimmedLine) {
            // Empty line might separate sheets or end current sheet
            if (inSheet && (currentTable.length > 0 || headerRow)) {
                // Check if next non-empty line is a new sheet or table row
                let nextNonEmpty = null;
                for (let j = i + 1; j < lines.length; j++) {
                    if (lines[j].trim()) {
                        nextNonEmpty = lines[j].trim();
                        break;
                    }
                }
                
                // If next line is a new sheet header, end current sheet
                if (nextNonEmpty && nextNonEmpty.match(/^Sheet:\s*(.+)$/i)) {
                    html += formatAsTable(currentTable, currentSheet, headerRow);
                    currentTable = [];
                    headerRow = null;
                    tableRows = [];
                    currentSheet = null;
                    sheetColumnCount = null;
                    sheetRowCount = null;
                    isFirstDataRow = true;
                    inSheet = false;
                } else if (!nextNonEmpty || !isLikelyTableRow(nextNonEmpty, sheetColumnCount, tableRows)) {
                    // Next line is not a table row, end current sheet
                    html += formatAsTable(currentTable, currentSheet, headerRow);
                    currentTable = [];
                    headerRow = null;
                    tableRows = [];
                    currentSheet = null;
                    sheetColumnCount = null;
                    sheetRowCount = null;
                    isFirstDataRow = true;
                    inSheet = false;
                }
            }
            continue;
        }
        
        // Skip explanatory text lines (metadata markers)
        if (isExplanatoryText(trimmedLine)) {
            // Extract sheet name from "Sheet: ..." for structure, but don't display the marker
            const sheetMatch = trimmedLine.match(/^Sheet:\s*([^|]+)/i);
            if (sheetMatch) {
                // End previous sheet if any
                if (currentTable.length > 0 || headerRow) {
                    html += formatAsTable(currentTable, currentSheet, headerRow);
                    currentTable = [];
                    headerRow = null;
                    tableRows = [];
                }
                
                // Start new sheet (use name but don't display the marker)
                currentSheet = {
                    name: sheetMatch[1].trim(),
                    type: 'sheet'
                };
                inSheet = true;
                sheetColumnCount = null;
                sheetRowCount = null;
                isFirstDataRow = true;
            }
            // Skip metadata lines (Rows:, Columns:, etc.)
            continue;
        }
        
        // Check for sheet header (storage format: "Sheet: SheetName")
        if (trimmedLine.match(/^Sheet:\s*(.+)$/i)) {
            const sheetMatch = trimmedLine.match(/^Sheet:\s*(.+)$/i);
            console.log('Found sheet header:', sheetMatch[1].trim());
            // End previous sheet if any
            if (currentTable.length > 0 || headerRow) {
                html += formatAsTable(currentTable, currentSheet, headerRow);
                currentTable = [];
                headerRow = null;
                tableRows = [];
            }
            
            // Start new sheet
            currentSheet = {
                name: sheetMatch[1].trim(),
                type: 'sheet'
            };
            inSheet = true;
            sheetColumnCount = null;
            sheetRowCount = null;
            isFirstDataRow = true;
            continue;
        }
        
        // Check for metadata lines (Rows:, Columns:) - skip these
        if (trimmedLine.match(/^(Rows|Columns):/i)) {
            const colsMatch = trimmedLine.match(/Columns:\s*:?(\d+)/i);
            if (colsMatch) {
                sheetColumnCount = parseInt(colsMatch[1]);
                console.log('Found column count:', sheetColumnCount);
                if (currentSheet) {
                    currentSheet.columnCount = sheetColumnCount;
                }
            }
            const rowsMatch = trimmedLine.match(/Rows:\s*:?(\d+)/i);
            if (rowsMatch) {
                sheetRowCount = parseInt(rowsMatch[1]);
                console.log('Found row count:', sheetRowCount);
                if (currentSheet) {
                    currentSheet.rowCount = sheetRowCount;
                }
            }
            inSheet = true;
            continue;
        }
        
        // If we're in a sheet, treat lines as table rows
        if (inSheet) {
            // Parse row using enhanced parser with previous rows context
            const cells = parseTableRow(trimmedLine, sheetColumnCount, tableRows);
            
            if (cells.length > 0) {
                // Update expected columns from first row if not set
                if (sheetColumnCount === null && cells.length > 1) {
                    sheetColumnCount = cells.length;
                    if (currentSheet) {
                        currentSheet.columnCount = sheetColumnCount;
                    }
                }
                
                // Normalize column count
                if (sheetColumnCount && cells.length !== sheetColumnCount) {
                    if (cells.length < sheetColumnCount) {
                        // Pad with empty cells
                        while (cells.length < sheetColumnCount) {
                            cells.push('');
                        }
                    } else if (cells.length > sheetColumnCount) {
                        // Merge excess into last column
                        const excess = cells.slice(sheetColumnCount).join(' ');
                        cells.splice(sheetColumnCount);
                        cells[sheetColumnCount - 1] = (cells[sheetColumnCount - 1] || '') + ' ' + excess;
                    }
                }
                
                // First non-metadata row is likely headers
                if (isFirstDataRow && headerRow === null) {
                    headerRow = cells;
                    isFirstDataRow = false;
                    tableRows.push(cells);
                } else {
                    // Ensure data rows match header length
                    if (headerRow && cells.length !== headerRow.length) {
                        if (cells.length < headerRow.length) {
                            while (cells.length < headerRow.length) {
                                cells.push('');
                            }
                        } else {
                            // Merge excess
                            const excess = cells.slice(headerRow.length).join(' ');
                            cells.splice(headerRow.length);
                            cells[headerRow.length - 1] = (cells[headerRow.length - 1] || '') + ' ' + excess;
                        }
                    }
                    currentTable.push(cells);
                    tableRows.push(cells);
                    isFirstDataRow = false;
                }
            }
        }
    }
    
    // Close any remaining sheet
    if (inSheet && (currentTable.length > 0 || headerRow)) {
        console.log('Closing sheet with', currentTable.length, 'rows and header:', !!headerRow);
        html += formatAsTable(currentTable, currentSheet, headerRow);
    }
    
    html += '</div>';
    console.log('formatExcelContent: Final HTML length:', html.length);
    return html;
}

/**
 * Format image content - display image and text
 * Enhanced version that uses file path from database with language detection
 * @param {string} filePath - Path to the image file (from database)
 * @param {string} content - Extracted text content
 * @param {number} fileId - Optional file ID for preview endpoint
 * @returns {string} - Formatted HTML
 */
function formatImageContent(filePath, content, fileId = null) {
    if (!filePath && !fileId) return '';
    
    // Detect language and direction from OCR text
    const direction = content ? detectTextDirection(content) : 'ltr';
    const lang = content ? detectLanguage(content) : 'en';
    
    let html = `<div class="formatted-image-content" dir="${direction}" lang="${lang}">`;
    
    // Display image
    html += '<div class="formatted-image-container">';
    
    // Try multiple methods to load the image
    let imageSrc = '';
    let imageSrcSet = [];
    
    if (filePath) {
        // Normalize path for use in URL
        const normalizedPath = filePath.replace(/\\/g, '/');
        
        // Method 1: Try file serving endpoint by path (preferred)
        const serveUrl = `/api/file/serve?path=${encodeURIComponent(filePath)}`;
        imageSrcSet.push(`"${serveUrl}"`);
        imageSrc = serveUrl;
        
        // Method 2: Try file serving endpoint by ID if available
        if (fileId) {
            const fileIdUrl = `/api/file/${fileId}/serve`;
            imageSrcSet.push(`"${fileIdUrl}"`);
        }
        
        // Method 3: Try direct file path as last resort (may work in some contexts)
        // For Windows paths, try file:/// protocol
        if (normalizedPath.match(/^[A-Za-z]:/)) {
            // Windows absolute path
            imageSrcSet.push(`"file:///${normalizedPath}"`);
        } else if (normalizedPath.startsWith('/')) {
            // Unix absolute path
            imageSrcSet.push(`"file://${normalizedPath}"`);
        }
    } else if (fileId) {
        // Only file ID available - use ID-based endpoint
        const fileIdUrl = `/api/file/${fileId}/serve`;
        imageSrc = fileIdUrl;
        imageSrcSet.push(`"${fileIdUrl}"`);
    }
    
    // Build img tag with data attributes for event handling
    // Use data attributes instead of inline handlers for better reliability
    const imageId = `img-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    html += `<img id="${imageId}" src="${imageSrc}" alt="Image" class="formatted-image" `;
    if (imageSrcSet.length > 1) {
        html += `data-fallback-sources='[${imageSrcSet.join(',')}]' `;
    }
    html += `data-file-id="${fileId || ''}" `;
    html += `data-file-path="${filePath ? escapeHtml(filePath) : ''}" `;
    html += `data-current-source-index="0">`;
    
    html += '<div class="image-load-error" style="display: none; padding: 1rem; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; color: #6c757d;">';
    html += '<i class="bi bi-exclamation-triangle me-2"></i><span class="error-message">Loading image...</span>';
    html += '</div>';
    html += '</div>';
    
    // Display file path info
    if (filePath) {
        html += '<div class="formatted-image-path">';
        html += '<small class="text-muted"><i class="bi bi-folder me-1"></i>Path: <code>' + escapeHtml(filePath) + '</code></small>';
        html += '</div>';
    }
    
    // Display extracted text if available
    if (content && content.trim()) {
        html += '<div class="formatted-image-text">';
        html += '<h5 class="formatted-image-text-title">Extracted Text (OCR):</h5>';
        html += `<pre class="formatted-text">${escapeHtml(content)}</pre>`;
        html += '</div>';
    }
    
    html += '</div>';
    
    // Return HTML - event listeners will be attached by the caller after DOM insertion
    return html;
}

/**
 * Organize content data for accurate display
 * This function processes the raw content to ensure proper structure before formatting
 * @param {string} content - Raw content text
 * @param {string} fileType - File type
 * @returns {string} - Organized content ready for formatting
 */
function organizeContentForDisplay(content, fileType) {
    if (!content || typeof content !== 'string') {
        return content || '';
    }
    
    const fileTypeLower = (fileType || '').toLowerCase();
    
    // For Word/Excel/PDF/PowerPoint files, ensure proper line breaks and structure
    if (fileTypeLower.match(/\.(docx?|docm|rtf|odt|xlsx?|xlsm|xlsb|xltx?|ods|pdf|pptx?|potx?|odp)$/)) {
        // Ensure proper line breaks and structure preservation
        let organized = content;
        
        // Normalize line breaks
        organized = organized.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        
        // Preserve spatial ordering markers if present (for new ordered format)
        // These markers help maintain the original document structure
        organized = organized.replace(/(word_paragraph|word_table|slide_text|slide_table|slide_image)/gi, '\n$1\n');
        
        // Ensure table headers are on separate lines (both legacy and new format)
        organized = organized.replace(/(Table\s+\d+)/gi, '\n$1\n');
        organized = organized.replace(/(Sheet:\s*[^\n]+)/gi, '\n$1\n');
        
        // Ensure page markers are on separate lines
        organized = organized.replace(/(Page\s+\d+)/gi, '\n$1\n');
        organized = organized.replace(/(Slide\s+\d+)/gi, '\n$1\n');
        
        // Preserve paragraph style markers
        organized = organized.replace(/(\[Style:\s*[^\]]+\])/g, '\n$1\n');
        
        // Clean up excessive newlines (more than 3 consecutive) but preserve structure
        organized = organized.replace(/\n{4,}/g, '\n\n\n');
        
        // Trim each line but preserve structure
        const lines = organized.split('\n');
        const cleanedLines = lines.map((line, index) => {
            // Don't trim lines that are clearly table rows (have tabs or multiple spaces)
            if (line.includes('\t') || line.match(/\s{2,}/)) {
                return line;
            }
            // Don't trim marker lines
            if (line.match(/^(word_|slide_|Table\s+\d+|Page\s+\d+|Slide\s+\d+|\[Style:)/i)) {
                return line.trim();
            }
            return line.trim();
        });
        
        return cleanedLines.join('\n');
    }
    
    return content;
}

/**
 * Format content based on file type
 * Enhanced version with content organization and better file type support
 * @param {string} content - Content text
 * @param {string} fileType - File type (e.g., '.docx', '.xlsx', '.jpg')
 * @param {string} filePath - File path (for images)
 * @param {number} fileId - Optional file ID (for image preview)
 * @returns {string} - Formatted HTML
 */
export function formatContentByType(content, fileType, filePath = '', fileId = null) {
    if (!content && !filePath) {
        console.log('formatContentByType: No content or file path provided');
        return '';
    }
    
    const fileTypeLower = (fileType || '').toLowerCase();
    // Normalize file type - ensure it starts with dot for pattern matching
    const normalizedFileType = fileTypeLower.startsWith('.') ? fileTypeLower : '.' + fileTypeLower;
    console.log('formatContentByType called:', {
        fileType: fileTypeLower,
        normalizedFileType: normalizedFileType,
        contentLength: content ? content.length : 0,
        hasFilePath: !!filePath,
        fileId: fileId
    });
    
    // Organize content for accurate display
    const organizedContent = organizeContentForDisplay(content || '', fileType);
    
    // Image files
    if (normalizedFileType.match(/\.(jpg|jpeg|png|gif|bmp|tiff|tif|webp|svg)$/)) {
        console.log('Formatting as image');
        return formatImageContent(filePath, organizedContent, fileId);
    }
    
    // Word documents - match both with and without dot
    if (normalizedFileType.match(/\.(docx?|docm|rtf|odt)$/) || fileTypeLower.match(/^(docx?|docm|rtf|odt)$/)) {
        console.log('Formatting as Word document');
        const result = formatWordContent(organizedContent);
        console.log('Word formatting result length:', result.length);
        return result;
    }
    
    // Excel files - match both with and without dot
    if (normalizedFileType.match(/\.(xlsx?|xlsm|xlsb|xltx?|ods|csv)$/) || fileTypeLower.match(/^(xlsx?|xlsm|xlsb|xltx?|ods|csv)$/)) {
        console.log('Formatting as Excel file');
        const result = formatExcelContent(organizedContent);
        console.log('Excel formatting result length:', result.length);
        return result;
    }
    
    // PowerPoint files - format as structured content with slides
    if (normalizedFileType.match(/\.(pptx?|potx?|odp)$/) || fileTypeLower.match(/^(pptx?|potx?|odp)$/)) {
        console.log('Formatting as PowerPoint file');
        return formatPowerPointContent(organizedContent);
    }
    
    // PDF files - format as structured content with pages
    if (normalizedFileType === '.pdf' || fileTypeLower === 'pdf') {
        console.log('Formatting as PDF file');
        return formatPDFContent(organizedContent);
    }
    
    // Email files - format as structured email messages
    if (normalizedFileType.match(/\.(eml|msg|mbox|pst)$/) || fileTypeLower.match(/^(eml|msg|mbox|pst)$/)) {
        console.log('Formatting as email file');
        return formatEmailContent(organizedContent);
    }
    
    // HTML files
    if (normalizedFileType.match(/\.(html|htm)$/) || fileTypeLower.match(/^(html|htm)$/)) {
        console.log('Formatting as HTML file');
        return formatHTMLContent(organizedContent);
    }
    
    // JSON files
    if (normalizedFileType === '.json' || fileTypeLower === 'json') {
        console.log('Formatting as JSON file');
        return formatJSONContent(organizedContent);
    }
    
    // XML files
    if (normalizedFileType.match(/\.(xml|xsl|xslt)$/) || fileTypeLower.match(/^(xml|xsl|xslt)$/)) {
        console.log('Formatting as XML file');
        return formatXMLContent(organizedContent);
    }
    
    // Text files with language detection
    if (normalizedFileType.match(/\.(txt|text|log|md|markdown)$/) || fileTypeLower.match(/^(txt|text|log|md|markdown)$/)) {
        console.log('Formatting as text file');
        return formatTextContent(organizedContent);
    }
    
    // Default: plain text with better formatting and language detection
    if (organizedContent) {
        return formatTextContent(organizedContent);
    }
    
    return '';
}

/**
 * Format PowerPoint content with slides
 * Enhanced with language detection and spatial order preservation
 * Preserves original slide element order: text, tables, and images appear
 * in the same spatial order as in the original presentation
 * @param {string} content - Content text (already in spatial order from database)
 * @returns {string} - Formatted HTML
 */
function formatPowerPointContent(content) {
    if (!content || typeof content !== 'string') {
        return '';
    }
    
    // Detect language and direction
    const direction = detectTextDirection(content);
    const lang = detectLanguage(content);
    
    const lines = content.split('\n');
    let html = `<div class="formatted-powerpoint-content" dir="${direction}" lang="${lang}">`;
    let currentSlide = [];
    let currentSlideHeader = null;
    let inSlide = false;
    let currentSlideNumber = 0;
    let currentTable = [];
    let currentTableHeader = null;
    let inTable = false;
    let expectedColumns = null;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();
        
        if (!trimmedLine) {
            // Empty line - end current table if in one
            if (inTable && currentTable.length > 0) {
                currentSlide.push({
                    type: 'table',
                    table: currentTable,
                    header: currentTableHeader
                });
                currentTable = [];
                currentTableHeader = null;
                inTable = false;
                expectedColumns = null;
            }
            continue;
        }
        
        // Skip explanatory text lines (metadata markers)
        if (isExplanatoryText(trimmedLine)) {
            // Extract slide number from "Slide N" for structure, but don't display the marker
            const slideMatch = trimmedLine.match(/^Slide\s+(\d+)/i);
            if (slideMatch) {
                if (inSlide && currentSlide.length > 0) {
                    html += formatSlide(currentSlide, currentSlideHeader);
                    currentSlide = [];
                }
                
                currentSlideHeader = {
                    number: parseInt(slideMatch[1]),
                    title: null  // Don't display metadata titles
                };
                currentSlideNumber = parseInt(slideMatch[1]);
                inSlide = true;
            }
            // Skip other metadata lines
            continue;
        }
        
        // Check for slide header (legacy format)
        const slideMatch = trimmedLine.match(/^Slide\s+(\d+)(?:\s*\|\s*(.+))?$/i);
        if (slideMatch) {
            // End previous slide
            if (inSlide && currentSlide.length > 0) {
                html += formatSlide(currentSlide, currentSlideHeader);
                currentSlide = [];
            }
            
            currentSlideHeader = {
                number: parseInt(slideMatch[1]),
                title: null  // Don't display metadata titles
            };
            currentSlideNumber = parseInt(slideMatch[1]);
            inSlide = true;
            continue;
        }
        
        // Check for slide element markers (new ordered format)
        const slideTextMatch = trimmedLine.match(/^slide_text/i);
        const slideTableMatch = trimmedLine.match(/^slide_table/i) || detectTableHeader(trimmedLine);
        const slideImageMatch = trimmedLine.match(/^slide_image/i) || trimmedLine.match(/\[Image:\s*(.+)\]/i);
        
        if (slideTextMatch) {
            // Slide text element - add to current slide
            if (!inSlide) {
                // Start new slide if not in one
                currentSlideNumber++;
                currentSlideHeader = { number: currentSlideNumber, title: null };
                inSlide = true;
            }
            // Skip the marker line, next line will be the text
            continue;
        } else if (slideTableMatch && !trimmedLine.match(/^slide_table/i)) {
            // Slide table element (detected via table header, not marker)
            if (!inSlide) {
                currentSlideNumber++;
                currentSlideHeader = { number: currentSlideNumber, title: null };
                inSlide = true;
            }
            
            // Check if this is a table header
            const tableHeader = detectTableHeader(trimmedLine);
            if (tableHeader && tableHeader.type === 'table') {
                // End previous table if any
                if (currentTable.length > 0) {
                    currentSlide.push({
                        type: 'table',
                        table: currentTable,
                        header: currentTableHeader
                    });
                    currentTable = [];
                }
                currentTableHeader = {
                    number: tableHeader.number,
                    caption: tableHeader.caption
                };
                inTable = true;
                expectedColumns = null;
            }
            // Continue processing - table rows will be handled below
        } else if (slideImageMatch) {
            // Slide image element
            if (!inSlide) {
                currentSlideNumber++;
                currentSlideHeader = { number: currentSlideNumber, title: null };
                inSlide = true;
            }
            const imageName = slideImageMatch[1] || 'image';
            currentSlide.push({
                type: 'image',
                name: imageName
            });
            continue;
        }
        
        if (inSlide) {
            // Check if we're in a table section
            if (inTable) {
                const cells = parseTableRow(trimmedLine, expectedColumns, currentTable);
                const isTableRow = cells.length > 1 || (cells.length === 1 && expectedColumns === 1);
                
                if (isTableRow) {
                    if (expectedColumns === null && currentTable.length === 0) {
                        expectedColumns = cells.length;
                    }
                    if (expectedColumns && cells.length !== expectedColumns) {
                        while (cells.length < expectedColumns) {
                            cells.push('');
                        }
                        if (cells.length > expectedColumns) {
                            const excess = cells.slice(expectedColumns).join(' ');
                            cells.splice(expectedColumns);
                            cells[expectedColumns - 1] = (cells[expectedColumns - 1] || '') + ' ' + excess;
                        }
                    }
                    currentTable.push(cells);
                } else if (currentTable.length > 0) {
                    // End of table
                    currentSlide.push({
                        type: 'table',
                        table: currentTable,
                        header: currentTableHeader
                    });
                    currentTable = [];
                    currentTableHeader = null;
                    inTable = false;
                    expectedColumns = null;
                    // Add this line as text
                    currentSlide.push({
                        type: 'text',
                        text: trimmedLine
                    });
                } else {
                    currentSlide.push({
                        type: 'text',
                        text: trimmedLine
                    });
                }
            } else {
                // Regular text content
                currentSlide.push({
                    type: 'text',
                    text: trimmedLine
                });
            }
        } else {
            // Regular content before first slide
            html += formatParagraph(trimmedLine);
        }
    }
    
    // Close any remaining table
    if (inTable && currentTable.length > 0) {
        currentSlide.push({
            type: 'table',
            table: currentTable,
            header: currentTableHeader
        });
    }
    
    // Close last slide
    if (inSlide && currentSlide.length > 0) {
        html += formatSlide(currentSlide, currentSlideHeader);
    }
    
    html += '</div>';
    return html;
}

/**
 * Format a single slide
 * @param {Array<string|Object>} slideContent - Slide content (lines or structured elements)
 * @param {Object} slideHeader - Slide header info
 * @returns {string} - Formatted HTML
 */
function formatSlide(slideContent, slideHeader) {
    let html = '<div class="formatted-slide">';
    
    // Don't display slide header - it's just explanatory metadata
    // The slide number is used internally for ordering only
    
    html += '<div class="formatted-slide-content">';
    
    // Check if slideContent is structured (new format) or plain lines (legacy)
    if (slideContent.length > 0 && typeof slideContent[0] === 'object' && slideContent[0].type) {
        // New structured format - process elements in order
        slideContent.forEach(element => {
            if (element.type === 'text') {
                html += formatParagraph(element.text);
            } else if (element.type === 'table') {
                html += formatAsTable(element.table, element.header);
            } else if (element.type === 'image') {
                html += `<div class="formatted-slide-image">[Image: ${escapeHtml(element.name)}]</div>`;
            }
        });
    } else {
        // Legacy format - plain text lines
        slideContent.forEach(line => {
            if (typeof line === 'string' && line.trim()) {
                html += formatParagraph(line);
            }
        });
    }
    
    html += '</div>';
    
    html += '</div>';
    return html;
}

/**
 * Format PDF content with pages
 * Preserves original page order and spatial relationships
 * Content is already in spatial order from database storage
 * Hides explanatory metadata (page headers, method info, etc.)
 * @param {string} content - Content text (already in spatial order)
 * @returns {string} - Formatted HTML
 */
function formatPDFContent(content) {
    if (!content || typeof content !== 'string') {
        return '';
    }
    
    // Detect language and direction
    const direction = detectTextDirection(content);
    const lang = detectLanguage(content);
    
    const lines = content.split('\n');
    let html = `<div class="formatted-pdf-content" dir="${direction}" lang="${lang}">`;
    let currentPage = [];
    let currentPageHeader = null;
    let inPage = false;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();
        
        if (!trimmedLine) {
            if (inPage && currentPage.length > 0) {
                html += formatPage(currentPage, currentPageHeader);
                currentPage = [];
                currentPageHeader = null;
                inPage = false;
            }
            continue;
        }
        
        // Skip explanatory text lines (metadata markers)
        if (isExplanatoryText(trimmedLine)) {
            // Extract page number from "Page N" for structure, but don't display the marker
            const pageMatch = trimmedLine.match(/^Page\s+(\d+)/i);
            if (pageMatch) {
                if (inPage && currentPage.length > 0) {
                    html += formatPage(currentPage, currentPageHeader);
                    currentPage = [];
                }
                
                currentPageHeader = {
                    number: parseInt(pageMatch[1]),
                    metadata: null  // Don't display metadata
                };
                inPage = true;
            }
            // Skip other metadata lines (Method:, Length:, etc.)
            continue;
        }
        
        // Check for page header
        const pageMatch = trimmedLine.match(/^Page\s+(\d+)(?:\s*\|\s*(.+))?$/i);
        if (pageMatch) {
            if (inPage && currentPage.length > 0) {
                html += formatPage(currentPage, currentPageHeader);
                currentPage = [];
            }
            
            currentPageHeader = {
                number: parseInt(pageMatch[1]),
                metadata: null  // Don't display metadata
            };
            inPage = true;
            continue;
        }
        
        if (inPage) {
            // Remove any remaining explanatory text from page content
            const cleanedLine = removeExplanatoryText(trimmedLine);
            if (cleanedLine && cleanedLine.trim()) {
                currentPage.push(cleanedLine.trim());
            }
        } else {
            // Regular content before first page - skip if it's explanatory
            if (!isExplanatoryText(trimmedLine)) {
                html += formatParagraph(trimmedLine);
            }
        }
    }
    
    if (inPage && currentPage.length > 0) {
        html += formatPage(currentPage, currentPageHeader);
    }
    
    html += '</div>';
    return html;
}

/**
 * Format a single PDF page
 * @param {Array<string>} pageContent - Page content lines
 * @param {Object} pageHeader - Page header info
 * @returns {string} - Formatted HTML
 */
function formatPage(pageContent, pageHeader) {
    let html = '<div class="formatted-page">';
    
    // Don't display page header - it's just explanatory metadata
    // The page number is used internally for ordering only
    
    html += '<div class="formatted-page-content">';
    pageContent.forEach(line => {
        if (line.trim()) {
            html += formatParagraph(line);
        }
    });
    html += '</div>';
    
    html += '</div>';
    return html;
}

/**
 * Format email content with proper structure
 * Handles single messages and multiple messages (MBOX/PST)
 * @param {string} content - Content text
 * @returns {string} - Formatted HTML
 */
function formatEmailContent(content) {
    if (!content || typeof content !== 'string') {
        return '';
    }
    
    // Detect language and direction
    const direction = detectTextDirection(content);
    const lang = detectLanguage(content);
    
    const lines = content.split('\n');
    let html = `<div class="formatted-email-content" dir="${direction}" lang="${lang}">`;
    let currentMessage = [];
    let currentMessageHeader = null;
    let inMessage = false;
    let messageIndex = 0;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();
        
        if (!trimmedLine) {
            if (inMessage && currentMessage.length > 0) {
                html += formatEmailMessage(currentMessage, currentMessageHeader, messageIndex);
                currentMessage = [];
                currentMessageHeader = null;
                inMessage = false;
                messageIndex++;
            }
            continue;
        }
        
        // Check for message header patterns
        const messageMatch = trimmedLine.match(/^Message\s*#(\d+)/i);
        const fromMatch = trimmedLine.match(/^From:\s*(.+)$/i);
        const subjectMatch = trimmedLine.match(/^Subject:\s*(.+)$/i);
        
        if (messageMatch || (fromMatch && !inMessage)) {
            // Start new message
            if (inMessage && currentMessage.length > 0) {
                html += formatEmailMessage(currentMessage, currentMessageHeader, messageIndex);
                currentMessage = [];
                messageIndex++;
            }
            
            currentMessageHeader = {
                index: messageMatch ? parseInt(messageMatch[1]) : messageIndex + 1
            };
            inMessage = true;
            
            if (fromMatch) {
                currentMessageHeader.from = fromMatch[1].trim();
            }
            if (subjectMatch) {
                currentMessageHeader.subject = subjectMatch[1].trim();
            }
            
            // Continue to collect header fields
            currentMessage.push(trimmedLine);
            continue;
        }
        
        // Collect header fields
        if (inMessage) {
            const toMatch = trimmedLine.match(/^To:\s*(.+)$/i);
            const dateMatch = trimmedLine.match(/^Date:\s*(.+)$/i);
            const ccMatch = trimmedLine.match(/^CC:\s*(.+)$/i);
            const bccMatch = trimmedLine.match(/^BCC:\s*(.+)$/i);
            const msgIdMatch = trimmedLine.match(/^Message-ID:\s*(.+)$/i);
            
            if (toMatch) {
                currentMessageHeader = currentMessageHeader || { index: messageIndex + 1 };
                currentMessageHeader.to = toMatch[1].trim();
                currentMessage.push(trimmedLine);
            } else if (dateMatch) {
                currentMessageHeader = currentMessageHeader || { index: messageIndex + 1 };
                currentMessageHeader.date = dateMatch[1].trim();
                currentMessage.push(trimmedLine);
            } else if (ccMatch) {
                currentMessageHeader = currentMessageHeader || { index: messageIndex + 1 };
                currentMessageHeader.cc = ccMatch[1].trim();
                currentMessage.push(trimmedLine);
            } else if (bccMatch) {
                currentMessageHeader = currentMessageHeader || { index: messageIndex + 1 };
                currentMessageHeader.bcc = bccMatch[1].trim();
                currentMessage.push(trimmedLine);
            } else if (msgIdMatch) {
                currentMessageHeader = currentMessageHeader || { index: messageIndex + 1 };
                currentMessageHeader.messageId = msgIdMatch[1].trim();
                currentMessage.push(trimmedLine);
            } else if (trimmedLine.match(/^---\s*Message Content\s*---/i)) {
                // Content separator - keep it but mark content start
                currentMessage.push(trimmedLine);
            } else {
                // Regular content line
                currentMessage.push(trimmedLine);
            }
        } else {
            // Content before first message
            html += formatParagraph(trimmedLine);
        }
    }
    
    if (inMessage && currentMessage.length > 0) {
        html += formatEmailMessage(currentMessage, currentMessageHeader, messageIndex);
    }
    
    html += '</div>';
    return html;
}

/**
 * Format a single email message
 * @param {Array<string>} messageContent - Message content lines
 * @param {Object} messageHeader - Message header info
 * @param {number} messageIndex - Message index
 * @returns {string} - Formatted HTML
 */
function formatEmailMessage(messageContent, messageHeader, messageIndex) {
    const direction = detectTextDirection(messageContent.join('\n'));
    const lang = detectLanguage(messageContent.join('\n'));
    
    let html = `<div class="formatted-email-message" dir="${direction}" lang="${lang}">`;
    
    // Message header
    html += '<div class="formatted-email-header">';
    if (messageHeader) {
        if (messageHeader.index) {
            html += `<div class="formatted-email-index">Message #${messageHeader.index}</div>`;
        }
        if (messageHeader.from) {
            html += `<div class="formatted-email-field"><strong>From:</strong> ${escapeHtml(messageHeader.from)}</div>`;
        }
        if (messageHeader.to) {
            html += `<div class="formatted-email-field"><strong>To:</strong> ${escapeHtml(messageHeader.to)}</div>`;
        }
        if (messageHeader.cc) {
            html += `<div class="formatted-email-field"><strong>CC:</strong> ${escapeHtml(messageHeader.cc)}</div>`;
        }
        if (messageHeader.bcc) {
            html += `<div class="formatted-email-field"><strong>BCC:</strong> ${escapeHtml(messageHeader.bcc)}</div>`;
        }
        if (messageHeader.subject) {
            html += `<div class="formatted-email-subject"><strong>Subject:</strong> ${escapeHtml(messageHeader.subject)}</div>`;
        }
        if (messageHeader.date) {
            html += `<div class="formatted-email-field"><strong>Date:</strong> ${escapeHtml(messageHeader.date)}</div>`;
        }
        if (messageHeader.messageId) {
            html += `<div class="formatted-email-field"><small><strong>Message-ID:</strong> ${escapeHtml(messageHeader.messageId)}</small></div>`;
        }
    }
    html += '</div>';
    
    // Message content
    html += '<div class="formatted-email-body">';
    let inContent = false;
    messageContent.forEach(line => {
        const trimmedLine = line.trim();
        if (trimmedLine.match(/^---\s*Message Content\s*---/i)) {
            inContent = true;
            return;
        }
        if (inContent || (!trimmedLine.match(/^(From|To|CC|BCC|Subject|Date|Message-ID|Message\s*#):/i) && trimmedLine)) {
            html += formatParagraph(trimmedLine);
        }
    });
    html += '</div>';
    
    html += '</div>';
    return html;
}

/**
 * Format HTML content
 * @param {string} content - Content text
 * @returns {string} - Formatted HTML
 */
function formatHTMLContent(content) {
    if (!content || typeof content !== 'string') {
        return '';
    }
    
    const direction = detectTextDirection(content);
    const lang = detectLanguage(content);
    
    // For HTML, we can display it directly but sanitize it
    // In a real implementation, you might want to use DOMPurify or similar
    let html = `<div class="formatted-html-content" dir="${direction}" lang="${lang}">`;
    html += `<pre class="formatted-text">${escapeHtml(content)}</pre>`;
    html += '</div>';
    return html;
}

/**
 * Format JSON content
 * @param {string} content - Content text
 * @returns {string} - Formatted HTML
 */
function formatJSONContent(content) {
    if (!content || typeof content !== 'string') {
        return '';
    }
    
    const direction = detectTextDirection(content);
    const lang = detectLanguage(content);
    
    let html = `<div class="formatted-json-content" dir="${direction}" lang="${lang}">`;
    
    try {
        // Try to parse and pretty-print JSON
        const parsed = JSON.parse(content);
        const pretty = JSON.stringify(parsed, null, 2);
        html += `<pre class="formatted-json"><code>${escapeHtml(pretty)}</code></pre>`;
    } catch (e) {
        // If not valid JSON, display as-is
        html += `<pre class="formatted-text">${escapeHtml(content)}</pre>`;
    }
    
    html += '</div>';
    return html;
}

/**
 * Format XML content
 * @param {string} content - Content text
 * @returns {string} - Formatted HTML
 */
function formatXMLContent(content) {
    if (!content || typeof content !== 'string') {
        return '';
    }
    
    const direction = detectTextDirection(content);
    const lang = detectLanguage(content);
    
    let html = `<div class="formatted-xml-content" dir="${direction}" lang="${lang}">`;
    
    // Simple XML formatting (indent based on tags)
    let formatted = content;
    try {
        // Basic XML indentation
        formatted = content.replace(/(>)(<)(\/*)/g, '$1\n$2$3');
        const lines = formatted.split('\n');
        let indent = 0;
        formatted = lines.map(line => {
            const trimmed = line.trim();
            if (!trimmed) return '';
            if (trimmed.match(/^<\/\w/)) indent--;
            const indented = '  '.repeat(Math.max(0, indent)) + trimmed;
            if (trimmed.match(/^<\w[^>]*[^\/]>.*$/)) indent++;
            return indented;
        }).join('\n');
    } catch (e) {
        formatted = content;
    }
    
    html += `<pre class="formatted-xml"><code>${escapeHtml(formatted)}</code></pre>`;
    html += '</div>';
    return html;
}

/**
 * Format text content with language detection
 * @param {string} content - Content text
 * @returns {string} - Formatted HTML
 */
function formatTextContent(content) {
    if (!content || typeof content !== 'string') {
        return '';
    }
    
    const direction = detectTextDirection(content);
    const lang = detectLanguage(content);
    
    let html = `<div class="formatted-text-content" dir="${direction}" lang="${lang}">`;
    html += `<pre class="formatted-text">${escapeHtml(content)}</pre>`;
    html += '</div>';
    return html;
}

/**
 * Escape HTML special characters
 * @param {string} text - Text to escape
 * @returns {string} - Escaped text
 */
function escapeHtml(text) {
    if (typeof text !== 'string') return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

