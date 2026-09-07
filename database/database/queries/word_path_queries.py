"""SQL queries for words_paths table"""
from .base_queries import BaseQueries


class WordPathQueries(BaseQueries):
    """SQL queries for word-path relationships"""
    
    @staticmethod
    def insert_word_path(placeholders = '(%s, %s, %s)') -> str:
        """Insert word-path relationship"""
        return f"""
            INSERT INTO words_paths (path_id, word_id, word_count, position_indexer)
            VALUES {placeholders}
        """
    
    @staticmethod
    def batch_insert_word_paths() -> str:
        """Batch insert word-path relationships"""
        return """
            INSERT INTO words_paths (path_id, word_id, word_count, position_indexer)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (path_id, word_id)
            DO UPDATE SET word_count = EXCLUDED.word_count
            RETURNING id;
        """
    
    @staticmethod
    def get_word_positions_by_path() -> str:
        """Get word positions for a path"""
        return """
            SELECT word_id, position_indexer
            FROM words_paths
            WHERE path_id = %s
        """

