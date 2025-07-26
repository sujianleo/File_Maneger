import os
import re
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import json
import subprocess
import sys

CONFIG_FILE = "last_state.json"
DRAG_THRESHOLD = 5

class FileManagerApp:
    def __init__(self, root):
        self.root = root
        self.drag_data = {"item": None, "index": None, "start_x": 0, "start_y": 0}

        self.selected_folder_path = tk.StringVar()
        last_state = self.load_last_state()
        initial_path = (last_state or {}).get("last_path", "未选择文件夹")
        self.selected_folder_path.set(initial_path)

        self.root.title("文件夹排序器")
        # self.root.overrideredirect(True)  # 已移除标题栏隐藏

        self.content_frame = tk.Frame(root)
        self.content_frame.pack(fill="both", expand=True)

        listbox_frame = tk.Frame(self.content_frame, bd=0, highlightthickness=0)
        listbox_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.top_line = tk.Frame(listbox_frame, height=2, bg="red")
        self.top_line.pack(fill="x", side="top")
        self.left_line = tk.Frame(listbox_frame, width=2, bg="red")
        self.left_line.pack(fill="y", side="left")
        self.right_line = tk.Frame(listbox_frame, width=2, bg="red")
        self.right_line.pack(fill="y", side="right")
        self.bottom_line = tk.Frame(listbox_frame, height=2, bg="red")
        self.bottom_line.pack(fill="x", side="bottom")

        self.path_entry = tk.Entry(
            listbox_frame, textvariable=self.selected_folder_path, font=("微软雅黑", 14)
        )
        self.path_entry.pack(fill="x", padx=4, pady=(0, 2))
        self.path_entry.bind("<Return>", self.on_path_entry)

        self.listbox = tk.Listbox(
            listbox_frame, selectmode=tk.SINGLE, height=20, width=50,
            highlightthickness=0, bd=0, font=("微软雅黑", 14)
        )
        self.listbox.pack(fill="both", expand=True)

        self.listbox.bind("<Button-1>", self.on_start_drag)
        self.listbox.bind("<B1-Motion>", self.on_drag)
        self.listbox.bind("<ButtonRelease-1>", self.on_drop)
        self.listbox.bind("<Button-3>", self.show_context_menu)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self.listbox.bind("<Double-Button-1>", self.open_folder_in_explorer)

        if os.path.exists(initial_path):
            self.refresh_listbox(initial_path)

        self.sort_paused = True  # 默认初始为暂停排序

    def save_last_state(self, path):
        with open(CONFIG_FILE, "w") as file:
            json.dump({"last_path": path}, file)

    def load_last_state(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as file:
                return json.load(file)
        return None

    def refresh_listbox(self, base_path):
        self.listbox.delete(0, tk.END)
        folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
        folders.sort()
        for folder in folders:
            self.listbox.insert(tk.END, folder)
            self.listbox.itemconfig(tk.END, {'bg': 'white'})

    def confirm_sort(self):
        base_path = self.selected_folder_path.get()
        folders = list(self.listbox.get(0, tk.END))
        used_names = set()
        for i, folder_name in enumerate(folders, 1):
            base_name = re.sub(r'^\d+_', '', folder_name)
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
        self.refresh_listbox(base_path)

    def create_new_folder(self):
        base_path = self.selected_folder_path.get()
        folder_name = tk.simpledialog.askstring("新建文件夹", "请输入文件夹名称：", initialvalue="新建")
        if not folder_name:
            return
        counter = 1
        original_name = folder_name
        while os.path.exists(os.path.join(base_path, folder_name)):
            folder_name = f"{original_name}({counter})"
            counter += 1
        try:
            os.makedirs(os.path.join(base_path, folder_name))
            self.refresh_listbox(base_path)
        except Exception as e:
            messagebox.showerror("错误", f"创建文件夹失败：{e}")

    def on_start_drag(self, event):
        index = self.listbox.nearest(event.y)
        self.drag_data.update({
            "start_x": event.x,
            "start_y": event.y,
            "item": self.listbox.get(index),
            "index": index
        })
        self.listbox.itemconfig(index, {'bg': '#66FF66'})

    def on_drag(self, event):
        if abs(event.y - self.drag_data["start_y"]) > DRAG_THRESHOLD:
            nearest_index = self.listbox.nearest(event.y)
            if nearest_index != self.drag_data["index"]:
                item = self.listbox.get(self.drag_data["index"])
                self.listbox.delete(self.drag_data["index"])
                self.listbox.insert(nearest_index, item)
                self.drag_data["index"] = nearest_index
            for i in range(self.listbox.size()):
                self.listbox.itemconfig(i, {'bg': 'white'})
            if self.drag_data["index"] is not None and self.drag_data["index"] < self.listbox.size():
                self.listbox.itemconfig(self.drag_data["index"], {'bg': '#66FF66'})

    def on_drop(self, event):
        index = self.drag_data["index"]
        self.drag_data.update({"item": None, "index": None})
        if not self.sort_paused:
            self.confirm_sort()
        if index is not None and index < self.listbox.size():
            self.listbox.itemconfig(index, {'bg': 'white'})

    def show_context_menu(self, event):
        menu_font = ("微软雅黑", 14)
        context_menu = tk.Menu(self.root, tearoff=0, font=menu_font)
        context_menu.add_command(label="新建文件", command=self.create_new_folder)
        context_menu.add_command(label="打开目录", command=self.select_directory)
        context_menu.add_command(label="重命名称", command=lambda: self.rename_selected_folder(event))
        context_menu.add_command(label="清除序号", command=self.clear_prefix_number)
        if self.sort_paused:
            context_menu.add_command(label="开始排序", command=self.resume_sort)
        else:
            context_menu.add_command(label="暂停排序", command=self.pause_sort)
        context_menu.tk_popup(event.x_root, event.y_root)

    def clear_prefix_number(self, event=None):
        base_path = self.selected_folder_path.get()
        folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
        changed = False
        for old_name in folders:
            new_name = re.sub(r'^\d+_?', '', old_name)
            if new_name and new_name != old_name:
                old_path = os.path.join(base_path, old_name)
                new_path = os.path.join(base_path, new_name)
                if os.path.exists(new_path):
                    continue
                try:
                    os.rename(old_path, new_path)
                    changed = True
                except Exception as e:
                    messagebox.showerror("错误", f"清除序号失败：{e}")
        if changed:
            self.refresh_listbox(base_path)

    def select_directory(self):
        base_path = filedialog.askdirectory(title="选择文件夹路径")
        if base_path:
            self.selected_folder_path.set(base_path)
            self.save_last_state(base_path)
            self.refresh_listbox(base_path)

    def on_select(self, event):
        for i in range(self.listbox.size()):
            self.listbox.itemconfig(i, {'fg': 'black'})
        selection = self.listbox.curselection()
        if selection:
            idx = selection[0]
            self.listbox.itemconfig(idx, {'fg': 'red'})

    def open_folder_in_explorer(self, event):
        index = self.listbox.nearest(event.y)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(index)
        folder_name = self.listbox.get(index)
        base_path = self.selected_folder_path.get()
        folder_path = os.path.join(base_path, folder_name)
        if os.path.exists(folder_path):
            if sys.platform.startswith("win"):
                os.startfile(folder_path)
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", folder_path])
            else:
                subprocess.Popen(["xdg-open", folder_path])

    def rename_selected_folder(self, event):
        index = self.listbox.nearest(event.y)
        if index < 0 or index >= self.listbox.size():
            return
        old_name = self.listbox.get(index)
        base_path = self.selected_folder_path.get()
        old_path = os.path.join(base_path, old_name)

        new_name = tk.simpledialog.askstring("重命名", f"将“{old_name}”重命名为：", initialvalue=old_name)
        if new_name and new_name != old_name:
            new_path = os.path.join(base_path, new_name)
            if os.path.exists(new_path):
                messagebox.showerror("错误", "已存在同名文件夹！")
                return
            try:
                os.rename(old_path, new_path)
                self.refresh_listbox(base_path)
            except Exception as e:
                messagebox.showerror("错误", f"重命名失败：{e}")

    def pause_sort(self):
        self.sort_paused = True
        for line in [self.top_line, self.bottom_line, self.left_line, self.right_line]:
            line.config(bg="red")

    def resume_sort(self):
        self.sort_paused = False
        for line in [self.top_line, self.bottom_line, self.left_line, self.right_line]:
            line.config(bg="green")
        self.confirm_sort()

    def on_path_entry(self, event):
        path = self.selected_folder_path.get()
        if os.path.isdir(path):
            self.save_last_state(path)
            self.refresh_listbox(path)
        else:
            messagebox.showerror("错误", "路径不存在！")



if __name__ == "__main__":
    root = tk.Tk()
    app = FileManagerApp(root)
    root.mainloop()
