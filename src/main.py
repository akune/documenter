"""
Main document processor application.
Watches input directory and processes PDF files.
"""

import logging
import os
import queue
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

from config import Config, load_config
from pdf_processor import PDFProcessor
from document_splitter import DocumentSplitter
from nextcloud_uploader import NextcloudUploader
from paperless_uploader import PaperlessUploader
from utils import (
    generate_filename,
    get_year_month_folder,
    wait_for_file_stability,
    ensure_directory,
    safe_delete,
    setup_logging,
)

logger = logging.getLogger(__name__)


class PDFEventHandler(FileSystemEventHandler):
    """Handles file system events for PDF files."""
    
    def __init__(self, processing_queue: queue.Queue):
        super().__init__()
        self.processing_queue = processing_queue
    
    def _is_pdf(self, path: str) -> bool:
        """Check if file is a PDF."""
        return path.lower().endswith('.pdf')
    
    def _should_ignore(self, path: str) -> bool:
        """Check if file should be ignored (e.g., hidden files, temp files)."""
        filename = os.path.basename(path)
        return (
            filename.startswith('.') or
            filename.startswith('~') or
            '.tmp' in filename.lower()
        )
    
    def on_created(self, event: FileCreatedEvent):
        """Handle file creation events."""
        if event.is_directory:
            return
        
        if self._is_pdf(event.src_path) and not self._should_ignore(event.src_path):
            logger.info(f"New PDF detected: {event.src_path}")
            self.processing_queue.put(event.src_path)
    
    def on_moved(self, event: FileMovedEvent):
        """Handle file move events (some scanners create temp files first)."""
        if event.is_directory:
            return
        
        if self._is_pdf(event.dest_path) and not self._should_ignore(event.dest_path):
            logger.info(f"PDF moved to input: {event.dest_path}")
            self.processing_queue.put(event.dest_path)


