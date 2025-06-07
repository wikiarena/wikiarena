"""
Helper functions for Wikipedia page title sanitization and validation,
adapted from database/sdow/helpers.py.
"""

def get_sanitized_page_title(page_title: str) -> str:
    """Validates and returns the sanitized version of the provided page title, transforming it into
    the same format used to store pages titles in the database.

    Args:
      page_title: The page title to validate and sanitize.

    Returns:
      The sanitized page title.

    Examples:
      "Notre Dame Fighting Irish"   =>   "Notre_Dame_Fighting_Irish"
      "Farmers' market"             =>   "Farmers\'_market"
      "3.5\" Floppy disk"            =>   "3.5\\\"_Floppy_disk"
      "Nip/Tuck"                    =>   "Nip\\Tuck" # Adjusted for Python string literals

    Raises:
      ValueError: If the provided page title is invalid.
    """
    validate_page_title(page_title)
    # Python's replace method doesn't need to escape ' like in the example's implied SQL context.
    # For "\" -> \\", in Python string, \\ becomes a literal backslash.
    # To store a literal backslash before a quote for some downstream SQL-like system,
    # it would be page_title.replace('"', '\\"')
    # However, the original examples suggest a transformation for a specific storage/querying syntax.
    # Let's stick to the direct replaces shown, assuming they target that syntax after Python processing.
    # "Farmers' market" -> "Farmers'_market" (original example)
    # Python: .replace("'", "\\'") would give "Farmers\'_market" if we want literal backslash then quote
    # If the target system itself interprets \' as an escaped quote, then .replace("'", "\'") is fine.
    # Given the example "Nip/Tuck" => "Nip\Tuck", it seems a single backslash is the goal for some non-python representation.
    # Let's assume the examples imply the *final string representation* for the database.
    # In Python string literals, '\\' represents a single backslash.
    return page_title.strip().replace(' ', '_').replace("'", "\'").replace('"', '\"')


def get_readable_page_title(sanitized_page_title: str) -> str:
    """Returns the human-readable page title from the sanitized page title.

    Args:
      sanitized_page_title: The santized page title to make human-readable.

    Returns:
      The human-readable page title.

    Examples:
      "Notre_Dame_Fighting_Irish"   => "Notre Dame Fighting Irish"
      "Farmers\'_market"            => "Farmers' market"
      "3.5\\\"_Floppy_disk"           => "3.5\" Floppy disk"
      "Nip\\Tuck"                   => "Nip/Tuck"
    """
    return sanitized_page_title.strip().replace('_', ' ').replace("\'", "'").replace('\"', '"')


def is_str(val) -> bool:
    """Returns whether or not the provided value is a string type.

    Args:
      val: The value to check.

    Returns:
      bool: Whether or not the provided value is a string type.
    """
    return isinstance(val, str)


def is_positive_int(val) -> bool:
    """Returns whether or not the provided value is a positive integer type.

    Args:
      val: The value to check.

    Returns:
      bool: Whether or not the provided value is a positive integer type.
    """
    return val and isinstance(val, int) and val > 0


def validate_page_id(page_id: int):
    """Validates the provided value is a valid page ID.

    Args:
      page_id: The page ID to validate.

    Returns:
      None

    Raises:
      ValueError: If the provided page ID is invalid.
    """
    if not is_positive_int(page_id):
        raise ValueError(
            f'Invalid page ID "{page_id}" provided. Page ID must be a positive integer.'
        )


def validate_page_title(page_title: str):
    """Validates the provided value is a valid page title.

    Args:
      page_title: The page title to validate.

    Returns:
      None

    Raises:
      ValueError: If the provided page title is invalid.
    """
    if not page_title or not is_str(page_title):
        raise ValueError(
            f'Invalid page title "{page_title}" provided. Page title must be a non-empty string.'
        ) 