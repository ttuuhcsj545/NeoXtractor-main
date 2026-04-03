"""NPK entry type definitions for the NPK file format."""

from dataclasses import dataclass
from enum import IntFlag, auto
import os

from core.file import IFile
from .enums import CompressionType, DecryptionType, NPKEntryFileCategories

class NPKEntryDataFlags(IntFlag):
    """Flags for NPK entry data."""
    NONE = 0
    TEXT = auto()
    NXS3_PACKED = auto()
    ROTOR_PACKED = auto()
    ENCRYPTED = auto()
    ERROR = auto()

@dataclass
class NPKReadOptions:
    """Options for reading NPK files."""

    decryption_key: int | None = None
    aes_key: bytes | None = None
    info_size: int | None = None

@dataclass
class NPKIndex:
    """Represents an index entry in an NPK file."""

    filename = ""

    file_signature: int = 0
    file_offset: int = 0
    file_length: int = 0
    file_original_length: int = 0
    zcrc: int = 0  # compressed CRC
    crc: int = 0   # decompressed CRC
    file_structure: bytes | None = None
    zip_flag: CompressionType = CompressionType.NONE
    encrypt_flag: DecryptionType = DecryptionType.NONE

    data_flags = NPKEntryDataFlags.NONE

    def __repr__(self) -> str:
        return (
            f"NPKIndex(offset=0x{self.file_offset:X}, "
            f"length={self.file_length}, "
            f"orig_length={self.file_original_length}, "
            f"compression={CompressionType.get_name(self.zip_flag)}, "
            f"encryption={DecryptionType.get_name(self.encrypt_flag)})"
        )

class NPKEntry(NPKIndex, IFile):
    """Represents a file entry in an NPK file, including the actual file data."""

    def __init__(self):
        super().__init__()
        self._data: bytes = b""
        self._extension: str | None = None
        self.category: NPKEntryFileCategories = NPKEntryFileCategories.OTHER

    @property
    def is_compressed(self) -> bool:
        """Check if the entry is compressed."""
        return self.zip_flag != 0

    @property
    def is_encrypted(self) -> bool:
        """Check if the entry is encrypted."""
        return self.encrypt_flag != 0

    def save_to_file(self, path: str) -> None:
        """Save the file data to the specified path."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(self.data)

    def __repr__(self) -> str:
        return (
            f"NPKEntry(filename='{self.filename}', "
            f"length={self.file_length}, "
            f"compression={CompressionType.get_name(self.zip_flag)}, "
            f"encryption={DecryptionType.get_name(self.encrypt_flag)})"
        )

    # IFile implementations
    @property
    def name(self) -> str:
        return self.filename

    @property
    def data(self) -> bytes:
        return self._data

    @data.setter
    def data(self, value: bytes) -> None:
        self._data = value

    @property
    def extension(self) -> str:
        return self._extension if self._extension else super().extension

    @extension.setter
    def extension(self, value: str) -> None:
        self._extension = value
