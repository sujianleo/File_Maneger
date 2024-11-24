import os
import re
import tkinter as tk
from tkinter import messagebox, filedialog

config_file = "last_path.txt"
selected_items = set()  # 用于存储多选的文件夹索引
drag_threshold = 5  # 拖拽判断的阈值（像素）

# 保存上次选择的路径到配置文件
def save_last_path(path):
    with open(config_file, "w") as file:
        file.write(path)

# 从配置文件加载上次选择的路径
def load_last_path():
    if os.path.exists(config_file):
        with open(config_file, "r") as file:
            return file.read().strip()
    return None

# 更新窗口标题为当前选择的文件夹路径
def update_window_title(path):
    root.title(f"{path}")

# 选择文件夹并保存路径
def select_directory():
    base_path = filedialog.askdirectory(title="选择文件夹路径", initialdir=load_last_path() or "/")
    if base_path:
        save_last_path(base_path)
        selected_folder_path.set(base_path)
        update_window_title(base_path)
        refresh_listbox(base_path)

# 刷新列表框
def refresh_listbox(base_path):
    listbox.delete(0, tk.END)
    all_folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
    for i, folder in enumerate(all_folders):
        listbox.insert(tk.END, folder)
        color = 'yellow' if i in selected_items else 'white'
        listbox.itemconfig(i, {'bg': color})

# 确认排序
def confirm_sort():
    base_path = selected_folder_path.get()
    all_folders = list(listbox.get(0, tk.END))
    unselected_folders = [all_folders[i] for i in range(len(all_folders)) if i not in selected_items]
    
    for i, folder_name in enumerate(unselected_folders, 1):
        new_name = f"{i:02d}_{re.sub(r'^\d+_', '', folder_name)}"
        current_path, new_path = os.path.join(base_path, folder_name), os.path.join(base_path, new_name)
        counter = 1
        while os.path.exists(new_path) and current_path != new_path:
            new_name = f"{i:02d}_{re.sub(r'^\d+_', '', folder_name)} ({counter})"
            new_path = os.path.join(base_path, new_name)
            counter += 1
        if os.path.exists(current_path):
            os.rename(current_path, new_path)
    refresh_listbox(base_path)

# 创建新文件夹
def create_new_folder():
    base_path = selected_folder_path.get()
    folder_name = "新建"
    counter = 1
    while os.path.exists(os.path.join(base_path, folder_name)):
        folder_name = f"新建 ({counter})"
        counter += 1
    os.makedirs(os.path.join(base_path, folder_name))
    refresh_listbox(base_path)

# 删除选中的文件夹
def delete_selected_folder():
    if not selected_items:
        messagebox.showwarning("删除警告", "没有选中文件夹")
        return
    
    base_path = selected_folder_path.get()
    folders_to_delete = [listbox.get(i) for i in selected_items]
    confirmation = messagebox.askyesno("删除确认", f"确认删除以下文件夹：\n\n" + "\n".join(folders_to_delete))
    
    if confirmation:
        for folder_name in folders_to_delete:
            folder_path = os.path.join(base_path, folder_name)
            if os.path.isdir(folder_path):
                try:
                    os.rmdir(folder_path)  # 删除文件夹
                    selected_items.remove(listbox.get(0, tk.END).index(folder_name))  # 从选中项中移除
                except Exception as e:
                    messagebox.showerror("删除错误", f"删除失败: {e}")
        refresh_listbox(base_path)

# 拖拽功能的全局变量
drag_data = {"item": None, "index": None, "start_x": 0, "start_y": 0}

# 开始拖拽事件
def on_start_drag(event):
    drag_data.update({"start_x": event.x, "start_y": event.y, "item": listbox.get("@%d,%d" % (event.x, event.y)), "index": listbox.nearest(event.y)})
    listbox.selection_clear(0, tk.END)
    listbox.selection_set(drag_data["index"])

