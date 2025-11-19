"""
Storywrangler Entity Standards v0.0.1

Patterns and rules from:
https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md
"""

import re

class Standards_v0_0_1:
    """
    Entity identifier and taxonomy patterns from Standards v0.0.1
    
    Reference: https://github.com/vermont-complex-systems/Storywrangler-Specification
    """
    
    # Entity Identifiers (Section 3.1)
    WIKIDATA_PATTERN = re.compile(r'^wikidata:Q[0-9]+$')
    ORCID_PATTERN = re.compile(r'^orcid:[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$')
    ROR_PATTERN = re.compile(r'^ror:[a-z0-9]{9}$')
    IPEDS_PATTERN = re.compile(r'^ipeds:[0-9]{6}$')
    DOI_PATTERN = re.compile(r'^doi:10\.[0-9]{4,}/[^\s]+$')
    ISBN_13_PATTERN = re.compile(r'^isbn:[0-9]{13}$')
    ISBN_10_PATTERN = re.compile(r'^isbn:[0-9]{9}[0-9X]$')
    
    # Field Taxonomies (Section 3.2)
    ARXIV_PATTERN = re.compile(r'^arxiv:[a-z-]+(\.[A-Z]{2})?$')
    MAG_PATTERN = re.compile(r'^mag:[0-9]+$')
    
    # Local Identifiers (Section 3.5)
    LOCAL_PATTERN = re.compile(r'^local:[a-z0-9_-]+:[a-z0-9_-]+$')
    
    @staticmethod
    def get_spec_url(section: str = "") -> str:
        """Get URL to specification section"""
        base = "https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md"
        return f"{base}#{section}" if section else base