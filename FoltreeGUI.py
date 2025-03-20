import os
import tkinter as tk
import customtkinter as ctk
from CTkToolTip import *
from tkinter import filedialog
import time
import random

def folder_to_text(folder_path, format_type):
    ignore_patterns = get_ignore_patterns()

    if format_type == "Indented":
        return generate_indented_format(folder_path, ignore_patterns)
    elif format_type == "Tree":
        return generate_tree_format(folder_path, ignore_patterns)
    elif format_type == "Clean Tree":
        return generate_clean_tree_format(folder_path, ignore_patterns)
    else:
        raise ValueError("Invalid format type. Choose 'Indented', 'Tree', or 'Clean Tree'.")

def generate_indented_format(folder_path, ignore_patterns):
    folder_structure = []
    for root, dirs, files in os.walk(folder_path):
        if should_ignore(root, ignore_patterns):
            continue
        level = root.replace(folder_path, '').count(os.sep)
        indent = ' ' * 4 * level
        folder_structure.append(f'{indent}{os.path.basename(root)}/')
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            if should_ignore(os.path.join(root, f), ignore_patterns):
                continue
            folder_structure.append(f'{sub_indent}{f}')
    return '\n'.join(folder_structure)

def generate_tree_format(folder_path, ignore_patterns):
    folder_structure = []
    for root, dirs, files in os.walk(folder_path):
        if should_ignore(root, ignore_patterns):
            continue
        level = root.replace(folder_path, '').count(os.sep)
        indent = '│   ' * level
        folder_structure.append(f'{indent}├── {os.path.basename(root)}')
        sub_indent = '│   ' * (level + 1)
        for f in files:
            if should_ignore(os.path.join(root, f), ignore_patterns):
                continue
            folder_structure.append(f'{sub_indent}├── {f}')
    return '\n'.join(folder_structure)

def generate_clean_tree_format(folder_path, ignore_patterns):
    folder_structure = []
    def process_folder(root, prefix="", is_last=False):
        entries = sorted(os.listdir(root))
        entries = [e for e in entries if not should_ignore(os.path.join(root, e), ignore_patterns)]
        dirs = [e for e in entries if os.path.isdir(os.path.join(root, e))]
        files = [e for e in entries if os.path.isfile(os.path.join(root, e))]
        connector = "└── " if is_last else "├── "
        folder_structure.append(f"{prefix}{connector}{os.path.basename(root)}")
        sub_prefix = prefix + ("    " if is_last else "│   ")
        for index, entry in enumerate(dirs):
            is_last_entry = index == len(dirs) - 1 and not files
            process_folder(os.path.join(root, entry), sub_prefix, is_last_entry)
        for index, entry in enumerate(files):
            file_connector = "└── " if index == len(files) - 1 else "├── "
            folder_structure.append(f"{sub_prefix}{file_connector}{entry}")
    process_folder(folder_path, "", True)
    return "\n".join(folder_structure)

def text_to_folder(text, output_path, format_type):
    lines = text.split('\n')
    current_path = [output_path]
    ignore_patterns = get_ignore_patterns()
    for line in lines:
        if format_type == "Indented":
            indent_level = len(line) - len(line.lstrip(' '))
            level = indent_level // 4
        elif format_type == "Tree":
            indent_level = line.count('│   ')
            level = indent_level
        elif format_type == "Clean Tree":
            indent_level = line.count('    ')
            level = indent_level
        while len(current_path) > level + 1:
            current_path.pop()
        if format_type == "Indented":
            path = os.path.join(*current_path, line.strip())
        elif format_type == "Tree" or format_type == "Clean Tree":
            item_name = line.strip().replace('├── ', '').replace('└── ', '').replace('│   ', '').replace('    ', '')
            path = os.path.join(*current_path, item_name)
        if should_ignore(path, ignore_patterns):
            continue
        if format_type in ["Tree", "Clean Tree"] and '.' not in item_name:
            os.makedirs(path, exist_ok=True)
            current_path.append(path)
        elif format_type == "Indented" and line.strip().endswith('/'):
            os.makedirs(path, exist_ok=True)
            current_path.append(path)
        else:
            dir_path = os.path.dirname(path)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            open(path, 'w').close()

def select_folder():
    folder_path = filedialog.askdirectory()
    if folder_path:
        global folder_structures
        folder_structures = {
            "Indented": folder_to_text(folder_path, "Indented"),
            "Tree": folder_to_text(folder_path, "Tree"),
            "Clean Tree": folder_to_text(folder_path, "Clean Tree")
        }
        display_selected_format()

def display_selected_format():
    format_type = format_var.get()
    text_box.delete(1.0, ctk.END)
    text_box.insert(ctk.END, folder_structures[format_type])

