from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from functools import partial

from PyQt5 import QtCore, QtGui, QtWidgets

CONFIG_FILE = "last_state.json"

LANG_STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        "window_title": "文件夹排序器",
        "browse_button": "浏览...",
        "path_placeholder": "输入或拖放文件夹路径",
        "select_dir_title": "选择文件夹路径",
        "new_folder_title": "新建文件夹",
        "new_folder_prompt": "请输入文件夹名称：",
        "new_folder_default": "新建",
        "error_title": "错误",
        "delete_failed_title": "删除失败",
        "rename_title": "重命名",
        "rename_prompt": "将“{name}”重命名为：",
        "rename_exists": "已存在同名文件夹！",
        "rename_failed": "重命名失败：{error}",
        "new_folder_failed": "创建文件夹失败：{error}",
        "clear_prefix_failed": "清除序号失败：{error}",
        "path_missing": "路径不存在！",
        "confirm_delete_title": "确认删除",
        "confirm_delete_message": "确定要删除以下文件夹？\n\n{items}",
        "delete_failed": "{name} 删除失败：{error}",
        "context_new_folder": "新建文件夹",
        "context_select_dir": "选择目录",
        "context_rename": "重命名",
        "context_delete": "删除所选",
        "context_clear_prefix": "清除全部序号",
        "context_start_sort": "开始排序",
        "context_pause_sort": "暂停排序",
        "context_language": "选择语言",
        "language_zh": "中文",
        "language_en": "English",
    },
    "en": {
        "window_title": "Folder Sorter",
        "browse_button": "Browse...",
        "path_placeholder": "Enter or drop a folder path",
        "select_dir_title": "Select Folder",
        "new_folder_title": "Create Folder",
        "new_folder_prompt": "Enter a folder name:",
        "new_folder_default": "New Folder",
        "error_title": "Error",
        "delete_failed_title": "Delete Failed",
        "rename_title": "Rename",
        "rename_prompt": "Rename \"{name}\" to:",
        "rename_exists": "A folder with that name already exists!",
        "rename_failed": "Failed to rename: {error}",
        "new_folder_failed": "Failed to create folder: {error}",
        "clear_prefix_failed": "Failed to clear prefix: {error}",
        "path_missing": "Path does not exist!",
        "confirm_delete_title": "Confirm Delete",
        "confirm_delete_message": "Are you sure you want to delete these folders?\n\n{items}",
        "delete_failed": "Failed to delete {name}: {error}",
        "context_new_folder": "New Folder",
        "context_select_dir": "Choose Directory",
        "context_rename": "Rename",
        "context_delete": "Delete Selected",
        "context_clear_prefix": "Clear Number Prefix",
        "context_start_sort": "Start Sorting",
        "context_pause_sort": "Pause Sorting",
        "context_language": "Language",
        "language_zh": "Chinese",
        "language_en": "English",
    },
}


class MyButton(QtWidgets.QPushButton):
    doubleClicked = QtCore.pyqtSignal()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[name-defined]
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class SortListWidget(QtWidgets.QListWidget):
    itemDropped = QtCore.pyqtSignal()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        super().dropEvent(event)
        self.itemDropped.emit()


