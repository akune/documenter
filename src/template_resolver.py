"""
Template resolver for variable substitution in strings.
Supports ${variable_name} syntax.
"""

import re
from datetime import datetime
from typing import Any, Dict


def resolve_template(template: str, context: Dict[str, Any]) -> str:
    """
    Resolve variables in a template string.
    
    Supported variables:
        ${directory_path} - Relative directory path
        ${year_month}     - Year and month (YYYY-MM)
        ${filename}       - Document filename
        ${title}          - Document title
    
    Args:
        template: String with ${variable} placeholders
        context: Dictionary of variable values
    
    Returns:
        String with variables resolved
    """
    def replace_var(match):
        var_name = match.group(1)
        
        # Look up in context
        if var_name in context:
            value = context[var_name]
            # Handle datetime objects
            if isinstance(value, datetime):
                if var_name == 'year_month':
                    return value.strftime('%Y-%m')
                return str(value)
            return str(value)
        
        # Variable not found, return as-is
        return match.group(0)
    
    # Match ${variable_name} pattern
    pattern = r'\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    return re.sub(pattern, replace_var, template)
