"""
PDF processing module.
Handles blank page detection/removal, deskewing, cleaning, and OCR.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import ocrmypdf
from pdf2image import convert_from_path
from PIL import Image
import pikepdf

from config import Config

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Handles PDF processing: blank page removal, deskewing, cleaning, and OCR."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def process(self, input_path: str, output_path: str) -> Tuple[bool, Optional[str]]:
        """
        Process a PDF file: remove blank pages, deskew, clean, and OCR.
        
        Args:
            input_path: Path to input PDF
            output_path: Path for output PDF
        
        Returns:
            Tuple of (success, error_message)
        """
        logger.info(f"Processing PDF: {input_path}")
        
        try:
            # Create temp directory for intermediate files
            with tempfile.TemporaryDirectory(dir=self.config.temp_dir) as temp_dir:
                current_file = input_path
                
                # Step 1: Remove blank pages if enabled
                if self.config.blank_page_removal:
                    blank_removed_path = os.path.join(temp_dir, "blank_removed.pdf")
                    pages_removed = self._remove_blank_pages(current_file, blank_removed_path)
                    if pages_removed > 0:
                        logger.info(f"Removed {pages_removed} blank page(s)")
                        current_file = blank_removed_path
                    elif pages_removed == 0:
                        logger.debug("No blank pages found")
                    else:
                        logger.warning("Blank page removal failed, continuing with original")
                
                # Step 2: OCR with deskew and clean
                success, error = self._run_ocr(current_file, output_path)
                if not success:
                    return False, error
                
                logger.info(f"Successfully processed PDF: {output_path}")
                return True, None
        
        except Exception as e:
            error_msg = f"Failed to process PDF: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def preprocess(self, input_path: str, output_path: str) -> Tuple[bool, Optional[str]]:
        """
        Preprocess a PDF file: remove blank pages only (no OCR).
        This is used before document splitting to preserve QR codes.
        
        Args:
            input_path: Path to input PDF
            output_path: Path for output PDF
        
        Returns:
            Tuple of (success, error_message)
        """
        logger.info(f"Preprocessing PDF (blank removal only): {input_path}")
        
        try:
            if self.config.blank_page_removal:
                pages_removed = self._remove_blank_pages(input_path, output_path)
                if pages_removed > 0:
                    logger.info(f"Removed {pages_removed} blank page(s)")
                elif pages_removed == 0:
                    logger.debug("No blank pages found")
                    # Copy original to output
                    import shutil
                    shutil.copy2(input_path, output_path)
                else:
                    logger.warning("Blank page removal failed, copying original")
                    import shutil
                    shutil.copy2(input_path, output_path)
            else:
                # No preprocessing needed, just copy
                import shutil
                shutil.copy2(input_path, output_path)
            
            return True, None
        
        except Exception as e:
            error_msg = f"Failed to preprocess PDF: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def ocr_only(self, input_path: str, output_path: str) -> Tuple[bool, Optional[str]]:
        """
        Run OCR only (no blank page removal).
        Used after document splitting.
        
        Args:
            input_path: Path to input PDF
            output_path: Path for output PDF
        
        Returns:
            Tuple of (success, error_message)
        """
        logger.info(f"Running OCR: {input_path}")
        
        try:
            success, error = self._run_ocr(input_path, output_path)
            if not success:
                return False, error
            
            logger.info(f"Successfully OCR'd PDF: {output_path}")
            return True, None
        
        except Exception as e:
            error_msg = f"Failed to OCR PDF: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def _has_split_marker_qr(self, image: Image.Image) -> bool:
        """
        Check if a page contains a QR code split marker.
        This prevents split marker pages from being removed as blank.
        
        Args:
            image: PIL Image of the page
        
        Returns:
            True if split marker QR code is found
        """
        if not self.config.split_qr_enabled:
            return False
        
        try:
            from pyzbar import pyzbar
            from pyzbar.pyzbar import ZBarSymbol
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Decode QR codes
            decoded_objects = pyzbar.decode(image, symbols=[ZBarSymbol.QRCODE])
            
            for obj in decoded_objects:
                try:
                    content = obj.data.decode('utf-8')
                    if content.strip() == self.config.split_qr_content:
                        logger.debug(f"Page has split marker QR code: {content}")
                        return True
                except UnicodeDecodeError:
                    pass
        except Exception as e:
            logger.debug(f"Error checking for split marker: {e}")
        
        return False
    
    def _remove_blank_pages(self, input_path: str, output_path: str) -> int:
        """
        Remove blank pages from PDF.
        Pages with split marker QR codes are preserved even if they appear blank.
        
        Args:
            input_path: Path to input PDF
            output_path: Path for output PDF
        
        Returns:
            Number of pages removed, or -1 on error
        """
        try:
            # Convert PDF pages to images for analysis
            logger.debug(f"Converting PDF to images for blank detection: {input_path}")
            images = convert_from_path(input_path, dpi=150)  # Higher DPI for QR detection
            
            # Open PDF for page manipulation
            with pikepdf.Pdf.open(input_path) as pdf:
                if len(pdf.pages) != len(images):
                    logger.warning("Page count mismatch between PDF and images")
                    return -1
                
                # Find non-blank pages (and preserve pages with split markers)
                pages_to_keep: List[int] = []
                for i, image in enumerate(images):
                    # Always keep pages with split marker QR codes
                    if self._has_split_marker_qr(image):
                        logger.debug(f"Page {i + 1} has split marker QR, keeping")
                        pages_to_keep.append(i)
                    elif not self._is_blank_page(image):
                        pages_to_keep.append(i)
                    else:
                        logger.debug(f"Page {i + 1} detected as blank")
                
                pages_removed = len(pdf.pages) - len(pages_to_keep)
                
                # If all pages are blank, keep the first one
                if not pages_to_keep:
                    logger.warning("All pages detected as blank, keeping first page")
                    pages_to_keep = [0]
                    pages_removed = len(pdf.pages) - 1
                
                # Create new PDF with non-blank pages only if pages were removed
                if pages_removed > 0:
                    new_pdf = pikepdf.Pdf.new()
                    for page_idx in pages_to_keep:
                        new_pdf.pages.append(pdf.pages[page_idx])
                    new_pdf.save(output_path)
                else:
                    # No blank pages, copy original
                    import shutil
                    shutil.copy2(input_path, output_path)
                
                return pages_removed
        
        except Exception as e:
            logger.error(f"Error removing blank pages: {e}")
            return -1
    
    def _is_blank_page(self, image: Image.Image) -> bool:
        """
        Check if a page image is blank using multiple methods.
        
        Uses a combination of:
        1. Content ratio: percentage of dark pixels (actual content)
        2. Edge detection: detect text/graphics edges
        3. Margin cropping: ignore scanner borders
        
        Args:
            image: PIL Image of the page
        
        Returns:
            True if page is blank
        """
        import numpy as np
        
        # Convert to grayscale
        grayscale = image.convert('L')
        
        # Get image dimensions and crop margins (10% on each side)
        # This helps ignore scanner borders and shadows
        width, height = grayscale.size
        margin_x = int(width * 0.1)
        margin_y = int(height * 0.1)
        cropped = grayscale.crop((margin_x, margin_y, width - margin_x, height - margin_y))
        
        # Convert to numpy array for faster processing
        pixels = np.array(cropped)
        
        # Method 1: Count dark pixels (potential content)
        # Pixels darker than 200 (out of 255) are considered "dark" / potential content
        dark_threshold = 200
        dark_pixels = np.sum(pixels < dark_threshold)
        total_pixels = pixels.size
        dark_ratio = dark_pixels / total_pixels
        
        # Method 2: Edge detection using gradient magnitude
        # Calculate horizontal and vertical gradients
        grad_x = np.abs(np.diff(pixels.astype(np.float32), axis=1))
        grad_y = np.abs(np.diff(pixels.astype(np.float32), axis=0))
        
        # Strong edges indicate content (text, graphics)
        edge_threshold = 30  # Minimum gradient to be considered an edge
        edge_pixels_x = np.sum(grad_x > edge_threshold)
        edge_pixels_y = np.sum(grad_y > edge_threshold)
        edge_ratio = (edge_pixels_x + edge_pixels_y) / (2 * total_pixels)
        
        # Method 3: Check for text-like patterns using local contrast
        # Divide image into blocks and check for high contrast blocks
        block_size = 50
        high_contrast_blocks = 0
        total_blocks = 0
        
        for y in range(0, pixels.shape[0] - block_size, block_size):
            for x in range(0, pixels.shape[1] - block_size, block_size):
                block = pixels[y:y+block_size, x:x+block_size]
                block_range = np.max(block) - np.min(block)
                total_blocks += 1
                if block_range > 100:  # High contrast block
                    high_contrast_blocks += 1
        
        contrast_ratio = high_contrast_blocks / max(total_blocks, 1)
        
        # Decision logic:
        # A page is considered blank if ALL of the following are true:
        # - Less than 1% dark pixels (configurable via threshold)
        # - Less than 0.5% edge pixels
        # - Less than 5% high-contrast blocks
        
        # Use config threshold: 0.99 means page must be 99% white
        # So content_threshold is 1 - 0.99 = 0.01 (1%)
        content_threshold = 1 - self.config.blank_page_threshold
        
        is_blank = (
            dark_ratio < content_threshold and
            edge_ratio < 0.005 and
            contrast_ratio < 0.05
        )
        
        logger.debug(
            f"Page analysis: dark_ratio={dark_ratio:.4f} (threshold={content_threshold:.4f}), "
            f"edge_ratio={edge_ratio:.4f}, contrast_ratio={contrast_ratio:.4f}, blank={is_blank}"
        )
        
        return is_blank
    
    def _run_ocr(self, input_path: str, output_path: str) -> Tuple[bool, Optional[str]]:
        """
        Run OCRmyPDF on the input file.
        
        Args:
            input_path: Path to input PDF
            output_path: Path for output PDF
        
        Returns:
            Tuple of (success, error_message)
        """
        try:
            logger.info(f"Running OCR on: {input_path}")
            
            # Parse language string into list (e.g., "deu+eng" -> ["deu", "eng"])
            languages = self.config.ocr_language.split('+')
            
            # Run OCRmyPDF using legacy API (positional arguments)
            # This is compatible with both old and new versions
            result = ocrmypdf.ocr(
                input_path,
                output_path,
                language=languages,
                deskew=self.config.ocr_deskew,
                clean=self.config.ocr_clean,
                rotate_pages=self.config.ocr_rotate_pages,
                skip_text=True,  # Skip pages that already have text
                optimize=1,  # Basic optimization
                progress_bar=False,
            )
            
            if result == ocrmypdf.ExitCode.ok:
                logger.info("OCR completed successfully")
                return True, None
            elif result == ocrmypdf.ExitCode.already_done_ocr:
                logger.info("PDF already has text layer, copying original")
                import shutil
                shutil.copy2(input_path, output_path)
                return True, None
            else:
                error_msg = f"OCRmyPDF returned exit code: {result}"
                logger.error(error_msg)
                return False, error_msg
        
        except ocrmypdf.exceptions.PriorOcrFoundError:
            logger.info("Prior OCR found, copying original")
            import shutil
            shutil.copy2(input_path, output_path)
            return True, None
        
        except Exception as e:
            error_msg = f"OCR failed: {e}"
            logger.error(error_msg)
            return False, error_msg
