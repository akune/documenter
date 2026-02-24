#!/usr/bin/env python3
"""
CLI tool to import existing documents to Paperless-ngx.

Searches for files matching the pattern YYYY-MM-DD_hh-mm_HASH.pdf
and uploads them to Paperless-ngx with appropriate tags.
"""

import argparse
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False
    
    def load_dotenv(path=None):
        """Fallback: manually load .env file."""
        env_file = path if path else '.env'
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        os.environ[key] = value

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from paperless_uploader import PaperlessUploader

# Regex pattern for filename: YYYY-MM-DD_hh-mm(-ss)?_HASH.pdf
FILENAME_PATTERN = re.compile(
    r'^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})(?:-(\d{2}))?_([a-f0-9]{8})\.pdf$',
    re.IGNORECASE
)


def extract_datetime_from_filename(filename: str) -> Optional[datetime]:
    """
    Extract datetime from a filename matching the pattern YYYY-MM-DD_hh-mm(-ss)?_HASH.pdf.
    
    Args:
        filename: The filename to parse
    
    Returns:
        datetime object if pattern matches, None otherwise
    """
    match = FILENAME_PATTERN.match(filename)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        hour = int(match.group(4))
        minute = int(match.group(5))
        second = int(match.group(6)) if match.group(6) else 0
        return datetime(year, month, day, hour, minute, second)
    return None


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def find_documents(search_path: Path, recursive: bool = True) -> List[Tuple[Path, str, Optional[datetime], str]]:
    """
    Find all documents matching the filename pattern.
    
    Args:
        search_path: Directory to search
        recursive: Whether to search subdirectories
    
    Returns:
        List of (file_path, year_month, created_date, relative_dir) tuples
    """
    documents = []
    
    if recursive:
        pattern = "**/*.pdf"
    else:
        pattern = "*.pdf"
    
    for pdf_path in search_path.glob(pattern):
        match = FILENAME_PATTERN.match(pdf_path.name)
        if match:
            year = match.group(1)
            month = match.group(2)
            year_month = f"{year}-{month}"
            created_date = extract_datetime_from_filename(pdf_path.name)
            
            # Calculate relative directory path from search_path
            try:
                relative_dir = str(pdf_path.parent.relative_to(search_path))
                if relative_dir == '.':
                    relative_dir = ''
            except ValueError:
                relative_dir = ''
            
            documents.append((pdf_path, year_month, created_date, relative_dir))
    
    # Sort by filename for consistent processing
    documents.sort(key=lambda x: x[0].name)
    
    return documents


