from __future__ import annotations

import errno
import json
import os
import re
import shutil
import subprocess
import sys

from PyQt5 import QtCore, QtGui, QtWidgets

CONFIG_FILE = "last_state.json"

class MyButton(QtWidgets.QPushButton):
    doubleClicked = QtCore.pyqtSignal()
    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

class SortListWidget(QtWidgets.QListWidget):
    itemDropped = QtCore.pyqtSignal()
    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        super().dropEvent(event)
        self.itemDropped.emit()

class FileManagerApp(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.sort_paused = True
        self._state: dict[str, object] = self._load_last_state()
        self._current_path = ""
        self._reserved: set[str] = set()
        self._setup_ui()
        self._setup_blur_overlay()
        self._load_notes_from_state()

        self._last_folder_list = []
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._auto_refresh_folder_list)
        self._timer.start(1000)

        initial_path = self._state.get("last_path", "")
        if initial_path:
            self.path_edit.setText(initial_path)
            if os.path.exists(initial_path):
                self._refresh_list(initial_path)
        self._pause_sort()

    def _auto_refresh_folder_list(self):
        base_path = self.path_edit.text()
        if not os.path.isdir(base_path):
            return
        try:
            folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
            folders.sort()
        except Exception:
            folders = []
        if folders != self._last_folder_list:
            self._refresh_list(base_path)

    def _setup_blur_overlay(self):
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

    def _update_blur_geometry(self):
        self.blur_overlay.setGeometry(self.list_widget.geometry())

    def eventFilter(self, obj, event):
        if obj is self.list_widget and event.type() == QtCore.QEvent.Resize:
            self._update_blur_geometry()
        return super().eventFilter(obj, event)

    def _show_blur(self, color):
        self._update_blur_geometry()
        self.blur_overlay.setStyleSheet(f"background: {color}; border-radius: 9px;")
        self.blur_overlay.show()
        self.blur_overlay.raise_()

    def _hide_blur(self):
        self.blur_overlay.hide()

    def _save_last_state(self, path: str) -> None:
        self._state["last_path"] = path
        self._write_state()

    def _write_state(self) -> None:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(f"保存状态失败: {exc}", file=sys.stderr)

    def _load_last_state(self) -> dict[str, object]:
        if not os.path.exists(CONFIG_FILE):
            return {"last_path": "", "reserved": {}, "notes": []}
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {"last_path": "", "reserved": {}, "notes": []}
        if not isinstance(data, dict):
            return {"last_path": "", "reserved": {}, "notes": []}
        reserved = data.get("reserved", {})
        if not isinstance(reserved, dict):
            reserved = {}
        else:
            sanitized_reserved: dict[str, list[str]] = {}
            for key, value in reserved.items():
                if not isinstance(key, str) or not isinstance(value, list):
                    continue
                sanitized_reserved[key] = [str(item) for item in value if isinstance(item, str)]
            reserved = sanitized_reserved
        data["reserved"] = reserved
        if "last_path" not in data or not isinstance(data["last_path"], str):
            data["last_path"] = ""
        notes = data.get("notes", [])
        if isinstance(notes, list):
            notes = [str(item) for item in notes if isinstance(item, str)]
        else:
            notes = []
        data["notes"] = notes
        return data

    def _get_reserved_dict(self) -> dict[str, list[str]]:
        reserved = self._state.setdefault("reserved", {})
        if not isinstance(reserved, dict):
            reserved = {}
            self._state["reserved"] = reserved
        return reserved

    def _save_reserved_state(self) -> None:
        if not self._current_path:
            return
        reserved_dict = self._get_reserved_dict()
        if self._reserved:
            reserved_dict[self._current_path] = sorted(self._reserved)
        else:
            reserved_dict.pop(self._current_path, None)
        self._write_state()

    def _apply_reserved_style(self, item: QtWidgets.QListWidgetItem, is_reserved: bool) -> None:
        item.setData(QtCore.Qt.UserRole, is_reserved)
        font = item.font()
        font.setItalic(is_reserved)
        item.setFont(font)
        if is_reserved:
            item.setForeground(QtGui.QColor("#8c8c8c"))
            item.setToolTip("已标记为保留，此文件夹不会参与自动排序或清除序号。")
        else:
            item.setForeground(QtGui.QBrush())
            item.setToolTip("")

    def _is_item_reserved(self, item: QtWidgets.QListWidgetItem) -> bool:
        data = item.data(QtCore.Qt.UserRole)
        if isinstance(data, bool):
            return data
        return item.text() in self._reserved

    def _mark_selected_as_reserved(self) -> None:
        if not self._current_path:
            return
        changed = False
        for item in self.list_widget.selectedItems():
            name = item.text()
            if name not in self._reserved:
                self._reserved.add(name)
                changed = True
            self._apply_reserved_style(item, True)
        if changed:
            self._save_reserved_state()

    def _unmark_selected_reserved(self) -> None:
        if not self._current_path or not self._reserved:
            return
        changed = False
        for item in self.list_widget.selectedItems():
            name = item.text()
            if name in self._reserved:
                self._reserved.remove(name)
                changed = True
            self._apply_reserved_style(item, name in self._reserved)
        if changed:
            self._save_reserved_state()

    @staticmethod
    def _is_folder_in_use_error(exc: OSError) -> bool:
        if isinstance(exc, PermissionError):
            return True
        err_no = getattr(exc, "errno", None)
        if err_no in {errno.EACCES, errno.EBUSY, errno.EPERM}:
            return True
        win_err = getattr(exc, "winerror", None)
        if win_err in {32, 33}:
            return True
        return False

    def _show_folder_in_use_warning(self, folder_name: str) -> None:
        QtWidgets.QMessageBox.warning(
            self,
            "文件夹被占用",
            f"文件夹“{folder_name}”当前正被其他程序占用，请关闭相关窗口或程序后重试。",
        )

    def _setup_ui(self) -> None:
        font = QtGui.QFont("微软雅黑", 14)
        self.setFont(font)
        self.setStyleSheet("""
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
        """)
        self.setWindowTitle("文件夹排序器")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 4)

        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)

        file_tab = QtWidgets.QWidget()
        file_layout = QtWidgets.QVBoxLayout(file_tab)
        file_layout.setSpacing(4)
        file_layout.setContentsMargins(0, 0, 0, 0)

        path_layout = QtWidgets.QHBoxLayout()
        path_layout.setSpacing(4)
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setFont(QtGui.QFont("微软雅黑", 20))  # 地址栏专用大字体
        self.path_edit.returnPressed.connect(self._on_path_entry)
        self.browse_btn = MyButton("浏览...")
        self.browse_btn.setFont(QtGui.QFont("微软雅黑", 18))
        self.browse_btn.clicked.connect(self._select_directory)
        self.browse_btn.doubleClicked.connect(self._on_browse_double_clicked)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.browse_btn)
        file_layout.addLayout(path_layout)

        self.list_widget = SortListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list_widget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list_widget.itemDropped.connect(self._on_drop)
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.list_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._open_folder_in_explorer)
        file_layout.addWidget(self.list_widget)

        self.tabs.addTab(file_tab, "文件整理")

        notes_tab = QtWidgets.QWidget()
        notes_layout = QtWidgets.QVBoxLayout(notes_tab)
        notes_layout.setSpacing(6)
        notes_layout.setContentsMargins(4, 4, 4, 4)

        notes_label = QtWidgets.QLabel("记录灵感或待办事项，每条一行，双击可直接编辑。")
        notes_label.setWordWrap(True)
        notes_layout.addWidget(notes_label)

        notes_input_layout = QtWidgets.QHBoxLayout()
        notes_input_layout.setSpacing(4)
        self.note_input = QtWidgets.QLineEdit()
        self.note_input.setPlaceholderText("输入新的灵感或代办事项，按回车或点击添加")
        self.note_input.returnPressed.connect(self._add_note)
        self.add_note_btn = QtWidgets.QPushButton("添加")
        self.add_note_btn.clicked.connect(self._add_note)
        notes_input_layout.addWidget(self.note_input)
        notes_input_layout.addWidget(self.add_note_btn)
        notes_layout.addLayout(notes_input_layout)

        self.notes_list = QtWidgets.QListWidget()
        self.notes_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.notes_list.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        self.notes_list.itemChanged.connect(self._on_note_changed)
        self.notes_list.itemSelectionChanged.connect(self._update_notes_actions)
        notes_layout.addWidget(self.notes_list)

        notes_actions_layout = QtWidgets.QHBoxLayout()
        notes_actions_layout.addStretch()
        self.delete_note_btn = QtWidgets.QPushButton("删除所选")
        self.delete_note_btn.clicked.connect(self._delete_selected_notes)
        notes_actions_layout.addWidget(self.delete_note_btn)
        notes_layout.addLayout(notes_actions_layout)

        self.tabs.addTab(notes_tab, "灵感与代办")

        shadow = QtWidgets.QGraphicsDropShadowEffect(self.list_widget)
        shadow.setBlurRadius(16)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QtGui.QColor(0,0,0,20))
        self.list_widget.setGraphicsEffect(shadow)

    def _on_browse_double_clicked(self):
        cur_w, cur_h = self.width(), self.height()
        self.resize(cur_w, cur_h * 2)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and os.path.isdir(path):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and os.path.isdir(path):
                    self.path_edit.setText(path)
                    self._save_last_state(path)
                    self._refresh_list(path)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def _refresh_list(self, base_path: str) -> None:
        self.list_widget.clear()
        try:
            folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
            folders.sort()
        except Exception:
            folders = []
        reserved_dict = self._get_reserved_dict()
        stored_reserved = set(reserved_dict.get(base_path, []))
        actual_reserved = stored_reserved & set(folders)
        self._current_path = base_path
        self._reserved = actual_reserved
        if actual_reserved != stored_reserved:
            self._save_reserved_state()
        for folder in folders:
            item = QtWidgets.QListWidgetItem(folder)
            self._apply_reserved_style(item, folder in self._reserved)
            self.list_widget.addItem(item)
        n = len(folders)
        max_show = min(n, 30)
        row_h = self.list_widget.sizeHintForRow(0) if n else 32
        list_h = max_show * row_h + 4
        self.list_widget.setFixedHeight(list_h)
        top_h = self.path_edit.sizeHint().height() + 10 + 16
        bottom_h = 18
        total_h = top_h + list_h + bottom_h
        self.list_widget.setMinimumHeight(list_h)
        self._last_folder_list = folders

    def _load_notes_from_state(self) -> None:
        notes = self._state.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        self.notes_list.blockSignals(True)
        self.notes_list.clear()
        for text in notes:
            item = QtWidgets.QListWidgetItem(text)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
            self.notes_list.addItem(item)
        self.notes_list.blockSignals(False)
        self._update_notes_actions()

    def _save_notes(self) -> None:
        notes = [self.notes_list.item(i).text() for i in range(self.notes_list.count())]
        self._state["notes"] = notes
        self._write_state()

    def _add_note(self) -> None:
        text = self.note_input.text().strip()
        if not text:
            return
        item = QtWidgets.QListWidgetItem(text)
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        self.notes_list.addItem(item)
        self.note_input.clear()
        self._save_notes()
        self._update_notes_actions()

    def _delete_selected_notes(self) -> None:
        selected = self.notes_list.selectedItems()
        if not selected:
            return
        for item in selected:
            row = self.notes_list.row(item)
            self.notes_list.takeItem(row)
        self._save_notes()
        self._update_notes_actions()

    def _on_note_changed(self, _item: QtWidgets.QListWidgetItem) -> None:
        self._save_notes()

    def _update_notes_actions(self) -> None:
        has_selection = bool(self.notes_list.selectedItems())
        self.delete_note_btn.setEnabled(has_selection)

    def _select_directory(self) -> None:
        cur_path = self.path_edit.text()
        if cur_path and os.path.isdir(cur_path):
            start_dir = cur_path
        else:
            start_dir = ""
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择文件夹路径", start_dir)
        if path:
            self.path_edit.setText(path)
            self._save_last_state(path)
            self._refresh_list(path)

    def _confirm_sort(self) -> None:
        base_path = self.path_edit.text()
        if not os.path.isdir(base_path):
            return
        items = [self.list_widget.item(i) for i in range(self.list_widget.count())]
        rename_plan: list[tuple[str, str]] = []
        used_names: set[str] = set()
        index = 1
        for item in items:
            if self._is_item_reserved(item):
                continue
            folder_name = item.text()
            base_name = re.sub(r"^\d+_?", "", folder_name)
            if not base_name:
                base_name = folder_name
            new_name = f"{index:02d}_{base_name}"
            current_path = os.path.join(base_path, folder_name)
            new_path = os.path.join(base_path, new_name)
            counter = 1
            while (
                new_name in used_names
                or (
                    os.path.exists(new_path)
                    and os.path.normcase(current_path) != os.path.normcase(new_path)
                )
            ):
                new_name = f"{index:02d}_{base_name} ({counter})"
                new_path = os.path.join(base_path, new_name)
                counter += 1
            used_names.add(new_name)
            rename_plan.append((folder_name, new_name))
            index += 1
        for old_name, new_name in rename_plan:
            current_path = os.path.join(base_path, old_name)
            if not os.path.exists(current_path):
                continue
            new_path = os.path.join(base_path, new_name)
            if os.path.normcase(current_path) == os.path.normcase(new_path):
                continue
            try:
                os.rename(current_path, new_path)
            except OSError as exc:
                if self._is_folder_in_use_error(exc):
                    self._show_folder_in_use_warning(old_name)
                else:
                    QtWidgets.QMessageBox.critical(self, "错误", f"重命名“{old_name}”失败：{exc}")
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
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "错误", f"创建文件夹失败：{exc}")

    def _clear_prefix_number(self) -> None:
        base_path = self.path_edit.text()
        if not os.path.isdir(base_path):
            return
        folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
        changed = False
        for old_name in folders:
            if old_name in self._reserved:
                continue
            new_name = re.sub(r"^\d+_?", "", old_name)
            if new_name and new_name != old_name:
                old_path = os.path.join(base_path, old_name)
                new_path = os.path.join(base_path, new_name)
                if os.path.exists(new_path):
                    continue
                try:
                    os.rename(old_path, new_path)
                    changed = True
                except OSError as exc:
                    if self._is_folder_in_use_error(exc):
                        self._show_folder_in_use_warning(old_name)
                    else:
                        QtWidgets.QMessageBox.critical(self, "错误", f"清除序号失败：{exc}")
        if changed:
            self._refresh_list(base_path)

    def _delete_selected_folders(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        names = [item.text() for item in items]
        msg = "确定要删除以下文件夹？\n\n" + "\n".join(names)
        if QtWidgets.QMessageBox.question(
            self, "确认删除", msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        ) != QtWidgets.QMessageBox.Yes:
            return
        base_path = self.path_edit.text()
        if not os.path.isdir(base_path):
            return
        reserved_changed = False
        for name in names:
            folder_path = os.path.join(base_path, name)
            try:
                shutil.rmtree(folder_path)
            except OSError as exc:
                if self._is_folder_in_use_error(exc):
                    self._show_folder_in_use_warning(name)
                else:
                    QtWidgets.QMessageBox.warning(self, "删除失败", f"{name} 删除失败：{exc}")
            except shutil.Error as exc:
                QtWidgets.QMessageBox.warning(self, "删除失败", f"{name} 删除失败：{exc}")
            else:
                if name in self._reserved:
                    self._reserved.remove(name)
                    reserved_changed = True
        if reserved_changed:
            self._save_reserved_state()
        self._refresh_list(base_path)

    def _on_select(self) -> None:
        pass  # 不做任何颜色处理，全部交给QSS

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
        new_name, ok = QtWidgets.QInputDialog.getText(self, "重命名", f"将“{old_name}”重命名为：", text=old_name)
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(base_path, new_name)
            if os.path.exists(new_path):
                QtWidgets.QMessageBox.critical(self, "错误", "已存在同名文件夹！")
                return
            try:
                os.rename(old_path, new_path)
            except OSError as exc:
                if self._is_folder_in_use_error(exc):
                    self._show_folder_in_use_warning(old_name)
                else:
                    QtWidgets.QMessageBox.critical(self, "错误", f"重命名失败：{exc}")
            else:
                if old_name in self._reserved:
                    self._reserved.remove(old_name)
                    self._reserved.add(new_name)
                    self._save_reserved_state()
                self._refresh_list(base_path)

    def _pause_sort(self) -> None:
        self.sort_paused = True
        self._show_blur("rgba(255,105,180,0.10)")

    def _resume_sort(self) -> None:
        self.sort_paused = False
        self._show_blur("rgba(120,255,170,0.10)")
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
        menu.addAction("选择目录", self._select_directory)
        menu.addSeparator()
        selected_items = self.list_widget.selectedItems()
        selected_count = len(selected_items)
        act_rename = menu.addAction("重命名", self._rename_selected_folder)
        act_rename.setEnabled(selected_count == 1)
        act_delete = menu.addAction("删除所选", self._delete_selected_folders)
        act_delete.setEnabled(selected_count >= 1)
        menu.addSeparator()
        reserved_selected = sum(1 for item in selected_items if self._is_item_reserved(item))
        act_mark_reserved = menu.addAction("标记为保留（不排序）", self._mark_selected_as_reserved)
        can_modify_reserved = bool(self._current_path)
        act_mark_reserved.setEnabled(can_modify_reserved and selected_count > reserved_selected)
        act_unmark_reserved = menu.addAction("取消保留", self._unmark_selected_reserved)
        act_unmark_reserved.setEnabled(can_modify_reserved and reserved_selected > 0)
        menu.addSeparator()
        menu.addAction("清除全部序号", self._clear_prefix_number)
        menu.addSeparator()
        if self.sort_paused:
            menu.addAction("开始排序", self._resume_sort)
        else:
            menu.addAction("暂停排序", self._pause_sort)
        menu.setStyleSheet("""
            QMenu { font-size:16px; }
            QMenu::item:selected { background-color: #3794ff; color: #fff; }
        """)
        menu.exec_(self.list_widget.mapToGlobal(pos))

def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = FileManagerApp()
    window.resize(600, 420)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