class DirectoryManagerApp(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        icon_path = os.path.join(os.path.dirname(__file__), "Directory_Manager.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))
        self.sort_paused = True
        self._state = self._load_last_state()
        self.language = self._state.get("language", "zh")
        if self.language not in LANG_STRINGS:
            self.language = "zh"
        self._setup_ui()
        self._setup_blur_overlay()

        self._last_folder_list: list[str] = []
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._auto_refresh_folder_list)
        self._timer.start(1000)

        last_path = self._state.get("last_path", "")
        if isinstance(last_path, str) and last_path:
            self.path_edit.setText(last_path)
            if os.path.exists(last_path):
                self._refresh_list(last_path)
        self._pause_sort()
        self._apply_language()

    def _t(self, key: str) -> str:
        return LANG_STRINGS.get(self.language, LANG_STRINGS["zh"]).get(key, key)

    def _apply_language(self) -> None:
        self.setWindowTitle(self._t("window_title"))
        self.browse_btn.setText(self._t("browse_button"))
        self.path_edit.setPlaceholderText(self._t("path_placeholder"))

    def _auto_refresh_folder_list(self) -> None:
        base_path = self.path_edit.text()
        if not os.path.isdir(base_path):
            return
        try:
            folders = [
                f
                for f in os.listdir(base_path)
                if os.path.isdir(os.path.join(base_path, f))
            ]
            folders.sort()
        except Exception:
            folders = []
        if folders != self._last_folder_list:
            self._refresh_list(base_path)

    def _setup_blur_overlay(self) -> None:
        parent = self.list_widget.parentWidget()
        self.blur_overlay = QtWidgets.QWidget(parent)
        self._update_blur_geometry()
        self.blur_overlay.lower()
        self.blur_overlay.hide()
        self.blur_overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        blur = QtWidgets.QGraphicsBlurEffect()
        blur.setBlurRadius(16)
        self.blur_overlay.setGraphicsEffect(blur)
        self.list_widget.installEventFilter(self)

    def _update_blur_geometry(self) -> None:
        self.blur_overlay.setGeometry(self.list_widget.geometry())

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if obj is self.list_widget and event.type() == QtCore.QEvent.Resize:
            self._update_blur_geometry()
        return super().eventFilter(obj, event)

    def _show_blur(self, color: str) -> None:
        self._update_blur_geometry()
        self.blur_overlay.setStyleSheet(f"background: {color}; border-radius: 9px;")
        self.blur_overlay.show()
        self.blur_overlay.raise_()

    def _hide_blur(self) -> None:
        self.blur_overlay.hide()

    def _write_state(self) -> None:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _update_state(self, **kwargs: str) -> None:
        self._state.update(kwargs)
        self._write_state()

    def _load_last_state(self) -> dict[str, str]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items() if isinstance(v, (str, int, float))}
            except Exception:
                return {}
        return {}

    def _setup_ui(self) -> None:
        font = QtGui.QFont("微软雅黑", 14)
        self.setFont(font)
        self.setStyleSheet(
            """
            QWidget { background: #f7fafd; }
            QLineEdit {
                border-radius: 4px; padding: 5px 8px;
                border: 1px solid #b7bec7; background: #fff;
                font-size: 20px;
                min-height: 40px;
            }
            QPushButton {
                border-radius: 4px; background: #3794ff;
                color: white; padding: 5px 16px;
                font-size: 18px; font-weight: bold;
                min-height: 40px;
            }
            QPushButton:hover { background: #2265b5;}
            QListWidget {
                border-radius: 9px;
                border: 0.7px solid #b5bac0;
                background: #fff; font-size: 18px;
            }
            QListWidget::item {
                height: 32px; border-radius: 5px; color: #222;
            }
            QListWidget::item:selected:active {
                background: #3794ff; color: #fff;
            }
            QListWidget::item:selected:!active {
                background: #b5c6e0; color: #222;
            }
            QListWidget::item:hover {
                background: #eef5ff;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 10px;
                margin: 1px 1px 1px 0;
                border-radius: 10px;
            }
            QScrollBar::handle:vertical {
                background: #3794ff;
                min-height: 28px;
                border: none;
                border-radius: 7px;
                margin: 1px;
            }
            QScrollBar::handle:vertical:hover {
                background: #2265b5;
            }
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 4)

        path_layout = QtWidgets.QHBoxLayout()
        path_layout.setSpacing(4)
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setFont(QtGui.QFont("微软雅黑", 20))
        self.path_edit.returnPressed.connect(self._on_path_entry)
        self.browse_btn = MyButton(self._t("browse_button"))
        self.browse_btn.setFont(QtGui.QFont("微软雅黑", 18))
        self.browse_btn.clicked.connect(self._select_directory)
        self.browse_btn.doubleClicked.connect(self._on_browse_double_clicked)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)

        self.list_widget = SortListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list_widget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list_widget.itemDropped.connect(self._on_drop)
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.list_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._open_folder_in_explorer)
        layout.addWidget(self.list_widget)

        shadow = QtWidgets.QGraphicsDropShadowEffect(self.list_widget)
        shadow.setBlurRadius(16)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QtGui.QColor(0, 0, 0, 20))
        self.list_widget.setGraphicsEffect(shadow)

    def _on_browse_double_clicked(self) -> None:
        cur_w, cur_h = self.width(), self.height()
        self.resize(cur_w, cur_h * 2)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and os.path.isdir(path):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and os.path.isdir(path):
                    self.path_edit.setText(path)
                    self._update_state(last_path=path)
                    self._refresh_list(path)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def _refresh_list(self, base_path: str) -> None:
        self.list_widget.clear()
        try:
            folders = [
                f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))
            ]
            folders.sort()
        except Exception:
            folders = []
        for folder in folders:
            item = QtWidgets.QListWidgetItem(folder)
            self.list_widget.addItem(item)
        n = len(folders)
        max_show = min(n, 30)
        row_h = self.list_widget.sizeHintForRow(0) if n else 32
        list_h = max_show * row_h + 4
        self.list_widget.setFixedHeight(list_h)
        top_h = self.path_edit.sizeHint().height() + 10 + 16
        bottom_h = 18
        total_h = top_h + list_h + bottom_h
        self.setFixedHeight(total_h)
        self._last_folder_list = folders

    def _select_directory(self) -> None:
        cur_path = self.path_edit.text()
        start_dir = cur_path if cur_path and os.path.isdir(cur_path) else ""
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, self._t("select_dir_title"), start_dir
        )
        if path:
            self.path_edit.setText(path)
            self._update_state(last_path=path)
            self._refresh_list(path)

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
        folder_name, ok = QtWidgets.QInputDialog.getText(
            self,
            self._t("new_folder_title"),
            self._t("new_folder_prompt"),
            text=self._t("new_folder_default"),
        )
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
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self, self._t("error_title"), self._t("new_folder_failed").format(error=exc)
            )

    def _clear_prefix_number(self) -> None:
        base_path = self.path_edit.text()
        folders = [
            f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))
        ]
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
                except Exception as exc:
                    QtWidgets.QMessageBox.critical(
                        self,
                        self._t("error_title"),
                        self._t("clear_prefix_failed").format(error=exc),
                    )
        if changed:
            self._refresh_list(base_path)

    def _delete_selected_folders(self) -> None:
        items = self.list_widget.selectedItems()
        if not items:
            return
        names = [item.text() for item in items]
        msg = self._t("confirm_delete_message").format(items="\n".join(names))
        if (
            QtWidgets.QMessageBox.question(
                self,
                self._t("confirm_delete_title"),
                msg,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            != QtWidgets.QMessageBox.Yes
        ):
            return
        base_path = self.path_edit.text()
        for name in names:
            folder_path = os.path.join(base_path, name)
            try:
                shutil.rmtree(folder_path)
            except Exception as exc:
                QtWidgets.QMessageBox.warning(
                    self,
                    self._t("delete_failed_title"),
                    self._t("delete_failed").format(name=name, error=exc),
                )
        self._refresh_list(base_path)

    def _on_select(self) -> None:
        pass

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
        selected = self.list_widget.selectedItems()
        if len(selected) != 1:
            return
        old_name = selected[0].text()
        base_path = self.path_edit.text()
        old_path = os.path.join(base_path, old_name)
        new_name, ok = QtWidgets.QInputDialog.getText(
            self,
            self._t("rename_title"),
            self._t("rename_prompt").format(name=old_name),
            text=old_name,
        )
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(base_path, new_name)
            if os.path.exists(new_path):
                QtWidgets.QMessageBox.critical(
                    self, self._t("error_title"), self._t("rename_exists")
                )
                return
            try:
                os.rename(old_path, new_path)
                self._refresh_list(base_path)
            except Exception as exc:
                QtWidgets.QMessageBox.critical(
                    self, self._t("error_title"), self._t("rename_failed").format(error=exc)
                )

    def _pause_sort(self) -> None:
        self.sort_paused = True
        self._show_blur("rgba(255,105,180,0.10)")

    def _resume_sort(self) -> None:
        self.sort_paused = False
        self._show_blur("rgba(120,255,170,0.10)")
        self._confirm_sort()

    def _set_language(self, language: str) -> None:
        if language not in LANG_STRINGS:
            return
        if language == self.language:
            return
        self.language = language
        self._apply_language()
        self._update_state(language=language)

    def _on_drop(self) -> None:
        if not self.sort_paused:
            self._confirm_sort()

    def _on_path_entry(self) -> None:
        path = self.path_edit.text()
        if os.path.isdir(path):
            self._update_state(last_path=path)
            self._refresh_list(path)
        else:
            QtWidgets.QMessageBox.critical(self, self._t("error_title"), self._t("path_missing"))

    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        menu.addAction(self._t("context_new_folder"), self._create_new_folder)
        menu.addAction(self._t("context_select_dir"), self._select_directory)
        menu.addSeparator()
        selected_count = len(self.list_widget.selectedItems())
        act_rename = menu.addAction(self._t("context_rename"), self._rename_selected_folder)
        act_rename.setEnabled(selected_count == 1)
        act_delete = menu.addAction(self._t("context_delete"), self._delete_selected_folders)
        act_delete.setEnabled(selected_count >= 1)
        menu.addSeparator()
        menu.addAction(self._t("context_clear_prefix"), self._clear_prefix_number)
        menu.addSeparator()
        if self.sort_paused:
            menu.addAction(self._t("context_start_sort"), self._resume_sort)
        else:
            menu.addAction(self._t("context_pause_sort"), self._pause_sort)
        menu.addSeparator()
        lang_menu = menu.addMenu(self._t("context_language"))
        for code, label_key in [("zh", "language_zh"), ("en", "language_en")]:
            action = lang_menu.addAction(self._t(label_key))
            action.setCheckable(True)
            action.setChecked(self.language == code)
            action.triggered.connect(partial(self._set_language, code))
        menu.setStyleSheet(
            """
            QMenu { font-size:16px; }
            QMenu::item:selected { background-color: #3794ff; color: #fff; }
            """
        )
        menu.exec_(self.list_widget.mapToGlobal(pos))


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = DirectoryManagerApp()
    window.resize(600, 420)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
