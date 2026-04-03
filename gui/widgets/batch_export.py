"""Batch export dialog and logic for converting NPK entries to common formats."""

import os
from typing import cast, TYPE_CHECKING
from PySide6 import QtCore, QtWidgets, QtGui

from core.images import convert_image, image_to_png_data
from core.mesh_converter import FORMATS as MESH_FORMATS, convert_mesh
from core.mesh_loader.loader import MeshLoader
from core.npk.class_types import NPKEntry
from core.npk.enums import NPKEntryFileCategories

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Supported image extensions that can be converted to raster formats
# ---------------------------------------------------------------------------
IMAGE_NATIVE_EXTENSIONS = {
    "png", "jpg", "jpeg", "bmp", "gif", "tga", "tiff", "webp"
}
IMAGE_CUSTOM_EXTENSIONS = {"dds", "pvr", "ktx", "ktx_low", "astc", "cbk"}
IMAGE_ALL_EXTENSIONS = IMAGE_NATIVE_EXTENSIONS | IMAGE_CUSTOM_EXTENSIONS

IMAGE_OUTPUT_FORMATS = ["PNG", "JPG", "BMP"]

# Mesh extensions handled by the mesh loader
MESH_EXTENSIONS = {"mesh"}


def _is_image_entry(entry: NPKEntry) -> bool:
    return entry.extension.lower() in IMAGE_ALL_EXTENSIONS


def _is_mesh_entry(entry: NPKEntry) -> bool:
    return entry.extension.lower() in MESH_EXTENSIONS


# ---------------------------------------------------------------------------
# Worker thread for batch conversion
# ---------------------------------------------------------------------------
class BatchExportSignals(QtCore.QObject):
    progress = QtCore.Signal(int)          # current count
    total = QtCore.Signal(int)             # total count
    log = QtCore.Signal(str)               # log message
    finished = QtCore.Signal(int, int)     # success_count, fail_count


class BatchExportWorker(QtCore.QRunnable):
    """Background worker that converts and saves entries."""

    def __init__(
        self,
        entries: list[tuple[str, NPKEntry]],
        output_dir: str,
        image_format: str | None,
        mesh_format,
    ):
        """
        Parameters
        ----------
        entries       : list of (display_name, NPKEntry) to process
        output_dir    : destination directory
        image_format  : "PNG" / "JPG" / "BMP" or None (skip images)
        mesh_format   : mesh format module (from MESH_FORMATS) or None (skip meshes)
        """
        super().__init__()
        self.entries = entries
        self.output_dir = output_dir
        self.image_format = image_format
        self.mesh_format = mesh_format
        self.signals = BatchExportSignals()
        self.cancelled = False

    @QtCore.Slot()
    def run(self):
        success = 0
        fail = 0
        total = len(self.entries)
        self.signals.total.emit(total)

        for i, (name, entry) in enumerate(self.entries):
            if self.cancelled:
                self.signals.log.emit("导出被用户取消。")
                break

            self.signals.progress.emit(i)
            ext = entry.extension.lower()
            base_name = os.path.splitext(name)[0]

            try:
                if self.image_format and ext in IMAGE_ALL_EXTENSIONS:
                    out_path = os.path.join(
                        self.output_dir,
                        f"{base_name}.{self.image_format.lower()}"
                    )
                    self._save_image(entry.data, ext, out_path)
                    success += 1
                    self.signals.log.emit(f"[成功] {name} -> {os.path.basename(out_path)}")

                elif self.mesh_format and ext in MESH_EXTENSIONS:
                    out_path = os.path.join(
                        self.output_dir,
                        f"{base_name}{self.mesh_format.EXTENSION}"
                    )
                    self._save_mesh(entry.data, out_path)
                    success += 1
                    self.signals.log.emit(f"[成功] {name} -> {os.path.basename(out_path)}")

                else:
                    # Entry type not selected for export, skip silently
                    pass

            except Exception as e:
                fail += 1
                self.signals.log.emit(f"[失败] {name}: {e}")

        self.signals.progress.emit(total)
        self.signals.finished.emit(success, fail)

    # ------------------------------------------------------------------
    def _save_image(self, data: bytes, ext: str, out_path: str):
        """Convert image data to the target format and write to disk."""
        if ext in IMAGE_NATIVE_EXTENSIONS:
            # Qt can load it directly
            qimage = QtGui.QImage.fromData(data, cast(bytes, ext))
            if qimage.isNull():
                raise ValueError("Qt failed to load image")
        else:
            # Custom decode path → PIL → PNG bytes → QImage
            pil_img = convert_image(data, ext)
            if pil_img is None:
                raise ValueError(f"Unsupported image extension: {ext}")
            png_bytes = image_to_png_data(pil_img)
            qimage = QtGui.QImage.fromData(png_bytes)
            if qimage.isNull():
                raise ValueError("Failed to convert image to QImage")

        fmt = self.image_format  # e.g. "PNG"
        byte_array = QtCore.QByteArray()
        buffer = QtCore.QBuffer(byte_array)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        qimage.save(buffer, cast(bytes, fmt))
        buffer.close()

        os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(byte_array.data())

    def _save_mesh(self, data: bytes, out_path: str):
        """Parse mesh and convert to target format, write to disk."""
        loader = MeshLoader()
        mesh_data = loader.load_from_bytes(data)
        if mesh_data is None:
            raise ValueError("Failed to parse mesh data")
        converted = convert_mesh(mesh_data, self.mesh_format)
        os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(converted)


