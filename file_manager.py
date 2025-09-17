from __future__ import annotations

import errno
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

from PyQt5 import QtCore, QtGui, QtWidgets

CONFIG_FILE = "last_state.json"

NOTE_ROLE = QtCore.Qt.UserRole + 1


class NotesListWidget(QtWidgets.QListWidget):
    tripleClicked = QtCore.pyqtSignal(QtWidgets.QListWidgetItem)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._click_timer = QtCore.QElapsedTimer()
        self._click_count = 0

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            app = QtWidgets.QApplication.instance()
            interval = app.doubleClickInterval() if app is not None else 400
            if not self._click_timer.isValid() or self._click_timer.elapsed() > interval:
                self._click_timer.start()
                self._click_count = 1
            else:
                self._click_count += 1
            item = self.itemAt(event.pos())
            if self._click_count == 3 and item is not None:
                self.tripleClicked.emit(item)
                self._click_count = 0
                self._click_timer.invalidate()
                event.accept()
                return
        else:
            self._click_count = 0
            self._click_timer.invalidate()
        super().mousePressEvent(event)

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
            print(f"Failed to save state: {exc}", file=sys.stderr)

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
        raw_notes = data.get("notes", [])
        normalized_notes: list[dict[str, object]] = []
        if isinstance(raw_notes, list):
            for item in raw_notes:
                if isinstance(item, dict):
                    content = str(item.get("content", "")).strip()
                    if not content:
                        continue
                    timestamp = str(item.get("timestamp", "")).strip()
                    if not timestamp:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                    category = str(item.get("category", "idea"))
                    if category not in {"idea", "todo"}:
                        category = "idea"
                    completed = bool(item.get("completed", False))
                    normalized_notes.append(
                        {
                            "content": content,
                            "timestamp": timestamp,
                            "category": category,
                            "completed": completed,
                        }
                    )
                elif isinstance(item, str):
                    content = item.strip()
                    if content:
                        normalized_notes.append(
                            {
                                "content": content,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "category": "idea",
                                "completed": False,
                            }
                        )
        data["notes"] = normalized_notes
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
            item.setToolTip("Marked as reserved. This folder will be skipped during sorting and renumbering.")
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
            "Folder in use",
            f"The folder “{folder_name}” is currently used by another application. Close related windows or programs and try again.",
        )

    def _setup_ui(self) -> None:
        base_font = QtGui.QFont("Segoe UI", 16)
        self.setFont(base_font)
        self.setStyleSheet("""
            QWidget { background: #eaf1fb; color: #1f2430; }
            QFrame#CardFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,0.96), stop:1 rgba(243,247,255,0.96));
                border-radius: 22px;
                border: 1px solid rgba(164, 180, 207, 0.45);
            }
            QLabel#SectionTitle {
                color: #18233d;
                font-size: 16px;
            }
            QLineEdit {
                border-radius: 14px; padding: 10px 16px;
                border: 1px solid rgba(122, 138, 170, 0.35);
                background: rgba(255,255,255,0.95);
                font-size: 16px;
                min-height: 44px;
            }
            QPushButton {
                border-radius: 16px; background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #6c8cff, stop:1 #4f56ff);
                color: white; padding: 10px 24px;
                font-size: 16px; font-weight: 600;
                min-height: 44px;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #5474ff, stop:1 #3d43f5); }
            QListWidget {
                border-radius: 18px;
                border: 1px solid rgba(152, 167, 196, 0.35);
                background: rgba(255,255,255,0.9); font-size: 16px;
                padding: 6px;
            }
            QListWidget::item {
                height: 40px; border-radius: 14px; padding-left: 12px;
            }
            QListWidget::item:selected:active {
                background: rgba(86, 112, 255, 0.18); color: #1a1f2b;
            }
            QListWidget::item:selected:!active {
                background: rgba(86, 112, 255, 0.12); color: #1a1f2b;
            }
            QListWidget::item:hover {
                background: rgba(120, 140, 255, 0.15);
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 12px;
                margin: 4px;
                border-radius: 10px;
            }
            QScrollBar::handle:vertical {
                background: rgba(76, 107, 255, 0.75);
                min-height: 36px;
                border: none;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(76, 107, 255, 0.95);
            }
        """)
        self.setWindowTitle("Folder Flow Organizer")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(28, 24, 28, 24)

        title = QtWidgets.QLabel("Flow through your folders and ideas")
        title_font = QtGui.QFont(base_font)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        layout.addWidget(title)

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setTabPosition(QtWidgets.QTabWidget.North)
        layout.addWidget(self.tab_widget, 1)

        notes_page = QtWidgets.QWidget()
        notes_page_layout = QtWidgets.QVBoxLayout(notes_page)
        notes_page_layout.setContentsMargins(0, 0, 0, 0)
        notes_page_layout.setSpacing(0)
        notes_card = QtWidgets.QFrame()
        notes_card.setObjectName("CardFrame")
        notes_layout = QtWidgets.QVBoxLayout(notes_card)
        notes_layout.setSpacing(16)
        notes_layout.setContentsMargins(24, 24, 24, 24)

        notes_input_layout = QtWidgets.QHBoxLayout()
        notes_input_layout.setSpacing(12)
        self.note_input = QtWidgets.QLineEdit()
        self.note_input.setPlaceholderText("Write a spark or a task and press Enter")
        self.note_input.returnPressed.connect(self._add_note)
        self.add_note_btn = QtWidgets.QPushButton("Add")
        self.add_note_btn.clicked.connect(self._add_note)
        notes_input_layout.addWidget(self.note_input, 1)
        notes_input_layout.addWidget(self.add_note_btn)
        notes_layout.addLayout(notes_input_layout)

        self.notes_list = NotesListWidget()
        self.notes_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.notes_list.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.notes_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.notes_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.notes_list.itemDoubleClicked.connect(self._toggle_note_completion)
        self.notes_list.tripleClicked.connect(self._handle_note_triple_click)
        self.notes_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.notes_list.customContextMenuRequested.connect(self._show_note_context_menu)
        notes_layout.addWidget(self.notes_list, 1)
        notes_page_layout.addWidget(notes_card, 1)
        self.tab_widget.addTab(notes_page, "Inspiration & To-dos")

        files_page = QtWidgets.QWidget()
        files_page_layout = QtWidgets.QVBoxLayout(files_page)
        files_page_layout.setContentsMargins(0, 0, 0, 0)
        files_page_layout.setSpacing(0)
        files_card = QtWidgets.QFrame()
        files_card.setObjectName("CardFrame")
        file_layout = QtWidgets.QVBoxLayout(files_card)
        file_layout.setSpacing(16)
        file_layout.setContentsMargins(24, 24, 24, 24)

        path_layout = QtWidgets.QHBoxLayout()
        path_layout.setSpacing(12)
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setPlaceholderText("Paste or drop a folder path here")
        self.path_edit.returnPressed.connect(self._on_path_entry)
        self.browse_btn = MyButton("Browse…")
        self.browse_btn.clicked.connect(self._select_directory)
        self.browse_btn.doubleClicked.connect(self._on_browse_double_clicked)
        path_layout.addWidget(self.path_edit, 1)
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
        file_layout.addWidget(self.list_widget, 1)
        files_page_layout.addWidget(files_card, 1)
        self.tab_widget.addTab(files_page, "Folder workspace")

        shadow = QtWidgets.QGraphicsDropShadowEffect(self.list_widget)
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QtGui.QColor(0, 0, 0, 35))
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

    def _normalize_note_data(self, data: dict[str, object]) -> dict[str, object]:
        content = str(data.get("content", "")).strip()
        timestamp = str(data.get("timestamp", "")).strip()
        if not timestamp:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        category = str(data.get("category", "idea"))
        if category not in {"idea", "todo"}:
            category = "idea"
        completed = bool(data.get("completed", False))
        return {
            "content": content,
            "timestamp": timestamp,
            "category": category,
            "completed": completed,
        }

    def _get_note_item_data(self, item: QtWidgets.QListWidgetItem) -> dict[str, object]:
        stored = item.data(NOTE_ROLE)
        if isinstance(stored, dict):
            return self._normalize_note_data(stored)
        return self._normalize_note_data({"content": item.text()})

    def _set_note_item_data(self, item: QtWidgets.QListWidgetItem, data: dict[str, object]) -> None:
        normalized = self._normalize_note_data(data)
        item.setData(NOTE_ROLE, normalized)
        self._apply_note_style(item, normalized)

    def _format_note_text(self, data: dict[str, object]) -> str:
        timestamp = data.get("timestamp", "")
        content = data.get("content", "")
        return f"{timestamp}   {content}".strip()

    def _apply_note_style(self, item: QtWidgets.QListWidgetItem, data: dict[str, object]) -> None:
        item.setText(self._format_note_text(data))
        font = item.font()
        font.setPointSize(self.notes_list.font().pointSize())
        font.setBold(False)
        font.setStrikeOut(bool(data.get("completed", False)))
        item.setFont(font)

        completed = bool(data.get("completed", False))
        category = data.get("category", "idea")
        if completed:
            item.setBackground(QtGui.QColor("#d9dce2"))
            item.setForeground(QtGui.QColor("#666b78"))
        else:
            if category == "todo":
                item.setBackground(QtGui.QColor("#ff6b6b"))
                item.setForeground(QtGui.QColor("#ffffff"))
            else:
                gradient = QtGui.QLinearGradient(0, 0, 1, 1)
                gradient.setCoordinateMode(QtGui.QGradient.ObjectBoundingMode)
                gradient.setColorAt(0.0, QtGui.QColor("#ff6ec7"))
                gradient.setColorAt(0.25, QtGui.QColor("#ffde59"))
                gradient.setColorAt(0.5, QtGui.QColor("#53f3ff"))
                gradient.setColorAt(0.75, QtGui.QColor("#7f6bff"))
                gradient.setColorAt(1.0, QtGui.QColor("#ff6ec7"))
                item.setBackground(QtGui.QBrush(gradient))
                item.setForeground(QtGui.QColor("#ffffff"))

        note_type = "Inspiration" if category == "idea" else "To-do"
        status = "Completed" if completed else "Active"
        item.setToolTip(f"{note_type} · {status}")

    def _toggle_note_completion(self, item: QtWidgets.QListWidgetItem) -> None:
        data = self._get_note_item_data(item)
        data["completed"] = not data.get("completed", False)
        self._set_note_item_data(item, data)
        row = self.notes_list.row(item)
        self.notes_list.takeItem(row)
        if data["completed"]:
            self.notes_list.addItem(item)
        else:
            self.notes_list.insertItem(0, item)
        self.notes_list.setCurrentItem(item)
        self._save_notes()

    def _set_note_category(self, item: QtWidgets.QListWidgetItem, category: str) -> None:
        data = self._get_note_item_data(item)
        if data.get("category") == category:
            return
        data["category"] = category
        self._set_note_item_data(item, data)
        self._save_notes()

    def _show_note_context_menu(self, position: QtCore.QPoint) -> None:
        item = self.notes_list.itemAt(position)
        if item is None:
            return
        data = self._get_note_item_data(item)
        menu = QtWidgets.QMenu(self.notes_list)
        toggle_completion_action = menu.addAction("Toggle completion")
        menu.addSeparator()
        mark_inspiration_action = menu.addAction("Mark as inspiration")
        mark_todo_action = menu.addAction("Mark as to-do")
        if data.get("category") == "idea":
            mark_inspiration_action.setEnabled(False)
        else:
            mark_todo_action.setEnabled(False)
        chosen = menu.exec_(self.notes_list.viewport().mapToGlobal(position))
        if chosen == toggle_completion_action:
            self._toggle_note_completion(item)
        elif chosen == mark_inspiration_action:
            self._set_note_category(item, "idea")
        elif chosen == mark_todo_action:
            self._set_note_category(item, "todo")

    def _handle_note_triple_click(self, item: QtWidgets.QListWidgetItem) -> None:
        row = self.notes_list.row(item)
        if row < 0:
            return
        self.notes_list.takeItem(row)
        self._save_notes()

    def _load_notes_from_state(self) -> None:
        notes = self._state.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        active_notes: list[dict[str, object]] = []
        completed_notes: list[dict[str, object]] = []
        for entry in notes:
            if isinstance(entry, dict):
                normalized = self._normalize_note_data(entry)
                if normalized["completed"]:
                    completed_notes.append(normalized)
                else:
                    active_notes.append(normalized)
        self.notes_list.blockSignals(True)
        self.notes_list.clear()
        for bucket in (active_notes, completed_notes):
            for note in bucket:
                item = QtWidgets.QListWidgetItem()
                item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                self._set_note_item_data(item, note)
                self.notes_list.addItem(item)
        self.notes_list.blockSignals(False)

    def _save_notes(self) -> None:
        notes: list[dict[str, object]] = []
        for index in range(self.notes_list.count()):
            item = self.notes_list.item(index)
            data = self._get_note_item_data(item)
            if data["content"]:
                notes.append(data)
        self._state["notes"] = notes
        self._write_state()

    def _add_note(self) -> None:
        text = self.note_input.text().strip()
        if not text:
            return
        item = QtWidgets.QListWidgetItem()
        item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        note_data = {
            "content": text,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "category": "idea",
            "completed": False,
        }
        self._set_note_item_data(item, note_data)
        self.notes_list.insertItem(0, item)
        self.notes_list.setCurrentItem(item)
        self.note_input.clear()
        self._save_notes()

    def _select_directory(self) -> None:
        cur_path = self.path_edit.text()
        if cur_path and os.path.isdir(cur_path):
            start_dir = cur_path
        else:
            start_dir = ""
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder", start_dir)
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
                    QtWidgets.QMessageBox.critical(
                        self, "Rename failed", f"Could not rename “{old_name}”: {exc}"
                    )
        self._refresh_list(base_path)

    def _create_new_folder(self) -> None:
        base_path = self.path_edit.text()
        folder_name, ok = QtWidgets.QInputDialog.getText(
            self, "Create folder", "Name for the new folder:", text="New folder"
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
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to create folder: {exc}")

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
                        QtWidgets.QMessageBox.critical(
                            self, "Error", f"Failed to clear numbering: {exc}"
                        )
        if changed:
            self._refresh_list(base_path)

    def _delete_selected_folders(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        names = [item.text() for item in items]
        msg = "Delete the following folders?\n\n" + "\n".join(names)
        if QtWidgets.QMessageBox.question(
            self, "Confirm deletion", msg,
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
                    QtWidgets.QMessageBox.warning(
                        self, "Delete failed", f"Could not delete {name}: {exc}"
                    )
            except shutil.Error as exc:
                QtWidgets.QMessageBox.warning(
                    self, "Delete failed", f"Could not delete {name}: {exc}"
                )
            else:
                if name in self._reserved:
                    self._reserved.remove(name)
                    reserved_changed = True
        if reserved_changed:
            self._save_reserved_state()
        self._refresh_list(base_path)

    def _on_select(self) -> None:
        pass  # Colors handled entirely via QSS

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
            self, "Rename folder", f"Rename “{old_name}” to:", text=old_name
        )
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(base_path, new_name)
            if os.path.exists(new_path):
                QtWidgets.QMessageBox.critical(
                    self, "Error", "A folder with that name already exists!"
                )
                return
            try:
                os.rename(old_path, new_path)
            except OSError as exc:
                if self._is_folder_in_use_error(exc):
                    self._show_folder_in_use_warning(old_name)
                else:
                    QtWidgets.QMessageBox.critical(
                        self, "Rename failed", f"Could not rename folder: {exc}"
                    )
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
            QtWidgets.QMessageBox.critical(self, "Error", "Path not found!")

    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        menu.addAction("Create folder", self._create_new_folder)
        menu.addAction("Browse for folder", self._select_directory)
        menu.addSeparator()
        selected_items = self.list_widget.selectedItems()
        selected_count = len(selected_items)
        act_rename = menu.addAction("Rename", self._rename_selected_folder)
        act_rename.setEnabled(selected_count == 1)
        act_delete = menu.addAction("Delete selected", self._delete_selected_folders)
        act_delete.setEnabled(selected_count >= 1)
        menu.addSeparator()
        reserved_selected = sum(1 for item in selected_items if self._is_item_reserved(item))
        act_mark_reserved = menu.addAction(
            "Mark as reserved (skip sorting)", self._mark_selected_as_reserved
        )
        can_modify_reserved = bool(self._current_path)
        act_mark_reserved.setEnabled(can_modify_reserved and selected_count > reserved_selected)
        act_unmark_reserved = menu.addAction("Remove reserved", self._unmark_selected_reserved)
        act_unmark_reserved.setEnabled(can_modify_reserved and reserved_selected > 0)
        menu.addSeparator()
        menu.addAction("Clear numbering", self._clear_prefix_number)
        menu.addSeparator()
        if self.sort_paused:
            menu.addAction("Start sorting", self._resume_sort)
        else:
            menu.addAction("Pause sorting", self._pause_sort)
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
