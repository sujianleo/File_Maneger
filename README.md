# Directory Manager

This desktop application, powered by `PyQt5`, lets you reorder folders with drag-and-drop, apply tidy numbering, and capture ideas alongside your workspace.

## How to run

1. Install Python 3 and the dependency:
   ```bash
   pip install pyqt5
   ```
2. From the project root, launch the app:
   ```bash
   python directory_manager.py
   ```

Once it opens, drop a folder onto the window or paste a path into the address box to get started.

## Highlights

- **Dual workspace** – Manage inspiration and to-dos at the top while keeping your folder operations below.
- **Drag-and-drop sorting** – Reorder folders directly in the list. Resume sorting to apply fresh numeric prefixes automatically.
- **Contextual tools** – Right-click folders to create, rename, delete, reserve, or clear numbering with ease.
- **Double-click actions** – Open folders in your system file manager or mark notes as finished with a quick double-click.
- **Reserved folders** – Flag specific folders so they remain untouched by batch operations.
- **Smart persistence** – The latest path, reserved list, and your idea log are saved in `last_state.json` for next time.
- **Live refresh** – The list keeps an eye on directory changes and refreshes itself automatically.

## Build an executable

This repository is now named **Directory_Manager**, and the recommended way to
package it is the fastest-starting *one-directory* bundle:

- **Preferred (fast startup)**
  ```bash
  python build_dist.py
  ```
  This creates `dist/directory_manager/`, so the app launches immediately
  without the self-extraction delay of the one-file mode.
- **Alternative single executable**
  ```bash
  pyinstaller directory_manager.spec
  ```
  A standalone executable is emitted to the `dist/` directory, but it takes
  longer to start because PyInstaller must unpack itself first.

## License

This project is released under the MIT License. See `LICENSE` if present.
