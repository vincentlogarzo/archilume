# ui_utils.py

import os
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional


def select_file_from_subdir(
    subdir_name: str = "lib", prompt_message: Optional[str] = None
) -> Optional[str]:
    """
    Displays a custom pop-up message and then opens a file dialog
    in a subdirectory of the current working directory.

    Args:
        subdir_name (str, optional): The name of the subdirectory. Defaults to "lib".
        prompt_message (str, optional): The message to display in a pop-up
                                         before the file dialog opens.
                                         If None, no message is shown. Defaults to None.

    Returns:
        str or None: The full path to the selected file, or an empty string/None
                     if the dialog is cancelled or an error occurs.
                     Returns None specifically if directory creation fails.
    """
    current_dir = os.getcwd()
    subdir_path = os.path.join(current_dir, subdir_name)

    if not os.path.exists(subdir_path):
        try:
            os.makedirs(subdir_path)
            print(f"Created directory: {subdir_path}")  # Feedback for directory creation
        except OSError as e:
            # Display error using messagebox if possible, or print
            error_title = "Directory Error"
            error_message = f"Error creating '{subdir_name}' directory: {e}\nPath: {subdir_path}"
            try:
                root_err = tk.Tk()
                root_err.withdraw()
                messagebox.showerror(error_title, error_message, parent=root_err)
                root_err.destroy()
            except Exception:  # Fallback to print if Tkinter fails early
                print(error_message)
            return None

    # Initialize Tkinter root only if we proceed
    root = tk.Tk()
    root.withdraw()  # Hide the main Tkinter window

    # Display the custom pop-up message if provided
    if prompt_message:
        # Using "Information" as a generic title for the message box
        messagebox.showinfo("Information", prompt_message, parent=root)

    # Open the file dialog
    # The parent=root argument helps in proper window layering and behavior.
    file_path = filedialog.askopenfilename(
        initialdir=subdir_path,
        title="Select a file",  # You can customize this title as well
        parent=root,
    )

    # Clean up the hidden Tkinter root window
    root.destroy()

    return file_path
