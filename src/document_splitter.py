"""
Document splitter module.
Splits PDF documents based on QR code markers.
"""

import logging
import os
import tempfile
from typing import List, Optional, Tuple

from pdf2image import convert_from_path
from PIL import Image
import pikepdf
from pyzbar import pyzbar
from pyzbar.pyzbar import ZBarSymbol

from config import Config

logger = logging.getLogger(__name__)


class DocumentSplitter:
    """Splits PDF documents based on QR code markers."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def _find_qr_codes(self, image: Image.Image) -> List[str]:
        """
        Find all QR codes in an image and return their decoded content.
        
        Args:
            image: PIL Image to scan
        
        Returns:
            List of decoded QR code contents
        """
        # Convert to RGB if necessary (pyzbar works better with RGB)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Decode QR codes
        decoded_objects = pyzbar.decode(image, symbols=[ZBarSymbol.QRCODE])
        
        contents = []
        for obj in decoded_objects:
            try:
                content = obj.data.decode('utf-8')
                contents.append(content)
                logger.debug(f"Found QR code with content: {content}")
            except UnicodeDecodeError:
                logger.warning("QR code with non-UTF8 content found, skipping")
        
        return contents
    
    def _page_has_split_marker(self, image: Image.Image) -> bool:
        """
        Check if a page contains the split marker QR code.
        
        Args:
            image: PIL Image of the page
        
        Returns:
            True if split marker QR code is found
        """
        qr_contents = self._find_qr_codes(image)
        
        for content in qr_contents:
            if content.strip() == self.config.split_qr_content:
                logger.debug(f"Split marker QR code found: {content}")
                return True
        
        return False
    
    def _find_split_points(self, pdf_path: str) -> List[int]:
        """
        Find all pages that contain the split marker QR code.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            List of page indices (0-based) where splits should occur
        """
        logger.info(f"Scanning for QR code split markers in: {pdf_path}")
        
        # Convert PDF pages to images
        # Use higher DPI for better QR code detection
        images = convert_from_path(pdf_path, dpi=300)
        
        split_points = []
        for i, image in enumerate(images):
            if self._page_has_split_marker(image):
                logger.info(f"Split marker found on page {i + 1}")
                split_points.append(i)
        
        logger.info(f"Found {len(split_points)} split marker(s)")
        return split_points
    
    def split(self, input_path: str, output_dir: str) -> Tuple[List[str], Optional[str]]:
        """
        Split a PDF document based on QR code markers.
        
        Each page with the split marker QR code starts a new document.
        If no split markers are found, returns the original file path.
        
        Args:
            input_path: Path to input PDF
            output_dir: Directory for output files
        
        Returns:
            Tuple of (list of output file paths, error message or None)
        """
        if not self.config.split_qr_enabled:
            logger.debug("QR code splitting disabled")
            return [input_path], None
        
        try:
            # Find split points
            split_points = self._find_split_points(input_path)
            
            # If no split markers found, return original file
            if not split_points:
                logger.info("No split markers found, keeping document as-is")
                return [input_path], None
            
            # Open PDF for splitting
            with pikepdf.Pdf.open(input_path) as pdf:
                total_pages = len(pdf.pages)
                
                # Build list of page ranges for each document
                # Each split point starts a new document
                ranges: List[Tuple[int, int]] = []
                
                # First document: from page 0 to first split point (exclusive)
                # But only if the first page is NOT a split marker
                if split_points[0] > 0:
                    ranges.append((0, split_points[0]))
                
                # Documents starting at each split point
                for i, start_page in enumerate(split_points):
                    # End is either the next split point or end of document
                    if i + 1 < len(split_points):
                        end_page = split_points[i + 1]
                    else:
                        end_page = total_pages
                    
                    ranges.append((start_page, end_page))
                
                logger.info(f"Splitting into {len(ranges)} document(s)")
                
                # Create output files
                output_files = []
                for idx, (start, end) in enumerate(ranges):
                    # Create new PDF with the page range
                    new_pdf = pikepdf.Pdf.new()
                    
                    for page_idx in range(start, end):
                        new_pdf.pages.append(pdf.pages[page_idx])
                    
                    # Generate output filename
                    base_name = os.path.splitext(os.path.basename(input_path))[0]
                    output_filename = f"{base_name}_part{idx + 1:03d}.pdf"
                    output_path = os.path.join(output_dir, output_filename)
                    
                    new_pdf.save(output_path)
                    output_files.append(output_path)
                    
                    logger.info(f"Created split document: {output_path} (pages {start + 1}-{end})")
                
                return output_files, None
        
        except Exception as e:
            error_msg = f"Failed to split document: {e}"
            logger.error(error_msg)
            return [input_path], error_msg
    
    def test_qr_detection(self, pdf_path: str) -> List[Tuple[int, List[str]]]:
        """
        Test QR code detection on a PDF file.
        Useful for debugging.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            List of tuples (page_number, list_of_qr_contents)
        """
        images = convert_from_path(pdf_path, dpi=150)
        results = []
        
        for i, image in enumerate(images):
            qr_contents = self._find_qr_codes(image)
            if qr_contents:
                results.append((i + 1, qr_contents))
        
        return results