# ---------------------------------------------------------------------------
# Batch Export Dialog
# ---------------------------------------------------------------------------
class BatchExportDialog(QtWidgets.QDialog):
    """
    Dialog that lets the user choose:
    - Output directory
    - Image format (or skip images)
    - Mesh format (or skip meshes)
    Then runs the batch export with a progress bar and log.
    """

    def __init__(
        self,
        entries: list[tuple[str, NPKEntry]],
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.entries = entries
        self.setWindowTitle("批量导出")
        self.setMinimumWidth(560)
        self.setMinimumHeight(480)

        # Count how many images vs meshes are in the selection
        self._image_count = sum(1 for _, e in entries if _is_image_entry(e))
        self._mesh_count = sum(1 for _, e in entries if _is_mesh_entry(e))

        self._worker: BatchExportWorker | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)

        # ---- Summary label ----
        summary = (
            f"已选择: {len(self.entries)} 个条目  "
            f"({self._image_count} 个图像, {self._mesh_count} 个模型)"
        )
        layout.addWidget(QtWidgets.QLabel(summary))

        # ---- Output directory ----
        dir_group = QtWidgets.QGroupBox("输出目录")
        dir_layout = QtWidgets.QHBoxLayout(dir_group)
        self._dir_edit = QtWidgets.QLineEdit()
        self._dir_edit.setPlaceholderText("选择输出文件夹…")
        browse_btn = QtWidgets.QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse_dir)
        dir_layout.addWidget(self._dir_edit)
        dir_layout.addWidget(browse_btn)
        layout.addWidget(dir_group)

        # ---- Image options ----
        img_group = QtWidgets.QGroupBox("图像导出")
        img_layout = QtWidgets.QHBoxLayout(img_group)
        img_layout.addWidget(QtWidgets.QLabel("导出图像为:"))
        self._img_combo = QtWidgets.QComboBox()
        self._img_combo.addItem("(跳过/不导出图像)", None)
        for fmt in IMAGE_OUTPUT_FORMATS:
            self._img_combo.addItem(fmt, fmt)
        self._img_combo.setCurrentIndex(1)  # default PNG
        img_layout.addWidget(self._img_combo)
        img_layout.addStretch()
        img_group.setEnabled(self._image_count > 0)
        layout.addWidget(img_group)

        # ---- Mesh options ----
        mesh_group = QtWidgets.QGroupBox("模型导出")
        mesh_layout = QtWidgets.QHBoxLayout(mesh_group)
        mesh_layout.addWidget(QtWidgets.QLabel("导出模型为:"))
        self._mesh_combo = QtWidgets.QComboBox()
        self._mesh_combo.addItem("(跳过/不导出模型)", None)
        for fmt in MESH_FORMATS:
            self._mesh_combo.addItem(fmt.NAME, fmt)
        self._mesh_combo.setCurrentIndex(2)  # default glTF
        mesh_layout.addWidget(self._mesh_combo)
        mesh_layout.addStretch()
        mesh_group.setEnabled(self._mesh_count > 0)
        layout.addWidget(mesh_group)

        # ---- Duplicate filename handling ----
        dedup_group = QtWidgets.QGroupBox("文件名冲突")
        dedup_layout = QtWidgets.QHBoxLayout(dedup_group)
        self._overwrite_radio = QtWidgets.QRadioButton("覆盖现有文件")
        self._skip_radio = QtWidgets.QRadioButton("跳过现有文件")
        self._rename_radio = QtWidgets.QRadioButton("自动重命名(添加 _1, _2…)")
        self._overwrite_radio.setChecked(True)
        dedup_layout.addWidget(self._overwrite_radio)
        dedup_layout.addWidget(self._skip_radio)
        dedup_layout.addWidget(self._rename_radio)
        layout.addWidget(dedup_group)

        # ---- Progress bar ----
        self._progress = QtWidgets.QProgressBar()
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        # ---- Log area ----
        self._log = QtWidgets.QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(140)
        self._log.setPlaceholderText("导出日志将显示在这里…")
        layout.addWidget(self._log)

        # ---- Buttons ----
        btn_layout = QtWidgets.QHBoxLayout()
        self._export_btn = QtWidgets.QPushButton("开始导出")
        self._export_btn.setDefault(True)
        self._export_btn.clicked.connect(self._start_export)
        self._cancel_btn = QtWidgets.QPushButton("取消")
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._close_btn = QtWidgets.QPushButton("关闭")
        self._close_btn.clicked.connect(self.accept)
        self._close_btn.setEnabled(False)
        btn_layout.addStretch()
        btn_layout.addWidget(self._export_btn)
        btn_layout.addWidget(self._cancel_btn)
        btn_layout.addWidget(self._close_btn)
        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    def _browse_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "选择输出目录", "")
        if d:
            self._dir_edit.setText(d)

    # ------------------------------------------------------------------
    def _resolve_path(self, out_path: str) -> str | None:
        """Apply conflict-resolution policy and return the final path, or None to skip."""
        if not os.path.exists(out_path):
            return out_path
        if self._overwrite_radio.isChecked():
            return out_path
        if self._skip_radio.isChecked():
            return None
        # Auto-rename
        base, ext = os.path.splitext(out_path)
        counter = 1
        while os.path.exists(out_path):
            out_path = f"{base}_{counter}{ext}"
            counter += 1
        return out_path

    # ------------------------------------------------------------------
    def _start_export(self):
        output_dir = self._dir_edit.text().strip()
        if not output_dir:
            QtWidgets.QMessageBox.warning(self, "未选择目录", "请选择一个输出目录。")
            return

        image_format = self._img_combo.currentData()
        mesh_format = self._mesh_combo.currentData()

        if image_format is None and mesh_format is None:
            QtWidgets.QMessageBox.warning(
                self, "无内容可导出",
                "请选择至少一种导出格式(图像或模型)。"
            )
            return

        os.makedirs(output_dir, exist_ok=True)

        # Pre-process entries with conflict resolution
        resolved_entries: list[tuple[str, NPKEntry, str]] = []
        ext_map = {
            "image": f".{image_format.lower()}" if image_format else None,
            "mesh": mesh_format.EXTENSION if mesh_format else None,
        }

        for name, entry in self.entries:
            e_ext = entry.extension.lower()
            base_name = os.path.splitext(name)[0]

            if image_format and e_ext in IMAGE_ALL_EXTENSIONS:
                out_path = os.path.join(output_dir, f"{base_name}{ext_map['image']}")
                out_path = self._resolve_path(out_path)
                if out_path:
                    resolved_entries.append((name, entry, out_path))

            elif mesh_format and e_ext in MESH_EXTENSIONS:
                out_path = os.path.join(output_dir, f"{base_name}{ext_map['mesh']}")
                out_path = self._resolve_path(out_path)
                if out_path:
                    resolved_entries.append((name, entry, out_path))

        if not resolved_entries:
            QtWidgets.QMessageBox.information(
                self, "无内容可导出",
                "所有文件都被跳过(已存在或无匹配类型)。"
            )
            return

        self._progress.setRange(0, len(resolved_entries))
        self._progress.setValue(0)
        self._log.clear()
        self._export_btn.setEnabled(False)
        self._close_btn.setEnabled(False)

        # Build a simple worker using resolved paths to honour rename/skip policy
        # We pass a pre-resolved list; the worker just saves directly.
        self._worker = _ResolvedBatchExportWorker(
            resolved_entries, image_format, mesh_format
        )
        self._worker.signals.progress.connect(self._progress.setValue)
        self._worker.signals.log.connect(self._log.appendPlainText)
        self._worker.signals.finished.connect(self._on_finished)
        QtCore.QThreadPool.globalInstance().start(self._worker)

    # ------------------------------------------------------------------
    def _on_cancel(self):
        if self._worker is not None:
            self._worker.cancelled = True
        else:
            self.reject()

    def _on_finished(self, success: int, fail: int):
        self._export_btn.setEnabled(True)
        self._close_btn.setEnabled(True)
        self._worker = None
        msg = f"导出完成: {success}成功, {fail}失败。"
        self._log.appendPlainText(msg)
        QtWidgets.QMessageBox.information(self, "导出完成", msg)


