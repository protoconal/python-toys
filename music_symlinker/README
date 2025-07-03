# Music Metadata Symlinker

A Python script for organizing `.flac` music files into a clean, structured folder hierarchy using symlinks based on metadata (Artist/Album). Tracks are hashed and indexed in a local SQLite database to detect changes and avoid redundant operations.

Generated with ChatGPT

---

## 🚀 Features

- ✅ Batch processing of thousands of `.flac` files
- ✅ Automatically creates symlinks in `Artist/Album/Track.flac` structure
- ✅ Audio-level MD5 hashing from FLAC stream (not file hash)
- ✅ SQLite3 database tracking
- ✅ Windows-compatible with automatic elevation
- ✅ Dry-run mode for safe previewing
- ✅ Safe filename handling to avoid collisions
- ✅ Automatically removes broken symlinks and empty folders

---

## 🧰 Requirements

- Python 3.8+
- [`mutagen`](https://pypi.org/project/mutagen/) (install via `pip install mutagen`)

---

## 🧪 Running Tests

```bash
python3 -m unittest test_symlinker.py
```

Tests include:
- FLAC metadata parsing
- Safe symlink naming
- Database insert/update
- Symlink logic (mocked on Windows/Linux)

---

## 🛠 Usage

### 🔁 Simple One-Click Run
```bash
python3 symlinker.py
```
This will:
- Read from `./input_music`
- Write symlinks to `./linked_music`
- Use `./music_metadata.db` for the database

### 🔧 CLI Options

```bash
python3 symlinker.py \
  --input ./music \
  --output ./symlinks \
  --db ./db.sqlite3 \
  --batch-size 500 \
  --verbosity 2 \
  --safe-filenames \
  --dry-run \
  --sanitizer-length 50
```

| Option              | Description |
|---------------------|-------------|
| `--input`           | Source folder to scan for `.flac` files |
| `--output`          | Where to write the symlink structure |
| `--db`              | SQLite3 DB file to store track info |
| `--batch-size`      | Limit memory by processing N files per chunk |
| `--verbosity`       | 0=warning, 1=info, 2=debug, 3=trace |
| `--log-file`        | Write logs to a file |
| `--dry-run`         | Simulate without writing or symlinking |
| `--safe-filenames`  | Avoid collisions with short hashes |
| `--sanitizer-length`| Trim long names before filesystem use |

---

## ⚠ Windows Notes

On Windows, creating symlinks usually requires Administrator permissions. This script:
- Automatically checks for elevation
- Relaunches itself with elevated permissions using the Windows shell

No additional setup required.

---

## 🧹 Example Folder Structure

```
linked_music/
├── Radiohead/
│   └── OK Computer/
│       ├── Paranoid Android.flac -> ../../../input_music/track1.flac
│       └── No Surprises.flac -> ../../../input_music/track2.flac
```

---

## 🧼 Maintenance

Symlinks are removed if:
- The source track metadata changes
- The original file is missing
- Folders are found to be empty after cleanup

---

## 👨‍💻 Credits
Developed using ChatGPT + Python ❤️

---

## 📝 License
MIT License (feel free to reuse, modify, and share)

