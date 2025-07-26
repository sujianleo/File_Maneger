# Folder Sorter

This project is a desktop application built with `PyQt5` that helps users drag-and-drop reorder folders and batch rename them within a selected directory.

## How to run

1. Install Python 3 and use `pip install pyqt5` to install dependencies.
2. From the project root, run:
   ```bash
   python file_manager.py
   ```

After launching, input or choose the folder path you want to manage.

## Key features

- **Drag-and-drop sorting**: Adjust folder order directly in the list. When unpaused, numbered prefixes are automatically applied.
- **Context menu**: Provides options for creating folders, opening directories, renaming, clearing numbers, and starting or pausing sorting.
- **Double-click to open**: Open a folder in the system file manager by double-clicking an item.
- **Remember path**: The last opened path is stored in `last_state.json` for next time.
- **Drag paths**: Drag a folder onto the window to switch paths, with the list refreshing automatically.
- **Bulk delete**: Delete multiple selected folders from the context menu.
- **Auto refresh**: The app periodically checks the directory for changes and refreshes the list.
- **Status overlay**: An overlay appears when sorting starts or pauses; double-clicking "Browse..." temporarily enlarges the window.

## Build an executable

Use `file_manager.spec` with [PyInstaller](https://pyinstaller.org/) to create an executable:

```bash
pyinstaller file_manager.spec
```

The result is placed in the `dist/` directory.

## License

This project is released under the MIT License. See `LICENSE` if available.