def import_documents(
    documents: List[Tuple[Path, str, Optional[datetime], str]],
    uploader: PaperlessUploader,
    base_path: Path,
    extra_tags: Optional[List[str]] = None,
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    Import documents to Paperless-ngx.
    
    Args:
        documents: List of (file_path, year_month, created_date, relative_dir) tuples
        uploader: PaperlessUploader instance
        base_path: Base path for calculating relative directory
        extra_tags: Additional tags to apply
        dry_run: If True, don't actually upload
    
    Returns:
        Tuple of (success_count, error_count)
    """
    logger = logging.getLogger(__name__)
    success_count = 0
    error_count = 0
    
    for file_path, year_month, created_date, relative_dir in documents:
        # Use extra_tags if provided (replaces default), otherwise None (uses default from config)
        tags = extra_tags if extra_tags else None
        
        # Title is the filename without extension
        title = file_path.stem
        
        # Build tag context for variable resolution
        tag_context = {
            'directory_path': relative_dir if relative_dir else year_month,
            'year_month': year_month,
        }
        
        if dry_run:
            logger.info(f"[DRY-RUN] Would upload: {file_path.name}")
            logger.info(f"  Title: {title}")
            logger.info(f"  Tags: {tags}")
            logger.info(f"  Context: directory_path={tag_context['directory_path']}")
            if created_date:
                logger.info(f"  Created: {created_date.strftime('%Y-%m-%d %H:%M:%S')}")
            success_count += 1
        else:
            logger.info(f"Uploading: {file_path.name}")
            success, error = uploader.upload(
                str(file_path), 
                title, 
                tags, 
                created_date,
                tag_context=tag_context
            )
            
            if success:
                logger.info(f"  ✓ Uploaded successfully")
                success_count += 1
            else:
                logger.error(f"  ✗ Upload failed: {error}")
                error_count += 1
    
    return success_count, error_count


def main():
    parser = argparse.ArgumentParser(
        description='Import existing documents to Paperless-ngx',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/documents
  %(prog)s /path/to/documents --dry-run
  %(prog)s /path/to/documents --tags Archive --tags '${year_month}'
  %(prog)s /path/to/documents --tags 'Cabinet-${directory_path}' --tags Inbox
  %(prog)s /path/to/documents --group Importers
  %(prog)s /path/to/documents --env /path/to/.env

Tag Variables:
  ${directory_path}  - Relative path from search directory (or year_month if empty)
  ${year_month}      - Year and month from document (YYYY-MM)
  ${filename}        - Document filename
  ${title}           - Document title

Environment variables (can be set in .env file):
  PAPERLESS_URL           - Paperless-ngx server URL
  PAPERLESS_API_TOKEN     - API token for authentication
  PAPERLESS_DEFAULT_TAGS  - Default tags (used when --tags is not specified)
  PAPERLESS_GROUP         - Group to grant document permissions (used when --group is not specified)
"""
    )
    
    parser.add_argument(
        'path',
        type=str,
        help='Path to search for documents (searches recursively)'
    )
    
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Show what would be uploaded without actually uploading'
    )
    
    parser.add_argument(
        '--tags', '-t',
        action='append',
        default=[],
        help='Tags to apply (replaces PAPERLESS_DEFAULT_TAGS, supports variables)'
    )
    
    parser.add_argument(
        '--env', '-e',
        type=str,
        default=None,
        help='Path to .env file (default: .env in current directory)'
    )
    
    parser.add_argument(
        '--no-recursive', '-R',
        action='store_true',
        help='Do not search subdirectories'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--group', '-g',
        type=str,
        default=None,
        help='Group to grant permissions on uploaded documents (overrides PAPERLESS_GROUP)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Load environment variables
    env_path = args.env if args.env else '.env'
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.debug(f"Loaded environment from: {env_path}")
    else:
        logger.debug(f"No .env file found at: {env_path}")
    
    # Validate search path
    search_path = Path(args.path)
    if not search_path.exists():
        logger.error(f"Path does not exist: {args.path}")
        sys.exit(1)
    
    if not search_path.is_dir():
        logger.error(f"Path is not a directory: {args.path}")
        sys.exit(1)
    
    # Find documents
    logger.info(f"Searching for documents in: {search_path}")
    recursive = not args.no_recursive
    documents = find_documents(search_path, recursive=recursive)
    
    if not documents:
        logger.info("No documents found matching pattern YYYY-MM-DD_hh-mm_HASH.pdf")
        sys.exit(0)
    
    logger.info(f"Found {len(documents)} document(s)")
    
    # Create config and uploader
    config = Config()
    
    # Validate Paperless configuration
    if not config.paperless_url:
        logger.error("PAPERLESS_URL is not set")
        sys.exit(1)
    
    if not config.paperless_api_token:
        logger.error("PAPERLESS_API_TOKEN is not set")
        sys.exit(1)
    
    # Create uploader with optional group override
    group_override = args.group if args.group else None
    uploader = PaperlessUploader(config, group_override=group_override)
    
    if group_override:
        logger.info(f"Using group override: {group_override}")
    elif config.paperless_group:
        logger.info(f"Using group from config: {config.paperless_group}")
    
    # Test connection (unless dry-run)
    if not args.dry_run:
        logger.info("Testing Paperless-ngx connection...")
        if not uploader.test_connection():
            logger.error("Failed to connect to Paperless-ngx")
            sys.exit(1)
        logger.info("Connection successful")
    
    # Import documents
    print()  # Empty line for readability
    success, errors = import_documents(
        documents,
        uploader,
        base_path=search_path,
        extra_tags=args.tags if args.tags else None,
        dry_run=args.dry_run
    )
    
    # Summary
    print()
    if args.dry_run:
        logger.info(f"Dry-run complete: {success} document(s) would be uploaded")
    else:
        logger.info(f"Import complete: {success} uploaded, {errors} failed")
    
    # Exit with error code if any failures
    sys.exit(1 if errors > 0 else 0)


if __name__ == '__main__':
    main()