# 拖拽中
def on_drag(event):
    if abs(event.x - drag_data["start_x"]) > drag_threshold or abs(event.y - drag_data["start_y"]) > drag_threshold:
        if drag_data["item"]:
            nearest_index = listbox.nearest(event.y)
            if nearest_index >= 0 and nearest_index != drag_data["index"]:
                item = listbox.get(drag_data["index"])
                listbox.delete(drag_data["index"])
                listbox.insert(nearest_index, item)
                drag_data["index"] = nearest_index
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(nearest_index)

# 结束拖拽
def on_drop(event):
    drag_data.update({"item": None, "index": None})

# 处理多选
def handle_ctrl_click(event):
    index = listbox.nearest(event.y)
    if event.state & 0x0004:  # 检查 Ctrl 键是否按下
        if index in selected_items:
            selected_items.remove(index)
            listbox.itemconfig(index, {'bg': 'white'})
        else:
            selected_items.add(index)
            listbox.itemconfig(index, {'bg': 'yellow'})

# 开始编辑文件夹名称
def start_edit():
    global edit_entry
    selected = listbox.curselection()
    if not selected:
        return
    x, y, w, h = listbox.bbox(selected[0])
    current_name = listbox.get(selected[0])
    clean_name = re.sub(r'^\d+_', '', re.sub(r'\(\d+\)$', '', current_name)).strip()
    edit_entry = tk.Entry(listbox, borderwidth=0)
    edit_entry.insert(0, clean_name)
    edit_entry.place(x=x, y=y, width=w, height=h)
    edit_entry.bind("<Return>", finish_edit)
    edit_entry.bind("<Escape>", cancel_edit)
    edit_entry.focus_set()

# 完成编辑
def finish_edit(event=None):
    global edit_entry
    if edit_entry:
        new_name = edit_entry.get().strip()
        selected = listbox.curselection()
        if selected:
            old_name = listbox.get(selected[0])
            base_path = selected_folder_path.get()
            new_path = os.path.join(base_path, re.sub(r'^\d+_', '', new_name))
            counter = 1
            while os.path.exists(new_path):
                new_path = os.path.join(base_path, f"{new_name} ({counter})")
                counter += 1
            os.rename(os.path.join(base_path, old_name), new_path)
            refresh_listbox(base_path)
        edit_entry.destroy()
        edit_entry = None

# 取消编辑
def cancel_edit(event=None):
    if edit_entry:
        edit_entry.destroy()

# 显示右键菜单
def show_context_menu(event):
    clicked_index = listbox.nearest(event.y)
    listbox.selection_clear(0, tk.END)
    listbox.selection_set(clicked_index)
    context_menu = tk.Menu(root, tearoff=0)
    context_menu.add_command(label="编辑", command=start_edit)
    context_menu.add_command(label="删除", command=delete_selected_folder)
    context_menu.add_command(label="新建", command=create_new_folder)
    context_menu.add_command(label="排序", command=confirm_sort)
    context_menu.add_command(label="打开", command=select_directory)
    context_menu.tk_popup(event.x_root, event.y_root)

# 主程序布局
root = tk.Tk()
selected_folder_path = tk.StringVar()
initial_path = load_last_path() or "未选择文件夹"
selected_folder_path.set(initial_path)
update_window_title(initial_path)

listbox = tk.Listbox(root, selectmode=tk.SINGLE, height=20, width=50)
listbox.pack(fill="both", expand=True, padx=10, pady=(5, 5))
listbox.bind("<Button-1>", on_start_drag)
listbox.bind("<B1-Motion>", on_drag)
listbox.bind("<ButtonRelease-1>", on_drop)
listbox.bind("<Control-Button-1>", handle_ctrl_click)
listbox.bind("<Button-3>", show_context_menu)

# 加载初始文件夹内容
if os.path.exists(initial_path):
    refresh_listbox(initial_path)

root.mainloop()
