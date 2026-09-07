"""
Data Models
Domain entities for the import process
"""

from dataclasses import dataclass, field
from typing import List
from enum import Enum


class TermType(Enum):
    """Type of term (single word or multi-word phrase)"""
    SINGLE_WORD = "single_word"
    MULTI_WORD_PHRASE = "multi_word_phrase"


@dataclass
class Term:
    """Represents a term (word or phrase) from domain data"""
    text: str
    term_type: TermType
    word_count: int = 1
    
    def __post_init__(self):
        """Calculate word count from text"""
        if not self.text:
            self.word_count = 0
        else:
            self.word_count = len(self.text.strip().split())
            
            # Determine term type based on word count
            if self.word_count == 1:
                self.term_type = TermType.SINGLE_WORD
            else:
                self.term_type = TermType.MULTI_WORD_PHRASE
    
    def is_single_word(self) -> bool:
        """Check if this is a single word"""
        return self.term_type == TermType.SINGLE_WORD
    
    def is_phrase(self) -> bool:
        """Check if this is a multi-word phrase"""
        return self.term_type == TermType.MULTI_WORD_PHRASE
    
    def __str__(self):
        return f"Term('{self.text}', {self.term_type.value}, {self.word_count} words)"


@dataclass
class Domain:
    """Represents a domain with its associated terms"""
    name: str
    terms: List[Term] = field(default_factory=list)
    
    def add_term(self, text: str):
        """Add a term to this domain (prevents duplicates)"""
        if text and text.strip():
            term_text = text.strip()
            # Check if term already exists (case-insensitive comparison)
            existing_terms = [t.text.lower() for t in self.terms]
            if term_text.lower() not in existing_terms:
                term = Term(text=term_text, term_type=TermType.SINGLE_WORD)
                self.terms.append(term)
    
    def add_terms(self, texts: List[str]):
        """Add multiple terms to this domain"""
        for text in texts:
            self.add_term(text)
    
    def get_single_words(self) -> List[Term]:
        """Get only single-word terms"""
        return [t for t in self.terms if t.is_single_word()]
    
    def get_phrases(self) -> List[Term]:
        """Get only multi-word phrases"""
        return [t for t in self.terms if t.is_phrase()]
    
    def __len__(self):
        """Return number of terms in domain"""
        return len(self.terms)
    
    def __str__(self):
        single_words = len(self.get_single_words())
        phrases = len(self.get_phrases())
        return f"Domain('{self.name}', {len(self)} terms: {single_words} words, {phrases} phrases)"


@dataclass
class ImportResult:
    """Result of a domain import operation"""
    domain_name: str
    total_terms: int = 0
    imported_words: int = 0
    imported_phrases: int = 0
    skipped: int = 0
    errors: int = 0
    
    def __str__(self):
        return (f"ImportResult({self.domain_name}: "
                f"{self.imported_words} words, "
                f"{self.imported_phrases} phrases, "
                f"{self.skipped} skipped, "
                f"{self.errors} errors)")


@dataclass
class Statistics:
    """Overall import statistics"""
    total_domains: int = 0
    total_terms: int = 0
    total_words: int = 0
    total_phrases: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    results: List[ImportResult] = field(default_factory=list)
    
    def add_result(self, result: ImportResult):
        """Add an import result"""
        self.results.append(result)
        self.total_terms += result.total_terms
        self.total_words += result.imported_words
        self.total_phrases += result.imported_phrases
        self.total_skipped += result.skipped
        self.total_errors += result.errors
    
    def __str__(self):
        return (f"Statistics: {self.total_domains} domains, "
                f"{self.total_terms} terms "
                f"({self.total_words} words, {self.total_phrases} phrases)")
