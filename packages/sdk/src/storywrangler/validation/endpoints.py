"""
Endpoint validation

Implements validation rules for Storywrangler API endpoint schemas.
Based on Storywrangler Entity Standards v0.0.1, Section 3.6:
https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md

Format-agnostic validation that works with any data storage (DuckLake, CSV, JSON).
"""

from typing import Dict, List, Any, Optional
from ..standards.v0_0_1 import Standards_v0_0_1


class EndpointValidator:
    """
    Validates API endpoint schemas against Storywrangler Standards v0.0.1

    See specification: https://github.com/vermont-complex-systems/Storywrangler-Specification
    Section 3.6: API Endpoint Schemas
    """

    def __init__(self):
        self.standards = Standards_v0_0_1()

    def validate_types_counts_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates types-counts endpoint schema against Standards v0.0.1 Section 3.6.1

        Spec: Column names MUST be exactly 'types' and 'counts'
        - types (VARCHAR): The item text (ngram, name, institution, ...)
        - counts (INTEGER): Frequency/occurrence count
        """
        result = {
            'valid': False,
            'errors': [],
            'warnings': [],
            'column_mapping': {}
        }

        if not isinstance(schema, dict):
            result['errors'].append("Schema must be a dictionary")
            return result

        columns = schema.get('columns', {})
        if not columns:
            result['errors'].append("Schema must contain 'columns' dictionary")
            return result

        required_schema = self.standards.ENDPOINT_SCHEMAS['types-counts']['required_columns']

        # Strict validation - column names must be exactly 'types' and 'counts'
        for required_col, required_type in required_schema.items():
            if required_col not in columns:
                result['errors'].append(f"Missing required column: '{required_col}'")
                continue

            # Validate column type
            col_info = columns[required_col]
            if isinstance(col_info, dict):
                col_type = col_info.get('type', '').lower()
                if not self._validate_column_type(col_type, required_type):
                    result['errors'].append(
                        f"Column '{required_col}' must be {required_type}, got {col_type}"
                    )

            result['column_mapping'][required_col] = required_col

        # Check if valid
        result['valid'] = len(result['errors']) == 0

        return result

    def validate_endpoint_schema(self, endpoint_name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Validates any supported endpoint schema"""
        if endpoint_name == 'types-counts':
            return self.validate_types_counts_schema(schema)
        else:
            return {
                'valid': False,
                'errors': [f"Unsupported endpoint: {endpoint_name}"],
                'warnings': [],
                'column_mapping': {}
            }

    def get_endpoint_requirements(self, endpoint_name: str) -> Optional[Dict[str, Any]]:
        """Get requirements for a specific endpoint"""
        return self.standards.ENDPOINT_SCHEMAS.get(endpoint_name)

    def list_supported_endpoints(self) -> List[str]:
        """List all supported endpoint types"""
        return list(self.standards.ENDPOINT_SCHEMAS.keys())

    def _validate_column_type(self, actual_type: str, required_type: str) -> bool:
        """Validate that actual column type matches required type"""
        type_mappings = {
            'varchar': ['string', 'text', 'varchar', 'character varying'],
            'integer': ['integer', 'int', 'bigint', 'int64', 'int32']
        }

        allowed_types = type_mappings.get(required_type, [required_type])
        return actual_type in allowed_types

    def validate_query_response(self, response_data: List[Dict[str, Any]], endpoint_name: str = 'types-counts') -> Dict[str, Any]:
        """
        Validate actual query response format

        Spec Section 3.6.1: Response MUST return data as a JSON array
        """
        result = {
            'valid': False,
            'errors': [],
            'warnings': []
        }

        if not isinstance(response_data, list):
            result['errors'].append("Response must be a JSON array")
            return result

        if not response_data:
            result['warnings'].append("Response is empty")
            result['valid'] = True
            return result

        # Check first row for required columns
        first_row = response_data[0]
        required_schema = self.standards.ENDPOINT_SCHEMAS[endpoint_name]['required_columns']

        for required_col in required_schema.keys():
            if required_col not in first_row:
                result['errors'].append(f"Response missing required column: '{required_col}'")

        result['valid'] = len(result['errors']) == 0
        return result