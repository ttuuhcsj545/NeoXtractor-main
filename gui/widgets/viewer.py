from abc import abstractmethod
from typing import TYPE_CHECKING

from PySide6 import QtWidgets

from core.file import IFile
if TYPE_CHECKING:
    from gui.windows.viewer_tab_window import ViewerTabWindow

class IViewer:
    """
    Base interface for all viewers.
    """

    name: str
    """Name of the viewer."""

    accepted_extensions: set[str]
    """Accepted extensions of the viewer."""

    allow_unsupported_extensions: bool = False
    """Indicates can the viewer accept unsupported extensions."""

    @abstractmethod
    def get_file(self) -> IFile | None:
        """Get the viewer's current file."""

    @abstractmethod
    def set_file(self, file: IFile):
        """Set the viewer's current file."""

    @abstractmethod
    def unload_file(self):
        """Unload the viewer's current file."""

class Viewer(IViewer, QtWidgets.QWidget):
    """A viewer."""

    @abstractmethod
    def get_file(self) -> IFile | None:
        pass

    @abstractmethod
    def set_file(self, file: IFile):
        pass

    @abstractmethod
    def unload_file(self):
        pass

class ICustomTabWindow:
    """Interface for viewers that customizes the tab window."""

    @staticmethod
    def setup_tab_window(tab_window: 'ViewerTabWindow') -> None:
        """Customize the tab window."""
