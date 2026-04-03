"""Custom QListView to display NPK files."""

import os
from typing import cast
from PySide6 import QtCore, QtWidgets

from core.config import Config
from core.npk.class_types import NPKEntry
from gui.models.npk_file_model import NPKFileModel
from gui.utils.config import save_config_manager_to_settings
from gui.utils.npk import get_npk_file
from gui.utils.viewer import ALL_VIEWERS
from gui.widgets.batch_export import BatchExportDialog, _is_image_entry, _is_mesh_entry

class NPKFileList(QtWidgets.QListView):
    """
    Custom QListView to display NPK files.
    """

    preview_entry = QtCore.Signal(int, NPKEntry)
    open_entry = QtCore.Signal(int, NPKEntry)
    open_entry_with = QtCore.Signal(int, NPKEntry, type, int)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)

        self._disabled = False
        self._select_after_enabled: QtCore.QModelIndex | None = None

        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        # Connect double-click signal to handler
        self.doubleClicked.connect(self.on_item_double_clicked)

    def setDisabled(self, disabled: bool):
        """
        Set the disabled state of the list view.

        :param disabled: True to disable, False to enable.
        """
        if disabled:
            self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
            self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            self.setProperty("disabled", True)
        else:
            self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
            self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            self.setProperty("disabled", None)
        self.style().unpolish(self)
        self.style().polish(self)

        self._disabled = disabled

        if self._select_after_enabled:
            self.selectionModel().select(self._select_after_enabled,
                                         QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)
            self.on_current_changed(self._select_after_enabled, QtCore.QModelIndex())
            self._select_after_enabled = None

    def disabled(self):
        """Get the disabled state of the list view."""
        return self._disabled

    def model(self) -> NPKFileModel:
        """
        Get the current model of the list view.

        :return: The current model, or None if not set.
        """
        return cast(NPKFileModel, super().model())

    def refresh_npk_file(self):
        """
        Set the NPK file to be displayed in the list.

        :param npk_file: The NPK file to display.
        """

        npk_file = get_npk_file()

        if npk_file is None:
            self.setModel(None)
        else:
            self.setModel(NPKFileModel(npk_file, self))
            self.selectionModel().currentChanged.connect(self.on_current_changed)

    def on_current_changed(self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex):
        """
        Handle single-click on an item in the list.
        
        :param index: The model index that was clicked.
        """
        if self._disabled:
            self._select_after_enabled = current
            return

        npk_file = get_npk_file()

        if not self.model() or npk_file is None:
            return

        # Get the row index from the model index
        row_index = current.row()

        entry = npk_file.read_entry(row_index)

        self.preview_entry.emit(row_index, entry)

    def on_item_double_clicked(self, index: QtCore.QModelIndex):
        """
        Handle double-click on an item in the list.
        
        :param index: The model index that was double-clicked.
        """
        if self._disabled:
            return

        npk_file = get_npk_file()

        if not self.model() or npk_file is None:
            return

        # Get the row index from the model index
        row_index = index.row()

        entry = npk_file.read_entry(row_index)

        self.open_entry.emit(row_index, entry)

    def show_context_menu(self, position):
        """
        Show a context menu for selected items.
        
        :param position: Position where the context menu was requested.
        """
        npk_file = get_npk_file()

        if not self.model() or npk_file is None:
            return

        # Check if there are any selected items
        indexes = self.selectedIndexes()
        if not indexes:
            return

        menu = QtWidgets.QMenu(self)

        # Add extract option for any selection
        extract = menu.addAction("提取")
        extract.triggered.connect(lambda: self.extract_entries(indexes))

        # Batch convert & export (images / meshes)
        menu.addSeparator()
        convert_export = menu.addAction("批量转换并导出…")
        convert_export.triggered.connect(lambda: self.batch_convert_export(indexes))

        # Check what types are in the selection to give a hint in the menu text
        npk_file = get_npk_file()
        if npk_file is not None:
            _entries_preview = [npk_file.read_entry(idx.row()) for idx in indexes]
            _has_img = any(_is_image_entry(e) for e in _entries_preview)
            _has_mesh = any(_is_mesh_entry(e) for e in _entries_preview)
            _type_hint = []
            if _has_img:
                _type_hint.append("图像")
            if _has_mesh:
                _type_hint.append("模型")
            if _type_hint:
                convert_export.setText(
                    f"批量转换并导出… ({'、'.join(_type_hint)})"
                )

        menu.addSeparator()
        for viewer in ALL_VIEWERS:
            viewer_action = menu.addAction("在 " + viewer.name + " 中打开")
            viewer_action.triggered.connect(
                lambda _checked, v=viewer: self.open_entries_with(indexes, v)
            )

        if len(indexes) == 1:
            menu.addSeparator()
            rename = menu.addAction("重命名")
            rename.triggered.connect(lambda: self.show_rename_dialog(indexes[0]))

        # Show the context menu at the current position
        menu.exec(self.viewport().mapToGlobal(position))

    def open_entries_with(self, indexes: list[QtCore.QModelIndex], viewer: type):
        """
        Open the selected entry with the specified viewer.
        
        :param indexes: List of model indexes for the selected entries.
        :param viewer: The viewer class to use.
        """
        npk_file = get_npk_file()
        if npk_file is None:
            return
        for i, index in enumerate(indexes):
            row = index.row()
            entry = npk_file.read_entry(row)
            self.open_entry_with.emit(row, entry, viewer, i)

    def extract_entries(self, indexes: list[QtCore.QModelIndex]):
        """
        Extract selected entries from the NPK file.
        
        :param indexes: List of model indexes for the selected entries.
        """
        npk_file = get_npk_file()
        if not self.model() or npk_file is None:
            return

        if len(indexes) == 1:
            # For single file, show file save dialog with filename pre-filled
            index = indexes[0]
            row_index = index.row()
            filename = self.model().get_filename(index)

            # Get the entry data
            entry = npk_file.read_entry(row_index)

            # Show save file dialog
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "提取文件",
                filename,
                "所有文件 (*.*)"
            )

            if file_path:
                try:
                    with open(file_path, 'wb') as f:
                        f.write(entry.data)
                    QtWidgets.QMessageBox.information(
                        self,
                        "成功", 
                        f"文件提取到 {file_path}"
                    )
                except Exception as e:
                    QtWidgets.QMessageBox.critical(
                        self,
                        "错误", 
                        f"提取文件失败: {str(e)}"
                    )
        else:
            # For multiple files, show directory selection dialog
            dir_path = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "选择提取文件的目录",
                "",
                QtWidgets.QFileDialog.Option.ShowDirsOnly
            )

            if dir_path:
                try:
                    success_count = 0
                    fail_count = 0

                    for index in indexes:
                        row_index = index.row()
                        filename = self.model().get_filename(index)

                        # Create safe filename
                        safe_filename = os.path.basename(filename)
                        if not safe_filename:
                            safe_filename = f"unknown_file_{row_index}"

                        file_path = os.path.join(dir_path, safe_filename)

                        # Get the entry data
                        entry = npk_file.read_entry(row_index)

                        try:
                            with open(file_path, 'wb') as f:
                                f.write(entry.data)
                            success_count += 1
                        except Exception:
                            fail_count += 1

                    message = f"已提取 {success_count} 个文件到 {dir_path}"
                    if fail_count > 0:
                        message += f"\n{fail_count} 个文件提取失败"

                    QtWidgets.QMessageBox.information(self, "提取完成", message)
                except Exception as e:
                    QtWidgets.QMessageBox.critical(
                        self,
                        "错误",
                        f"提取文件失败: {str(e)}"
                    )

    def batch_convert_export(self, indexes: list[QtCore.QModelIndex]):
        """
        Open the Batch Convert & Export dialog for the selected entries.

        :param indexes: List of model indexes for the selected entries.
        """
        npk_file = get_npk_file()
        if not self.model() or npk_file is None:
            return

        entries: list[tuple[str, object]] = []
        for index in indexes:
            row_index = index.row()
            filename = self.model().get_filename(index)
            entry = npk_file.read_entry(row_index)
            entries.append((os.path.basename(filename), entry))

        if not entries:
            return

        dialog = BatchExportDialog(entries, self)
        dialog.exec()

    def show_rename_dialog(self, index: QtCore.QModelIndex):
        """
        Show a dialog to rename the selected file.
        
        :param index: The model index of the item to rename.
        """
        npk_file = get_npk_file()

        if not self.model() or npk_file is None:
            return

        entry_index = npk_file.indices[index.row()]

        # Show input dialog to get new name
        new_name, ok = QtWidgets.QInputDialog.getText(
            self,
            "重命名文件",
            f"为 {self.model().get_filename(index)} 输入新名称:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            ""
        )

        if ok and new_name:
            app = cast(QtCore.QCoreApplication, QtWidgets.QApplication.instance())
            config: Config = app.property("game_config")
            config_manager = app.property("config_manager")
            settings_manager = app.property("settings_manager")
            config.entry_signature_name_map[hex(entry_index.file_signature)] = new_name
            save_config_manager_to_settings(config_manager, settings_manager)
            model = self.model()
            model.get_filename(index, invalidate_cache=True)
            self.update(model.index(index.row()))