# ---------------------------------------------------------------------------
# Simplified worker that uses pre-resolved (name, entry, out_path) triples
# ---------------------------------------------------------------------------
class _ResolvedBatchExportWorker(QtCore.QRunnable):
    def __init__(
        self,
        entries: list[tuple[str, NPKEntry, str]],
        image_format: str | None,
        mesh_format,
    ):
        super().__init__()
        self.entries = entries
        self.image_format = image_format
        self.mesh_format = mesh_format
        self.signals = BatchExportSignals()
        self.cancelled = False

    @QtCore.Slot()
    def run(self):
        success = 0
        fail = 0
        total = len(self.entries)
        self.signals.total.emit(total)

        for i, (name, entry, out_path) in enumerate(self.entries):
            if self.cancelled:
                self.signals.log.emit("导出被用户取消。")
                break

            self.signals.progress.emit(i)
            ext = entry.extension.lower()

            try:
                os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

                if self.image_format and ext in IMAGE_ALL_EXTENSIONS:
                    _save_image_to(entry.data, ext, self.image_format, out_path)
                    success += 1
                    self.signals.log.emit(f"[成功]   {name}  →  {os.path.basename(out_path)}")

                elif self.mesh_format and ext in MESH_EXTENSIONS:
                    _save_mesh_to(entry.data, self.mesh_format, out_path)
                    success += 1
                    self.signals.log.emit(f"[成功]   {name}  →  {os.path.basename(out_path)}")

            except Exception as e:
                fail += 1
                self.signals.log.emit(f"[失败] {name}: {e}")

        self.signals.progress.emit(total)
        self.signals.finished.emit(success, fail)


