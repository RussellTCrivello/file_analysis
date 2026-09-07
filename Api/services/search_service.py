"""
Search Service - Enhanced Full-Text Search with PostgreSQL
Provides advanced search capabilities including full-text search, sorting, and filtering
Now includes Google-like search algorithms: BM25, query expansion, fuzzy matching, autocomplete
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date
from Api.utils import execute_query, load_text_content, get_connection, return_connection
from Api.services.search_algorithms import (
    SearchRanker, QueryExpander, FuzzyMatcher, QueryUnderstanding
)

logger = logging.getLogger(__name__)


class SearchService:
    """
    Enhanced search service with PostgreSQL full-text search capabilities.
    
    This service provides:
    - Full-text search using PostgreSQL tsvector/tsquery
    - Google-like BM25 ranking algorithm
    - Query expansion with synonyms
    - Fuzzy matching for typo tolerance
    - Autocomplete/suggestions
    - Multi-field boosting
    - Recency boost
    - Phrase matching
    - Sortable search results
    - Advanced filtering
    - Search history tracking
    - Saved searches management
    """
    
    # Initialize algorithm components (singleton pattern)
    _search_ranker = None
    _query_expander = None
    _fuzzy_matcher = None
    _query_understanding = None
    
    @classmethod
    def _get_ranker(cls):
        """Get or create search ranker instance."""
        if cls._search_ranker is None:
            cls._search_ranker = SearchRanker()
        return cls._search_ranker
    
    @classmethod
    def _get_expander(cls):
        """Get or create query expander instance."""
        if cls._query_expander is None:
            cls._query_expander = QueryExpander()
        return cls._query_expander
    
    @classmethod
    def _get_fuzzy_matcher(cls):
        """Get or create fuzzy matcher instance."""
        if cls._fuzzy_matcher is None:
            cls._fuzzy_matcher = FuzzyMatcher()
        return cls._fuzzy_matcher
    
    @classmethod
    def _get_query_understanding(cls):
        """Get or create query understanding instance."""
        if cls._query_understanding is None:
            cls._query_understanding = QueryUnderstanding()
        return cls._query_understanding
    
    @staticmethod
    def full_text_search(
        query: str,
        file_type: Optional[str] = None,
        source_id: Optional[int] = None,
        side_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        category_id: Optional[int] = None,
        sort_by: str = 'relevance',
        sort_order: str = 'desc',
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Perform full-text search using PostgreSQL tsvector/tsquery.
        
        Args:
            query: Search query string
            file_type: Filter by file type
            source_id: Filter by source ID
            side_id: Filter by side ID
            date_from: Start date filter (YYYY-MM-DD)
            date_to: End date filter (YYYY-MM-DD)
            category_id: Filter by category ID
            sort_by: Sort field ('relevance', 'date', 'name', 'type', 'size')
            sort_order: Sort order ('asc' or 'desc')
            limit: Maximum number of results
            offset: Offset for pagination
        
        Returns:
            Tuple of (results list, total count)
        """
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Build WHERE conditions
            where_conditions = []
            params = []
            
            # Google-like search: supports partial words, multiple words, numbers, and partial text
            if query and len(query.strip()) >= 2:
                query_clean = query.strip()
                search_terms = query_clean.split()
                
                # Build search conditions using ILIKE for partial matching (Google-like)
                # This supports:
                # - Partial word matching (e.g., "fin" matches "financial")
                # - Multiple words with OR logic (at least one word matches)
                # - Numbers (e.g., "2023", "12345")
                # - Partial text matching (e.g., "report 2023" matches files with "report" or "2023")
                
                search_conditions = []
                
                # For each search term, create a condition that matches:
                # 1. File names containing the term (partial match)
                # 2. Words in file content containing the term (partial match)
                for term in search_terms:
                    # Escape special characters for ILIKE
                    term_escaped = term.replace("'", "''").replace("%", "\\%").replace("_", "\\_")
                    term_pattern = f'%{term_escaped}%'
                    
                    # Search in file names
                    search_conditions.append(f"p.file_name ILIKE %s")
                    params.append(term_pattern)
                    
                    # Search in content words
                    search_conditions.append(f"""
                        EXISTS (
                            SELECT 1 FROM words_paths wp
                            JOIN words w ON wp.word_id = w.id
                            WHERE wp.path_id = p.id
                            AND w.word ILIKE %s
                        )
                    """)
                    params.append(term_pattern)
                
                # Combine all conditions with OR (Google-like: at least one term matches)
                # This allows searching for "financial report" to find files with either "financial" OR "report"
                if search_conditions:
                    where_conditions.append(f"({' OR '.join(search_conditions)})")
                
                # Also try full-text search for better ranking (optional enhancement)
                # This provides better relevance scoring for exact word matches
                try:
                    tsquery_terms = ' & '.join([term.replace("'", "''") for term in search_terms])
                    # Add full-text search as additional boost (not required, just for ranking)
                    # We'll use this in the ORDER BY for relevance scoring
                except:
                    tsquery_terms = None
            
            # File type filter
            if file_type:
                where_conditions.append("p.file_type = %s")
                params.append(file_type)
            
            # Source filter
            if source_id:
                where_conditions.append("h.source_id = %s")
                params.append(source_id)
            
            # Side filter
            if side_id:
                where_conditions.append("h.side_id = %s")
                params.append(side_id)
            
            # Date filters
            if date_from:
                where_conditions.append("p.file_date >= %s")
                params.append(date_from)
            
            if date_to:
                where_conditions.append("p.file_date <= %s")
                params.append(date_to)
            
            # Category filter
            if category_id:
                where_conditions.append("""
                    EXISTS (
                        SELECT 1 FROM words_paths wp2
                        JOIN words_categorys wc ON wp2.word_id = wc.word_id
                        WHERE wp2.path_id = p.id AND wc.category_id = %s
                    )
                """)
                params.append(category_id)
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            # Build ORDER BY clause for window function and final sorting
            order_by_clause = SearchService._build_order_by(sort_by, sort_order, query)
            # For final ORDER BY, remove table alias prefix since we're selecting from CTE
            order_by_final = order_by_clause.replace('p.', '')
            
            # For window function ORDER BY, we need to handle relevance_score specially
            # PostgreSQL doesn't allow referencing column aliases in window functions in the same SELECT
            # So we need to use the full expression when sorting by relevance
            order_by_window = order_by_clause
            if sort_by == 'relevance' and query:
                # Extract the sort order (ASC/DESC)
                order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
                # Use the same relevance calculation as in the SELECT clause
                # This ensures consistent ranking
                order_by_window = f"""
                    (CASE
                        WHEN query IS NOT NULL THEN
                            COALESCE((
                                SELECT 
                                    SUM(
                                        CASE 
                                            WHEN p.file_name ILIKE '%' || term || '%' THEN 2.0
                                            WHEN EXISTS (
                                                SELECT 1 FROM words_paths wp
                                                JOIN words w ON wp.word_id = w.id
                                                WHERE wp.path_id = p.id
                                                AND w.word ILIKE '%' || term || '%'
                                            ) THEN 1.0
                                            ELSE 0.0
                                        END
                                    )
                                FROM unnest(string_to_array(query, ' ')) AS term
                            ), 0)
                        ELSE 0
                    END) {order}, p.file_date DESC
                """
            
            # Count query
            count_query = f"""
                SELECT COUNT(DISTINCT p.id)
                FROM paths p
                LEFT JOIN hashs h ON p.hash_id = h.id
                WHERE {where_clause}
            """
            
            cursor.execute(count_query, tuple(params))
            total_count = cursor.fetchone()[0]
            
            # Main search query with ranking using window function for proper sorting
            # Use ROW_NUMBER() instead of DISTINCT ON to allow flexible sorting
            search_query = f"""
                WITH ranked_results AS (
                    SELECT 
                        p.id,
                        p.file_name,
                        p.file_path,
                        p.file_type,
                        p.file_size,
                        p.file_date,
                        p.file_status,
                        p.date_creation,
                        COALESCE(s.name, 'Unknown') as source_name,
                        COALESCE(si.name, 'Unknown') as side_name,
                        h.source_id,
                        h.side_id,
                        CASE
                            WHEN query IS NOT NULL THEN
                                -- Google-like relevance: count matching search terms
                                -- Higher score for matches in file name, lower for content matches
                                (
                                    -- Check each search term and sum relevance
                                    -- File name matches get 2.0 points, content matches get 1.0 point
                                    COALESCE((
                                        SELECT 
                                            SUM(
                                                CASE 
                                                    WHEN p.file_name ILIKE '%' || term || '%' THEN 2.0
                                                    WHEN EXISTS (
                                                        SELECT 1 FROM words_paths wp
                                                        JOIN words w ON wp.word_id = w.id
                                                        WHERE wp.path_id = p.id
                                                        AND w.word ILIKE '%' || term || '%'
                                                    ) THEN 1.0
                                                    ELSE 0.0
                                                END
                                            )
                                        FROM unnest(string_to_array(query, ' ')) AS term
                                    ), 0)
                                )
                            ELSE 0
                        END as relevance_score,
                        ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY {order_by_window}) as rn
                    FROM paths p
                    LEFT JOIN hashs h ON p.hash_id = h.id
                    LEFT JOIN sources s ON h.source_id = s.id
                    LEFT JOIN sides si ON h.side_id = si.id
                    CROSS JOIN LATERAL (
                        SELECT %s::text as query
                    ) q
                    WHERE {where_clause}
                )
                SELECT 
                    id,
                    file_name,
                    file_path,
                    file_type,
                    file_size,
                    file_date,
                    file_status,
                    date_creation,
                    source_name,
                    side_name,
                    source_id,
                    side_id,
                    relevance_score
                FROM ranked_results
                WHERE rn = 1
                ORDER BY {order_by_final}
                LIMIT %s OFFSET %s
            """
            
            # Add query parameter for relevance calculation
            if query and len(query.strip()) >= 2:
                # Pass the full query string for relevance calculation
                params_with_query = [query.strip()] + params + [limit, offset]
            else:
                params_with_query = [''] + params + [limit, offset]
            
            cursor.execute(search_query, tuple(params_with_query))
            
            # Fetch results
            results = []
            for row in cursor.fetchall():
                result = {
                    'id': row[0],
                    'file_name': row[1],
                    'file_path': row[2],
                    'file_type': row[3],
                    'file_size': row[4],
                    'file_date': row[5].isoformat() if row[5] else None,
                    'file_status': str(row[6]),
                    'date_creation': row[7].isoformat() if row[7] else None,
                    'source_name': row[8],
                    'side_name': row[9],
                    'source_id': row[10],
                    'side_id': row[11],
                    'relevance_score': float(row[12]) if row[12] else 0.0
                }
                
                # Find matching lines in content if query is provided
                # Return all matching lines (no limit for comprehensive search)
                if query and len(query.strip()) >= 2:
                    line_matches = SearchService._find_matching_lines(row[0], query, max_matches=None)
                    if line_matches:
                        result['line_matches'] = line_matches
                        result['line_match_count'] = len(line_matches)
                
                results.append(result)
            
            cursor.close()
            return_connection(conn)
            
            return results, total_count
            
        except Exception as e:
            logger.error(f"Full-text search error: {e}", exc_info=True)
            if conn:
                return_connection(conn)
            return [], 0
    
    @staticmethod
    def _find_matching_lines(path_id: int, query: str, max_matches: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Find lines in file content that contain the search query.
        
        Args:
            path_id: Path ID of the file
            query: Search query string
            max_matches: Maximum number of line matches to return (None = all matches)
        
        Returns:
            List of dictionaries with line_number, line_text, and context
        """
        try:
            # Load file content
            content = load_text_content(path_id)
            if not content:
                return []
            
            # Split content into lines
            lines = content.split('\n')
            
            # Clean the query - search for the entire phrase as a whole
            query_clean = query.strip()
            
            if not query_clean:
                return []
            
            # Prepare the search pattern - search for the entire query text as a phrase
            # Handle whitespace variations (multiple spaces, tabs) but keep word order
            # Split query into words and create a flexible pattern
            query_words = query_clean.split()
            
            if len(query_words) == 1:
                # Single word - simple search
                search_pattern = re.escape(query_clean)
            else:
                # Multiple words - create pattern that allows flexible whitespace
                # Escape each word and join with pattern that matches whitespace variations
                escaped_words = [re.escape(word) for word in query_words]
                # Match any whitespace (spaces, tabs) between words
                search_pattern = r'\s+'.join(escaped_words)
            
            # Compile pattern for case-insensitive search
            pattern = re.compile(search_pattern, re.IGNORECASE)
            
            # Find matching lines
            matches = []
            for line_num, line in enumerate(lines, start=1):
                # Check if the entire query phrase appears in this line
                if pattern.search(line):
                    # Get context (previous and next line if available)
                    context_before = lines[line_num - 2] if line_num > 1 else None
                    context_after = lines[line_num] if line_num < len(lines) else None
                    
                    # Highlight the entire phrase in the line
                    # Find all occurrences and highlight them
                    highlighted_line = pattern.sub(
                        lambda m: f'<mark>{m.group()}</mark>',
                        line
                    )
                    
                    matches.append({
                        'line_number': line_num,
                        'line_text': line,
                        'highlighted_line': highlighted_line,
                        'context_before': context_before,
                        'context_after': context_after
                    })
                    
                    # Limit number of matches if specified
                    if max_matches and len(matches) >= max_matches:
                        break
            
            return matches
            
        except Exception as e:
            logger.error(f"Error finding matching lines for path_id={path_id}: {e}", exc_info=True)
            return []
    
    @staticmethod
    def _build_order_by(sort_by: str, sort_order: str, query: Optional[str] = None) -> str:
        """
        Build ORDER BY clause based on sort parameters.
        
        Args:
            sort_by: Sort field name
            sort_order: Sort order ('asc' or 'desc')
            query: Optional search query for relevance sorting
        
        Returns:
            ORDER BY clause string (without p.id prefix, as we use window functions)
        """
        order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
        
        if sort_by == 'relevance' and query:
            return f"relevance_score {order}, p.file_date DESC"
        elif sort_by == 'date':
            return f"p.file_date {order}, p.id"
        elif sort_by == 'name':
            return f"p.file_name {order}, p.id"
        elif sort_by == 'type':
            return f"p.file_type {order}, p.file_name ASC, p.id"
        elif sort_by == 'size':
            return f"p.file_size {order}, p.file_name ASC, p.id"
        else:
            return f"p.file_date DESC, p.id"
    
    @staticmethod
    def simple_search(
        query: str,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Simple search using ILIKE for backward compatibility.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            offset: Offset for pagination
        
        Returns:
            Tuple of (results list, total count)
        """
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            if not query or len(query.strip()) < 2:
                cursor.close()
                return_connection(conn)
                return [], 0
            
            query_clean = query.strip()
            search_terms = query_clean.split()
            
            # Google-like search: build conditions for each term with OR logic
            search_conditions = []
            search_params = []
            
            for term in search_terms:
                # Escape special characters for ILIKE
                term_escaped = term.replace("'", "''").replace("%", "\\%").replace("_", "\\_")
                term_pattern = f'%{term_escaped}%'
                
                # Search in file names
                search_conditions.append("p.file_name ILIKE %s")
                search_params.append(term_pattern)
                
                # Search in content words
                search_conditions.append("""
                    EXISTS (
                        SELECT 1 FROM words_paths wp
                        JOIN words w ON wp.word_id = w.id
                        WHERE wp.path_id = p.id
                        AND w.word ILIKE %s
                    )
                """)
                search_params.append(term_pattern)
            
            where_clause = f"({' OR '.join(search_conditions)})" if search_conditions else "1=1"
            
            # Count query
            count_query = f"""
                SELECT COUNT(DISTINCT p.id)
                FROM paths p
                LEFT JOIN hashs h ON p.hash_id = h.id
                WHERE {where_clause}
            """
            
            cursor.execute(count_query, tuple(search_params))
            total_count = cursor.fetchone()[0]
            
            # Main query with relevance scoring
            search_query = f"""
                SELECT DISTINCT ON (p.id)
                    p.id, p.file_name, p.file_path, p.file_type,
                    p.file_size, p.file_date, p.file_status, p.date_creation,
                    COALESCE(s.name, 'Unknown') as source_name,
                    COALESCE(si.name, 'Unknown') as side_name,
                    h.source_id, h.side_id,
                    -- Google-like relevance score
                    COALESCE((
                        SELECT 
                            SUM(
                                CASE 
                                    WHEN p.file_name ILIKE '%' || term || '%' THEN 2.0
                                    WHEN EXISTS (
                                        SELECT 1 FROM words_paths wp
                                        JOIN words w ON wp.word_id = w.id
                                        WHERE wp.path_id = p.id
                                        AND w.word ILIKE '%' || term || '%'
                                    ) THEN 1.0
                                    ELSE 0.0
                                END
                            )
                        FROM unnest(string_to_array(%s, ' ')) AS term
                    ), 0) as relevance_score
                FROM paths p
                LEFT JOIN hashs h ON p.hash_id = h.id
                LEFT JOIN sources s ON h.source_id = s.id
                LEFT JOIN sides si ON h.side_id = si.id
                WHERE {where_clause}
                ORDER BY p.id, relevance_score DESC, p.file_date DESC
                LIMIT %s OFFSET %s
            """
            
            cursor.execute(search_query, tuple(search_params + [query_clean, limit, offset]))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row[0],
                    'file_name': row[1],
                    'file_path': row[2],
                    'file_type': row[3],
                    'file_size': row[4],
                    'file_date': row[5].isoformat() if row[5] else None,
                    'file_status': str(row[6]),
                    'date_creation': row[7].isoformat() if row[7] else None,
                    'source_name': row[8],
                    'side_name': row[9],
                    'source_id': row[10],
                    'side_id': row[11],
                    'relevance_score': float(row[12]) if len(row) > 12 and row[12] is not None else 0.0
                })
            
            cursor.close()
            return_connection(conn)
            
            return results, total_count
            
        except Exception as e:
            logger.error(f"Simple search error: {e}", exc_info=True)
            if conn:
                return_connection(conn)
            return [], 0
    
    @staticmethod
    def advanced_search(
        query: str,
        file_type: Optional[str] = None,
        source_id: Optional[int] = None,
        side_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        category_id: Optional[int] = None,
        source_ids: Optional[List[int]] = None,
        side_ids: Optional[List[int]] = None,
        category_ids: Optional[List[int]] = None,
        sort_by: str = 'relevance',
        sort_order: str = 'desc',
        limit: int = 100,
        offset: int = 0,
        use_bm25: bool = True,
        use_expansion: bool = True,
        use_fuzzy: bool = True
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Advanced search using Google-like algorithms (BM25, query expansion, fuzzy matching).
        
        Args:
            query: Search query string
            file_type: Filter by file type (can be string or list)
            source_id: Filter by source ID (single value, for backward compatibility)
            side_id: Filter by side ID (single value, for backward compatibility)
            date_from: Start date filter (YYYY-MM-DD)
            date_to: End date filter (YYYY-MM-DD)
            category_id: Filter by category ID (single value, for backward compatibility)
            source_ids: Filter by multiple source IDs (list)
            side_ids: Filter by multiple side IDs (list)
            category_ids: Filter by multiple category IDs (list)
            sort_by: Sort field ('relevance', 'date', 'name', 'type', 'size')
            sort_order: Sort order ('asc' or 'desc')
            limit: Maximum number of results
            offset: Offset for pagination
            use_bm25: Use BM25 ranking algorithm
            use_expansion: Use query expansion
            use_fuzzy: Use fuzzy matching
        
        Returns:
            Tuple of (results list, total count)
        """
        # Initialize lists if not provided
        if source_ids is None:
            source_ids = []
        if side_ids is None:
            side_ids = []
        if category_ids is None:
            category_ids = []
        
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                
                # Understand query intent
                intent = SearchService._get_query_understanding().detect_intent(query)
                
                # Build WHERE conditions
                where_conditions = []
                params = []
                
                # Handle Google-like query parsing with operators and quotes
                if intent['has_quotes'] or intent['has_operators']:
                    # Complex query with phrases and/or operators
                    query_conditions = []
                    
                    # Handle quoted phrases (exact matches)
                    if intent['has_quotes']:
                        phrases = intent['phrases']
                        for phrase in phrases:
                            phrase_conditions = []
                            phrase_conditions.append("p.file_name ILIKE %s")
                            phrase_conditions.append("""
                                EXISTS (
                                    SELECT 1 FROM words_paths wp
                                    JOIN words w ON wp.word_id = w.id
                                    WHERE wp.path_id = p.id
                                    AND w.word ILIKE %s
                                )
                            """)
                            phrase_pattern = f'%{phrase}%'
                            params.extend([phrase_pattern, phrase_pattern])
                            query_conditions.append(f"({' OR '.join(phrase_conditions)})")
                    
                    # Handle terms with operators
                    if intent.get('terms'):
                        term_conditions = []
                        for term_obj in intent['terms']:
                            term = term_obj['term']
                            operator = term_obj.get('operator', 'AND')
                            
                            term_cond = f"""
                                (
                                    p.file_name ILIKE %s
                                    OR EXISTS (
                                        SELECT 1 FROM words_paths wp
                                        JOIN words w ON wp.word_id = w.id
                                        WHERE wp.path_id = p.id
                                        AND w.word ILIKE %s
                                    )
                                )
                            """
                            term_pattern = f'%{term}%'
                            params.extend([term_pattern, term_pattern])
                            
                            if operator == 'OR':
                                # For OR, we'll combine with existing conditions
                                term_conditions.append(term_cond)
                            else:  # AND (default)
                                term_conditions.append(term_cond)
                        
                        if term_conditions:
                            # Combine with AND (all terms must match)
                            query_conditions.append(f"({' AND '.join(term_conditions)})")
                    
                    # Handle exclude terms (NOT)
                    if intent.get('exclude_terms'):
                        exclude_conditions = []
                        for exclude_term in intent['exclude_terms']:
                            exclude_conditions.append("""
                                NOT (
                                    p.file_name ILIKE %s
                                    OR EXISTS (
                                        SELECT 1 FROM words_paths wp
                                        JOIN words w ON wp.word_id = w.id
                                        WHERE wp.path_id = p.id
                                        AND w.word ILIKE %s
                                    )
                                )
                            """)
                            exclude_pattern = f'%{exclude_term}%'
                            params.extend([exclude_pattern, exclude_pattern])
                        
                        if exclude_conditions:
                            query_conditions.extend(exclude_conditions)
                    
                    if query_conditions:
                        # Combine all conditions with AND
                        where_conditions.append(f"({' AND '.join(query_conditions)})")
                elif query and len(query.strip()) >= 2:
                    # Regular search with potential expansion
                    search_query = query.strip()
                
                # Expand query if enabled
                if use_expansion:
                    expander = SearchService._get_expander()
                    expanded_terms = expander.expand(search_query)
                    # Use original query + expanded terms
                    all_terms = [search_query] + expanded_terms[:3]  # Limit expansions
                    search_query = ' '.join(set(all_terms))  # Remove duplicates
                
                # Create tsquery from search terms - handle multi-word searches
                # Split by spaces and join with & (AND) for multi-word support
                search_terms = [t.strip() for t in search_query.split() if t.strip()]
                
                if not search_terms:
                    # No valid terms
                    where_conditions.append("1=0")  # No results
                elif len(search_terms) == 1:
                    # Single word - use prefix matching for better results
                    term = search_terms[0].replace("'", "''")
                    tsquery_terms = f"{term}:*"
                    where_conditions.append("""
                        (
                            to_tsvector('english', COALESCE(p.file_name, '')) @@ to_tsquery(%s)
                            OR p.file_name ILIKE %s
                            OR EXISTS (
                                SELECT 1 FROM words_paths wp
                                JOIN words w ON wp.word_id = w.id
                                WHERE wp.path_id = p.id
                                AND (
                                    to_tsvector('english', w.word) @@ to_tsquery(%s)
                                    OR w.word ILIKE %s
                                )
                            )
                        )
                    """)
                    like_pattern = f'%{search_terms[0]}%'
                    params.extend([tsquery_terms, like_pattern, tsquery_terms, like_pattern])
                else:
                    # Multi-word search - use AND logic (all words must appear)
                    # Use & operator for AND logic in PostgreSQL tsquery
                    tsquery_terms = ' & '.join([term.replace("'", "''") for term in search_terms])
                    
                    # Also create ILIKE patterns for each term (fallback for better multi-word matching)
                    like_patterns = [f'%{term}%' for term in search_terms]
                    
                    # Build condition: all terms must appear in file name OR all terms appear in content
                    where_conditions.append("""
                        (
                            (
                                to_tsvector('english', COALESCE(p.file_name, '')) @@ to_tsquery(%s)
                                OR (p.file_name ILIKE ALL(ARRAY[%s]))
                            )
                            OR EXISTS (
                                SELECT 1 FROM words_paths wp
                                JOIN words w ON wp.word_id = w.id
                                WHERE wp.path_id = p.id
                                AND (
                                    to_tsvector('english', w.word) @@ to_tsquery(%s)
                                    OR w.word ILIKE ANY(ARRAY[%s])
                                )
                            )
                        )
                    """)
                    params.extend([tsquery_terms, like_patterns, tsquery_terms, like_patterns])
            
                # Apply filters - optimize query order (source/side first for better performance)
                # Source and side filters are applied early to reduce dataset size
                # Handle multiple source_ids
                if source_ids and len(source_ids) > 0:
                    if len(source_ids) == 1:
                        where_conditions.append("h.source_id = %s")
                        params.append(source_ids[0])
                    else:
                        placeholders = ','.join(['%s'] * len(source_ids))
                        where_conditions.append(f"h.source_id IN ({placeholders})")
                        params.extend(source_ids)
                elif source_id:
                    where_conditions.append("h.source_id = %s")
                    params.append(source_id)
                
                # Handle multiple side_ids
                if side_ids and len(side_ids) > 0:
                    if len(side_ids) == 1:
                        where_conditions.append("h.side_id = %s")
                        params.append(side_ids[0])
                    else:
                        placeholders = ','.join(['%s'] * len(side_ids))
                        where_conditions.append(f"h.side_id IN ({placeholders})")
                        params.extend(side_ids)
                elif side_id:
                    where_conditions.append("h.side_id = %s")
                    params.append(side_id)
                
                # Handle file_type (can be list or single value)
                if file_type:
                    if isinstance(file_type, (list, tuple)):
                        if len(file_type) > 0:
                            placeholders = ','.join(['%s'] * len(file_type))
                            where_conditions.append(f"p.file_type IN ({placeholders})")
                            params.extend(file_type)
                    else:
                        where_conditions.append("p.file_type = %s")
                        params.append(file_type)
                
                if date_from:
                    where_conditions.append("p.file_date >= %s")
                    params.append(date_from)
                
                if date_to:
                    where_conditions.append("p.file_date <= %s")
                    params.append(date_to)
                
                # Handle multiple category_ids
                if category_ids and len(category_ids) > 0:
                    if len(category_ids) == 1:
                        where_conditions.append("""
                            EXISTS (
                                SELECT 1 FROM words_paths wp2
                                JOIN words_categorys wc ON wp2.word_id = wc.word_id
                                WHERE wp2.path_id = p.id AND wc.category_id = %s
                            )
                        """)
                        params.append(category_ids[0])
                    else:
                        placeholders = ','.join(['%s'] * len(category_ids))
                        where_conditions.append(f"""
                            EXISTS (
                                SELECT 1 FROM words_paths wp2
                                JOIN words_categorys wc ON wp2.word_id = wc.word_id
                                WHERE wp2.path_id = p.id AND wc.category_id IN ({placeholders})
                            )
                        """)
                        params.extend(category_ids)
                elif category_id:
                    where_conditions.append("""
                        EXISTS (
                            SELECT 1 FROM words_paths wp2
                            JOIN words_categorys wc ON wp2.word_id = wc.word_id
                            WHERE wp2.path_id = p.id AND wc.category_id = %s
                        )
                    """)
                    params.append(category_id)
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            # Count query
            count_query = f"""
                SELECT COUNT(DISTINCT p.id)
                FROM paths p
                LEFT JOIN hashs h ON p.hash_id = h.id
                WHERE {where_clause}
            """
            
            cursor.execute(count_query, tuple(params))
            total_count = cursor.fetchone()[0]
            
            # Fetch candidate documents (get more than limit for ranking)
            fetch_limit = min(limit * 3, 1000)  # Get 3x results for ranking
            
            candidate_query = f"""
                SELECT DISTINCT
                    p.id,
                    p.file_name,
                    p.file_path,
                    p.file_type,
                    p.file_size,
                    p.file_date,
                    p.file_status,
                    p.date_creation,
                    COALESCE(s.name, 'Unknown') as source_name,
                    COALESCE(si.name, 'Unknown') as side_name,
                    h.source_id,
                    h.side_id
                FROM paths p
                LEFT JOIN hashs h ON p.hash_id = h.id
                LEFT JOIN sources s ON h.source_id = s.id
                LEFT JOIN sides si ON h.side_id = si.id
                WHERE {where_clause}
                LIMIT %s
            """
            
            cursor.execute(candidate_query, tuple(params + [fetch_limit]))
            candidates = cursor.fetchall()
            
            # Convert to document dictionaries
            documents = []
            for row in candidates:
                doc = {
                    'id': row[0],
                    'file_name': row[1] or '',
                    'file_path': row[2] or '',
                    'file_type': row[3],
                    'file_size': row[4],
                    'file_date': row[5],
                    'file_status': str(row[6]),
                    'date_creation': row[7],
                    'source_name': row[8],
                    'side_name': row[9],
                    'source_id': row[10],
                    'side_id': row[11],
                    'content': ''  # Will be loaded if needed
                }
                documents.append(doc)
            
            # Apply advanced ranking if enabled
            if use_bm25 and query and documents:
                try:
                    # Load content snippets for ranking (first 1000 chars)
                    for doc in documents:
                        try:
                            content = load_text_content(doc['id'])
                            doc['content'] = content[:1000] if content else ''
                        except:
                            doc['content'] = ''
                    
                    # Rank documents using BM25 and other algorithms
                    ranker = SearchService._get_ranker()
                    ranked_docs = ranker.rank_documents(
                        query=query,
                        documents=documents,
                        use_expansion=False,  # Already expanded in query
                        use_fuzzy=use_fuzzy
                    )
                    
                    # Extract documents and scores
                    documents = [doc for doc, score in ranked_docs]
                    
                    # Update relevance scores
                    for i, (doc, score) in enumerate(ranked_docs):
                        if i < len(documents):
                            documents[i]['relevance_score'] = float(score)
                except Exception as e:
                    logger.warning(f"Advanced ranking failed, using basic ranking: {e}")
                    # Fallback to basic relevance
                    for doc in documents:
                        doc['relevance_score'] = 0.0
            
            # Apply sorting
            if sort_by == 'relevance':
                documents.sort(key=lambda x: x.get('relevance_score', 0), reverse=(sort_order.lower() == 'desc'))
            elif sort_by == 'date':
                documents.sort(key=lambda x: x.get('file_date') or date.min, reverse=(sort_order.lower() == 'desc'))
            elif sort_by == 'name':
                documents.sort(key=lambda x: x.get('file_name', '').lower(), reverse=(sort_order.lower() == 'desc'))
            elif sort_by == 'type':
                documents.sort(key=lambda x: (x.get('file_type', ''), x.get('file_name', '').lower()), 
                             reverse=(sort_order.lower() == 'desc'))
            elif sort_by == 'size':
                documents.sort(key=lambda x: x.get('file_size', 0), reverse=(sort_order.lower() == 'desc'))
            
            # Apply pagination
            paginated_docs = documents[offset:offset + limit]
            
            # Format results
            results = []
            for doc in paginated_docs:
                result = {
                    'id': doc['id'],
                    'file_name': doc['file_name'],
                    'file_path': doc['file_path'],
                    'file_type': doc['file_type'],
                    'file_size': doc['file_size'],
                    'file_date': doc['file_date'].isoformat() if doc.get('file_date') else None,
                    'file_status': doc['file_status'],
                    'date_creation': doc['date_creation'].isoformat() if doc.get('date_creation') else None,
                    'source_name': doc['source_name'],
                    'side_name': doc['side_name'],
                    'source_id': doc['source_id'],
                    'side_id': doc['side_id'],
                    'relevance_score': doc.get('relevance_score', 0.0)
                }
                
                # Find matching lines in content if query is provided
                if query and len(query.strip()) >= 2:
                    line_matches = SearchService._find_matching_lines(doc['id'], query, max_matches=5)
                    if line_matches:
                        result['line_matches'] = line_matches
                        result['line_match_count'] = len(line_matches)
                
                    results.append(result)
                
                cursor.close()
                return results, total_count
                
        except Exception as e:
            logger.error(f"Advanced search error: {e}", exc_info=True)
            return [], 0
    
    @staticmethod
    def autocomplete(
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get autocomplete suggestions for a search query.
        
        Args:
            query: Partial query string
            limit: Maximum number of suggestions
        
        Returns:
            List of suggestion dictionaries
        """
        try:
            if not query or len(query.strip()) < 2:
                return []
            
            with get_connection() as conn:
                cursor = conn.cursor()
                
                query_lower = query.strip().lower()
                pattern = f'{query_lower}%'
                
                # Get suggestions from file names
                suggestions_query = """
                    SELECT DISTINCT file_name, COUNT(*) as count
                    FROM paths
                    WHERE LOWER(file_name) LIKE %s
                    GROUP BY file_name
                    ORDER BY count DESC, file_name
                    LIMIT %s
                """
                
                cursor.execute(suggestions_query, (pattern, limit))
                file_suggestions = cursor.fetchall()
                
                # Get suggestions from words
                word_suggestions_query = """
                    SELECT DISTINCT w.word, COUNT(*) as count
                    FROM words w
                    JOIN words_paths wp ON w.id = wp.word_id
                    WHERE LOWER(w.word) LIKE %s
                    GROUP BY w.word
                    ORDER BY count DESC, w.word
                    LIMIT %s
                """
                
                cursor.execute(word_suggestions_query, (pattern, limit))
                word_suggestions = cursor.fetchall()
                
                # Combine and deduplicate suggestions
                suggestions = []
                seen = set()
                
                # Add file name suggestions
                for name, count in file_suggestions:
                    if name and name.lower() not in seen:
                        suggestions.append({
                            'text': name,
                            'type': 'file_name',
                            'count': count
                        })
                        seen.add(name.lower())
                
                # Add word suggestions
                for word, count in word_suggestions:
                    if word and word.lower() not in seen and len(word) >= 3:
                        suggestions.append({
                            'text': word,
                            'type': 'word',
                            'count': count
                        })
                        seen.add(word.lower())
                
                # Apply fuzzy matching for better suggestions
                if len(suggestions) < limit:
                    fuzzy_matcher = SearchService._get_fuzzy_matcher()
                    all_file_names = [s['text'] for s in suggestions if s['type'] == 'file_name']
                    
                    # Get more candidates for fuzzy matching
                    cursor.execute("""
                        SELECT DISTINCT file_name
                        FROM paths
                        WHERE LENGTH(file_name) >= 3
                        LIMIT 1000
                    """)
                    candidates = [row[0] for row in cursor.fetchall() if row[0]]
                    
                    fuzzy_matches = fuzzy_matcher.get_close_matches(
                        query_lower,
                        candidates,
                        n=limit - len(suggestions),
                        cutoff=0.6
                    )
                    
                    for match in fuzzy_matches:
                        if match.lower() not in seen:
                            suggestions.append({
                                'text': match,
                                'type': 'fuzzy_match',
                                'count': 0
                            })
                            seen.add(match.lower())
                
                # Sort by relevance (exact matches first, then by count)
                suggestions.sort(key=lambda x: (
                    0 if x['text'].lower().startswith(query_lower) else 1,
                    -x['count'],
                    x['text'].lower()
                ))
                
                cursor.close()
                return suggestions[:limit]
            
        except Exception as e:
            logger.error(f"Autocomplete error: {e}", exc_info=True)
            return []
    
    @staticmethod
    def get_search_suggestions(
        query: str,
        limit: int = 5
    ) -> List[str]:
        """
        Get search query suggestions (simpler version for quick suggestions).
        
        Args:
            query: Partial query string
            limit: Maximum number of suggestions
        
        Returns:
            List of suggestion strings
        """
        suggestions = SearchService.autocomplete(query, limit=limit)
        return [s['text'] for s in suggestions]

