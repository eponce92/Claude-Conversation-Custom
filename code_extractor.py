"""
Project Scanner

This program provides a graphical user interface for scanning and analyzing project directories.
It allows users to view the structure of their project, extract code from files, and get statistics
about the scanned project.

Features:
- Select project type (Generic, Python, Java, C/C++) to apply preset exclusion rules
- Customize folders, file extensions, and specific files to exclude from the scan
- View project structure and file contents
- Navigate through scanned files using a sidebar
- Display statistics (total files scanned and total lines extracted)
- Copy extracted content to clipboard

Usage:
1. Run the script to open the GUI window
2. Select a project type from the dropdown menu
3. Click "Browse" to select your project folder
4. Modify exclusion fields if needed
5. Click "Scan Project" to start the scanning process
6. Use the sidebar to navigate between files
7. View project structure and file contents in the main text area
8. Check statistics displayed above the "Copy to Clipboard" button
9. Use "Copy to Clipboard" to copy the entire output

Requirements: tkinter, pyperclip, pathspec

Author: [Ernesto Ponce]
Date: [8/7/2024]
Version: 1.0
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pyperclip
import pathspec
import sys

def load_gitignore_patterns(root_folder):
    """
    Load .gitignore patterns from the project root folder.
    
    Args:
    root_folder (str): Path to the project root folder

    Returns:
    pathspec.PathSpec: PathSpec object with gitignore patterns, or None if .gitignore doesn't exist
    """
    gitignore_path = os.path.join(root_folder, '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r') as file:
            return pathspec.PathSpec.from_lines('gitwildmatch', file)
    return None

def scan_project(root_folder, exclude_folders, exclude_extensions, exclude_files):
    """
    Scan the project directory and extract file contents based on exclusion rules.
    
    Args:
    root_folder (str): Path to the project root folder
    exclude_folders (str): Comma-separated list of folders to exclude
    exclude_extensions (str): Comma-separated list of file extensions to exclude
    exclude_files (str): Comma-separated list of specific files to exclude

    Returns:
    tuple: (content, file_list, total_files, total_lines)
        content (str): Extracted content from scanned files
        file_list (list): List of scanned files
        total_files (int): Total number of files scanned
        total_lines (int): Total number of lines extracted
    """
    gitignore_spec = load_gitignore_patterns(root_folder)
    ignore_dirs = set(folder.strip() for folder in exclude_folders.split(',') if folder.strip())
    ignore_exts = set(ext.strip().lower() for ext in exclude_extensions.split(',') if ext.strip())
    ignore_files = set(file.strip() for file in exclude_files.split(',') if file.strip())
    
    ignore_files.add(os.path.basename(__file__))  # Add the script's filename to the ignore list
    
    content = []
    file_list = []
    total_lines = 0
    total_files = 0
    
    content.append(f"Root folder name: {os.path.basename(root_folder)}\n\n")
    content.append("Project folder and file structure:\n")
    
    # Walk through the project directory
    for folder_name, subfolders, filenames in os.walk(root_folder):
        subfolders[:] = [d for d in subfolders if d not in ignore_dirs]
        level = folder_name.replace(root_folder, '').count(os.sep)
        indent = ' ' * 4 * (level)
        rel_folder = os.path.relpath(folder_name, root_folder)
        
        if gitignore_spec and gitignore_spec.match_file(rel_folder):
            continue
        
        content.append(f"{indent}{os.path.basename(folder_name)}/\n")
        subindent = ' ' * 4 * (level + 1)
        
        # Process files in the current folder
        for filename in filenames:
            if filename in ignore_files:
                continue
            
            rel_file = os.path.relpath(os.path.join(folder_name, filename), root_folder)
            
            if gitignore_spec and gitignore_spec.match_file(rel_file):
                continue
            
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext not in ignore_exts:
                content.append(f"{subindent}{filename}\n")
                file_list.append(rel_file)
    
    content.append("\nFile Code:\n")
    
    # Extract content from scanned files
    for file_path in file_list:
        full_path = os.path.join(root_folder, file_path)
        try:
            with open(full_path, "r", errors="ignore") as file:
                file_content = file.read()
                content.append(f"\nFile: {file_path}\n")
                content.append(file_content)
                content.append("\n" + "="*80 + "\n")
                total_lines += len(file_content.splitlines())
                total_files += 1
        except Exception as e:
            content.append(f"\nFile: {file_path}\n")
            content.append(f"Error reading file: {e}\n")
            content.append("\n" + "="*80 + "\n")
    
    return "".join(content), file_list, total_files, total_lines

class ProjectScannerGUI:
    """
    GUI class for the Project Scanner application.
    """
    def __init__(self, master):
        self.master = master
        master.title("Project Scanner")
        master.geometry("1000x600")

        # Define project types with their default exclusion settings
        self.project_types = {
            "Generic": {
                "folders": ".git,__pycache__,venv,node_modules",
                "extensions": ".pyc,.pyo,.pyd,.pdf,.json,.md",
                "files": "README.md,LICENSE,.gitignore, code_extraction_UI.py"
            },
            "Python": {
                "folders": ".git,__pycache__,venv,.eggs,build,dist, reports, assets, internal_libs, auth",
                "extensions": ".pyc,.pyo,.pyd,.egg-info,.whl, .json, .md, .pdf, .pptx, .docx, .xlsx, .ppt, .doc, .xls, .ipynb",
                "files": "README.md,LICENSE,.gitignore,setup.py,requirements.txt, code_extraction_UI.py, BatchCaller.py"
            },
            "Java": {
                "folders": ".git,target,build,.gradle",
                "extensions": ".class,.jar,.war,.ear",
                "files": "README.md,LICENSE,.gitignore,pom.xml,build.gradle, code_extraction_UI.py"
            },
            "C/C++": {
                "folders": ".git,build,bin,lib",
                "extensions": ".o,.obj,.a,.lib,.so,.dll",
                "files": "README.md,LICENSE,.gitignore,Makefile,CMakeLists.txt,code_extraction_UI.py"
            }
        }

        # Left side - Input fields
        left_frame = tk.Frame(master, width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        # Project Type selection
        tk.Label(left_frame, text="Project Type:").pack(anchor=tk.W)
        self.project_type = tk.StringVar(value="Generic")
        self.project_type_combo = ttk.Combobox(left_frame, textvariable=self.project_type, values=list(self.project_types.keys()), state="readonly")
        self.project_type_combo.pack(anchor=tk.W)
        self.project_type_combo.bind("<<ComboboxSelected>>", self.update_exclusions)

        # Project Folder selection
        tk.Label(left_frame, text="Project Folder:").pack(anchor=tk.W, pady=(10, 0))
        self.folder_path = tk.StringVar()
        tk.Entry(left_frame, textvariable=self.folder_path, width=30).pack(anchor=tk.W)
        
        folder_buttons_frame = tk.Frame(left_frame)
        folder_buttons_frame.pack(anchor=tk.W)
        
        tk.Button(folder_buttons_frame, text="Browse", command=self.browse_folder).pack(side=tk.LEFT)
        tk.Button(folder_buttons_frame, text="Use Current Folder ↑", command=self.use_current_folder).pack(side=tk.LEFT, padx=(5, 0))

        # Exclusion fields
        tk.Label(left_frame, text="Exclude Folders (comma-separated):").pack(anchor=tk.W, pady=(10, 0))
        self.exclude_folders = tk.StringVar()
        tk.Entry(left_frame, textvariable=self.exclude_folders, width=30).pack(anchor=tk.W)

        tk.Label(left_frame, text="Exclude File Extensions (comma-separated):").pack(anchor=tk.W, pady=(10, 0))
        self.exclude_extensions = tk.StringVar()
        tk.Entry(left_frame, textvariable=self.exclude_extensions, width=30).pack(anchor=tk.W)

        tk.Label(left_frame, text="Exclude File Names (comma-separated):").pack(anchor=tk.W, pady=(10, 0))
        self.exclude_files = tk.StringVar()
        tk.Entry(left_frame, textvariable=self.exclude_files, width=30).pack(anchor=tk.W)

        # Scan button
        tk.Button(left_frame, text="Scan Project", command=self.scan_project).pack(anchor=tk.W, pady=(10, 0))

        # Right side - Sidebar, Output text, and Statistics
        right_frame = tk.Frame(master)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create a PanedWindow for resizable sections
        paned_window = tk.PanedWindow(right_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)

        # Sidebar (File list)
        sidebar_frame = tk.Frame(paned_window, width=200)
        paned_window.add(sidebar_frame)

        self.file_listbox = tk.Listbox(sidebar_frame, width=30)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sidebar_scrollbar = tk.Scrollbar(sidebar_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        sidebar_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=sidebar_scrollbar.set)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

        # Output text area
        text_frame = tk.Frame(paned_window)
        paned_window.add(text_frame)

        self.output_text = tk.Text(text_frame, wrap=tk.WORD)
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.output_text.yview)
        text_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.output_text.config(yscrollcommand=text_scrollbar.set)

        # Statistics and Copy button frame
        stats_frame = tk.Frame(right_frame)
        stats_frame.pack(fill=tk.X, pady=(10, 0))

        self.stats_label = tk.Label(stats_frame, text="")
        self.stats_label.pack(side=tk.LEFT)

        tk.Button(stats_frame, text="Copy to Clipboard", command=self.copy_to_clipboard).pack(side=tk.RIGHT)

        # Initialize exclusions
        self.update_exclusions()

    def update_exclusions(self, event=None):
        """Update exclusion fields based on the selected project type."""
        project_type = self.project_type.get()
        self.exclude_folders.set(self.project_types[project_type]["folders"])
        self.exclude_extensions.set(self.project_types[project_type]["extensions"])
        self.exclude_files.set(self.project_types[project_type]["files"])

    def browse_folder(self):
        """Open a file dialog to select the project folder."""
        folder_selected = filedialog.askdirectory()
        self.folder_path.set(folder_selected)

    def scan_project(self):
        """Initiate the project scanning process."""
        folder = self.folder_path.get()
        exclude_folders = self.exclude_folders.get()
        exclude_extensions = self.exclude_extensions.get()
        exclude_files = self.exclude_files.get()

        if not folder:
            messagebox.showerror("Error", "Please select a project folder.")
            return

        result, file_list, total_files, total_lines = scan_project(folder, exclude_folders, exclude_extensions, exclude_files)
        
        # Update GUI with scan results
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, result)

        self.file_listbox.delete(0, tk.END)
        for file in file_list:
            self.file_listbox.insert(tk.END, file)

        self.stats_label.config(text=f"Total files scanned: {total_files} | Total lines extracted: {total_lines}")

    def on_file_select(self, event):
        """Handle file selection in the sidebar."""
        selection = event.widget.curselection()
        if selection:
            index = selection[0]
            file = event.widget.get(index)
            self.scroll_to_file(file)

    def scroll_to_file(self, file):
        """Scroll the output text to the selected file and highlight its header."""
        content = self.output_text.get(1.0, tk.END)
        file_header = f"\nFile: {file}\n"
        file_start = content.find(file_header)
        if file_start != -1:
            self.output_text.see(f"1.0+{file_start}c")
            self.output_text.tag_remove("highlight", "1.0", tk.END)
            end_of_header = file_start + len(file_header)
            self.output_text.tag_add("highlight", f"1.0+{file_start}c", f"1.0+{end_of_header}c")
            self.output_text.tag_config("highlight", background="#A9A9A9", foreground="white")


    def copy_to_clipboard(self):
        """Copy the contents of the output text to the clipboard."""
        content = self.output_text.get(1.0, tk.END)
        pyperclip.copy(content)
        messagebox.showinfo("Success", "Content copied to clipboard!")

    def use_current_folder(self):
        """Set the folder path to the directory where the script is located."""
        current_folder = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.folder_path.set(current_folder)

if __name__ == "__main__":
    root = tk.Tk()
    app = ProjectScannerGUI(root)
    root.mainloop()