class DocumentProcessor:
    """Main document processing orchestrator."""
    
    def __init__(self, config: Config):
        self.config = config
        self.pdf_processor = PDFProcessor(config)
        self.document_splitter = DocumentSplitter(config)
        self.nextcloud_uploader = NextcloudUploader(config) if config.nextcloud_enabled else None
        self.paperless_uploader = PaperlessUploader(config) if config.paperless_enabled else None
        self.processing_queue: queue.Queue = queue.Queue()
        self.running = False
    
    def _test_connections(self) -> bool:
        """Test connections to configured services."""
        success = True
        
        if self.nextcloud_uploader:
            ok, error = self.nextcloud_uploader.test_connection()
            if not ok:
                logger.error(f"Nextcloud connection failed: {error}")
                success = False
            else:
                logger.info("Nextcloud connection OK")
        
        if self.paperless_uploader:
            ok, error = self.paperless_uploader.test_connection()
            if not ok:
                logger.error(f"Paperless-ngx connection failed: {error}")
                success = False
            else:
                logger.info("Paperless-ngx connection OK")
        
        return success
    
    def _write_to_output_dir(self, source_path: str, filename: str, year_month: str) -> tuple[bool, str | None]:
        """
        Write a file to the output directory.
        
        Args:
            source_path: Path to the source file
            filename: Target filename
            year_month: Year-month string for subfolder (e.g., "2026-02")
        
        Returns:
            Tuple of (success, error_message)
        """
        import shutil
        
        try:
            # Determine target directory
            if self.config.output_dir_use_subfolders:
                target_dir = os.path.join(self.config.output_dir, year_month)
            else:
                target_dir = self.config.output_dir
            
            # Ensure directory exists
            if not ensure_directory(target_dir):
                return False, f"Failed to create output directory: {target_dir}"
            
            # Copy file
            target_path = os.path.join(target_dir, filename)
            shutil.copy2(source_path, target_path)
            logger.info(f"Written to output directory: {target_path}")
            return True, None
        
        except Exception as e:
            error_msg = f"Failed to write to output directory: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def _process_file(self, input_path: str) -> bool:
        """
        Process a single PDF file.
        
        Args:
            input_path: Path to the input PDF
        
        Returns:
            True if processing was successful
        """
        logger.info(f"Starting processing: {input_path}")
        
        # Wait for file to be fully written
        if not wait_for_file_stability(input_path, self.config.file_stability_seconds, self.config.poll_interval):
            logger.error(f"File not stable or disappeared: {input_path}")
            return False
        
        # Check file still exists
        if not os.path.exists(input_path):
            logger.warning(f"File no longer exists: {input_path}")
            return False
        
        try:
            # Get file date for naming
            file_mtime = os.path.getmtime(input_path)
            file_date = datetime.fromtimestamp(file_mtime)
            year_month = get_year_month_folder(file_date)
            
            # Create temp file for preprocessed output (blank removal only)
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False, dir=self.config.temp_dir) as tmp_file:
                preprocessed_path = tmp_file.name
            
            # List to track all temp files for cleanup
            temp_files_to_cleanup: List[str] = [preprocessed_path]
            
            try:
                # Step 1: Preprocess PDF (blank removal only - preserves QR codes)
                success, error = self.pdf_processor.preprocess(input_path, preprocessed_path)
                if not success:
                    logger.error(f"PDF preprocessing failed: {error}")
                    return False
                
                # Step 2: Split document based on QR code markers (before OCR!)
                # This is done before OCR because OCR cleaning destroys QR codes
                split_output_dir = os.path.join(self.config.temp_dir, "split")
                ensure_directory(split_output_dir)
                
                split_files, split_error = self.document_splitter.split(preprocessed_path, split_output_dir)
                if split_error:
                    logger.warning(f"Document splitting had issues: {split_error}")
                
                # Track split files for cleanup (if different from original)
                if split_files != [preprocessed_path]:
                    temp_files_to_cleanup.extend(split_files)
                
                logger.info(f"Processing {len(split_files)} document(s) after splitting")
                
                # Step 3: OCR each split document and upload
                ocr_output_dir = os.path.join(self.config.temp_dir, "ocr")
                ensure_directory(ocr_output_dir)
                
                all_uploads_successful = True
                for idx, doc_path in enumerate(split_files):
                    # Create OCR output path
                    ocr_output_path = os.path.join(ocr_output_dir, f"ocr_{idx:03d}.pdf")
                    temp_files_to_cleanup.append(ocr_output_path)
                    
                    # Run OCR on this split document
                    success, error = self.pdf_processor.ocr_only(doc_path, ocr_output_path)
                    if not success:
                        logger.error(f"OCR failed for split document {idx + 1}: {error}")
                        all_uploads_successful = False
                        continue
                    
                    # Generate new filename based on OCR'd file
                    new_filename = generate_filename(ocr_output_path, file_date)
                    logger.info(f"Document {idx + 1}/{len(split_files)}: {new_filename}")
                    
                    # Step 4a: Write to output directory
                    if self.config.output_dir_enabled:
                        success, error = self._write_to_output_dir(ocr_output_path, new_filename, year_month)
                        if not success:
                            logger.error(f"Output directory write failed for {new_filename}: {error}")
                            all_uploads_successful = False
                            continue
                    
                    # Step 4b: Upload to Nextcloud
                    if self.nextcloud_uploader:
                        success, error = self.nextcloud_uploader.upload(
                            ocr_output_path,
                            new_filename,
                            subfolder=year_month
                        )
                        if not success:
                            logger.error(f"Nextcloud upload failed for {new_filename}: {error}")
                            all_uploads_successful = False
                            continue
                    
                    # Step 5: Upload to Paperless-ngx
                    if self.paperless_uploader:
                        # Tag context - use year_month as directory_path for processed documents
                        tag_context = {
                            'directory_path': year_month,
                            'year_month': year_month,
                        }
                        success, error = self.paperless_uploader.upload(
                            ocr_output_path,
                            new_filename,
                            created_date=file_date,
                            tag_context=tag_context
                        )
                        if not success:
                            logger.error(f"Paperless-ngx upload failed for {new_filename}: {error}")
                            all_uploads_successful = False
                            continue
                    
                    logger.info(f"Successfully processed: {new_filename}")
                
                if not all_uploads_successful:
                    logger.error("Some uploads failed")
                    return False
                
                # Step 6: Delete source file
                if self.config.delete_source:
                    if safe_delete(input_path):
                        logger.info(f"Deleted source file: {input_path}")
                    else:
                        logger.warning(f"Failed to delete source file: {input_path}")
                
                logger.info(f"Successfully processed: {input_path} -> {len(split_files)} document(s)")
                return True
            
            finally:
                # Clean up all temp files
                for temp_file in temp_files_to_cleanup:
                    safe_delete(temp_file)
                # Clean up split directory
                split_dir = os.path.join(self.config.temp_dir, "split")
                if os.path.isdir(split_dir):
                    import shutil
                    try:
                        shutil.rmtree(split_dir)
                    except Exception as e:
                        logger.warning(f"Failed to clean up split directory: {e}")
                # Clean up OCR directory
                ocr_dir = os.path.join(self.config.temp_dir, "ocr")
                if os.path.isdir(ocr_dir):
                    import shutil
                    try:
                        shutil.rmtree(ocr_dir)
                    except Exception as e:
                        logger.warning(f"Failed to clean up OCR directory: {e}")
        
        except Exception as e:
            logger.exception(f"Error processing {input_path}: {e}")
            return False
    
    def _process_existing_files(self):
        """Process any existing PDF files in the input directory."""
        logger.info(f"Scanning for existing PDFs in: {self.config.input_dir}")
        
        for filename in os.listdir(self.config.input_dir):
            if filename.lower().endswith('.pdf') and not filename.startswith('.'):
                file_path = os.path.join(self.config.input_dir, filename)
                if os.path.isfile(file_path):
                    logger.info(f"Found existing PDF: {file_path}")
                    self.processing_queue.put(file_path)
    
    def _worker_loop(self):
        """Worker thread that processes files from the queue."""
        while self.running:
            try:
                # Get next file with timeout to allow checking running flag
                try:
                    file_path = self.processing_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Process the file
                try:
                    self._process_file(file_path)
                except Exception as e:
                    logger.exception(f"Unhandled error processing {file_path}: {e}")
                finally:
                    self.processing_queue.task_done()
            
            except Exception as e:
                logger.exception(f"Worker loop error: {e}")
    
    def run(self):
        """Main run loop."""
        logger.info("Document Processor starting...")
        logger.info(f"Configuration:\n{self.config}")
        
        # Validate configuration
        errors = self.config.validate()
        if errors:
            for error in errors:
                logger.error(f"Configuration error: {error}")
            sys.exit(1)
        
        # Ensure temp directory exists
        ensure_directory(self.config.temp_dir)
        
        # Test connections
        if not self._test_connections():
            logger.warning("Some connection tests failed, continuing anyway...")
        
        # Start worker thread
        self.running = True
        worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        worker_thread.start()
        
        # Process existing files
        self._process_existing_files()
        
        # Set up file watcher
        event_handler = PDFEventHandler(self.processing_queue)
        observer = Observer()
        observer.schedule(event_handler, self.config.input_dir, recursive=False)
        observer.start()
        
        logger.info(f"Watching for PDFs in: {self.config.input_dir}")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
            observer.stop()
        
        observer.join()
        worker_thread.join(timeout=5.0)
        
        logger.info("Document Processor stopped.")


def main():
    """Main entry point."""
    # Setup logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_logging(log_level)
    
    # Load configuration
    config = load_config()
    
    # Create and run processor
    processor = DocumentProcessor(config)
    processor.run()


if __name__ == "__main__":
    main()
