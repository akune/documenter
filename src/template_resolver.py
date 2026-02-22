"""
Template resolver module for variable substitution.
Provides an extensible system for resolving variables in configuration templates.
"""

import re
from typing import Any, Callable, Dict, Optional

# Registry of available variable resolvers
# Each resolver is a function that takes a context dict and returns a string
_VARIABLE_RESOLVERS: Dict[str, Callable[[Dict[str, Any]], Optional[str]]] = {}

# Pattern for matching variables: ${variable_name}
VARIABLE_PATTERN = re.compile(r'\$\{([^}]+)\}')


def register_variable(name: str, resolver: Callable[[Dict[str, Any]], Optional[str]]) -> None:
    """
    Register a variable resolver function.
    
    Args:
        name: Variable name (without ${})
        resolver: Function that takes context dict and returns resolved value
    """
    _VARIABLE_RESOLVERS[name] = resolver


def resolve_template(template: str, context: Dict[str, Any]) -> str:
    """
    Resolve all variables in a template string.
    
    Args:
        template: Template string with ${variable} placeholders
        context: Context dictionary passed to resolvers
    
    Returns:
        Resolved string with all variables substituted
    """
    def replace_var(match: re.Match) -> str:
        var_name = match.group(1)
        
        # Check if there's a resolver for this variable
        if var_name in _VARIABLE_RESOLVERS:
            resolved = _VARIABLE_RESOLVERS[var_name](context)
            if resolved is not None:
                return str(resolved)
        
        # Check if the variable is directly in context
        if var_name in context:
            value = context[var_name]
            if value is not None:
                return str(value)
        
        # Variable not found, return original placeholder
        return match.group(0)
    
    return VARIABLE_PATTERN.sub(replace_var, template)


def get_available_variables() -> list:
    """
    Get list of registered variable names.
    
    Returns:
        List of variable names
    """
    return list(_VARIABLE_RESOLVERS.keys())


# ============================================================================
# Built-in variable resolvers
# ============================================================================

def _resolve_directory_path(context: Dict[str, Any]) -> Optional[str]:
    """
    Resolve ${directory_path} variable.
    
    Context keys:
        - directory_path: Direct path value (for import)
        - year_month: YYYY-MM value (for processing)
    
    Returns:
        The directory path or year_month value
    """
    # First check for explicit directory_path
    if 'directory_path' in context and context['directory_path']:
        return context['directory_path']
    
    # Fall back to year_month for processing mode
    if 'year_month' in context and context['year_month']:
        return context['year_month']
    
    return None


def _resolve_year_month(context: Dict[str, Any]) -> Optional[str]:
    """
    Resolve ${year_month} variable.
    
    Context keys:
        - year_month: YYYY-MM value
        - created_date: datetime object to extract year-month from
    
    Returns:
        The year-month string (YYYY-MM)
    """
    if 'year_month' in context and context['year_month']:
        return context['year_month']
    
    if 'created_date' in context and context['created_date']:
        return context['created_date'].strftime('%Y-%m')
    
    return None


def _resolve_filename(context: Dict[str, Any]) -> Optional[str]:
    """
    Resolve ${filename} variable.
    
    Context keys:
        - filename: The document filename
    
    Returns:
        The filename
    """
    return context.get('filename')


def _resolve_title(context: Dict[str, Any]) -> Optional[str]:
    """
    Resolve ${title} variable.
    
    Context keys:
        - title: The document title
    
    Returns:
        The title
    """
    return context.get('title')


# Register built-in variables
register_variable('directory_path', _resolve_directory_path)
register_variable('year_month', _resolve_year_month)
register_variable('filename', _resolve_filename)
register_variable('title', _resolve_title)
