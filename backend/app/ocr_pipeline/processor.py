"""
This module handles the core OCR processing using Tesseract.
"""

from typing import IO

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path


def preprocess_image_for_ocr(image_stream: IO[bytes]) -> np.ndarray:
    """
    Preprocesses the image to improve OCR accuracy.
    - Converts to grayscale
    - Applies thresholding
    - Removes noise
    """
    image_bytes = np.frombuffer(image_stream.read(), np.uint8)
    img = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Apply adaptive thresholding to handle different lighting conditions
    processed_img = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    # Optional: Denoising
    # processed_img = cv2.medianBlur(processed_img, 3)

    return processed_img


def extract_text_from_image(image_stream: IO[bytes]) -> str:
    """
    Takes an image file stream, preprocesses it, and extracts text using Tesseract.

    Args:
        image_stream: A file-like object containing the image data in bytes.

    Returns:
        The extracted text as a string.
    """
    try:
        # Set the path to the Tesseract executable if it's not in your PATH
        # Example for Windows:
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

        processed_image = preprocess_image_for_ocr(
            image_stream
        )  # Use Tesseract to do OCR on the image
        # We use French ('fra') as the primary language
        custom_config = r"-l fra --oem 3 --psm 6"
        text = pytesseract.image_to_string(processed_image, config=custom_config)

        return text
    except Exception as e:
        print(f"An error occurred during OCR processing: {e}")
        # It might be useful to check if Tesseract is installed and configured correctly.
        try:
            tesseract_version = pytesseract.get_tesseract_version()
            print(f"Tesseract version {tesseract_version} is installed.")
        except pytesseract.TesseractNotFoundError:
            print("Tesseract is not installed or not in your PATH.")
            return "Error: Tesseract is not installed or configured."
        return f"Error processing image: {e}"


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts text from a PDF file by converting it to images and processing with OCR.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        The extracted text as a string (all pages combined).
    """
    try:
        # Set Tesseract path
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

        # Convert PDF to images (one per page)
        print(f"Converting PDF to images: {pdf_path}")
        images = convert_from_path(pdf_path, dpi=300)

        all_text = []

        for i, image in enumerate(images, 1):
            print(f"Processing page {i}/{len(images)}...")

            # Convert PIL Image to numpy array
            img_array = np.array(image)

            # Convert RGB to BGR for OpenCV
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

            # Convert to grayscale
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

            # Apply adaptive thresholding
            processed = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )

            # Extract text with Tesseract
            custom_config = r"-l fra --oem 3 --psm 6"
            text = pytesseract.image_to_string(processed, config=custom_config)

            all_text.append(f"=== PAGE {i} ===\n{text}")

        combined_text = "\n\n".join(all_text)
        print(f"✅ Extracted {len(combined_text)} characters from {len(images)} pages")

        return combined_text

    except Exception as e:
        print(f"Error processing PDF: {e}")
        return f"Error: {e}"
