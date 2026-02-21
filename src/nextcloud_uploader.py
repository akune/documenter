"""
Nextcloud uploader module.
Uploads files to Nextcloud via WebDAV.
"""

import logging
from typing import Optional, Tuple
from urllib.parse import quote

import requests
from requests.auth import HTTPBasicAuth

from config import Config

logger = logging.getLogger(__name__)


class NextcloudUploader:
    """Handles file uploads to Nextcloud via WebDAV."""
    
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.nextcloud_url.rstrip('/')
        self.auth = HTTPBasicAuth(config.nextcloud_user, config.nextcloud_password)
        self.timeout = 120  # 2 minutes timeout for large files
    
    def _get_webdav_url(self, path: str) -> str:
        """
        Build WebDAV URL for a given path.
        
        Args:
            path: Remote path (relative to user's files)
        
        Returns:
            Full WebDAV URL
        """
        # Ensure path starts with /
        if not path.startswith('/'):
            path = '/' + path
        
        # URL-encode the path components (but not the slashes)
        encoded_path = '/'.join(quote(part, safe='') for part in path.split('/'))
        
        return f"{self.base_url}/remote.php/dav/files/{self.config.nextcloud_user}{encoded_path}"
    
    def _create_directory(self, remote_path: str) -> bool:
        """
        Create a directory on Nextcloud (MKCOL).
        
        Args:
            remote_path: Path to create
        
        Returns:
            True if created or already exists
        """
        url = self._get_webdav_url(remote_path)
        
        try:
            response = requests.request(
                'MKCOL',
                url,
                auth=self.auth,
                timeout=30
            )
            
            if response.status_code in [201, 405]:  # 201 Created, 405 Already exists
                logger.debug(f"Directory ready: {remote_path}")
                return True
            else:
                logger.error(f"Failed to create directory {remote_path}: {response.status_code} {response.text}")
                return False
        
        except requests.RequestException as e:
            logger.error(f"Error creating directory {remote_path}: {e}")
            return False
    
    def _ensure_directory_path(self, remote_path: str) -> bool:
        """
        Ensure all directories in path exist, creating them if necessary.
        
        Args:
            remote_path: Full path including filename
        
        Returns:
            True if all directories exist or were created
        """
        # Get directory path (remove filename)
        dir_path = '/'.join(remote_path.split('/')[:-1])
        
        if not dir_path:
            return True
        
        # Create each directory level
        parts = dir_path.split('/')
        current_path = ''
        
        for part in parts:
            if not part:
                continue
            current_path += '/' + part
            if not self._create_directory(current_path):
                return False
        
        return True
    
    def upload(self, local_path: str, remote_filename: str, subfolder: str = "") -> Tuple[bool, Optional[str]]:
        """
        Upload a file to Nextcloud.
        
        Args:
            local_path: Path to local file
            remote_filename: Name for the file on Nextcloud
            subfolder: Optional subfolder (e.g., "2024-02" for YYYY-MM)
        
        Returns:
            Tuple of (success, error_message)
        """
        # Build remote path
        target_dir = self.config.nextcloud_target_dir.rstrip('/')
        if subfolder:
            target_dir = f"{target_dir}/{subfolder}"
        
        remote_path = f"{target_dir}/{remote_filename}"
        
        logger.info(f"Uploading to Nextcloud: {remote_path}")
        
        try:
            # Ensure directory exists
            if not self._ensure_directory_path(remote_path):
                return False, "Failed to create target directory"
            
            # Upload file
            url = self._get_webdav_url(remote_path)
            
            with open(local_path, 'rb') as f:
                response = requests.put(
                    url,
                    data=f,
                    auth=self.auth,
                    timeout=self.timeout,
                    headers={'Content-Type': 'application/pdf'}
                )
            
            if response.status_code in [200, 201, 204]:
                logger.info(f"Successfully uploaded to Nextcloud: {remote_path}")
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
        Test connection to Nextcloud.
        
        Returns:
            Tuple of (success, error_message)
        """
        try:
            url = self._get_webdav_url('/')
            response = requests.request(
                'PROPFIND',
                url,
                auth=self.auth,
                headers={'Depth': '0'},
                timeout=30
            )
            
            if response.status_code in [200, 207]:  # 207 Multi-Status is normal for PROPFIND
                logger.info("Nextcloud connection test successful")
                return True, None
            else:
                error_msg = f"Connection test failed: {response.status_code}"
                logger.error(error_msg)
                return False, error_msg
        
        except requests.RequestException as e:
            error_msg = f"Connection error: {e}"
            logger.error(error_msg)
            return False, error_msg
