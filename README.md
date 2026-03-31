<div align="center">

# 🧹 Leftover App Folder Finder

**A Windows utility to detect and clean orphaned application folders and temporary files**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 📋 Overview

**Leftover App Folder Finder** is a GUI-based Windows utility that identifies orphaned application folders left behind after software uninstallation and provides safe cleanup options for temporary/cache files.

<details>
<summary><strong>Key Features</strong></summary>

- 🔍 **Smart Detection** — Scans common installation directories and cross-references with Windows Registry
- 🗑️ **Safe Deletion** — Option to move files to Recycle Bin instead of permanent deletion
- 📊 **Detailed Analysis** — Shows folder size, item count, and last modified date
- 🧹 **Temp Cleanup** — Identifies safe-to-delete temporary and cache files
- ✅ **Checkbox Selection** — Select individual items or toggle all at once
- 📋 **Context Menu** — Right-click to copy paths or open in Explorer

</details>

---

## 🎬 Demo

<div align="center">

https://github.com/user-attachments/assets/b2a1b7b6-c3d4-4e5f-a6b7-8c9d0e1f2a3b

</div>

> **Note:** Replace the video URL above with your actual GitHub video link after uploading `Demo.mp4` to your repository.

---

## 🚀 Getting Started

### Prerequisites

- **Windows 10/11**
- **Python 3.10+**
- No external dependencies required (uses standard library only)

### Installation

```bash
# Clone or download the repository
git clone https://github.com/yourusername/leftover-cleaner.git

# Navigate to the directory
cd leftover-cleaner

# Run the application
python LeftoverCleanerGUI.py
```

---

## 📖 Usage

<table>
<tr>
<th>Step</th>
<th>Action</th>
</tr>
<tr>
<td><strong>1</strong></td>
<td>Click <code>Scan</code> to analyze your system</td>
</tr>
<tr>
<td><strong>2</strong></td>
<td>Review detected leftover folders and temp files</td>
</tr>
<tr>
<td><strong>3</strong></td>
<td>Check items you want to remove (click checkbox column)</td>
</tr>
<tr>
<td><strong>4</strong></td>
<td>Enable <code>Move to Recycle Bin</code> for safe deletion (recommended)</td>
</tr>
<tr>
<td><strong>5</strong></td>
<td>Click <code>Delete Selected Leftovers</code> or <code>Clean Selected Temp/Cache</code></td>
</tr>
</table>

### Scanned Locations

| Category | Paths |
|----------|-------|
| **Leftover Folders** | `C:\Program Files`, `C:\Program Files (x86)`, `%LOCALAPPDATA%`, `%APPDATA%`, `C:\ProgramData` |
| **Temp/Cache** | User Temp, Windows Temp, Prefetch, Thumbnail Cache, Windows Update Cache, Recent Files |

---

## ⚙️ How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    SCAN PROCESS                             │
├─────────────────────────────────────────────────────────────┤
│  1. Query Windows Registry for installed applications       │
│  2. Scan common installation directories                    │
│  3. Filter out system folders and known safe directories    │
│  4. Match folder names against installed app names          │
│  5. Flag unmatched folders as potential leftovers           │
│  6. Scan temp/cache locations for cleanup candidates        │
└─────────────────────────────────────────────────────────────┘
```

### Smart Matching Algorithm

- **Direct name matching** — Checks if folder name contains or is contained in app name
- **Word intersection** — Matches common words between folder and app names
- **Acronym detection** — Matches "IDM" with "Internet Download Manager"
- **Exclusion patterns** — Filters known system folders and common patterns

---

## 🛡️ Safety Features

<table>
<tr>
<td>✅</td>
<td><strong>Recycle Bin Support</strong> — Files can be recovered if deleted accidentally</td>
</tr>
<tr>
<td>✅</td>
<td><strong>Confirmation Dialogs</strong> — Always asks before deletion</td>
</tr>
<tr>
<td>✅</td>
<td><strong>Exclusion List</strong> — System folders are automatically excluded</td>
</tr>
<tr>
<td>✅</td>
<td><strong>Safe Levels</strong> — Temp items are labeled with safety indicators</td>
</tr>
<tr>
<td>✅</td>
<td><strong>Contents Only</strong> — Temp cleanup only removes contents, not root folders</td>
</tr>
</table>

---

## 📁 Project Structure

```
LeftOverFile/
├── LeftoverCleanerGUI.py   # Main application
└── README.md               # Documentation
```

---

## ⚠️ Disclaimer

> **Use at your own risk.** While this tool includes safety features, always review items before deletion. The developer is not responsible for any data loss. It is recommended to keep the "Move to Recycle Bin" option enabled.

---

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Made with ❤️ for Windows users**

</div>