def generate_folder():
    global folder_structures
    text = text_box.get(1.0, ctk.END).strip()
    format_type = format_var.get()
    if use_output_folder.get():
        output_path = os.path.join(os.path.dirname(__file__), 'output')
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        unique_folder_name = f"{time.strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"
        output_path = os.path.join(output_path, unique_folder_name)
        os.makedirs(output_path)
    else:
        output_path = filedialog.askdirectory()
        if not output_path:
            return
    text_to_folder(text, output_path, format_type)
    
    readme_path = os.path.join(output_path, "README.md")
    with open(readme_path, 'w', encoding='utf-8') as readme_file:
        readme_file.write("# Foltree\n\n")
        readme_file.write("This folder structure was generated by Foltree.\n")
        readme_file.write("Foltree is a bidirectional converter for folder to text and text to folder.\n")
        readme_file.write("Foltree by [kiliannnnn](https://github.com/kiliannnnn)\n\n")
        readme_file.write("## Structure\n\n")
        readme_file.write("```\n")
        readme_file.write(folder_structures[format_type])
        readme_file.write("\n```\n")
    
    status_var.set("Folder structure generated successfully.")

def on_format_change(*args):
    display_selected_format()

def get_ignore_patterns():
    patterns = ignore_text.get(1.0, ctk.END).strip().split('\n')
    return [pattern.strip() for pattern in patterns if pattern.strip()]

def should_ignore(path, ignore_patterns):
    for pattern in ignore_patterns:
        if pattern in path:
            return True
    return False

root = ctk.CTk()
root.title("Foltree")
root.geometry("400x600")

# Define the status variable
status_var = ctk.StringVar(value="Status: Ready")

# Create a label to display the status
status_label = ctk.CTkLabel(root, textvariable=status_var, fg_color=("white", "gray"), font=("Arial", 10))
status_label.grid(row=0, column=0, columnspan=2, pady=10)

# Create a frame for the text box and scrollbar
text_frame = ctk.CTkFrame(root)
text_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")

# Create a Text widget with a scrollbar
text_box = ctk.CTkTextbox(text_frame, wrap='word', width=50, height=15)
text_box.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True)

scrollbar = ctk.CTkScrollbar(text_frame, command=text_box.yview)
scrollbar.pack(side=ctk.RIGHT, fill=ctk.Y)
text_box.configure(yscrollcommand=scrollbar.set)

# Create a frame for the options
options_frame = ctk.CTkFrame(root)
options_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")

# Create a Checkbutton widget
use_output_folder = ctk.BooleanVar()
output_folder_checkbox = ctk.CTkCheckBox(options_frame, text="Use 'output' folder", variable=use_output_folder)
output_folder_checkbox.grid(row=0, column=0, padx=5, pady=5, sticky="w")

# Create a tooltip for the checkbox with a small delay and some custom styling
tooltip_checkbox = CTkToolTip(
    output_folder_checkbox,
    alpha= 0.9,
    message="If checked, the result will be saved in an 'output' folder with a unique name. If unchecked, you will be prompted to select a folder."
)

# Create a dropdown menu to select format under the checkbox
format_var = ctk.StringVar(value="Indented")
format_var.trace('w', on_format_change)
format_dropdown = ctk.CTkOptionMenu(options_frame, variable=format_var, values=["Indented", "Tree", "Clean Tree"])
format_dropdown.grid(row=2, column=0, padx=5, pady=5, sticky="w")

# Create ignore_text input that takes the entire width and more height with default values
ignore_text = ctk.CTkTextbox(root, height=10, width=60)
ignore_text.grid(row=2, column=1, padx=10, pady=10, sticky="nsew")

# Add default values inside the ignore_text box
ignore_text.insert(1.0, ".git\nnode_modules\ndist\n.vscode\n.env\n.env.local\n")

# Create buttons
button_frame = ctk.CTkFrame(root)
button_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

generate_button = ctk.CTkButton(button_frame, text="Generate Folder", command=generate_folder)
generate_button.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

select_folder_button = ctk.CTkButton(button_frame, text="Select Folder", command=select_folder)
select_folder_button.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

# Configure grid weights to make the layout responsive
root.grid_columnconfigure(0, weight=1)
root.grid_columnconfigure(1, weight=1)
root.grid_rowconfigure(1, weight=1)
root.grid_rowconfigure(2, weight=1)

folder_structures = {
    "Indented": "Some folder structure for Indented",
    "Tree": "Some folder structure for Tree",
    "Clean Tree": "Some folder structure for Clean Tree"
}

# Start the Tkinter main loop
root.mainloop()
