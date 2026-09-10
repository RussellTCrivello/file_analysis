"""
Data Parser
Parses raw domain data into structured Domain and Term objects
"""

from typing import Dict, List
from apps.importing.data.models import Domain, Term
from apps.importing.utils.logger import get_logger
from apps.importing.utils.exceptions import DataParseException

logger = get_logger(__name__)


class DataParser:
    """Parses raw domain data into structured objects"""
    
    def __init__(self):
        self.logger = logger
    
    def parse(self, raw_data: Dict[str, List[str]]) -> List[Domain]:
        """
        Parse raw domain data into Domain objects
        
        Args:
            raw_data: Dict mapping domain_name -> list of terms
            
        Returns:
            List of Domain objects
        """
        if not raw_data:
            raise DataParseException("No data to parse")
        
        domains = []
        
        for domain_name, terms_list in raw_data.items():
            try:
                domain = self._parse_domain(domain_name, terms_list)
                domains.append(domain)
                self.logger.debug(f"Parsed {domain}")
            except Exception as e:
                self.logger.error(f"Failed to parse domain '{domain_name}': {e}")
                raise DataParseException(f"Failed to parse domain '{domain_name}'") from e
        
        self.logger.info(f"Parsed {len(domains)} domains")
        return domains
    
    def _parse_domain(self, name: str, terms_list: List[str]) -> Domain:
        """
        Parse a single domain
        
        Args:
            name: Domain name
            terms_list: List of term strings
            
        Returns:
            Domain object
        """
        if not name or not name.strip():
            raise DataParseException("Domain name cannot be empty")
        
        domain = Domain(name=name.strip())
        
        for term_text in terms_list:
            if term_text and term_text.strip():
                domain.add_term(term_text.strip())
        
        if len(domain) == 0:
            self.logger.warning(f"Domain '{name}' has no valid terms")
        
        return domain
    
