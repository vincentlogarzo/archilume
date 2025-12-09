"""
Module description: [Brief description of what this module does]

This module contains:
- ClassName: [Brief description of the main class]
"""

# Archilume imports
from archilume import config

# Standard library imports
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

# Third-party imports


# Constants


@dataclass
class ClassName:
    """
    [Brief description of the class purpose]

    Attributes:
        attribute_name (type): Description of the attribute

    Methods:
        method_name(): Description of what the method does

    Example:
        >>> obj = ClassName(param1="value")
        >>> obj.method_name()
    """

    # Required attributes
    required_param: str

    # Optional attributes with defaults
    optional_param: int = 100
    optional_path: Optional[Path] = None

    # Attributes initialized by __post_init__
    derived_attribute: str = field(init=False)

    def __post_init__(self):
        """
        Post-initialization processing.

        Called automatically after __init__. Use this to:
        - Validate input parameters
        - Initialize derived attributes
        - Set up internal state
        """
        # Validate inputs
        if self.required_param == "":
            raise ValueError("required_param cannot be empty")

        # Initialize derived attributes
        self.derived_attribute = f"Processed: {self.required_param}"

        # Set defaults for optional attributes
        if self.optional_path is None:
            self.optional_path = config.OUTPUTS_DIR / "default"

    def public_method(self) -> None:
        """
        [Description of what this method does]

        Args:
            None

        Returns:
            None

        Example:
            >>> obj = ClassName(required_param="test")
            >>> obj.public_method()
        """
        print(f"Processing {self.required_param}")
        self._private_helper()

    def _private_helper(self) -> None:
        """Private helper method (not part of public API)"""
        pass


# Standalone helper functions (if needed)
def standalone_function(param: str) -> str:
    """
    [Description of standalone function]

    Args:
        param: Description of parameter

    Returns:
        Description of return value

    Example:
        >>> result = standalone_function("test")
        >>> print(result)
    """
    return f"Result: {param}"