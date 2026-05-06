import os
import re
import shutil
import threading
import queue
import subprocess
from dataclasses import dataclass
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import winreg
except ImportError:
    winreg = None


def send_to_recycle_bin(path: str) -> tuple[bool, str]:
    """Move a file or folder to the Recycle Bin using PowerShell."""
    try:
        # Use PowerShell's Remove-Item with -Confirm:$false to move to recycle bin
        # We use the .NET Shell.Application COM object for proper recycle bin support
        ps_script = f'''
Add-Type -AssemblyName Microsoft.VisualBasic
[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('{path.replace("'", "''")}', 'OnlyErrorDialogs', 'SendToRecycleBin')
'''
        if os.path.isdir(path):
            ps_script = f'''
Add-Type -AssemblyName Microsoft.VisualBasic
[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory('{path.replace("'", "''")}', 'OnlyErrorDialogs', 'SendToRecycleBin')
'''
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        if result.returncode == 0:
            return True, "Moved to Recycle Bin"
        else:
            return False, result.stderr.strip() or "Unknown error"
    except Exception as e:
        return False, str(e)


@dataclass
class LeftoverItem:
    folder_name: str
    full_path: str
    base_location: str
    last_write_time: str
    item_count: int
    size_mb: float


@dataclass
class TempItem:
    category: str
    path: str
    item_count: int
    size_mb: float
    safe_level: str


class LeftoverCleanerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Leftover App Folder Finder")
        self.root.geometry("1250x760")

        self.scan_queue: queue.Queue = queue.Queue()
        self.leftover_items: list[LeftoverItem] = []
        self.temp_items: list[TempItem] = []

        self.exclude_names = {
            "Common Files", "Internet Explorer", "ModifiableWindowsApps", "PackageManagement",
            "Windows Defender", "Windows Mail", "Windows Multimedia Platform", "Windows NT",
            "Windows Photo Viewer", "Windows Portable Devices", "Windows Security", "WindowsPowerShell",
            "Windows Media Player", "WindowsApps", "Uninstall Information", "Package Cache", "Packages",
            "Temp", "Templates", "SoftwareDistribution", "USOPrivate", "USOShared", "ssh", "Whesvc",
            "WindowsHolographicDevices", "regid.1991-06.com.microsoft", "Propagation", "Microsoft_Corporation",
            "Microsoft", "Microsoft Office", "Microsoft Office 15", "Microsoft Visual Studio", "Microsoft.NET",
            "dotnet", ".NET", "NVIDIA Corporation", "NVIDIA", "Intel", "AMD", "ASUSTeK COMPUTER INC",
            "Corsair", "Apps", "Comms", "ConnectedDevicesPlatform", "CrashDumps", "D3DSCache",
            "IsolatedStorage", "PlaceholderTileLogoFolder", "Programs", "Publishers", "VirtualStore",
            "ToastNotificationManagerCompat", "Backup", "cache", "CEF", "Package", "Sentry", "SquirrelTemp",
            "DMCache", "network-sessions", "npm", "npm-cache", "node-gyp", "nodejs", "kotlin", "java-db",
            "jupyter", "gcloud", "cloud-code", "google-vscode-extension", "main.kts.compiled.cache",
            "eas-cli", "eas-cli-nodejs", "nextjs-nodejs", "vscode-react-native", "ms-playwright-go", "fanal",
            "clerk", "WSL", "wsl", "DockerDesktop", "docker-secrets-engine",
            # User profile folders (not leftover app folders)
            "Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "Favorites", "Links",
            "Saved Games", "Searches", "Contacts", "3D Objects", "OneDrive", "AppData", "Application Data",
            "Local Settings", "NetHood", "PrintHood", "Recent", "SendTo", "Start Menu", "My Documents",
            "source", "repos", "projects", "workspace", "dev", "code", "git", "GitHub",
            "NTUSER.DAT", "ntuser.dat.LOG1", "ntuser.dat.LOG2", "ntuser.ini",
            "IntelGraphicsProfiles", "MicrosoftEdgeBackups", "Roaming", "Local", "LocalLow"
        }

        self.exclude_patterns = [
            re.compile(r"^McInstTemp", re.IGNORECASE),
            re.compile(r"^Mozilla-", re.IGNORECASE),
            re.compile(r"^com\.", re.IGNORECASE),
            re.compile(r"^\."),
            re.compile(r"^crypto_dbg", re.IGNORECASE),
            re.compile(r"-updater$", re.IGNORECASE),
            re.compile(r"-nodejs$", re.IGNORECASE),
        ]

        self._build_ui()
        self._poll_queue()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=tk.X)

        self.scan_btn = ttk.Button(top, text="Scan", command=self.start_scan)
        self.scan_btn.pack(side=tk.LEFT)

        self.delete_leftover_btn = ttk.Button(
            top,
            text="Delete Selected Leftovers",
            command=self.delete_selected_leftovers,
            state=tk.DISABLED,
        )
        self.delete_leftover_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.delete_temp_btn = ttk.Button(
            top,
            text="Clean Selected Temp/Cache",
            command=self.clean_selected_temp_cache,
            state=tk.DISABLED,
        )
        self.delete_temp_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Recycle bin checkbox
        self.use_recycle_bin = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Move to Recycle Bin", variable=self.use_recycle_bin).pack(side=tk.LEFT, padx=(12, 0))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(top, textvariable=self.status_var).pack(side=tk.RIGHT)

        # Second row for size display only
        row2 = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        row2.pack(fill=tk.X)

        # Total size label
        self.total_size_var = tk.StringVar(value="Selected: 0 items, 0 MB")
        ttk.Label(row2, textvariable=self.total_size_var, font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, padx=10)

        panes = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        leftover_frame = ttk.Labelframe(panes, text="Potential Leftover Folders")
        temp_frame = ttk.Labelframe(panes, text="Safe Temp/Cache Cleanup")
        panes.add(leftover_frame, weight=3)
        panes.add(temp_frame, weight=2)

        # Checkbox symbols
        self.CHECK_ON = "☑"
        self.CHECK_OFF = "☐"

        # Leftover tree with checkbox column
        self.leftover_tree = ttk.Treeview(
            leftover_frame,
            columns=("Check", "Folder", "Path", "Base", "Modified", "Items", "SizeMB"),
            show="headings",
            selectmode="none",
        )
        self.leftover_sort_state: dict[str, bool] = {}
        self.leftover_checked: set[str] = set()  # Set of checked item IDs
        self.leftover_all_checked = False

        # Checkbox header
        self.leftover_tree.heading("Check", text=self.CHECK_OFF, command=self._toggle_all_leftovers)
        self.leftover_tree.column("Check", width=30, anchor=tk.CENTER, stretch=False)

        for col, width in [
            ("Folder", 200),
            ("Path", 440),
            ("Base", 180),
            ("Modified", 140),
            ("Items", 80),
            ("SizeMB", 80),
        ]:
            self.leftover_tree.heading(col, text=col, command=lambda c=col: self._sort_leftover_tree(c))
            self.leftover_tree.column(col, width=width, anchor=tk.W)

        y1 = ttk.Scrollbar(leftover_frame, orient=tk.VERTICAL, command=self.leftover_tree.yview)
        self.leftover_tree.configure(yscrollcommand=y1.set)
        self.leftover_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y1.pack(side=tk.RIGHT, fill=tk.Y)

        # Temp tree with checkbox column
        self.temp_tree = ttk.Treeview(
            temp_frame,
            columns=("Check", "Category", "Path", "Items", "SizeMB", "SafeLevel"),
            show="headings",
            selectmode="none",
        )
        self.temp_sort_state: dict[str, bool] = {}
        self.temp_checked: set[str] = set()  # Set of checked item IDs
        self.temp_all_checked = False

        # Checkbox header
        self.temp_tree.heading("Check", text=self.CHECK_OFF, command=self._toggle_all_temp)
        self.temp_tree.column("Check", width=30, anchor=tk.CENTER, stretch=False)

        for col, width in [
            ("Category", 190),
            ("Path", 570),
            ("Items", 80),
            ("SizeMB", 80),
            ("SafeLevel", 180),
        ]:
            self.temp_tree.heading(col, text=col, command=lambda c=col: self._sort_temp_tree(c))
            self.temp_tree.column(col, width=width, anchor=tk.W)

        y2 = ttk.Scrollbar(temp_frame, orient=tk.VERTICAL, command=self.temp_tree.yview)
        self.temp_tree.configure(yscrollcommand=y2.set)
        self.temp_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y2.pack(side=tk.RIGHT, fill=tk.Y)

        # Context menus for copying
        self._setup_context_menus()

    def _sort_leftover_tree(self, col: str) -> None:
        if col == "Check":
            return  # Don't sort by checkbox column
        self._sort_treeview(
            self.leftover_tree,
            col,
            self.leftover_sort_state,
            ("Folder", "Path", "Base", "Modified", "Items", "SizeMB"),
            numeric_cols={"Items", "SizeMB"}
        )

    def _sort_temp_tree(self, col: str) -> None:
        if col == "Check":
            return  # Don't sort by checkbox column
        self._sort_treeview(
            self.temp_tree,
            col,
            self.temp_sort_state,
            ("Category", "Path", "Items", "SizeMB", "SafeLevel"),
            numeric_cols={"Items", "SizeMB"}
        )

    def _sort_treeview(
        self,
        tree: ttk.Treeview,
        col: str,
        sort_state: dict[str, bool],
        all_cols: tuple[str, ...],
        numeric_cols: set[str]
    ) -> None:
        # Toggle sort direction
        ascending = not sort_state.get(col, True)
        sort_state[col] = ascending

        # Get all items
        items = [(tree.set(iid, col), iid) for iid in tree.get_children("")]

        # Sort - numeric or string
        if col in numeric_cols:
            def sort_key(x):
                try:
                    return float(x[0]) if x[0] else 0
                except ValueError:
                    return 0
            items.sort(key=sort_key, reverse=not ascending)
        else:
            items.sort(key=lambda x: x[0].lower(), reverse=not ascending)

        # Rearrange items
        for idx, (_, iid) in enumerate(items):
            tree.move(iid, "", idx)

        # Update headers with arrow symbols
        arrow = " ▲" if ascending else " ▼"
        for c in all_cols:
            if c == col:
                tree.heading(c, text=f"{c}{arrow}")
            else:
                tree.heading(c, text=c)

    def _toggle_all_leftovers(self) -> None:
        """Toggle all checkboxes in leftover tree"""
        items = self.leftover_tree.get_children("")
        if not items:
            return

        self.leftover_all_checked = not self.leftover_all_checked
        
        if self.leftover_all_checked:
            self.leftover_checked = set(items)
            new_symbol = self.CHECK_ON
        else:
            self.leftover_checked.clear()
            new_symbol = self.CHECK_OFF

        # Update header
        self.leftover_tree.heading("Check", text=new_symbol)
        
        # Update all rows
        for iid in items:
            self.leftover_tree.set(iid, "Check", new_symbol)

        self._update_button_states()
        self._update_total_size()

    def _toggle_all_temp(self) -> None:
        """Toggle all checkboxes in temp tree"""
        items = self.temp_tree.get_children("")
        if not items:
            return

        self.temp_all_checked = not self.temp_all_checked
        
        if self.temp_all_checked:
            self.temp_checked = set(items)
            new_symbol = self.CHECK_ON
        else:
            self.temp_checked.clear()
            new_symbol = self.CHECK_OFF

        # Update header
        self.temp_tree.heading("Check", text=new_symbol)
        
        # Update all rows
        for iid in items:
            self.temp_tree.set(iid, "Check", new_symbol)

        self._update_button_states()
        self._update_total_size()

    def _toggle_leftover_checkbox(self, event) -> None:
        """Toggle individual checkbox in leftover tree"""
        region = self.leftover_tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        
        col = self.leftover_tree.identify_column(event.x)
        if col != "#1":  # First column (Check)
            return
        
        iid = self.leftover_tree.identify_row(event.y)
        if not iid:
            return

        if iid in self.leftover_checked:
            self.leftover_checked.discard(iid)
            self.leftover_tree.set(iid, "Check", self.CHECK_OFF)
        else:
            self.leftover_checked.add(iid)
            self.leftover_tree.set(iid, "Check", self.CHECK_ON)

        # Update header checkbox state
        all_items = set(self.leftover_tree.get_children(""))
        if self.leftover_checked == all_items and all_items:
            self.leftover_all_checked = True
            self.leftover_tree.heading("Check", text=self.CHECK_ON)
        else:
            self.leftover_all_checked = False
            self.leftover_tree.heading("Check", text=self.CHECK_OFF)

        self._update_button_states()
        self._update_total_size()

    def _toggle_temp_checkbox(self, event) -> None:
        """Toggle individual checkbox in temp tree"""
        region = self.temp_tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        
        col = self.temp_tree.identify_column(event.x)
        if col != "#1":  # First column (Check)
            return
        
        iid = self.temp_tree.identify_row(event.y)
        if not iid:
            return

        if iid in self.temp_checked:
            self.temp_checked.discard(iid)
            self.temp_tree.set(iid, "Check", self.CHECK_OFF)
        else:
            self.temp_checked.add(iid)
            self.temp_tree.set(iid, "Check", self.CHECK_ON)

        # Update header checkbox state
        all_items = set(self.temp_tree.get_children(""))
        if self.temp_checked == all_items and all_items:
            self.temp_all_checked = True
            self.temp_tree.heading("Check", text=self.CHECK_ON)
        else:
            self.temp_all_checked = False
            self.temp_tree.heading("Check", text=self.CHECK_OFF)

        self._update_button_states()
        self._update_total_size()

    def _setup_context_menus(self) -> None:
        # Leftover tree context menu
        self.leftover_menu = tk.Menu(self.root, tearoff=0)
        self.leftover_menu.add_command(label="Copy Folder Name", command=lambda: self._copy_from_tree(self.leftover_tree, 1))
        self.leftover_menu.add_command(label="Copy Full Path", command=lambda: self._copy_from_tree(self.leftover_tree, 2))
        self.leftover_menu.add_command(label="Copy Base Location", command=lambda: self._copy_from_tree(self.leftover_tree, 3))
        self.leftover_menu.add_separator()
        self.leftover_menu.add_command(label="Open in Explorer", command=lambda: self._open_in_explorer(self.leftover_tree, 2))

        self.leftover_tree.bind("<Button-3>", self._show_leftover_menu)
        self.leftover_tree.bind("<Double-1>", self._on_leftover_double_click)
        self.leftover_tree.bind("<Button-1>", self._toggle_leftover_checkbox)

        # Temp tree context menu
        self.temp_menu = tk.Menu(self.root, tearoff=0)
        self.temp_menu.add_command(label="Copy Category", command=lambda: self._copy_from_tree(self.temp_tree, 1))
        self.temp_menu.add_command(label="Copy Path", command=lambda: self._copy_from_tree(self.temp_tree, 2))
        self.temp_menu.add_separator()
        self.temp_menu.add_command(label="Open in Explorer", command=lambda: self._open_in_explorer(self.temp_tree, 2))

        self.temp_tree.bind("<Button-3>", self._show_temp_menu)
        self.temp_tree.bind("<Double-1>", self._on_temp_double_click)
        self.temp_tree.bind("<Button-1>", self._toggle_temp_checkbox)

    def _on_leftover_double_click(self, event) -> None:
        col = self.leftover_tree.identify_column(event.x)
        if col != "#1":  # Not checkbox column
            self._open_in_explorer(self.leftover_tree, 2)

    def _on_temp_double_click(self, event) -> None:
        col = self.temp_tree.identify_column(event.x)
        if col != "#1":  # Not checkbox column
            self._open_in_explorer(self.temp_tree, 2)

    def _update_button_states(self) -> None:
        # Enable/disable buttons based on checked items
        has_leftover_checked = bool(self.leftover_checked)
        has_temp_checked = bool(self.temp_checked)
        
        if has_leftover_checked:
            self.delete_leftover_btn.config(state=tk.NORMAL)
        else:
            self.delete_leftover_btn.config(state=tk.DISABLED)
            
        if has_temp_checked:
            self.delete_temp_btn.config(state=tk.NORMAL)
        else:
            self.delete_temp_btn.config(state=tk.DISABLED)

    def _update_total_size(self) -> None:
        total_size = 0.0
        count = 0

        # Check leftover checked items
        for iid in self.leftover_checked:
            idx = int(iid.split("_")[1])
            if idx < len(self.leftover_items):
                total_size += self.leftover_items[idx].size_mb
                count += 1

        # Check temp checked items
        for iid in self.temp_checked:
            idx = int(iid.split("_")[1])
            if idx < len(self.temp_items):
                total_size += self.temp_items[idx].size_mb
                count += 1

        if total_size >= 1024:
            size_str = f"{total_size / 1024:.2f} GB"
        else:
            size_str = f"{total_size:.2f} MB"

        self.total_size_var.set(f"Selected: {count} items, {size_str}")

    def _show_leftover_menu(self, event) -> None:
        item = self.leftover_tree.identify_row(event.y)
        if item:
            self.leftover_menu.post(event.x_root, event.y_root)
            self._context_menu_item = item

    def _show_temp_menu(self, event) -> None:
        item = self.temp_tree.identify_row(event.y)
        if item:
            self.temp_menu.post(event.x_root, event.y_root)
            self._context_menu_item = item

    def _copy_from_tree(self, tree: ttk.Treeview, col_index: int) -> None:
        # Copy from context menu item
        if hasattr(self, '_context_menu_item') and self._context_menu_item:
            item_values = tree.item(self._context_menu_item, "values")
            if item_values and len(item_values) > col_index:
                text = str(item_values[col_index])
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.status_var.set("Copied to clipboard")

    def _open_in_explorer(self, tree: ttk.Treeview, col_index: int) -> None:
        # For double-click, get clicked item
        item = None
        if hasattr(self, '_context_menu_item') and self._context_menu_item:
            item = self._context_menu_item
        
        if not item:
            return
        
        item_values = tree.item(item, "values")
        if item_values and len(item_values) > col_index:
            path = str(item_values[col_index])
            if os.path.exists(path):
                os.startfile(path)
            elif os.path.exists(os.path.dirname(path)):
                os.startfile(os.path.dirname(path))

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self.scan_queue.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, percent, text = msg
                    self.progress["value"] = percent
                    self.status_var.set(text)
                elif kind == "done":
                    _, leftovers, temps = msg
                    self.leftover_items = leftovers
                    self.temp_items = temps
                    self._populate_tables()
                    self.scan_btn.config(state=tk.NORMAL)
                    # Both buttons disabled until user selects something
                    self.delete_leftover_btn.config(state=tk.DISABLED)
                    self.delete_temp_btn.config(state=tk.DISABLED)
                    self.progress["value"] = 100
                    self.status_var.set(
                        f"Scan complete: {len(self.leftover_items)} leftovers, {len(self.temp_items)} temp/cache entries"
                    )
                elif kind == "error":
                    _, err = msg
                    self.scan_btn.config(state=tk.NORMAL)
                    self.status_var.set("Error")
                    messagebox.showerror("Scan Error", err)
                elif kind == "delete_done":
                    _, ok, failed, fail_msgs, use_recycle = msg
                    self.status_var.set("Deletion complete")
                    self.start_scan()
                    action_past = "Moved to Recycle Bin" if use_recycle else "Permanently deleted"
                    detail = f"✓ {action_past}: {ok} folder(s)"
                    if failed > 0:
                        detail += f"\n✗ Could not delete: {failed} folder(s)"
                        detail += "\n\n(Some files may be in use by other programs)"
                    messagebox.showinfo("Delete Result", detail)
                elif kind == "cleanup_done":
                    _, total_deleted, total_failed, fail_msgs, use_recycle = msg
                    self.status_var.set("Cleanup complete")
                    self.start_scan()
                    action_past = "Moved to Recycle Bin" if use_recycle else "Permanently deleted"
                    detail = f"✓ Cleaned: {total_deleted} file(s)"
                    if total_failed > 0:
                        detail += f"\n✗ Could not clean: {total_failed} file(s)"
                        detail += "\n\n(Some files may be locked or in use.\nClose related programs and try again.)"
                    messagebox.showinfo("Cleanup Result", detail)
        except queue.Empty:
            pass

        self.root.after(150, self._poll_queue)

    def _populate_tables(self) -> None:
        for iid in self.leftover_tree.get_children():
            self.leftover_tree.delete(iid)
        for iid in self.temp_tree.get_children():
            self.temp_tree.delete(iid)

        # Reset checked states
        self.leftover_checked.clear()
        self.temp_checked.clear()
        self.leftover_all_checked = False
        self.temp_all_checked = False
        self.leftover_tree.heading("Check", text=self.CHECK_OFF)
        self.temp_tree.heading("Check", text=self.CHECK_OFF)

        for idx, item in enumerate(self.leftover_items):
            self.leftover_tree.insert(
                "",
                tk.END,
                iid=f"left_{idx}",
                values=(
                    self.CHECK_OFF,
                    item.folder_name,
                    item.full_path,
                    item.base_location,
                    item.last_write_time,
                    item.item_count,
                    f"{item.size_mb:.2f}",
                ),
            )

        for idx, item in enumerate(self.temp_items):
            self.temp_tree.insert(
                "",
                tk.END,
                iid=f"temp_{idx}",
                values=(
                    self.CHECK_OFF,
                    item.category,
                    item.path,
                    item.item_count,
                    f"{item.size_mb:.2f}",
                    item.safe_level,
                ),
            )
        
        self._update_total_size()

    def start_scan(self) -> None:
        self.scan_btn.config(state=tk.DISABLED)
        self.delete_leftover_btn.config(state=tk.DISABLED)
        self.delete_temp_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.status_var.set("Scanning...")

        worker = threading.Thread(target=self._scan_worker, daemon=True)
        worker.start()

    def _scan_worker(self) -> None:
        try:
            installed = self._get_installed_app_names()
            leftovers = self._find_leftover_folders(installed)
            temps = self._find_temp_cache_candidates()
            self.scan_queue.put(("done", leftovers, temps))
        except Exception as exc:
            self.scan_queue.put(("error", str(exc)))

    def _get_installed_app_names(self) -> list[str]:
        names: set[str] = set()
        if winreg is None:
            return []

        hives = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]

        for hive, base in hives:
            try:
                key = winreg.OpenKey(hive, base)
            except OSError:
                continue

            with key:
                count, _, _ = winreg.QueryInfoKey(key)
                for i in range(count):
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        sub_key = winreg.OpenKey(key, sub_name)
                    except OSError:
                        continue

                    with sub_key:
                        try:
                            display_name, _ = winreg.QueryValueEx(sub_key, "DisplayName")
                            if isinstance(display_name, str):
                                cleaned = display_name.strip()
                                if cleaned:
                                    names.add(cleaned)
                        except OSError:
                            pass

        return sorted(names)

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9 ]", " ", text).strip().lower()

    def _matches_exclude_pattern(self, folder_name: str) -> bool:
        for pattern in self.exclude_patterns:
            if pattern.search(folder_name):
                return True
        return False

    def _get_acronym(self, text: str) -> str:
        """Get acronym from text, e.g., 'Internet Download Manager' -> 'idm'"""
        words = text.split()
        if len(words) > 1:
            return ''.join(w[0].lower() for w in words if w)
        return ''

    def _folder_matches_installed_app(self, folder_name: str, installed_names: list[str]) -> bool:
        normalized_folder = self._normalize(folder_name)
        folder_lower = folder_name.lower().strip()
        
        if len(normalized_folder) < 2:
            return True

        folder_words = [w for w in normalized_folder.split() if len(w) >= 2]

        for app in installed_names:
            normalized_app = self._normalize(app)
            app_lower = app.lower().strip()
            
            if len(normalized_app) < 2:
                continue

            # Direct containment check
            if normalized_folder in normalized_app or normalized_app in normalized_folder:
                return True

            # Word intersection check
            app_words = [w for w in normalized_app.split() if len(w) >= 2]
            if set(folder_words).intersection(app_words):
                return True

            # Acronym check: "IDM" matches "Internet Download Manager"
            app_acronym = self._get_acronym(app)
            if app_acronym and len(app_acronym) >= 2:
                if folder_lower == app_acronym or normalized_folder == app_acronym:
                    return True

            # Reverse acronym check: folder "Internet Download Manager" matches app "IDM"
            folder_acronym = self._get_acronym(folder_name)
            if folder_acronym and len(folder_acronym) >= 2:
                if app_lower == folder_acronym or normalized_app == folder_acronym:
                    return True

            # Check if folder starts with significant part of app name
            # e.g., "VLC" matches "VLC media player"
            if len(folder_lower) >= 2 and len(app_words) > 0:
                first_app_word = app_words[0]
                if folder_lower == first_app_word or first_app_word == folder_lower:
                    return True

        return False

    def _safe_list_dir(self, path: str) -> list[os.DirEntry]:
        try:
            with os.scandir(path) as it:
                return list(it)
        except OSError:
            return []

    def _folder_file_size_mb(self, path: str) -> float:
        size = 0
        for entry in self._safe_list_dir(path):
            if entry.is_file(follow_symlinks=False):
                try:
                    size += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    pass
        return round(size / (1024 * 1024), 2)

    def _find_leftover_folders(self, installed: list[str]) -> list[LeftoverItem]:
        scan_paths = [
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("APPDATA", ""),
            r"C:\ProgramData",
            os.path.expanduser("~"),  # User profile folder (C:\Users\username)
        ]
        scan_paths = [p for p in scan_paths if p and os.path.isdir(p)]

        leftovers: list[LeftoverItem] = []
        total = max(len(scan_paths), 1)

        for idx, base in enumerate(scan_paths, start=1):
            self.scan_queue.put(("progress", int((idx - 1) * 70 / total), f"Scanning {base}"))
            folders = [e for e in self._safe_list_dir(base) if e.is_dir(follow_symlinks=False)]

            for folder in folders:
                name = folder.name
                if name in self.exclude_names:
                    continue
                if self._matches_exclude_pattern(name):
                    continue
                if self._folder_matches_installed_app(name, installed):
                    continue

                full = folder.path
                try:
                    modified = datetime.fromtimestamp(folder.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                except OSError:
                    modified = ""

                item_count = len(self._safe_list_dir(full))
                size_mb = self._folder_file_size_mb(full)

                leftovers.append(
                    LeftoverItem(
                        folder_name=name,
                        full_path=full,
                        base_location=base,
                        last_write_time=modified,
                        item_count=item_count,
                        size_mb=size_mb,
                    )
                )

        leftovers.sort(key=lambda x: (x.base_location.lower(), x.folder_name.lower()))
        self.scan_queue.put(("progress", 75, "Scanning safe temp/cache locations"))
        return leftovers

    def _find_temp_cache_candidates(self) -> list[TempItem]:
        items: list[TempItem] = []

        temp_locations = [
            ("User Temp", os.environ.get("TEMP", ""), "Very Safe"),
            ("Windows Temp", r"C:\Windows\Temp", "Very Safe"),
            ("Prefetch Cache", r"C:\Windows\Prefetch", "Safe"),
            ("Thumbnail Cache", os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Windows\Explorer"), "Very Safe"),
            ("Windows Update Cache", r"C:\Windows\SoftwareDistribution\Download", "Safe (stop Windows Update first)"),
            ("Recent Files", os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Recent"), "Very Safe"),
        ]

        for i, (category, path, level) in enumerate(temp_locations, start=1):
            if not path or not os.path.isdir(path):
                continue

            if category == "Thumbnail Cache":
                entries = []
                for entry in self._safe_list_dir(path):
                    if entry.is_file(follow_symlinks=False) and entry.name.lower().startswith("thumbcache_") and entry.name.lower().endswith(".db"):
                        entries.append(entry)
            else:
                entries = self._safe_list_dir(path)

            size = 0
            for entry in entries:
                if entry.is_file(follow_symlinks=False):
                    try:
                        size += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass

            items.append(
                TempItem(
                    category=category,
                    path=path,
                    item_count=len(entries),
                    size_mb=round(size / (1024 * 1024), 2),
                    safe_level=level,
                )
            )
            self.scan_queue.put(("progress", 75 + int(i * 25 / 6), f"Scanned {category}"))

        return items

    def _delete_path_recursive(self, path: str, use_recycle: bool = False) -> tuple[bool, str]:
        if not os.path.exists(path):
            return False, "Path no longer exists"

        try:
            if use_recycle:
                return send_to_recycle_bin(path)
            else:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                return True, "Deleted permanently"
        except Exception as exc:
            return False, str(exc)

    def _clear_folder_contents_only(self, folder_path: str, thumbcache_only: bool = False, use_recycle: bool = False) -> tuple[int, int, list[str]]:
        deleted = 0
        failed = 0
        errors: list[str] = []

        if not os.path.isdir(folder_path):
            return deleted, failed, ["Folder not found"]

        entries = self._safe_list_dir(folder_path)
        for entry in entries:
            try:
                if thumbcache_only:
                    is_target = entry.is_file(follow_symlinks=False) and entry.name.lower().startswith("thumbcache_") and entry.name.lower().endswith(".db")
                    if not is_target:
                        continue

                target = entry.path
                if use_recycle:
                    success, msg = send_to_recycle_bin(target)
                    if success:
                        deleted += 1
                    else:
                        failed += 1
                        errors.append(f"{target}: {msg}")
                else:
                    if entry.is_dir(follow_symlinks=False):
                        shutil.rmtree(target)
                    else:
                        os.remove(target)
                    deleted += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{entry.path}: {exc}")

        return deleted, failed, errors

    def delete_selected_leftovers(self) -> None:
        if not self.leftover_checked:
            messagebox.showinfo("No Selection", "Check one or more leftover folders first.")
            return

        use_recycle = self.use_recycle_bin.get()
        action = "move to Recycle Bin" if use_recycle else "permanently delete"
        
        # Build list of folders to delete for confirmation
        folders_to_delete = []
        for iid in self.leftover_checked:
            idx = int(iid.split("_")[1])
            if idx < len(self.leftover_items):
                folders_to_delete.append(self.leftover_items[idx])

        folder_list = "\n".join([f"• {f.folder_name}" for f in folders_to_delete[:10]])
        if len(folders_to_delete) > 10:
            folder_list += f"\n... and {len(folders_to_delete) - 10} more"

        confirmed = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to {action} these {len(folders_to_delete)} folder(s)?\n\n{folder_list}",
            icon=messagebox.WARNING,
        )
        if not confirmed:
            return

        # Disable buttons during deletion
        self.delete_leftover_btn.config(state=tk.DISABLED)
        self.delete_temp_btn.config(state=tk.DISABLED)
        self.scan_btn.config(state=tk.DISABLED)
        self.status_var.set(f"Deleting {len(folders_to_delete)} folders...")

        # Run deletion in background thread to prevent UI freeze
        def delete_worker():
            ok = 0
            failed = 0
            fail_msgs = []

            for item in folders_to_delete:
                success, msg = self._delete_path_recursive(item.full_path, use_recycle=use_recycle)
                if success:
                    ok += 1
                else:
                    failed += 1
                    fail_msgs.append(f"{item.folder_name}: {msg}")

            # Send results back to main thread
            self.scan_queue.put(("delete_done", ok, failed, fail_msgs, use_recycle))

        threading.Thread(target=delete_worker, daemon=True).start()

    def clean_selected_temp_cache(self) -> None:
        if not self.temp_checked:
            messagebox.showinfo("No Selection", "Check one or more temp/cache rows first.")
            return

        use_recycle = self.use_recycle_bin.get()
        action = "move to Recycle Bin" if use_recycle else "permanently delete"

        confirmed = messagebox.askyesno(
            "Confirm Cleanup",
            f"Clean selected temp/cache entries now?\n\n"
            f"This will {action} contents inside folders.\nIt does NOT delete the temp root folders.",
            icon=messagebox.WARNING,
        )
        if not confirmed:
            return

        # Build list of items to clean
        items_to_clean = []
        for iid in self.temp_checked:
            idx = int(iid.split("_")[1])
            if idx < len(self.temp_items):
                items_to_clean.append(self.temp_items[idx])

        # Disable buttons during cleanup
        self.delete_leftover_btn.config(state=tk.DISABLED)
        self.delete_temp_btn.config(state=tk.DISABLED)
        self.scan_btn.config(state=tk.DISABLED)
        self.status_var.set(f"Cleaning {len(items_to_clean)} temp/cache locations...")

        # Run cleanup in background thread to prevent UI freeze
        def cleanup_worker():
            total_deleted = 0
            total_failed = 0
            fail_msgs = []

            for item in items_to_clean:
                # Safety rule: always delete contents only, never the folder itself.
                thumbcache_only = item.category == "Thumbnail Cache"
                deleted, failed, errors = self._clear_folder_contents_only(
                    item.path, thumbcache_only=thumbcache_only, use_recycle=use_recycle
                )
                total_deleted += deleted
                total_failed += failed
                fail_msgs.extend([f"{item.category}: {e}" for e in errors[:5]])

            # Send results back to main thread
            self.scan_queue.put(("cleanup_done", total_deleted, total_failed, fail_msgs, use_recycle))

        threading.Thread(target=cleanup_worker, daemon=True).start()


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")

    app = LeftoverCleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
