"""
Entity ID validation

Implements validation rules from Storywrangler Entity Standards v0.0.1:
https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.3.md
"""

from storywrangler_schemas.standards import Standards as Standards_v0_0_1


class EntityValidator:
    """
    Validates entity identifiers against Storywrangler Standards v0.0.1
    
    See specification: https://github.com/vermont-complex-systems/Storywrangler-Specification
    """
    
    def __init__(self):
        self.standards = Standards_v0_0_1()
    
    def validate_wikidata(self, entity_id: str) -> bool:
        """
        Validates Wikidata Q-code format
        
        Spec: Section 3.1.1
        Format: wikidata:Q[0-9]+
        Example: wikidata:Q937
        """
        return bool(self.standards.WIKIDATA.match(entity_id))
    
    def validate_orcid(self, entity_id: str) -> bool:
        """
        Validates ORCID format with checksum
        
        Spec: Section 3.1.2
        Format: orcid:[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]
        Checksum: Appendix A.1 (ISO 7064 mod 11-2)
        """
        if not self.standards.ORCID.match(entity_id):
            return False
        return self._validate_orcid_checksum(entity_id)
    
    def validate_ror(self, entity_id: str) -> bool:
        """Validates ROR format (Spec: Section 3.1.3)"""
        return bool(self.standards.ROR.match(entity_id))
    
    def validate_ipeds(self, entity_id: str) -> bool:
        """Validates IPEDS format (Spec: Section 3.1.4)"""
        return bool(self.standards.IPEDS.match(entity_id))
    
    def validate_doi(self, entity_id: str) -> bool:
        """Validates DOI format (Spec: Section 3.1.5)"""
        return bool(self.standards.DOI.match(entity_id))
    
    def validate_isbn(self, entity_id: str) -> bool:
        """Validates ISBN format with checksum (Spec: Section 3.1.6)"""
        if self.standards.ISBN_13.match(entity_id):
            return self._validate_isbn13_checksum(entity_id)
        elif self.standards.ISBN_10.match(entity_id):
            return self._validate_isbn10_checksum(entity_id)
        return False
    
    def validate_openalex(self, entity_id: str) -> bool:
        """
        Validates OpenAlex identifier format (Spec: Section 3.1.3)

        Covers all OpenAlex entity types:
          A — author, W — work, I — institution, C — concept,
          S — source, F — funder, P — publisher

        Format: openalex:[AWICSFP][0-9]+
        Example: openalex:A5002034958
        """
        return bool(self.standards.OPENALEX.match(entity_id))

    def validate_local(self, entity_id: str) -> bool:
        """Validates local identifier format (Spec: Section 3.5.1)"""
        return bool(self.standards.LOCAL.match(entity_id))

    def validate(self, entity_id: str) -> bool:
        """Validates any supported entity identifier"""
        validators = [
            self.validate_wikidata,
            self.validate_orcid,
            self.validate_openalex,
            self.validate_ror,
            self.validate_ipeds,
            self.validate_doi,
            self.validate_isbn,
            self.validate_local,
        ]
        return any(validator(entity_id) for validator in validators)
    
    def _validate_orcid_checksum(self, orcid: str) -> bool:
        """ISO 7064 mod 11-2 checksum (Spec: Appendix A.1)"""
        digits = orcid.replace('orcid:', '').replace('-', '')
        total = 0
        for digit in digits[:-1]:
            total = (total + int(digit)) * 2
        remainder = total % 11
        result = (12 - remainder) % 11
        check = digits[-1]
        expected = 'X' if result == 10 else str(result)
        return check == expected
    
    def _validate_isbn13_checksum(self, isbn: str) -> bool:
        """ISBN-13 checksum (Spec: Appendix A.2.1)"""
        digits = isbn.replace('isbn:', '')
        weighted_sum = sum(
            int(d) * (1 if i % 2 == 0 else 3)
            for i, d in enumerate(digits[:-1])
        )
        check_digit = (10 - (weighted_sum % 10)) % 10
        return int(digits[-1]) == check_digit
    
    def _validate_isbn10_checksum(self, isbn: str) -> bool:
        """ISBN-10 checksum (Spec: Appendix A.2.2)"""
        digits = isbn.replace('isbn:', '')
        weighted_sum = sum(
            int(d) * (10 - i)
            for i, d in enumerate(digits[:-1])
        )
        remainder = weighted_sum % 11
        check_digit = (11 - remainder) % 11
        check_char = 'X' if check_digit == 10 else str(check_digit)
        return digits[-1] == check_char