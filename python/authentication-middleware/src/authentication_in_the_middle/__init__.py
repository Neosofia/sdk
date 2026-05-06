"""
authentication-in-the-middle

Shared JWT authentication middleware for Neosofia platform services.
Provides reusable decorators for protecting API routes using bearer tokens.
"""

from authentication_in_the_middle.decorators import with_authentication
from authentication_in_the_middle.dev_jwt import generate

__version__ = "0.1.0"
__all__ = [
    "with_authentication",
    "generate",
]
