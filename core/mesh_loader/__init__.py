"""
Mesh Loader Module

A modular mesh loading system for parsing .mesh files using multiple parsing strategies.
Supports adaptive parsing with fallback mechanisms for robust file handling.
"""

from . import parsers
from .exceptions import MeshParsingError
from .types import MeshData

# Import the loader components after defining parsers
from .loader import MeshLoader

__all__ = [
    'parsers',
    'MeshLoader',
    'MeshData',
    'MeshParsingError'
]
