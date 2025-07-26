"""Simple folder manager GUI implemented with PyQt5.

This version replaces the previous Tk based implementation and keeps the same
features such as drag and drop sorting, context menu actions and remembering
the last opened directory.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from PyQt5 import QtCore, QtGui, QtWidgets


CONFIG_FILE = "last_state.json"


class SortListWidget(QtWidgets.QListWidget):
    """QListWidget with a signal emitted after items are dropped."""

    itemDropped = QtCore.pyqtSignal()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[override]
        super().dropEvent(event)
        self.itemDropped.emit()


class FileManagerApp(QtWidgets.QWidget):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.sort_paused = True
        self._setup_ui()

        last_state = self._load_last_state()
        initial_path = (last_state or {}).get("last_path", "")
        if initial_path:
            self.path_edit.setText(initial_path)
            if os.path.exists(initial_path):
                self._refresh_list(initial_path)

        self._pause_sort()

    # ------------------------------------------------------------------ utils
    def _save_last_state(self, path: str) -> None:
        with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
            json.dump({"last_path": path}, fh)

    def _load_last_state(self) -> dict | None:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        return None

    # --------------------------------------------------------------------- UI
    def _setup_ui(self) -> None:
        self.setWindowTitle("文件夹排序器")

        layout = QtWidgets.QVBoxLayout(self)

        path_layout = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.returnPressed.connect(self._on_path_entry)
        browse_btn = QtWidgets.QPushButton("浏览...")
        browse_btn.clicked.connect(self._select_directory)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        self.list_widget = SortListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list_widget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list_widget.itemDropped.connect(self._on_drop)
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.list_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._open_folder_in_explorer)
        layout.addWidget(self.list_widget)

    # ------------------------------------------------------------------ actions
    def _refresh_list(self, base_path: str) -> None:
        self.list_widget.clear()
        folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
        folders.sort()
        for folder in folders:
            item = QtWidgets.QListWidgetItem(folder)
            item.setBackground(QtGui.QColor("white"))
            self.list_widget.addItem(item)

    def _confirm_sort(self) -> None:
        base_path = self.path_edit.text()
        folders = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        used_names: set[str] = set()
        for i, folder_name in enumerate(folders, 1):
            base_name = re.sub(r"^\d+_", "", folder_name)
            new_name = f"{i:02d}_{base_name}"
            current_path = os.path.join(base_path, folder_name)
            new_path = os.path.join(base_path, new_name)
            counter = 1
            while new_name in used_names or (os.path.exists(new_path) and current_path != new_path):
                new_name = f"{i:02d}_{base_name} ({counter})"
                new_path = os.path.join(base_path, new_name)
                counter += 1
            used_names.add(new_name)
            if os.path.exists(current_path):
                os.rename(current_path, new_path)
        self._refresh_list(base_path)

    def _create_new_folder(self) -> None:
        base_path = self.path_edit.text()
        folder_name, ok = QtWidgets.QInputDialog.getText(self, "新建文件夹", "请输入文件夹名称：", text="新建")
        if not ok or not folder_name:
            return
        counter = 1
        original_name = folder_name
        while os.path.exists(os.path.join(base_path, folder_name)):
            folder_name = f"{original_name}({counter})"
            counter += 1
        try:
            os.makedirs(os.path.join(base_path, folder_name))
            self._refresh_list(base_path)
        except Exception as exc:  # pragma: no cover - OS errors hard to trigger
            QtWidgets.QMessageBox.critical(self, "错误", f"创建文件夹失败：{exc}")

    def _clear_prefix_number(self) -> None:
        base_path = self.path_edit.text()
        folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
        changed = False
        for old_name in folders:
            new_name = re.sub(r"^\d+_?", "", old_name)
            if new_name and new_name != old_name:
                old_path = os.path.join(base_path, old_name)
                new_path = os.path.join(base_path, new_name)
                if os.path.exists(new_path):
                    continue
                try:
                    os.rename(old_path, new_path)
                    changed = True
                except Exception as exc:  # pragma: no cover - OS errors hard to trigger
                    QtWidgets.QMessageBox.critical(self, "错误", f"清除序号失败：{exc}")
        if changed:
            self._refresh_list(base_path)

    def _select_directory(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择文件夹路径")
        if path:
            self.path_edit.setText(path)
            self._save_last_state(path)
            self._refresh_list(path)

    def _on_select(self) -> None:
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setForeground(QtGui.QColor("black"))
        idx = self.list_widget.currentRow()
        if idx >= 0:
            self.list_widget.item(idx).setForeground(QtGui.QColor("red"))

    def _open_folder_in_explorer(self, item: QtWidgets.QListWidgetItem) -> None:
        folder_name = item.text()
        base_path = self.path_edit.text()
        folder_path = os.path.join(base_path, folder_name)
        if os.path.exists(folder_path):
            if sys.platform.startswith("win"):
                os.startfile(folder_path)
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])

    def _rename_selected_folder(self) -> None:
        idx = self.list_widget.currentRow()
        if idx < 0:
            return
        old_name = self.list_widget.item(idx).text()
        base_path = self.path_edit.text()
        old_path = os.path.join(base_path, old_name)
        new_name, ok = QtWidgets.QInputDialog.getText(self, "重命名", f"将“{old_name}”重命名为：", text=old_name)
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(base_path, new_name)
            if os.path.exists(new_path):
                QtWidgets.QMessageBox.critical(self, "错误", "已存在同名文件夹！")
                return
            try:
                os.rename(old_path, new_path)
                self._refresh_list(base_path)
            except Exception as exc:  # pragma: no cover - OS errors hard to trigger
                QtWidgets.QMessageBox.critical(self, "错误", f"重命名失败：{exc}")

    def _pause_sort(self) -> None:
        self.sort_paused = True
        self.list_widget.setStyleSheet("border:2px solid red;")

    def _resume_sort(self) -> None:
        self.sort_paused = False
        self.list_widget.setStyleSheet("border:2px solid green;")
        self._confirm_sort()

    def _on_drop(self) -> None:
        if not self.sort_paused:
            self._confirm_sort()

    def _on_path_entry(self) -> None:
        path = self.path_edit.text()
        if os.path.isdir(path):
            self._save_last_state(path)
            self._refresh_list(path)
        else:
            QtWidgets.QMessageBox.critical(self, "错误", "路径不存在！")

    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        menu.addAction("新建文件夹", self._create_new_folder)
        menu.addAction("打开目录", self._select_directory)
        menu.addAction("重命名称", self._rename_selected_folder)
        menu.addAction("清除序号", self._clear_prefix_number)
        if self.sort_paused:
            menu.addAction("开始排序", self._resume_sort)
        else:
            menu.addAction("暂停排序", self._pause_sort)
        menu.exec_(self.list_widget.mapToGlobal(pos))


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = FileManagerApp()
    window.resize(600, 400)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()

