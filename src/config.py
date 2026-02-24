"""
Configuration module for the document processor.
Loads settings from environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import List


def _strip_quotes(value: str) -> str:
    """Strip surrounding single or double quotes from a value."""
    if len(value) >= 2:
        if (value.startswith("'") and value.endswith("'")) or \
           (value.startswith('"') and value.endswith('"')):
            return value[1:-1]
    return value


@dataclass
class Config:
    """Configuration settings loaded from environment variables."""
    
    # Input/Output directories
    input_dir: str = field(default_factory=lambda: os.getenv("INPUT_DIR", "/input"))
    temp_dir: str = field(default_factory=lambda: os.getenv("TEMP_DIR", "/tmp/processing"))
    
    # OCR Settings
    ocr_language: str = field(default_factory=lambda: os.getenv("OCR_LANGUAGE", "deu+eng"))
    ocr_deskew: bool = field(default_factory=lambda: os.getenv("OCR_DESKEW", "true").lower() == "true")
    ocr_clean: bool = field(default_factory=lambda: os.getenv("OCR_CLEAN", "true").lower() == "true")
    ocr_rotate_pages: bool = field(default_factory=lambda: os.getenv("OCR_ROTATE_PAGES", "true").lower() == "true")
    ocr_rotate_pages_threshold: float = field(default_factory=lambda: float(os.getenv("OCR_ROTATE_PAGES_THRESHOLD", "1.0")))
    
    # Blank page detection
    blank_page_threshold: float = field(default_factory=lambda: float(os.getenv("BLANK_PAGE_THRESHOLD", "0.99")))
    blank_page_removal: bool = field(default_factory=lambda: os.getenv("BLANK_PAGE_REMOVAL", "true").lower() == "true")
    
    # QR code document splitting
    split_qr_enabled: bool = field(default_factory=lambda: os.getenv("SPLIT_QR_ENABLED", "true").lower() == "true")
    split_qr_content: str = field(default_factory=lambda: os.getenv("SPLIT_QR_CONTENT", "[dmsqrnd]"))
    
    # Nextcloud settings
    nextcloud_enabled: bool = field(default_factory=lambda: os.getenv("NEXTCLOUD_ENABLED", "true").lower() == "true")
    nextcloud_url: str = field(default_factory=lambda: os.getenv("NEXTCLOUD_URL", ""))
    nextcloud_user: str = field(default_factory=lambda: os.getenv("NEXTCLOUD_USER", ""))
    nextcloud_password: str = field(default_factory=lambda: os.getenv("NEXTCLOUD_PASSWORD", ""))
    nextcloud_target_dir: str = field(default_factory=lambda: os.getenv("NEXTCLOUD_TARGET_DIR", "/Documents/Scans"))
    
    # Paperless-ngx settings
    paperless_enabled: bool = field(default_factory=lambda: os.getenv("PAPERLESS_ENABLED", "true").lower() == "true")
    paperless_url: str = field(default_factory=lambda: os.getenv("PAPERLESS_URL", ""))
    paperless_api_token: str = field(default_factory=lambda: os.getenv("PAPERLESS_API_TOKEN", ""))
    paperless_default_tags: List[str] = field(default_factory=lambda: [
        tag.strip()
        for tag in _strip_quotes(os.getenv("PAPERLESS_DEFAULT_TAGS", "Inbox")).split(",")
        if tag.strip()
    ])
    paperless_group: str = field(default_factory=lambda: os.getenv("PAPERLESS_GROUP", ""))
    
    # Processing settings
    delete_source: bool = field(default_factory=lambda: os.getenv("DELETE_SOURCE", "true").lower() == "true")
    file_stability_seconds: int = field(default_factory=lambda: int(os.getenv("FILE_STABILITY_SECONDS", "5")))
    poll_interval: float = field(default_factory=lambda: float(os.getenv("POLL_INTERVAL", "1.0")))
    
    # Output directory settings
    output_dir_enabled: bool = field(default_factory=lambda: os.getenv("OUTPUT_DIR_ENABLED", "false").lower() == "true")
    output_dir: str = field(default_factory=lambda: os.getenv("OUTPUT_DIR", "/output"))
    output_dir_use_subfolders: bool = field(default_factory=lambda: os.getenv("OUTPUT_DIR_USE_SUBFOLDERS", "true").lower() == "true")
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        if not os.path.isdir(self.input_dir):
            errors.append(f"Input directory does not exist: {self.input_dir}")
        
        if self.output_dir_enabled and not os.path.isdir(self.output_dir):
            errors.append(f"Output directory does not exist: {self.output_dir}")
        
        if self.nextcloud_enabled:
            if not self.nextcloud_url:
                errors.append("NEXTCLOUD_URL is required when Nextcloud is enabled")
            if not self.nextcloud_user:
                errors.append("NEXTCLOUD_USER is required when Nextcloud is enabled")
            if not self.nextcloud_password:
                errors.append("NEXTCLOUD_PASSWORD is required when Nextcloud is enabled")
        
        if self.paperless_enabled:
            if not self.paperless_url:
                errors.append("PAPERLESS_URL is required when Paperless-ngx is enabled")
            if not self.paperless_api_token:
                errors.append("PAPERLESS_API_TOKEN is required when Paperless-ngx is enabled")
        
        return errors
    
    def __str__(self) -> str:
        """Return a safe string representation (without secrets)."""
        return (
            f"Config(\n"
            f"  input_dir={self.input_dir}\n"
            f"  ocr_language={self.ocr_language}\n"
            f"  ocr_deskew={self.ocr_deskew}\n"
            f"  ocr_clean={self.ocr_clean}\n"
            f"  ocr_rotate_pages={self.ocr_rotate_pages}\n"
            f"  ocr_rotate_pages_threshold={self.ocr_rotate_pages_threshold}\n"
            f"  blank_page_removal={self.blank_page_removal}\n"
            f"  blank_page_threshold={self.blank_page_threshold}\n"
            f"  split_qr_enabled={self.split_qr_enabled}\n"
            f"  split_qr_content={self.split_qr_content}\n"
            f"  nextcloud_enabled={self.nextcloud_enabled}\n"
            f"  nextcloud_url={self.nextcloud_url}\n"
            f"  nextcloud_target_dir={self.nextcloud_target_dir}\n"
            f"  paperless_enabled={self.paperless_enabled}\n"
            f"  paperless_url={self.paperless_url}\n"
            f"  paperless_default_tags={self.paperless_default_tags}\n"
            f"  paperless_group={self.paperless_group}\n"
            f"  output_dir_enabled={self.output_dir_enabled}\n"
            f"  output_dir={self.output_dir}\n"
            f"  output_dir_use_subfolders={self.output_dir_use_subfolders}\n"
            f"  delete_source={self.delete_source}\n"
            f")"
        )


def load_config() -> Config:
    """Load and return configuration from environment variables."""
    return Config()
