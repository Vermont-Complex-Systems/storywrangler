# packages/sdk/tests/test_entity_validation.py

"""
Tests for entity validation

Based on examples from Storywrangler Specification v0.0.1
https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md
"""

from storywrangler.validation import EntityValidator


def test_wikidata_validation():
    """Test Wikidata Q-code validation (Spec: Section 3.1.1)"""
    validator = EntityValidator()
    
    # Valid examples from spec
    assert validator.validate_wikidata("wikidata:Q937")  # Albert Einstein
    assert validator.validate_wikidata("wikidata:Q7942")  # Climate change
    
    # Invalid
    assert not validator.validate_wikidata("wikidata:123")  # Missing Q
    assert not validator.validate_wikidata("wiki:Q937")  # Wrong namespace


def test_orcid_validation():
    """Test ORCID validation with checksum (Spec: Section 3.1.2, Appendix A.1)"""
    validator = EntityValidator()
    
    # Valid ORCID with correct checksum
    assert validator.validate_orcid("orcid:0000-0002-1825-0097")
    
    # Invalid checksum
    assert not validator.validate_orcid("orcid:0000-0002-1825-0098")