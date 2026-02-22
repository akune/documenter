"""
Paperless-ngx uploader module.
Uploads documents to Paperless-ngx via REST API.
"""

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from config import Config

logger = logging.getLogger(__name__)

# Regex pattern for document filenames
# Matches: YYYY-MM-DD_hh-mm-ss_HASH.pdf or YYYY-MM-DD_hh-mm_HASH.pdf
FILENAME_PATTERN = re.compile(
    r'^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})(?:-(\d{2}))?_([a-f0-9]{8})\.pdf$',
    re.IGNORECASE
)


def extract_date_from_filename(filename: str) -> Optional[datetime]:
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


class PaperlessUploader:
    """Handles document uploads to Paperless-ngx via REST API."""
    
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.paperless_url.rstrip('/')
        self.headers = {
            'Authorization': f'Token {config.paperless_api_token}',
            'Accept': 'application/json; version=6'
        }
        self.timeout = 120  # 2 minutes timeout for large files
        self._tag_cache: Dict[str, int] = {}  # Cache tag name -> ID mappings
    
    def _get_tag_id(self, tag_name: str) -> Optional[int]:
        """
        Get tag ID by name, creating the tag if it doesn't exist.
        
        Args:
            tag_name: Name of the tag
        
        Returns:
            Tag ID or None on error
        """
        # Check cache first
        if tag_name in self._tag_cache:
            return self._tag_cache[tag_name]
        
        try:
            # Search for existing tag
            response = requests.get(
                f"{self.base_url}/api/tags/",
                headers=self.headers,
                params={'name__iexact': tag_name},
                timeout=30
            )
            
            if response.status_code == 200:
                results = response.json().get('results', [])
                if results:
                    tag_id = results[0]['id']
                    self._tag_cache[tag_name] = tag_id
                    logger.debug(f"Found existing tag '{tag_name}' with ID {tag_id}")
                    return tag_id
            
            # Tag doesn't exist, create it
            response = requests.post(
                f"{self.base_url}/api/tags/",
                headers=self.headers,
                json={'name': tag_name},
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                tag_id = response.json()['id']
                self._tag_cache[tag_name] = tag_id
                logger.info(f"Created new tag '{tag_name}' with ID {tag_id}")
                return tag_id
            else:
                logger.error(f"Failed to create tag '{tag_name}': {response.status_code} {response.text}")
                return None
        
        except requests.RequestException as e:
            logger.error(f"Error getting/creating tag '{tag_name}': {e}")
            return None
    
    def _resolve_tags(self, tag_names: List[str]) -> List[int]:
        """
        Resolve tag names to IDs, creating tags if necessary.
        
        Args:
            tag_names: List of tag names
        
        Returns:
            List of tag IDs (may be shorter if some tags failed)
        """
        tag_ids = []
        for name in tag_names:
            tag_id = self._get_tag_id(name)
            if tag_id is not None:
                tag_ids.append(tag_id)
        return tag_ids
    
    def upload(
        self,
        local_path: str,
        title: str,
        additional_tags: Optional[List[str]] = None,
        created_date: Optional[datetime] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Upload a document to Paperless-ngx.
        
        Args:
            local_path: Path to local file
            title: Document title
            additional_tags: Additional tags beyond the default ones
            created_date: Document creation date (extracted from filename if not provided)
        
        Returns:
            Tuple of (success, error_message)
        """
        # Extract date from filename if not provided
        if created_date is None:
            filename = Path(local_path).name
            created_date = extract_date_from_filename(filename)
            if created_date:
                logger.debug(f"Extracted date from filename: {created_date}")
        
        logger.info(f"Uploading to Paperless-ngx: {title}")
        if created_date:
            logger.info(f"  Created date: {created_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Combine default tags with additional tags
            all_tag_names = list(self.config.paperless_default_tags)
            if additional_tags:
                all_tag_names.extend(additional_tags)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_tags = []
            for tag in all_tag_names:
                if tag not in seen:
                    seen.add(tag)
                    unique_tags.append(tag)
            
            # Resolve tag names to IDs
            tag_ids = self._resolve_tags(unique_tags)
            logger.debug(f"Resolved tags: {dict(zip(unique_tags, tag_ids))}")
            
            # Prepare upload
            url = f"{self.base_url}/api/documents/post_document/"
            
            with open(local_path, 'rb') as f:
                files = {'document': (title, f, 'application/pdf')}
                
                # Build data items as list of tuples to allow multiple values with same key
                data_items = [('title', title)]
                
                # Add created date if available (format: YYYY-MM-DD)
                if created_date:
                    data_items.append(('created', created_date.strftime('%Y-%m-%d')))
                
                # Add tags (paperless-ngx accepts multiple 'tags' fields)
                for tag_id in tag_ids:
                    data_items.append(('tags', str(tag_id)))
                
                response = requests.post(
                    url,
                    headers={'Authorization': f'Token {self.config.paperless_api_token}'},
                    files=files,
                    data=data_items,
                    timeout=self.timeout
                )
            
            if response.status_code in [200, 202]:
                task_id = response.json() if response.text else None
                logger.info(f"Successfully uploaded to Paperless-ngx. Task ID: {task_id}")
                return True, None
            else:
                error_msg = f"Upload failed: {response.status_code} {response.text}"
                logger.error(error_msg)
                return False, error_msg
        
        except requests.RequestException as e:
            error_msg = f"Upload error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def test_connection(self) -> Tuple[bool, Optional[str]]:
        """
        Test connection to Paperless-ngx.
        
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Use /api/tags/ endpoint for connection test as it's more reliable
            # The /api/ root endpoint redirects to schema which may return 406
            response = requests.get(
                f"{self.base_url}/api/tags/",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info("Paperless-ngx connection test successful")
                return True, None
            else:
                error_msg = f"Connection test failed: {response.status_code}"
                logger.error(error_msg)
                return False, error_msg
        
        except requests.RequestException as e:
            error_msg = f"Connection error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def wait_for_consumption(self, task_id: str, timeout: int = 300) -> Tuple[bool, Optional[str]]:
        """
        Wait for a document to be consumed (optional).
        
        Args:
            task_id: Task UUID from upload
            timeout: Maximum seconds to wait
        
        Returns:
            Tuple of (success, error_message)
        """
        if not task_id:
            return True, None
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.base_url}/api/tasks/",
                    headers=self.headers,
                    params={'task_id': task_id},
                    timeout=30
                )
                
                if response.status_code == 200:
                    tasks = response.json().get('results', [])
                    if tasks:
                        task = tasks[0]
                        status = task.get('status')
                        
                        if status == 'SUCCESS':
                            logger.info(f"Document consumption completed: {task_id}")
                            return True, None
                        elif status == 'FAILURE':
                            error_msg = f"Document consumption failed: {task.get('result')}"
                            logger.error(error_msg)
                            return False, error_msg
                
                time.sleep(5)  # Poll every 5 seconds
            
            except requests.RequestException as e:
                logger.warning(f"Error checking task status: {e}")
                time.sleep(5)
        
        return False, f"Timeout waiting for consumption after {timeout} seconds"
