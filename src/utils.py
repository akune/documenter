"""
Utility functions for the document processor.
"""

import hashlib
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def calculate_md5(file_path: str) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def generate_filename(file_path: str, date: Optional[datetime] = None) -> str:
    """
    Generate filename in format YYYY-MM-DD_hh-mm_HASH.pdf
    
    Args:
        file_path: Path to the file
        date: Optional date to use, defaults to file modification time or current time
    
    Returns:
        Formatted filename (e.g., 2026-02-21_14-30_a1b2c3d4.pdf)
    """
    # Get date from file modification time or use current time
    if date is None:
        try:
            mtime = os.path.getmtime(file_path)
            date = datetime.fromtimestamp(mtime)
        except OSError:
            date = datetime.now()
    
    # Calculate MD5 hash (shortened to 8 characters)
    file_hash = calculate_md5(file_path)[:8]
    
    # Format filename with date, time including seconds (24h format), and short hash
    return f"{date.strftime('%Y-%m-%d_%H-%M-%S')}_{file_hash}.pdf"


def get_year_month_folder(date: Optional[datetime] = None) -> str:
    """
    Get folder name in format YYYY-MM
    
    Args:
        date: Optional date, defaults to current time
    
    Returns:
        Folder name in YYYY-MM format
    """
    if date is None:
        date = datetime.now()
    return date.strftime("%Y-%m")


def wait_for_file_stability(file_path: str, stability_seconds: int = 5, poll_interval: float = 1.0) -> bool:
    """
    Wait until file size stops changing (file is fully written).
    
    Args:
        file_path: Path to the file to check
        stability_seconds: Seconds the file must be stable
        poll_interval: Interval between size checks
    
    Returns:
        True if file is stable, False if file was deleted or error occurred
    """
    logger.debug(f"Waiting for file stability: {file_path}")
    
    try:
        last_size = -1
        stable_count = 0
        required_checks = int(stability_seconds / poll_interval)
        
        while stable_count < required_checks:
            if not os.path.exists(file_path):
                logger.warning(f"File disappeared while waiting: {file_path}")
                return False
            
            current_size = os.path.getsize(file_path)
            
            if current_size == last_size:
                stable_count += 1
            else:
                stable_count = 0
                last_size = current_size
            
            time.sleep(poll_interval)
        
        logger.debug(f"File is stable: {file_path}")
        return True
    
    except Exception as e:
        logger.error(f"Error waiting for file stability: {e}")
        return False


def ensure_directory(path: str) -> bool:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Directory path
    
    Returns:
        True if directory exists or was created
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create directory {path}: {e}")
        return False


def safe_delete(file_path: str) -> bool:
    """
    Safely delete a file.
    
    Args:
        file_path: Path to file to delete
    
    Returns:
        True if deleted successfully
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
            return True
        return True  # File already doesn't exist
    except Exception as e:
        logger.error(f"Failed to delete {file_path}: {e}")
        return False


def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
