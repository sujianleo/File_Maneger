# Directory Manager

This project is a desktop application built with `PyQt5` that helps users drag-and-drop reorder folders and batch rename them within a selected directory.

## How to run

1. Install Python 3 and use `pip install pyqt5` to install dependencies.
2. From the project root, run:
   ```bash
   python directory_manager.py
   ```

After launching, input or choose the folder path you want to manage.

## Key features

- **Drag-and-drop sorting**: Adjust folder order directly in the list. When unpaused, numbered prefixes are automatically applied.
- **Context menu**: Provides options for creating folders, opening directories, renaming, clearing numbers, and starting or pausing sorting.
- **Double-click to open**: Open a folder in the system file manager by double-clicking an item.
- **Remember path**: The last opened path is stored in `last_state.json` for next time.
- **Drag paths**: Drag a folder onto the window to switch paths, with the list refreshing automatically.
- **Bulk delete**: Delete multiple selected folders from the context menu.
- **Keep folders**: Mark folders as preserved from the context menu so they are skipped when sorting or clearing numbers.
- **Auto refresh**: The app periodically checks the directory for changes and refreshes the list.
- **Locked folder warning**: If an operation fails because a folder is in use, a dialog reminds you to close the other program first.
- **Status overlay**: An overlay appears when sorting starts or pauses; double-clicking "Browse..." temporarily enlarges the window.

## Build an executable

The project repository has been renamed **Directory_Manager**. For the quickest
launching packaged build, use the *one-directory* option:

- **Preferred (fast startup)**:
  ```bash
  python build_dist.py
  ```
  The script generates `dist/directory_manager/`, letting the app open instantly
  because no extraction step is required.
- **Alternative single-file build**:
  ```bash
  pyinstaller directory_manager.spec
  ```
  This produces an executable in `dist/`, but startup is slower while the
  bundled archive unpacks.

## License

This project is released under the MIT License. See `LICENSE` if available.
