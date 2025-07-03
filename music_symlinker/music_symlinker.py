#!/usr/bin/env python3

"""
MIT License

Copyright (c) 2025 protoconal

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import ctypes
import sys
import os
import sqlite3
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Union
from mutagen.flac import FLAC
from itertools import islice
import argparse
import ntpath
import copy
import re

# Generated with ChatGPT

# =========================
# Configuration & Logging
# =========================
logger = logging.getLogger("music_symlinker")


def setup_logging(verbosity: int, log_file: str = None, dry_run: bool = False):
    # Add extra logging level
    addLoggingLevel('TRACE', logging.DEBUG - 5)

    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity == 2:
        level = logging.DEBUG
    elif verbosity >= 3:
        level = logging.TRACE

    handlers = [logging.StreamHandler(sys.stdout)]
    format_string = "%(asctime)s [%(levelname)s] %(message)s"
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode='a', encoding='utf-8'))
    if dry_run:
        if verbosity < 3:
            level = logging.DEBUG
        format_string = "%(asctime)s [%(levelname)s] ==DRYRUN== %(message)s"
    logging.basicConfig(
        level=level,
        format=format_string,
        datefmt="%H:%M:%S",
        handlers=handlers
    )


# https://stackoverflow.com/a/35804945
def addLoggingLevel(levelName, levelNum, methodName=None):
    """
    Comprehensively adds a new logging level to the `logging` module and the
    currently configured logging class.

    `levelName` becomes an attribute of the `logging` module with the value
    `levelNum`. `methodName` becomes a convenience method for both `logging`
    itself and the class returned by `logging.getLoggerClass()` (usually just
    `logging.Logger`). If `methodName` is not specified, `levelName.lower()` is
    used.

    To avoid accidental clobberings of existing attributes, this method will
    raise an `AttributeError` if the level name is already an attribute of the
    `logging` module or if the method name is already present

    Example
    -------
    >>> addLoggingLevel('TRACE', logging.DEBUG - 5)
    >>> logging.getLogger(__name__).setLevel("TRACE")
    >>> logging.getLogger(__name__).trace('that worked')
    >>> logging.trace('so did this')
    >>> logging.TRACE
    5

    """
    if not methodName:
        methodName = levelName.lower()

    if hasattr(logging, levelName):
        raise AttributeError('{} already defined in logging module'.format(levelName))
    if hasattr(logging, methodName):
        raise AttributeError('{} already defined in logging module'.format(methodName))
    if hasattr(logging.getLoggerClass(), methodName):
        raise AttributeError('{} already defined in logger class'.format(methodName))

    # This method was inspired by the answers to Stack Overflow post
    # http://stackoverflow.com/q/2183233/2988730, especially
    # http://stackoverflow.com/a/13638084/2988730
    def logForLevel(self, message, *args, **kwargs):
        if self.isEnabledFor(levelNum):
            self._log(levelNum, message, args, **kwargs)

    def logToRoot(message, *args, **kwargs):
        logging.log(levelNum, message, *args, **kwargs)

    logging.addLevelName(levelNum, levelName)
    setattr(logging, levelName, levelNum)
    setattr(logging.getLoggerClass(), methodName, logForLevel)
    setattr(logging, methodName, logToRoot)


# =========================
# Utility Functions
# =========================
def chunked(iterable, size):
    iterable = iter(iterable)
    while chunk := list(islice(iterable, size)):
        yield chunk


# https://stackoverflow.com/a/46801075
def sanitize_for_path(s: str, sanitizer_length: int):
    # https://stackoverflow.com/q/1033424
    # Remove illegal Windows Characters
    s = "".join(_ for _ in s if _ not in r'\/:*?"<>|')

    # Remove excess whitespace
    s = re.sub('\s{2,}', ' ', s)
    s = s.lstrip(" ")
    s = s.rstrip(" ")

    if len(s) > sanitizer_length:
        s = s[:sanitizer_length]
        # Absolute Limit...
        if len(s) > 250:
            s = s[:250]
        logger.warning(f"Massive String being cut down: {s[:50]}...")
    return s


# =========================
# Elevation on Windows
# =========================
def is_windows():
    return os.name == 'nt'


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception as e:
        logger.error(f"Failed to elevate privileges, exiting with: {e}")
        sys.exit(-1)


def elevate():
    if is_windows() and not is_admin():
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        logger.info("Attempting to restart script with administrator privileges...")
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
        sys.exit(0)


# =========================
# Track Class
# =========================
class Track:
    def __init__(self, filepath: Path, safe_filename: bool = False):
        self.filepath = filepath
        self.filename = ntpath.basename(str(filepath))
        self.metadata_hash = ""
        self.symlink_path = ""
        self.artist_album = ""
        self.album = ""
        self.title = ""
        self.audio_md5 = ""
        self.track_number = 0
        self.safe_filename = safe_filename

        logger.trace(f"Initializing Track: {self.filename}")

        if not filepath.exists():
            logger.warning(f"File does not exist: {filepath}")
            return

        try:
            audio = FLAC(filepath)
            self.artist_album, self.album, self.title, self.track_number = self._read_metadata(audio)
            self.audio_md5 = self._compute_audio_md5(audio)
            self.metadata_hash = self._compute_metadata_hash()
        except Exception as e:
            logger.warning(f"Failed to initialize Track for {filepath}: {e}")

    def _read_metadata(self, audio):
        try:
            artist = audio.get("albumartist", ["Unknown Artist"])[0]
            album = audio.get("album", ["Unknown Album"])[0]
            title = audio.get("title", [self.filepath.stem])[0]
            track_number = audio.get("tracknumber", [0])[0]
            return artist, album, title, track_number
        except Exception as e:
            logger.warning(f"Error reading metadata for {self.filepath}: {e}")
            return "Unknown Artist", "Unknown Album", self.filepath.stem

    def _compute_audio_md5(self, audio):
        try:
            # Signature is returned as integer
            audio_md5 = audio.info.md5_signature
            if audio_md5:
                return hex(audio_md5)
            else:
                logger.warning(f"No audio MD5 signature found for {self.filepath}, using file hash fallback.")
        except Exception as e:
            logger.warning(f"Failed to read audio MD5 from FLAC metadata for {self.filepath}: {e}")
            logger.warning(f"This may be because of data corruption, please review its file integrity.")
            logger.info(f"Fallback: hashing whole file for {self.filepath}: {e}")

        # Fallback: hash full file content (not ideal)
        hasher = hashlib.md5()
        with open(self.filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _compute_metadata_hash(self):
        hasher = hashlib.md5()
        hasher.update(self.filename.encode('utf-8'))
        hasher.update(self.artist_album.encode('utf-8'))
        hasher.update(self.album.encode('utf-8'))
        hasher.update(self.title.encode('utf-8'))
        hasher.update(self.audio_md5.encode('utf-8'))
        return hasher.hexdigest()

    def to_tuple(self):
        return (self.audio_md5, self.metadata_hash, self.artist_album, self.album, self.title, str(self.filepath),
                str(self.symlink_path))

    def get_safe_symlink_name(self, sanitizer_length: int = 80):
        safe_file_tag = ""
        if self.safe_filename:
            safe_file_tag = "-" + self.audio_md5[:4]
        filename = f"{self.title}{safe_file_tag}.flac"
        if len(filename) > sanitizer_length:
            filename = f"{self.track_number}-{self.audio_md5[:4]}.flac"
        if len(filename) > sanitizer_length:
            filename = self.filename
        return sanitize_for_path(filename, sanitizer_length=sanitizer_length)


# =========================
# Database Functions
# =========================
def establish_db_connection(db_path='music_metadata.db') -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            audio_md5 TEXT PRIMARY KEY,
            metadata_hash TEXT,
            artist TEXT,
            album TEXT,
            title TEXT,
            filepath TEXT,
            symlink_path TEXT
        )
    """)
    conn.commit()
    return conn


def update_tracks_in_db(tracks: List[Track], db: sqlite3.Connection, dry_run: bool = False) -> bool:
    if dry_run:
        logger.info(f"Updated {len(tracks)} tracks in the database.")
        return True

    try:
        cursor = db.cursor()
        values = [track.to_tuple() for track in tracks]
        cursor.executemany("""
            INSERT OR REPLACE INTO tracks (audio_md5, metadata_hash, artist, album, title, filepath, symlink_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, values)
        db.commit()
        logger.info(f"Updated {len(tracks)} tracks in the database.")
        return True
    except Exception as e:
        logger.error(f"Failed to bulk update DB: {e}")
        return False


def bulk_compare_with_db(tracks: List[Track], db: sqlite3.Connection) -> Dict[str, Dict[str, Union[bool, Track]]]:
    cursor = db.cursor()
    track_map = {track.audio_md5: track for track in tracks if track.audio_md5}
    hashes = tuple(track_map.keys())
    if not hashes:
        return {}
    placeholder = ",".join("?" for _ in hashes)

    logger.debug(f"Running SELECT for {len(hashes)} tracks by audio_md5.")
    query = f"SELECT * FROM tracks WHERE audio_md5 IN ({placeholder})"
    cursor.execute(query, hashes)
    rows = cursor.fetchall()
    logger.info(f"Found {len(rows)} matching tracks in DB.")

    db_lookup = {}
    # row definiton
    # audio_md5, metadata_hash, artist, album, title, filepath, symlink_path
    for row in rows:
        # Check if DB filepath is still accurate.
        # Grab TrackPath from DB
        track_path = Path(row[5])
        if not track_path.exists():
            # File No Longer exists at DB location, yet it has to somewhere...
            # because we processed the MD5.
            logger.info(f"Mismatch between saved filename in DB for Track '{row[2]} - {row[4]}'.")
            logger.warning(f"Reconstructing Track Info from DB for '{row[2]} - {row[4]}'.")
        else:
            logger.trace(f"Previous Track Info is available for {row[2]} - {row[4]}.")
        # Pull TrackObject from cache.
        track_audio_md5 = row[0]
        previous_track = copy.deepcopy(track_map[track_audio_md5])
        # Update TrackObject with DB data.
        previous_track.artist_album = row[2]
        previous_track.album = row[3]
        previous_track.title = row[4]
        previous_track.filepath = Path(row[5])
        previous_track.symlink_path = Path(row[6])
        previous_track.metadata_hash = row[1]
        db_lookup[row[0]] = previous_track
    logger.debug(f"Finished Processing DB Results.")

    results = {}
    for track in tracks:
        if not track.audio_md5:
            continue
        prev = db_lookup.get(track.audio_md5)
        if prev:
            changed = compare_tracks(track, prev)
            logger.debug(f"HasChanged: {changed} - Track {track.filename} found in DB.")
            results[track.audio_md5] = {"result": changed, "previousTrack": prev}
        else:
            logger.debug(f"Track {track.filename} not found in DB.")
            results[track.audio_md5] = {"result": True, "previousTrack": track}
    return results


def compare_tracks(current: Track, previous: Track) -> bool:
    result = current.metadata_hash != previous.metadata_hash
    if logger.isEnabledFor(logging.TRACE):
        logger.trace(f"{result, current.metadata_hash, previous.metadata_hash}")
        logger.trace(f"new:{current.to_tuple()}")
        logger.trace(f"old:{previous.to_tuple()}")
    return result


# =========================
# Symlink Functions
# =========================
def create_symlink(track: Track, base_dir: str, dry_run: bool, sanitizer_length: int) -> bool:
    try:
        artist, album = [
            sanitize_for_path(_, sanitizer_length=sanitizer_length) for _ in [track.artist_album, track.album]
        ]
        target_dir = Path(base_dir) / artist / album
        symlink_path = target_dir / track.get_safe_symlink_name(sanitizer_length=sanitizer_length)
        if not dry_run:
            _create_symlink(track, target_dir, symlink_path)
        track.symlink_path = symlink_path
        logger.debug(f"Updated Track Object with symlinkpath: {symlink_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create symlink for {track.filepath}: {e}")
        return False


def _create_symlink(track: Track, target_dir: Path, symlink_path: Path):
    target_dir.mkdir(parents=True, exist_ok=True)
    if symlink_path.exists():
        symlink_path.unlink()
        logger.debug(f"Removed existing symlink: {symlink_path}")
    symlink_path.symlink_to(track.filepath.resolve())
    logger.info(f"Created symlink: {symlink_path} -> {track.filepath}")


def remove_symlink(track: Track, baseDir: str, dry_run: bool) -> bool:
    try:
        symlink_path = Path(baseDir) / track.artist_album / track.album / track.filepath.name
        if symlink_path.is_symlink():
            if not dry_run:
                _remove_symlink(symlink_path)
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to remove symlink: {e}")
        return False


def _remove_symlink(symlink_path: Path):
    symlink_path.unlink()
    logger.info(f"Removed symlink: {symlink_path}")


def remove_empty_folders_and_broken_symlinks(path: Path, dry_run: bool) -> (int, int):
    symlinks_removed = 0
    folders_removed = 0
    for root, dirs, files in os.walk(path, topdown=False):
        # Remove broken symlinks in files
        for name in files:
            file_path = Path(root) / name
            if file_path.is_symlink() and not file_path.exists():
                logger.trace(f"Removing broken symlink: {str(file_path)}")
                if not dry_run:
                    _remove_symlink(file_path)
                symlinks_removed += 1

        # Remove broken symlinks in dirs (possible if symlinked dirs exist)
        for d in dirs[:]:
            dir_path = Path(root) / d
            if dir_path.is_symlink() and not dir_path.exists():
                logger.trace(f"Removing broken symlink: {str(dir_path)}")
                if not dry_run:
                    _remove_symlink(dir_path)
                symlinks_removed += 1
                dirs.remove(d)  # Remove from traversal to avoid walking into it

        # Now check for truly empty dirs (after symlink cleanup)
        for d in dirs:
            dir_path = Path(root) / d
            if not any(dir_path.iterdir()):
                logger.trace(f"Removing empty folder: {str(dir_path)}")
                if not dry_run:
                    dir_path.rmdir()
                folders_removed += 1

    return symlinks_removed, folders_removed


# =========================
# Main Function
# =========================
def read_input_directory(path: str, safe_filename: bool) -> List[Track]:
    tracks = []
    for root, _, files in os.walk(path):
        for f in files:
            if f.lower().endswith(".flac"):
                track_path = Path(root) / f
                track = Track(track_path, safe_filename=safe_filename)
                if track.audio_md5:
                    tracks.append(track)
    logger.info(f"Discovered {len(tracks)} FLAC files.")
    logger.debug(f"sys.sizeof(tracks): {sys.getsizeof(tracks)} bytes")
    logger.debug(f"sys.sizeof(tracks): {sys.getsizeof(tracks) / 1e+6} megabytes")
    return tracks


def main(input_dir: str, base_symlink_dir: str, db_path: str, batch_size: int, safe_filename: bool, dry_run: bool,
         sanitizer_length: int):
    start_time = time.time()
    logger.info(f"{datetime.today().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("Starting music metadata symlink manager...")
    db = establish_db_connection(db_path)
    all_tracks = read_input_directory(input_dir, safe_filename=safe_filename)

    logger.info("Initialization - Cleaning up any previous empty folders and broken symlinks.")
    removed_counts = remove_empty_folders_and_broken_symlinks(Path(base_symlink_dir), dry_run=dry_run)
    logger.info(f"Removed {removed_counts[0]} broken symlinks.")
    logger.info(f"Removed {removed_counts[1]} folders.")

    seen_md5s = set()
    total_results = 0
    total_symlinks = 0
    for batch in chunked(all_tracks, batch_size):
        start_batch = time.time()
        compare_results = bulk_compare_with_db(batch, db)

        for track in batch:

            if track.audio_md5 in seen_md5s:
                logger.error(f"Duplicate MD5 detected: {track.audio_md5} in {track.filepath}")
            seen_md5s.add(track.audio_md5)

            result = compare_results.get(track.audio_md5)
            if not result:
                continue
            if result["result"]:
                total_results += 1
                remove_symlink(result["previousTrack"], base_symlink_dir, dry_run=dry_run)
            if create_symlink(track, base_symlink_dir, dry_run=dry_run, sanitizer_length=sanitizer_length):
                total_symlinks += 1

        update_tracks_in_db(batch, db, dry_run=dry_run)
        logger.info(f"Batch processed in {time.time() - start_batch:.2f}s")
    logger.info(f"Processed {total_symlinks} tracks in total.")
    logger.info(f"Created {total_symlinks} symlinks in total.")

    logger.info("Resolving Errors - Cleaning up any new empty folders and broken symlinks.")
    removed_counts = remove_empty_folders_and_broken_symlinks(Path(base_symlink_dir), dry_run=dry_run)
    logger.info(f"Removed {removed_counts[0]} broken symlinks.")
    logger.info(f"Removed {removed_counts[1]} folders.")

    elapsed = time.time() - start_time
    logger.info(f"Finished processing in {elapsed:.2f} seconds.")


# =========================
# CLI Entrypoint
# =========================
if __name__ == "__main__":
    # Must be administrator for symlink creation.
    if is_windows():
        elevate()

    parser = argparse.ArgumentParser(
        description="Organize and symlink FLAC files by metadata. Will always regenerate symlinks.")
    parser.add_argument("--input", default="./input_music",
                        help="Input directory containing FLAC files, default = ./input_music")
    parser.add_argument("--output", default="./linked_music",
                        help="Base directory for symlinks, default = ./linked_music")
    parser.add_argument("--db", default="./music_metadata.db", help="Path to the SQLite database")
    parser.add_argument("--batch-size", type=int, default=500, help="Number of tracks to process at a time")
    parser.add_argument("--verbosity", type=int, default=1,
                        help="Logging verbosity (0=WARNING, 1=INFO, 2=DEBUG, 3=TRACE)")
    parser.add_argument("--log-file", default="./music_log.txt", help="Path to a log file to write output")
    parser.add_argument("--safe-filenames", default=True, action="store_true",
                        help="Ensure symlinks use safe, unique filenames")
    parser.add_argument("--dry-run", default=False, action="store_true", help="Simulate actions without making changes")
    parser.add_argument("--sanitizer-length", type=int, default=50,
                        help="Define maximum string length before being shortened forcibly")
    args = parser.parse_args()

    setup_logging(args.verbosity, args.log_file, args.dry_run)

    main(args.input, args.output, args.db, args.batch_size, args.safe_filenames, args.dry_run, args.sanitizer_length)
