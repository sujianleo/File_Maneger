from __future__ import annotations

import errno
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from functools import partial

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

DEFAULT_FONT_BASE = 30
MIN_FONT_BASE = 20
MAX_FONT_BASE = 48


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


class NoteWidget(QtWidgets.QFrame):
    """Compact note widget with fixed timestamp placement."""

    doubleClicked = QtCore.pyqtSignal()
    tripleClicked = QtCore.pyqtSignal()

    def __init__(
        self,
        timestamp: str,
        content: str,
        category: str = "idea",
        completed: bool = False,
        pinned: bool = False,
        parent: QtWidgets.QWidget | None = None,
        *,
        content_size: int = 28,
        time_size: int = 20,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("NoteItemFrame")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        self._layout = layout

        self.content_label = QtWidgets.QLabel(content)
        self.content_label.setWordWrap(True)
        self.content_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.content_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.content_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
        )

        formatted = self._format_timestamp(timestamp)
        self.time_label = QtWidgets.QLabel(formatted)
        self.time_label.setObjectName("NoteTimestampLabel")
        self.time_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.time_label.setFixedWidth(116)
        self.time_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.time_label.setWordWrap(False)
        self.time_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.NoTextInteraction
        )
        self.time_label.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.PreventContextMenu
        )

        layout.addWidget(self.content_label, 1)
        layout.addWidget(self.time_label, 0)
        layout.setStretch(0, 1)

        self.set_font_sizes(content_size, time_size)
        self.update_style(category, completed, pinned)

        self._click_timer = QtCore.QElapsedTimer()
        self._click_count = 0
        self.installEventFilter(self)
        self.content_label.installEventFilter(self)
        self.time_label.installEventFilter(self)

    def set_font_sizes(self, content_size: int, time_size: int) -> None:
        content_font = QtGui.QFont(self.content_label.font())
        content_font.setPointSize(max(1, content_size))
        content_font.setWeight(QtGui.QFont.Weight.Medium)
        self.content_label.setFont(content_font)
        self.content_label.adjustSize()

        time_font = QtGui.QFont(self.time_label.font())
        time_font.setPointSize(max(1, time_size))
        self.time_label.setFont(time_font)
        self.time_label.adjustSize()

        metrics = QtGui.QFontMetrics(time_font)
        timestamp_width = metrics.horizontalAdvance("12-31 23:59") + 12
        self.time_label.setFixedWidth(timestamp_width)

        margin_h = max(8, int(round(content_size * 0.35)))
        margin_v = max(6, int(round(content_size * 0.28)))
        spacing = max(8, int(round(content_size * 0.32)))
        if self._layout is not None:
            self._layout.setContentsMargins(margin_h, margin_v, margin_h, margin_v)
            self._layout.setSpacing(spacing)
            self._layout.activate()

        self.updateGeometry()

    def update_style(self, category: str, completed: bool, pinned: bool) -> None:
        self.setProperty("pinned", bool(pinned))
        self.setProperty("completed", bool(completed))
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if isinstance(event, QtGui.QMouseEvent):
            et = event.type()
            if et == QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self._register_click()
                else:
                    self._reset_click_state()
            elif et == QtCore.QEvent.Type.MouseButtonRelease:
                if event.button() != QtCore.Qt.MouseButton.LeftButton:
                    self._reset_click_state()
        return super().eventFilter(obj, event)

    def _register_click(self) -> None:
        app = QtWidgets.QApplication.instance()
        interval = app.doubleClickInterval() if app is not None else 400
        if not self._click_timer.isValid() or self._click_timer.elapsed() > interval:
            self._click_timer.start()
            self._click_count = 1
            return
        self._click_count += 1
        if self._click_count == 2:
            self.doubleClicked.emit()
        elif self._click_count >= 3:
            self.tripleClicked.emit()
            self._reset_click_state()

    def _reset_click_state(self) -> None:
        self._click_count = 0
        if self._click_timer.isValid():
            self._click_timer.invalidate()

        if completed:
            self.content_label.setStyleSheet(
                "color: #475569; text-decoration: line-through; font-weight: 500;"
            )
        elif category == "todo":
            self.content_label.setStyleSheet(
                "color: #0f172a; font-weight: 600; text-decoration: none;"
            )
        else:
            self.content_label.setStyleSheet(
                "color: #1f2937; font-weight: 600; text-decoration: none;"
            )

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
            | QtCore.Qt.WindowType.WindowCloseButtonHint
            | QtCore.Qt.WindowType.WindowMinimizeButtonHint
            | QtCore.Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setWindowFlags(flags)
        self.setAcceptDrops(True)
        self.sort_paused = True
        self._state: dict[str, object] = self._load_last_state()
        base_font = int(self._state.get("font_base", DEFAULT_FONT_BASE) or DEFAULT_FONT_BASE)
        self._font_sizes = self._compute_font_sizes(base_font)
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
        self._apply_font_settings(save_state=False)

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

    # ------------------ Font helpers ------------------
    def _compute_font_sizes(self, base: int) -> dict[str, int]:
        base_int = max(MIN_FONT_BASE, min(MAX_FONT_BASE, int(base)))
        return {
            "base": base_int,
            "input": max(14, base_int + 2),
            "button": max(14, base_int),
            "list": max(14, base_int),
            "note_content": max(12, base_int - 2),
            "note_time": max(10, base_int - 10),
            "menu": max(12, base_int - 2),
            "note_spacing": max(2, int(round(base_int * 0.15))),
        }

    def _calculate_field_height(self) -> int:
        return max(48, int(round(self._font_sizes["input"] * 2.4)))

    def _calculate_scroll_handle_height(self) -> int:
        return max(48, int(round(self._font_sizes["base"] * 2.0)))

    def _apply_font_settings(self, *, save_state: bool = True) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            try:
                font = QtGui.QFont(app.font())
                font.setPointSize(self._font_sizes["base"])
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

        if hasattr(self, "note_input"):
            try:
                input_font = QtGui.QFont(self.note_input.font())
                input_font.setPointSize(self._font_sizes["input"])
                self.note_input.setFont(input_font)
                self.note_input.setFixedHeight(self._calculate_field_height())
            except Exception:
                pass

        if hasattr(self, "path_edit"):
            try:
                path_font = QtGui.QFont(self.path_edit.font())
                path_font.setPointSize(self._font_sizes["input"])
                self.path_edit.setFont(path_font)
                self.path_edit.setFixedHeight(self._calculate_field_height())
            except Exception:
                pass

        if hasattr(self, "notes_list"):
            try:
                notes_font = QtGui.QFont(self.notes_list.font())
                notes_font.setPointSize(self._font_sizes["note_content"])
                self.notes_list.setFont(notes_font)
                self.notes_list.setSpacing(self._font_sizes["note_spacing"])
                self._update_note_item_fonts()
            except Exception:
                pass

        if hasattr(self, "list_widget"):
            try:
                list_font = QtGui.QFont(self.list_widget.font())
                list_font.setPointSize(self._font_sizes["list"])
                self.list_widget.setFont(list_font)
                for row in range(self.list_widget.count()):
                    item = self.list_widget.item(row)
                    if item is not None:
                        item.setFont(QtGui.QFont(list_font))
                self._update_folder_list_metrics()
            except Exception:
                pass

        if hasattr(self, "tab_widget"):
            try:
                tab_font = QtGui.QFont(self.tab_widget.font())
                tab_font.setPointSize(self._font_sizes["button"])
                self.tab_widget.setFont(tab_font)
            except Exception:
                pass

        try:
            self.setStyleSheet(self._get_stylesheet())
        except Exception:
            pass

        layout = self.layout()
        if layout is not None:
            try:
                layout.activate()
            except Exception:
                pass
        self.updateGeometry()

        if save_state:
            self._state["font_base"] = self._font_sizes["base"]
            self._write_state()

        if hasattr(self, "notes_list") and hasattr(self, "_notes"):
            self._render_notes()

    def _update_note_item_fonts(self) -> None:
        if not hasattr(self, "notes_list"):
            return
        for row in range(self.notes_list.count()):
            item = self.notes_list.item(row)
            widget = self.notes_list.itemWidget(item)
            if isinstance(widget, NoteWidget):
                widget.set_font_sizes(
                    self._font_sizes["note_content"],
                    self._font_sizes["note_time"],
                )
                widget.adjustSize()
                item.setSizeHint(widget.sizeHint())
        self.notes_list.updateGeometry()

    def _update_folder_list_metrics(self) -> None:
        if not hasattr(self, "list_widget"):
            return
        count = self.list_widget.count()
        if count:
            row_h = self.list_widget.sizeHintForRow(0)
            if row_h <= 0:
                row_h = max(48, int(round(self._font_sizes["list"] * 2.2)))
            list_h = max(480, min(count, 30) * row_h + 4)
            self.list_widget.setMinimumHeight(list_h)
        else:
            self.list_widget.setMinimumHeight(480)
        self.list_widget.updateGeometry()

    def _apply_menu_style(self, menu: QtWidgets.QMenu) -> None:
        if menu is None:
            return
        menu.setStyleSheet(
            f"""
            QMenu {{ font-size:{self._font_sizes['menu']}px; }}
            QMenu::item:selected {{ background-color: #3794ff; color: #fff; }}
            """
        )

    def _change_font_size(self, delta: int) -> None:
        new_base = max(
            MIN_FONT_BASE,
            min(MAX_FONT_BASE, self._font_sizes["base"] + int(delta)),
        )
        if new_base == self._font_sizes["base"]:
            return
        self._font_sizes = self._compute_font_sizes(new_base)
        self._apply_font_settings()

    def _reset_font_size(self) -> None:
        if self._font_sizes["base"] == DEFAULT_FONT_BASE:
            return
        self._font_sizes = self._compute_font_sizes(DEFAULT_FONT_BASE)
        self._apply_font_settings()

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
            return {
                "last_path": "",
                "reserved": {},
                "notes": [],
                "font_base": DEFAULT_FONT_BASE,
            }
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {
                "last_path": "",
                "reserved": {},
                "notes": [],
                "font_base": DEFAULT_FONT_BASE,
            }
        if not isinstance(data, dict):
            return {
                "last_path": "",
                "reserved": {},
                "notes": [],
                "font_base": DEFAULT_FONT_BASE,
            }
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
        font_base = data.get("font_base", DEFAULT_FONT_BASE)
        try:
            font_base = int(font_base)
        except (TypeError, ValueError):
            font_base = DEFAULT_FONT_BASE
        font_base = max(MIN_FONT_BASE, min(MAX_FONT_BASE, font_base))
        data["font_base"] = font_base
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

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
        layout.addWidget(self.tab_widget, 1)

        self._build_notes_tab()
        self._build_folder_tab()
        self._apply_list_shadow()

    def _configure_window(self) -> None:
        self.setWindowTitle("Folder Flow Organizer")
        app = QtWidgets.QApplication.instance()
        if app is not None:
            try:
                font = QtGui.QFont(app.font())
                font.setPointSize(self._font_sizes["base"])
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
        notes_page_layout.setSpacing(6)

        notes_card = QtWidgets.QFrame()
        notes_card.setObjectName("CardFrame")
        notes_layout = QtWidgets.QVBoxLayout(notes_card)
        notes_layout.setSpacing(6)
        notes_layout.setContentsMargins(10, 10, 10, 10)

        notes_input_layout = QtWidgets.QHBoxLayout()
        notes_input_layout.setSpacing(8)
        self.note_input = QtWidgets.QLineEdit()
        self.note_input.setPlaceholderText("Write a spark or a task and press Enter")
        self.note_input.setFixedHeight(self._calculate_field_height())
        note_input_font = QtGui.QFont(self.note_input.font())
        note_input_font.setPointSize(self._font_sizes["input"])
        self.note_input.setFont(note_input_font)
        self.note_input.returnPressed.connect(self._add_note)
        notes_input_layout.addWidget(self.note_input, 1)
        notes_layout.addLayout(notes_input_layout)

        self.notes_list = QtWidgets.QListWidget()
        self.notes_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.notes_list.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.notes_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.notes_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notes_list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notes_list.setSpacing(self._font_sizes.get("note_spacing", 4))
        notes_font = QtGui.QFont(self.notes_list.font())
        notes_font.setPointSize(self._font_sizes["note_content"])
        self.notes_list.setFont(notes_font)
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
        self.path_edit.setFixedHeight(self._calculate_field_height())
        path_font = QtGui.QFont(self.path_edit.font())
        path_font.setPointSize(self._font_sizes["input"])
        self.path_edit.setFont(path_font)
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
        list_font.setPointSize(self._font_sizes["list"])
        self.list_widget.setFont(list_font)
        self.list_widget.itemDropped.connect(self._on_drop)
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.list_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._open_folder_in_explorer)
        file_layout.addWidget(self.list_widget, 1)

        files_page_layout.addWidget(files_card, 1)
        self.tab_widget.addTab(files_page, "Folder")

    def _apply_list_shadow(self) -> None:
        shadow = QtWidgets.QGraphicsDropShadowEffect(self.list_widget)
        shadow.setBlurRadius(4)
        shadow.setXOffset(0)
        shadow.setYOffset(1)
        shadow.setColor(QtGui.QColor(0, 0, 0, 12))
        self.list_widget.setGraphicsEffect(shadow)

    # ------------------ Notes (single source) ------------------
    def _render_notes(self) -> None:
        self.notes_list.blockSignals(True)
        self.notes_list.clear()
        active_notes = [n for n in self._notes if not bool(n.get("completed", False))]
        completed_notes = [n for n in self._notes if bool(n.get("completed", False))]

        def sort_key(note: dict[str, object]) -> tuple[int, str]:
            return (
                1 if bool(note.get("pinned", False)) else 0,
                str(note.get("timestamp", "")),
            )

        active_notes.sort(key=sort_key, reverse=True)
        completed_notes.sort(key=sort_key, reverse=True)

        ordered_notes = active_notes + completed_notes

        for note in ordered_notes:
            item = QtWidgets.QListWidgetItem()
            widget = NoteWidget(
                str(note.get("timestamp", "")),
                str(note.get("content", "")),
                category=str(note.get("category", "idea")),
                completed=bool(note.get("completed", False)),
                pinned=bool(note.get("pinned", False)),
                content_size=self._font_sizes["note_content"],
                time_size=self._font_sizes["note_time"],
            )
            item.setData(NOTE_ROLE, note)
            widget.doubleClicked.connect(partial(self._handle_note_item_double_click, item))
            widget.tripleClicked.connect(partial(self._handle_note_triple_click, item))
            widget.adjustSize()
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

    def _handle_note_item_double_click(self, item: QtWidgets.QListWidgetItem) -> None:
        if item is not None:
            self._toggle_note_completion(item)

    def _toggle_note_completion(self, item: QtWidgets.QListWidgetItem) -> None:
        if item is None:
            return
        note = item.data(NOTE_ROLE)
        if not isinstance(note, dict):
            return
        note["completed"] = not bool(note.get("completed", False))
        self._render_notes()
        self._save_notes()

    def _set_note_category(self, item: QtWidgets.QListWidgetItem, category: str) -> None:
        if item is None:
            return
        note = item.data(NOTE_ROLE)
        if not isinstance(note, dict):
            return
        note["category"] = "todo" if category == "todo" else "idea"
        self._render_notes()
        self._save_notes()

    def _toggle_note_pin(self, item: QtWidgets.QListWidgetItem) -> None:
        if item is None:
            return
        note = item.data(NOTE_ROLE)
        if not isinstance(note, dict):
            return
        note["pinned"] = not bool(note.get("pinned", False))
        self._render_notes()
        self._save_notes()

    def _show_note_context_menu(self, position: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self.notes_list)
        view = self.notes_list.viewport()
        if view is None:
            return

        item = self.notes_list.itemAt(position)
        toggle_completion_action = None
        mark_inspiration_action = None
        mark_todo_action = None
        pin_action = None
        if item is not None:
            note = item.data(NOTE_ROLE)
            if isinstance(note, dict):
                toggle_completion_action = menu.addAction("Toggle completion")
                menu.addSeparator()
                mark_inspiration_action = menu.addAction("Mark as inspiration")
                mark_todo_action = menu.addAction("Mark as to-do")
                menu.addSeparator()
                pinned = bool(note.get("pinned", False))
                pin_action = menu.addAction("Unpin" if pinned else "Pin to top")
                menu.addSeparator()

        increase_font_action = menu.addAction("Increase font size")
        decrease_font_action = menu.addAction("Decrease font size")
        reset_font_action = menu.addAction("Reset font size")
        increase_font_action.setEnabled(self._font_sizes["base"] < MAX_FONT_BASE)
        decrease_font_action.setEnabled(self._font_sizes["base"] > MIN_FONT_BASE)
        reset_font_action.setEnabled(self._font_sizes["base"] != DEFAULT_FONT_BASE)

        self._apply_menu_style(menu)
        chosen = menu.exec(view.mapToGlobal(position))
        if chosen == increase_font_action:
            self._change_font_size(2)
            return
        if chosen == decrease_font_action:
            self._change_font_size(-2)
            return
        if chosen == reset_font_action:
            self._reset_font_size()
            return
        if item is None or chosen is None:
            return
        if chosen == toggle_completion_action:
            self._toggle_note_completion(item)
        elif chosen == mark_inspiration_action:
            self._set_note_category(item, "idea")
        elif chosen == mark_todo_action:
            self._set_note_category(item, "todo")
        elif chosen == pin_action:
            self._toggle_note_pin(item)

    def _handle_note_triple_click(self, item: QtWidgets.QListWidgetItem) -> None:
        if item is None:
            return
        note = item.data(NOTE_ROLE)
        if not isinstance(note, dict):
            return
        try:
            self._notes.remove(note)
        except ValueError:
            return
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
            item.setFont(QtGui.QFont(self.list_widget.font()))
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
        menu.addSeparator()
        increase_font_action = menu.addAction("Increase font size", lambda: self._change_font_size(2))
        decrease_font_action = menu.addAction("Decrease font size", lambda: self._change_font_size(-2))
        reset_font_action = menu.addAction("Reset font size", self._reset_font_size)
        increase_font_action.setEnabled(self._font_sizes["base"] < MAX_FONT_BASE)
        decrease_font_action.setEnabled(self._font_sizes["base"] > MIN_FONT_BASE)
        reset_font_action.setEnabled(self._font_sizes["base"] != DEFAULT_FONT_BASE)
        self._apply_menu_style(menu)
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
    def _get_stylesheet(self, theme: str | None = None) -> str:
        if theme is None:
            theme = getattr(self, "_current_theme", "card")
        scroll_handle = self._calculate_scroll_handle_height()
        base_css = f"""
            QWidget {{
                background: #f4f5f7;
                color: #1f2937;
                font-family: "Inter", "Segoe UI", "Microsoft YaHei", "PingFang SC", "Helvetica Neue", sans-serif;
                font-size: {self._font_sizes['base']}px;
            }}
            QLineEdit {{
                border-radius: {SMALL_RADIUS}px;
                padding: 12px 20px;
                border: 1px solid #d1d5db;
                background: #ffffff;
                font-size: {self._font_sizes['input']}px;
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
                font-size: {self._font_sizes['button']}px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #4338ca; }}
            QPushButton:pressed {{ background: #3730a3; }}
            QListWidget {{
                border-radius: {CARD_RADIUS}px;
                border: 1px solid #e5e7eb;
                background: #ffffff;
                font-size: {self._font_sizes['list']}px;
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
            QFrame#NoteItemFrame {{
                background: rgba(255,255,255,0.92);
                border: 1px solid rgba(148,163,184,0.35);
                border-radius: {CARD_RADIUS}px;
            }}
            QFrame#NoteItemFrame[pinned="true"] {{
                background: rgba(255,255,255,0.98);
                border: 1px solid rgba(79,70,229,0.35);
                border-left: 4px solid #f97316;
            }}
            QFrame#NoteItemFrame QLabel {{ background: transparent; }}
            QLabel#NoteTimestampLabel {{
                color: #64748b;
                font-weight: 600;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 16px;
                margin: 4px;
                border-radius: {SCROLLBAR_RADIUS}px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(79,70,229,0.75);
                min-height: {scroll_handle}px;
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
                QFrame#NoteItemFrame { background: #2d2d2d; border: 1px solid #3c3c3c; }
                QFrame#NoteItemFrame[pinned="true"] { border: 1px solid #4c1d95; border-left: 4px solid #f97316; }
                QLabel#NoteTimestampLabel { color: #94a3b8; }
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

        return base_css + extra

    def _apply_theme(self, theme: str) -> None:
        self._current_theme = theme
        self.setStyleSheet(self._get_stylesheet(theme))
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
