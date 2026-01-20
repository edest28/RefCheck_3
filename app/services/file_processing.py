"""
File processing utilities for PDF and document extraction.
"""
import os
import tempfile


def extract_text_from_pdf(pdf_data):
    """Extract text from PDF binary data."""
    try:
        # Write to temp file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(pdf_data)
            temp_path = f.name

        try:
            import pdfplumber
            text = ""
            with pdfplumber.open(temp_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text
        except ImportError:
            from pypdf import PdfReader
            reader = PdfReader(temp_path)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return None
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass
