#!/usr/bin/env python3
"""
GenHat Temp Directory Manager
Utility script to manage cached files and logs in the OS temp directory
"""

import os
import sys
import platform
import tempfile
from pathlib import Path
import shutil
from datetime import datetime

def get_genhat_temp_dir() -> Path:
    """Get GenHat temp directory based on OS"""
    system = platform.system()
    if system == "Linux":
        temp_base = Path("/var/tmp")
    elif system == "Windows":
        temp_base = Path(os.environ.get("TEMP", tempfile.gettempdir()))
    elif system == "Darwin":  # macOS
        temp_base = Path(tempfile.gettempdir())
    else:
        temp_base = Path(tempfile.gettempdir())
    
    return temp_base / "genhat"

def get_dir_size(path: Path) -> int:
    """Calculate total size of directory in bytes"""
    total = 0
    try:
        for entry in path.rglob('*'):
            if entry.is_file():
                total += entry.stat().st_size
    except Exception as e:
        print(f"Error calculating size: {e}")
    return total

def format_size(bytes: int) -> str:
    """Format bytes to human readable size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} TB"

def count_files(path: Path) -> tuple:
    """Count files and directories"""
    files = 0
    dirs = 0
    try:
        for entry in path.rglob('*'):
            if entry.is_file():
                files += 1
            elif entry.is_dir():
                dirs += 1
    except Exception as e:
        print(f"Error counting files: {e}")
    return files, dirs

def show_info():
    """Display information about GenHat temp directory"""
    temp_dir = get_genhat_temp_dir()
    
    print("=" * 70)
    print("🎩 GenHat Temp Directory Manager")
    print("=" * 70)
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"GenHat Temp Dir: {temp_dir}")
    print()
    
    if not temp_dir.exists():
        print("❌ GenHat temp directory does not exist")
        print("   (It will be created when you start the backend)")
        return
    
    # Get directory statistics
    size = get_dir_size(temp_dir)
    files, dirs = count_files(temp_dir)
    
    print(f"📊 Statistics:")
    print(f"   Total Size: {format_size(size)}")
    print(f"   Files: {files:,}")
    print(f"   Directories: {dirs:,}")
    print()
    
    # Show subdirectories
    print("📁 Directory Structure:")
    subdirs = [
        ("logs", "Application logs"),
        ("projects", "Cached project data"),
        ("uploads", "Temporary PDF uploads")
    ]
    
    for subdir, description in subdirs:
        subpath = temp_dir / subdir
        if subpath.exists():
            sub_size = get_dir_size(subpath)
            sub_files, sub_dirs = count_files(subpath)
            print(f"   ├─ {subdir}/ - {description}")
            print(f"   │  Size: {format_size(sub_size)}, Files: {sub_files}, Dirs: {sub_dirs}")
        else:
            print(f"   ├─ {subdir}/ - {description} (not created yet)")
    
    print()
    
    # Show recent logs
    log_dir = temp_dir / "logs"
    if log_dir.exists():
        log_files = sorted(log_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
        if log_files:
            print("📝 Recent Log Files:")
            for log_file in log_files[:5]:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                size = log_file.stat().st_size
                print(f"   • {log_file.name} ({format_size(size)}) - {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

def clean_temp(confirm=True):
    """Clean GenHat temp directory"""
    temp_dir = get_genhat_temp_dir()
    
    if not temp_dir.exists():
        print("❌ GenHat temp directory does not exist")
        return
    
    size = get_dir_size(temp_dir)
    files, dirs = count_files(temp_dir)
    
    print("⚠️  Warning: This will delete all cached data!")
    print(f"   Directory: {temp_dir}")
    print(f"   Size: {format_size(size)}")
    print(f"   Files: {files:,}")
    print()
    
    if confirm:
        response = input("Are you sure you want to delete? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Cancelled")
            return
    
    try:
        shutil.rmtree(temp_dir)
        print(f"✅ Deleted: {temp_dir}")
        print(f"   Freed up: {format_size(size)}")
    except Exception as e:
        print(f"❌ Error deleting directory: {e}")

def clean_logs(days=7):
    """Clean log files older than specified days"""
    temp_dir = get_genhat_temp_dir()
    log_dir = temp_dir / "logs"
    
    if not log_dir.exists():
        print("❌ Log directory does not exist")
        return
    
    now = datetime.now().timestamp()
    cutoff = now - (days * 24 * 60 * 60)
    
    deleted = 0
    freed_space = 0
    
    for log_file in log_dir.glob("*.log"):
        if log_file.stat().st_mtime < cutoff:
            size = log_file.stat().st_size
            try:
                log_file.unlink()
                deleted += 1
                freed_space += size
                print(f"🗑️  Deleted: {log_file.name} ({format_size(size)})")
            except Exception as e:
                print(f"❌ Error deleting {log_file.name}: {e}")
    
    if deleted > 0:
        print()
        print(f"✅ Deleted {deleted} log file(s)")
        print(f"   Freed up: {format_size(freed_space)}")
    else:
        print(f"✅ No log files older than {days} days")

def clean_uploads():
    """Clean temporary upload directory"""
    temp_dir = get_genhat_temp_dir()
    upload_dir = temp_dir / "uploads"
    
    if not upload_dir.exists():
        print("❌ Upload directory does not exist")
        return
    
    size = get_dir_size(upload_dir)
    files, dirs = count_files(upload_dir)
    
    if files == 0:
        print("✅ Upload directory is empty")
        return
    
    print(f"⚠️  Warning: This will delete all temporary uploads!")
    print(f"   Directory: {upload_dir}")
    print(f"   Size: {format_size(size)}")
    print(f"   Files: {files:,}")
    print()
    
    response = input("Are you sure you want to delete? (yes/no): ")
    if response.lower() != "yes":
        print("❌ Cancelled")
        return
    
    try:
        shutil.rmtree(upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        print(f"✅ Cleaned upload directory")
        print(f"   Freed up: {format_size(size)}")
    except Exception as e:
        print(f"❌ Error cleaning uploads: {e}")

def main():
    if len(sys.argv) < 2:
        show_info()
        print()
        print("Usage:")
        print("  python temp_manager.py info              - Show directory info")
        print("  python temp_manager.py clean             - Clean all temp data")
        print("  python temp_manager.py clean-logs [days] - Clean old logs (default: 7 days)")
        print("  python temp_manager.py clean-uploads     - Clean temporary uploads")
        print()
        return
    
    command = sys.argv[1].lower()
    
    if command == "info":
        show_info()
    elif command == "clean":
        clean_temp()
    elif command == "clean-logs":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        clean_logs(days)
    elif command == "clean-uploads":
        clean_uploads()
    else:
        print(f"❌ Unknown command: {command}")
        print("   Use: info, clean, clean-logs, or clean-uploads")

if __name__ == "__main__":
    main()