# ---------------------------------------------------------------------------
# Standalone helpers (also used by the viewer-tab "Save All As" code)
# ---------------------------------------------------------------------------
def _save_image_to(data: bytes, ext: str, image_format: str, out_path: str):
    """Convert image data and write to *out_path*."""
    if ext in IMAGE_NATIVE_EXTENSIONS:
        qimage = QtGui.QImage.fromData(data, cast(bytes, ext))
        if qimage.isNull():
            raise ValueError("Qt failed to load image")
    else:
        pil_img = convert_image(data, ext)
        if pil_img is None:
            raise ValueError(f"Unsupported image extension: {ext}")
        png_bytes = image_to_png_data(pil_img)
        qimage = QtGui.QImage.fromData(png_bytes)
        if qimage.isNull():
            raise ValueError("Failed to build QImage from decoded data")

    byte_array = QtCore.QByteArray()
    buffer = QtCore.QBuffer(byte_array)
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    qimage.save(buffer, cast(bytes, image_format))
    buffer.close()
    with open(out_path, "wb") as f:
        f.write(byte_array.data())


def _save_mesh_to(data: bytes, mesh_format, out_path: str):
    """Parse mesh bytes and write converted file to *out_path*."""
    loader = MeshLoader()
    mesh_data = loader.load_from_bytes(data)
    if mesh_data is None:
        raise ValueError("Failed to parse mesh data")
    converted = convert_mesh(mesh_data, mesh_format)
    with open(out_path, "wb") as f:
        f.write(converted)
