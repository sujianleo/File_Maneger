from __future__ import annotations

import errno
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

from PyQt6 import QtCore, QtGui, QtWidgets

CONFIG_FILE = "last_state.json"

NOTE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
# UI radius/border configuration - change these to adjust border sizes
CARD_RADIUS = 6
SMALL_RADIUS = 4
CARD_BORDER_WIDTH = 1.0
FIELD_BORDER_WIDTH = 1.0
SCROLLBAR_RADIUS = 4
SCROLLBAR_HANDLE_RADIUS = 4


class NotesListWidget(QtWidgets.QListWidget):
    tripleClicked = QtCore.pyqtSignal(QtWidgets.QListWidgetItem)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._click_timer = QtCore.QElapsedTimer()
        self._click_count = 0

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
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


class NoteWidget(QtWidgets.QWidget):
    """两行文字的便签部件"""
    def __init__(
        self,
        timestamp: str,
        content: str,
        category: str = "idea",
        completed: bool = False,
        pinned: bool = False,
        parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(4)

        self.content_label = QtWidgets.QLabel(content)
        content_font = QtGui.QFont()
        content_font.setPointSize(28)
        content_font.setWeight(QtGui.QFont.Weight.Medium)
        self.content_label.setFont(content_font)
        self.content_label.setWordWrap(True)

        formatted = self._format_timestamp(timestamp)
        self.time_label = QtWidgets.QLabel(formatted)
        time_font = QtGui.QFont()
        time_font.setPointSize(20)
        self.time_label.setFont(time_font)
        self.time_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

        row_layout = QtWidgets.QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        self.content_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        row_layout.addWidget(self.content_label, 1)
        row_layout.addWidget(self.time_label)
        layout.addLayout(row_layout)

        self.update_style(category, completed, pinned)

    def update_style(self, category: str, completed: bool, pinned: bool) -> None:
        if pinned:
            self.setStyleSheet("background: rgba(254,202,202,0.35); border: none; border-radius: 12px;")
        else:
            self.setStyleSheet("background: transparent; border: none;")
        self.time_label.setStyleSheet("color: #94a3b8;")

        if completed:
            self.content_label.setStyleSheet("color: #475569; text-decoration: line-through;")
        else:
            if category == "todo":
                self.content_label.setStyleSheet("color: #111827; font-weight: 600; text-decoration: none;")
            else:  # idea
                self.content_label.setStyleSheet("color: #1f2937; font-weight: 600; text-decoration: none;")

    @staticmethod
    def _format_timestamp(value: str) -> str:
        pattern = r"^\d{4}-(\d{2}-\d{2}\s+\d{2}:\d{2})$"
        match = re.match(pattern, value)
        if match:
            return match.group(1)
        return value


class FileManagerApp(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        # use standard window chrome so OS title bar and native drag/resize work
        flags = (
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.WindowSystemMenuHint
            | QtCore.Qt.WindowType.WindowMinimizeButtonHint
            | QtCore.Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setWindowFlags(flags)
        self.setAcceptDrops(True)
        self.sort_paused = True
        self._state: dict[str, object] = self._load_last_state()
        self._current_path = ""
        self._reserved: set[str] = set()
        # window drag/resize states
        self._drag_position = None
        self._dragging = False
        self._resizing = False
        self._resize_direction = None
        self._resize_start_rect = None
        self._resize_start_pos = None
        # notes single source
        self._notes: list[dict[str, object]] = []
        self._build_ui()
        self._setup_blur_overlay()
        self._load_notes_from_state()

        self._last_folder_list: list[str] = []
        self._watched_path = ""
        self._watcher = QtCore.QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_directory_changed)

        initial_path = self._state.get("last_path", "")
        if initial_path:
            self.path_edit.setText(initial_path)
            if os.path.exists(initial_path):
                self._refresh_list(initial_path)
        # restore window size
        win_w = int(self._state.get("win_width", 0) or 0)
        win_h = int(self._state.get("win_height", 0) or 0)
        if win_w > 0 and win_h > 0:
            self.resize(win_w, win_h)

        # no system tray: run in foreground only
        # force card theme by default (user requested keep card)
        theme = "card"
        self._apply_theme(theme)

    def _setup_blur_overlay(self) -> None:
        parent = self.list_widget.parentWidget()
        self.blur_overlay = QtWidgets.QWidget(parent)
        self._update_blur_geometry()
        self.blur_overlay.lower()
        self.blur_overlay.hide()
        self.blur_overlay.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        blur = QtWidgets.QGraphicsBlurEffect()
        blur.setBlurRadius(16)
        self.blur_overlay.setGraphicsEffect(blur)
        self.list_widget.installEventFilter(self)

    def _update_blur_geometry(self) -> None:
        self.blur_overlay.setGeometry(self.list_widget.geometry())

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.list_widget and event.type() == QtCore.QEvent.Type.Resize:
            self._update_blur_geometry()

        et = event.type()
        if et in (
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.MouseMove,
            QtCore.QEvent.Type.MouseButtonRelease,
        ) and isinstance(event, QtGui.QMouseEvent):
            global_pos = event.globalPos()
            widget = QtWidgets.QApplication.widgetAt(global_pos)
            if widget is None or widget.window() is not self:
                return super().eventFilter(obj, event)

            local_pos = self.mapFromGlobal(global_pos)

            if et == QtCore.QEvent.Type.MouseMove and not (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                direction = self._detect_edge(local_pos)
                if direction is None:
                    try:
                        self.unsetCursor()
                    except Exception:
                        pass
                else:
                    cursor = self._cursor_for_direction(direction)
                    if cursor is not None:
                        try:
                            self.setCursor(cursor)
                        except Exception:
                            pass
                return super().eventFilter(obj, event)

            if et == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
                direction = self._detect_edge(local_pos)
                if direction is not None:
                    self._resizing = True
                    self._resize_direction = direction
                    self._resize_start_rect = self.geometry()
                    self._resize_start_pos = global_pos
                    return True

                child = self.childAt(local_pos)
                interactive_types = (
                    QtWidgets.QPushButton,
                    QtWidgets.QLineEdit,
                    QtWidgets.QListWidget,
                    QtWidgets.QAbstractScrollArea,
                    QtWidgets.QTabWidget,
                    QtWidgets.QTabBar,
                    QtWidgets.QToolButton,
                    QtWidgets.QComboBox,
                    QtWidgets.QSpinBox,
                    QtWidgets.QAbstractButton,
                )
                is_interactive = False
                probe = child
                while probe is not None:
                    if isinstance(probe, interactive_types):
                        is_interactive = True
                        break
                    probe = probe.parentWidget() if hasattr(probe, "parentWidget") else None

                if not is_interactive:
                    self._dragging = True
                    self._drag_position = global_pos - self.frameGeometry().topLeft()
                    return True
                return super().eventFilter(obj, event)

            if et == QtCore.QEvent.Type.MouseMove and (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                if self._resizing and self._resize_start_rect is not None and self._resize_start_pos is not None:
                    self._perform_resize(global_pos)
                    return True
                if not self._resizing:
                    direction = self._detect_edge(local_pos)
                    if direction is not None:
                        self._resizing = True
                        self._resize_direction = direction
                        self._resize_start_rect = self.geometry()
                        self._resize_start_pos = global_pos
                        return True
                if self._dragging and self._drag_position is not None:
                    self.move(event.globalPos() - self._drag_position)
                    return True
                return super().eventFilter(obj, event)

            if et == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
                if self._resizing:
                    self._resizing = False
                    self._resize_direction = None
                    self._resize_start_rect = None
                    self._resize_start_pos = None
                    return True
                if self._dragging:
                    self._dragging = False
                    self._drag_position = None
                    return True

        return super().eventFilter(obj, event)

    def _detect_edge(self, pos: QtCore.QPoint) -> str | None:
        margin = 10
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        left = x <= margin
        right = x >= w - margin
        top = y <= margin
        bottom = y >= h - margin
        if top and left: return "top-left"
        if top and right: return "top-right"
        if bottom and left: return "bottom-left"
        if bottom and right: return "bottom-right"
        if left: return "left"
        if right: return "right"
        if top: return "top"
        if bottom: return "bottom"
        return None

    def _cursor_for_direction(self, dir: str):
        if dir in ("left", "right"):
            return QtGui.QCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        if dir in ("top", "bottom"):
            return QtGui.QCursor(QtCore.Qt.CursorShape.SizeVerCursor)
        if dir in ("top-left", "bottom-right"):
            return QtGui.QCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
        if dir in ("top-right", "bottom-left"):
            return QtGui.QCursor(QtCore.Qt.CursorShape.SizeBDiagCursor)
        return None

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        try:
            pad = 6
            if hasattr(self, '_close_btn'):
                # keep the small close button in the top-left and ensure it's on top
                self._close_btn.move(pad, pad)
                try:
                    self._close_btn.raise_()
                except Exception:
                    pass
        except Exception:
            pass
        return super().resizeEvent(event)

    def _perform_resize(self, global_pos: QtCore.QPoint) -> None:
        if self._resize_start_rect is None or self._resize_start_pos is None or self._resize_direction is None:
            return
        dx = global_pos.x() - self._resize_start_pos.x()
        dy = global_pos.y() - self._resize_start_pos.y()
        rect = self._resize_start_rect
        min_w, min_h = 520, 320
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        dir = self._resize_direction
        new_x, new_y, new_w, new_h = x, y, w, h
        if "left" in dir:
            new_x = x + dx
            new_w = w - dx
        if "right" in dir:
            new_w = w + dx
        if "top" in dir:
            new_y = y + dy
            new_h = h - dy
        if "bottom" in dir:
            new_h = h + dy
        if new_w < min_w:
            if "left" in dir:
                new_x = x + (w - min_w)
            new_w = min_w
        if new_h < min_h:
            if "top" in dir:
                new_y = y + (h - min_h)
            new_h = min_h
        self.setGeometry(new_x, new_y, new_w, new_h)

    def _show_blur(self, color):
        self._update_blur_geometry()
        # ensure overlay is opaque (use solid colors) to avoid showing desktop through the window
        self.blur_overlay.setStyleSheet(f"background: {color}; border-radius: {CARD_RADIUS}px;")
        self.blur_overlay.show()
        self.blur_overlay.raise_()

    def _hide_blur(self):
        self.blur_overlay.hide()

    # ------------------ State I/O ------------------
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
                        {"content": content, "timestamp": timestamp, "category": category, "completed": completed}
                    )
                elif isinstance(item, str):
                    content = item.strip()
                    if content:
                        normalized_notes.append(
                            {"content": content, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                             "category": "idea", "completed": False}
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

    # ------------------ Basic mouse passthrough ------------------
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        return super().mousePressEvent(event)
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        return super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        return super().mouseReleaseEvent(event)
    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        return super().mouseDoubleClickEvent(event)

    # ------------------ Reserved styling helpers ------------------
    def _apply_reserved_style(self, item: QtWidgets.QListWidgetItem, is_reserved: bool) -> None:
        item.setData(QtCore.Qt.ItemDataRole.UserRole, is_reserved)
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
        data = item.data(QtCore.Qt.ItemDataRole.UserRole)
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

    # ------------------ UI setup ------------------
    def _build_ui(self) -> None:
        self._configure_window()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        self._close_btn = QtWidgets.QPushButton(self)
        self._close_btn.setFixedSize(12, 12)
        self._close_btn.setToolTip("Close")
        self._close_btn.setObjectName("MacCloseButton")
        self._close_btn.setFlat(True)
        self._close_btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self._close_btn.clicked.connect(self.close)

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
        layout.addWidget(self.tab_widget, 1)

        self._build_notes_tab()
        self._build_folder_tab()
        self._apply_mac_close_style()

    def _configure_window(self) -> None:
        self.setWindowTitle("Folder Flow Organizer")
        app = QtWidgets.QApplication.instance()
        if app is not None:
            try:
                font = QtGui.QFont()
                font.setPointSize(26)
                if hasattr(font, "setFamilies"):
                    font.setFamilies([
                        "Inter",
                        "Segoe UI",
                        "Microsoft YaHei",
                        "PingFang SC",
                        "Helvetica Neue",
                        "Arial",
                    ])
                else:
                    font.setFamily("Inter")
                app.setFont(font)
            except Exception:
                pass

    def _build_notes_tab(self) -> None:
        notes_page = QtWidgets.QWidget()
        notes_page_layout = QtWidgets.QVBoxLayout(notes_page)
        notes_page_layout.setContentsMargins(0, 0, 0, 0)
        notes_page_layout.setSpacing(8)

        notes_card = QtWidgets.QFrame()
        notes_card.setObjectName("CardFrame")
        notes_layout = QtWidgets.QVBoxLayout(notes_card)
        notes_layout.setSpacing(8)
        notes_layout.setContentsMargins(12, 12, 12, 12)

        notes_input_layout = QtWidgets.QHBoxLayout()
        notes_input_layout.setSpacing(8)
        self.note_input = QtWidgets.QLineEdit()
        self.note_input.setPlaceholderText("Write a spark or a task and press Enter")
        self.note_input.setFixedHeight(72)
        self.note_input.returnPressed.connect(self._add_note)
        notes_input_layout.addWidget(self.note_input, 1)
        notes_layout.addLayout(notes_input_layout)

        self.notes_list = NotesListWidget()
        self.notes_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.notes_list.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.notes_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.notes_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notes_list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        notes_font = QtGui.QFont(self.notes_list.font())
        notes_font.setPointSize(max(26, notes_font.pointSize()))
        self.notes_list.setFont(notes_font)
        self.notes_list.itemDoubleClicked.connect(self._toggle_note_completion)
        self.notes_list.tripleClicked.connect(self._handle_note_triple_click)
        self.notes_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.notes_list.customContextMenuRequested.connect(self._show_note_context_menu)
        notes_layout.addWidget(self.notes_list, 1)

        notes_page_layout.addWidget(notes_card, 1)
        self.tab_widget.addTab(notes_page, "To-dos")

    def _build_folder_tab(self) -> None:
        files_page = QtWidgets.QWidget()
        files_page_layout = QtWidgets.QVBoxLayout(files_page)
        files_page_layout.setContentsMargins(0, 0, 0, 0)
        files_page_layout.setSpacing(8)

        files_card = QtWidgets.QFrame()
        files_card.setObjectName("CardFrame")
        file_layout = QtWidgets.QVBoxLayout(files_card)
        file_layout.setSpacing(8)
        file_layout.setContentsMargins(12, 12, 12, 12)

        path_layout = QtWidgets.QHBoxLayout()
        path_layout.setSpacing(8)
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setPlaceholderText("Paste or drop a folder path here")
        self.path_edit.setFixedHeight(72)
        self.path_edit.returnPressed.connect(self._on_path_entry)
        path_layout.addWidget(self.path_edit, 1)
        file_layout.addLayout(path_layout)

        self.list_widget = SortListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        list_font = QtGui.QFont(self.list_widget.font())
        list_font.setPointSize(max(28, list_font.pointSize()))
        self.list_widget.setFont(list_font)
        self.list_widget.itemDropped.connect(self._on_drop)
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.list_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._open_folder_in_explorer)
        file_layout.addWidget(self.list_widget, 1)

        files_page_layout.addWidget(files_card, 1)
        self.tab_widget.addTab(files_page, "Folder")

    def _apply_mac_close_style(self) -> None:
        shadow = QtWidgets.QGraphicsDropShadowEffect(self.list_widget)
        shadow.setBlurRadius(4)
        shadow.setXOffset(0)
        shadow.setYOffset(1)
        shadow.setColor(QtGui.QColor(0, 0, 0, 12))
        self.list_widget.setGraphicsEffect(shadow)

        current = self.styleSheet()
        mac_close_css = (
            "\n#MacCloseButton { border-radius:6px; background:#ff5f57; border:1px solid rgba(0,0,0,0.08);"
            " width:12px; height:12px; padding:0px; margin:0px; } #MacCloseButton:hover { background:#ff7b6b; }\n"
        )
        if mac_close_css not in current:
            self.setStyleSheet(current + mac_close_css)

    # ------------------ Notes (single source) ------------------
    def _render_notes(self) -> None:
        self.notes_list.blockSignals(True)
        self.notes_list.clear()
        active_notes = [n for n in self._notes if not bool(n.get("completed", False))]
        completed_notes = [n for n in self._notes if bool(n.get("completed", False))]

        active_notes.sort(
            key=lambda n: (
                not bool(n.get("pinned", False)),
                str(n.get("timestamp", "")),
            ),
            reverse=True,
        )
        completed_notes.sort(
            key=lambda n: (
                not bool(n.get("pinned", False)),
                str(n.get("timestamp", "")),
            ),
            reverse=True,
        )

        ordered_notes = active_notes + completed_notes

        for note in ordered_notes:
            item = QtWidgets.QListWidgetItem()
            widget = NoteWidget(
                str(note.get("timestamp", "")),
                str(note.get("content", "")),
                category=str(note.get("category", "idea")),
                completed=bool(note.get("completed", False)),
                pinned=bool(note.get("pinned", False)),
            )
            item.setSizeHint(widget.sizeHint())
            self.notes_list.addItem(item)
            self.notes_list.setItemWidget(item, widget)
        self.notes_list.blockSignals(False)

    def _load_notes_from_state(self) -> None:
        notes = self._state.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        self._notes = []
        for entry in notes:
            if isinstance(entry, dict):
                content = str(entry.get("content", "")).strip()
                if not content:
                    continue
                timestamp = str(entry.get("timestamp", "")).strip()
                if not timestamp:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                category = str(entry.get("category", "idea"))
                if category not in {"idea", "todo"}:
                    category = "idea"
                completed = bool(entry.get("completed", False))
                pinned = bool(entry.get("pinned", False))
                self._notes.append(
                    {
                        "content": content,
                        "timestamp": timestamp,
                        "category": category,
                        "completed": completed,
                        "pinned": pinned,
                    }
                )
            elif isinstance(entry, str):
                content = entry.strip()
                if content:
                    self._notes.append(
                        {
                            "content": content,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "category": "idea",
                            "completed": False,
                            "pinned": False,
                        }
                    )
        self._render_notes()

    def _save_notes(self) -> None:
        self._state["notes"] = self._notes
        self._write_state()

    def _add_note(self) -> None:
        text = self.note_input.text().strip()
        if not text:
            return
        self._add_note_with_text(text)

    def _add_note_with_text(self, text: str, category: str = "idea") -> None:
        self._notes.insert(
            0,
            {
                "content": text.strip(),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "category": category,
                "completed": False,
                "pinned": False,
            },
        )
        self._render_notes()
        self.note_input.clear()
        self._save_notes()

    def _toggle_note_completion(self, item: QtWidgets.QListWidgetItem) -> None:
        row = self.notes_list.row(item)
        if row < 0 or row >= len(self._notes):
            return
        self._notes[row]["completed"] = not self._notes[row]["completed"]
        self._render_notes()
        self._save_notes()

    def _set_note_category(self, item: QtWidgets.QListWidgetItem, category: str) -> None:
        row = self.notes_list.row(item)
        if row < 0 or row >= len(self._notes):
            return
        self._notes[row]["category"] = "todo" if category == "todo" else "idea"
        self._render_notes()
        self._save_notes()

    def _toggle_note_pin(self, item: QtWidgets.QListWidgetItem) -> None:
        row = self.notes_list.row(item)
        if row < 0 or row >= len(self._notes):
            return
        self._notes[row]["pinned"] = not bool(self._notes[row].get("pinned", False))
        self._render_notes()
        self._save_notes()

    def _show_note_context_menu(self, position: QtCore.QPoint) -> None:
        item = self.notes_list.itemAt(position)
        menu = QtWidgets.QMenu(self.notes_list)
        view = self.notes_list.viewport()
        if view is None:
            return

        if item is None:
            return

        data = self._notes[self.notes_list.row(item)]
        toggle_completion_action = menu.addAction("Toggle completion")
        menu.addSeparator()
        mark_inspiration_action = menu.addAction("Mark as inspiration")
        mark_todo_action = menu.addAction("Mark as to-do")
        menu.addSeparator()
        pinned = bool(data.get("pinned", False))
        pin_action = menu.addAction("Unpin" if pinned else "Pin to top")

        chosen = menu.exec(view.mapToGlobal(position))
        if chosen == toggle_completion_action:
            self._toggle_note_completion(item)
        elif chosen == mark_inspiration_action:
            self._set_note_category(item, "idea")
        elif chosen == mark_todo_action:
            self._set_note_category(item, "todo")
        elif chosen == pin_action:
            self._toggle_note_pin(item)

    def _handle_note_triple_click(self, item: QtWidgets.QListWidgetItem) -> None:
        row = self.notes_list.row(item)
        if row < 0 or row >= len(self._notes):
            return
        del self._notes[row]
        self._render_notes()
        self._save_notes()

    def _update_directory_watch(self, path: str) -> None:
        if path == self._watched_path:
            return
        if self._watched_path:
            try:
                self._watcher.removePath(self._watched_path)
            except Exception:
                pass
            self._watched_path = ""
        if os.path.isdir(path):
            try:
                added = self._watcher.addPath(path)
            except Exception:
                added = []
            if added:
                self._watched_path = path

    def _on_directory_changed(self, path: str) -> None:
        if path != self._current_path:
            return
        QtCore.QTimer.singleShot(0, lambda: self._refresh_list(path))

    # ------------------ Folder list ------------------
    def _refresh_list(self, base_path: str) -> None:
        try:
            with os.scandir(base_path) as entries:
                folders = sorted(entry.name for entry in entries if entry.is_dir())
        except OSError:
            folders = []

        if base_path == self._current_path and folders == self._last_folder_list:
            return

        self._update_directory_watch(base_path)

        reserved_dict = self._get_reserved_dict()
        stored_reserved = set(reserved_dict.get(base_path, []))
        actual_reserved = stored_reserved & set(folders)
        self._current_path = base_path
        self._reserved = actual_reserved
        if actual_reserved != stored_reserved:
            self._save_reserved_state()

        selected_names = {item.text() for item in self.list_widget.selectedItems()}
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        for folder in folders:
            item = QtWidgets.QListWidgetItem(folder)
            self._apply_reserved_style(item, folder in self._reserved)
            self.list_widget.addItem(item)
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.text() in selected_names:
                item.setSelected(True)

        self.list_widget.blockSignals(False)

        n = len(folders)
        if n:
            row_h = self.list_widget.sizeHintForRow(0)
            if row_h <= 0:
                row_h = 64
            list_h = max(480, min(n, 30) * row_h + 4)
            self.list_widget.setMinimumHeight(list_h)
        else:
            # keep a comfortable baseline height so the layout doesn't collapse when empty
            self.list_widget.setMinimumHeight(480)
        self.list_widget.updateGeometry()
        self._last_folder_list = folders

    # ------------------ Folder actions ------------------
    def _select_directory(self) -> None:
        cur_path = self.path_edit.text()
        start_dir = cur_path if cur_path and os.path.isdir(cur_path) else ""
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
        try:
            with os.scandir(base_path) as entries:
                existing_norm = {os.path.normcase(entry.name) for entry in entries if entry.is_dir()}
        except OSError:
            existing_norm = set()

        index = 1
        for item in items:
            if self._is_item_reserved(item):
                continue
            folder_name = item.text()
            base_name = re.sub(r"^\d+_?", "", folder_name) or folder_name
            new_name = f"{index:02d}_{base_name}"
            current_norm = os.path.normcase(folder_name)
            counter = 1
            while True:
                new_norm = os.path.normcase(new_name)
                if new_name not in used_names and (new_norm == current_norm or new_norm not in existing_norm):
                    break
                new_name = f"{index:02d}_{base_name} ({counter})"
                counter += 1
            used_names.add(new_name)
            existing_norm.add(os.path.normcase(new_name))
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
                    QtWidgets.QMessageBox.critical(self, "Rename failed", f"Could not rename “{old_name}”: {exc}")
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
        try:
            with os.scandir(base_path) as entries:
                folders = [entry.name for entry in entries if entry.is_dir()]
        except OSError:
            return

        existing_norm = {os.path.normcase(name) for name in folders}
        changed = False
        for old_name in folders:
            if old_name in self._reserved:
                continue
            new_name = re.sub(r"^\d+_?", "", old_name)
            if not new_name or new_name == old_name:
                continue
            old_norm = os.path.normcase(old_name)
            new_norm = os.path.normcase(new_name)
            if new_norm in existing_norm and new_norm != old_norm:
                continue
            old_path = os.path.join(base_path, old_name)
            new_path = os.path.join(base_path, new_name)
            try:
                os.rename(old_path, new_path)
            except OSError as exc:
                if self._is_folder_in_use_error(exc):
                    self._show_folder_in_use_warning(old_name)
                else:
                    QtWidgets.QMessageBox.critical(self, "Error", f"Failed to clear numbering: {exc}")
            else:
                existing_norm.discard(old_norm)
                existing_norm.add(new_norm)
                changed = True
        if changed:
            self._refresh_list(base_path)

    def _delete_selected_folders(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        names = [item.text() for item in items]
        msg = "Delete the following folders?\n\n" + "\n".join(names)
        if (
            QtWidgets.QMessageBox.question(
                self,
                "Confirm deletion",
                msg,
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
            )
            != QtWidgets.QMessageBox.StandardButton.Yes
        ):
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
            else:
                if name in self._reserved:
                    self._reserved.remove(name)
                    reserved_changed = True
        if reserved_changed:
            self._save_reserved_state()
        self._refresh_list(base_path)

    def _on_select(self) -> None:
        pass

    def _open_folder_in_explorer(self, item: QtWidgets.QListWidgetItem) -> None:
        if item is None:
            return
        folder_name = item.text()
        base_path = self.path_edit.text()
        folder_path = os.path.join(base_path, folder_name)
        if os.path.exists(folder_path):
            try:
                if sys.platform.startswith("win"):
                    os.startfile(folder_path)
                elif sys.platform.startswith("darwin"):
                    subprocess.Popen(["open", folder_path])
                else:
                    subprocess.Popen(["xdg-open", folder_path])
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Open failed", f"Could not open folder: {exc}")

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

    # ------------------ Sort control ------------------
    def _pause_sort(self) -> None:
        self.sort_paused = True
        # use a subtle solid tint instead of a semi-transparent color
        self._show_blur("#fff0f6")

    def _resume_sort(self) -> None:
        self.sort_paused = False
        # use a subtle solid tint instead of a semi-transparent color
        self._show_blur("#f0fff4")
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
        menu.addAction("Paste and open folder", self._paste_and_open_folder)
        menu.addSeparator()
        selected_items = self.list_widget.selectedItems()
        selected_count = len(selected_items)
        act_rename = menu.addAction("Rename", self._rename_selected_folder)
        act_rename.setEnabled(selected_count == 1)
        act_delete = menu.addAction("Delete selected", self._delete_selected_folders)
        if act_delete is not None:
            act_delete.setEnabled(selected_count >= 1)
        menu.addSeparator()
        reserved_selected = sum(1 for item in selected_items if self._is_item_reserved(item))
        act_mark_reserved = menu.addAction(
            "Mark as reserved (skip sorting)", self._mark_selected_as_reserved
        )
        can_modify_reserved = bool(self._current_path)
        if act_mark_reserved is not None:
            act_mark_reserved.setEnabled(can_modify_reserved and selected_count > reserved_selected)
        act_unmark_reserved = menu.addAction("Remove reserved", self._unmark_selected_reserved)
        if act_unmark_reserved is not None:
            act_unmark_reserved.setEnabled(can_modify_reserved and reserved_selected > 0)
        menu.addSeparator()
        menu.addAction("Clear numbering", self._clear_prefix_number)
        menu.addSeparator()
        if self.sort_paused:
            menu.addAction("Start sorting", self._resume_sort)
        else:
            menu.addAction("Pause sorting", self._pause_sort)
        menu.setStyleSheet("""
            QMenu { font-size:30px; }
            QMenu::item:selected { background-color: #3794ff; color: #fff; }
        """)
        menu.exec(self.list_widget.mapToGlobal(pos))

    def _paste_and_open_folder(self) -> None:
        clipboard = QtWidgets.QApplication.clipboard()
        clip = clipboard.text().strip() if clipboard is not None else ""
        if not clip:
            QtWidgets.QMessageBox.information(self, "Paste folder", "Clipboard is empty.")
            return
        if os.path.isdir(clip):
            self.path_edit.setText(clip)
            self._save_last_state(clip)
            self._refresh_list(clip)
            try:
                if sys.platform.startswith("win"):
                    os.startfile(clip)
                elif sys.platform.startswith("darwin"):
                    subprocess.Popen(["open", clip])
                else:
                    subprocess.Popen(["xdg-open", clip])
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Open failed", f"Could not open folder: {exc}")
        else:
            QtWidgets.QMessageBox.warning(self, "Invalid folder", "Clipboard does not contain a valid folder path.")

    # ------------------ Tray ------------------
    # removed system tray and background behavior — app runs in foreground only

    # ------------------ Theme: beautified baseline + overrides ------------------
    def _apply_theme(self, theme: str) -> None:
        self._current_theme = theme

        base_css = f"""
            QWidget {{
                background: #f4f5f7;
                color: #1f2937;
                font-family: "Inter", "Segoe UI", "Microsoft YaHei", "PingFang SC", "Helvetica Neue", sans-serif;
                font-size: 30px;
            }}
            QLineEdit {{
                border-radius: {SMALL_RADIUS}px;
                padding: 12px 20px;
                border: 1px solid #d1d5db;
                background: #ffffff;
                font-size: 32px;
            }}
            QFrame#CardFrame {{
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: {CARD_RADIUS}px;
            }}
            QPushButton {{
                border-radius: {SMALL_RADIUS}px;
                background: #4f46e5;
                color: #ffffff;
                padding: 12px 28px;
                font-size: 30px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #4338ca; }}
            QPushButton:pressed {{ background: #3730a3; }}
            QListWidget {{
                border-radius: {CARD_RADIUS}px;
                border: 1px solid #e5e7eb;
                background: #ffffff;
                font-size: 30px;
                padding: 12px;
            }}
            QListWidget::item:hover {{
                background: #eef2ff;
                border-radius: 16px;
            }}
            QListWidget::item:selected {{
                background: #e0e7ff;
                color: #1f2937;
                border-radius: 16px;
            }}
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                background: transparent;
                padding: 12px 28px;
                margin: 4px;
                border-radius: 16px;
                color: #6b7280;
                font-weight: 600;
            }}
            QTabBar::tab:selected {{
                background: #4f46e5;
                color: #ffffff;
            }}
            #MacCloseButton {{ border-radius:7px; background:#ef4444; border:1px solid rgba(0,0,0,0.08); }}
            #MacCloseButton:hover {{ background:#dc2626; }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 16px;
                margin: 4px;
                border-radius: {SCROLLBAR_RADIUS}px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(79,70,229,0.75);
                min-height: 72px;
                border: none;
                border-radius: {SCROLLBAR_HANDLE_RADIUS}px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(67,56,202,0.95);
            }}
        """

        if theme == "dark":
            extra = """
                QWidget { background: #1e1e1e; color: #d4d4d4; }
                QLineEdit { background: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; }
                QFrame#CardFrame { background: #2d2d2d; border: 1px solid #3c3c3c; }
                QListWidget { background: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; }
                QPushButton { background: #569cd6; }
                QPushButton:hover { background: #3794ff; }
                QTabBar::tab { color: #9aa0a6; }
                QTabBar::tab:selected { background: #569cd6; color: #ffffff; }
                QScrollBar::handle:vertical { background: rgba(86,156,214,0.8); }
                QScrollBar::handle:vertical:hover { background: rgba(55,148,255,0.95); }
            """
        elif theme == "card":
            extra = f"""
                QFrame#CardFrame {{
                    background: rgba(255,255,255,0.85);
                    border: 1px solid rgba(0,0,0,0.08);
                    border-radius: {CARD_RADIUS}px;
                }}
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #f1f5f9);
                    color: #1e293b;
                    border: 1px solid #e2e8f0;
                }}
                QPushButton:hover {{ background: #e2e8f0; }}
            """
        else:
            extra = ""

        self.setStyleSheet(base_css + extra)
        self._state["theme"] = theme
        self._write_state()
        # combobox removed; nothing to sync

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # save and exit (no background/tray behavior)
        self._state["win_width"] = self.width()
        self._state["win_height"] = self.height()
        self._write_state()
        event.accept()
        QtWidgets.QApplication.quit()


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = FileManagerApp()
    window.resize(800, 560)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
