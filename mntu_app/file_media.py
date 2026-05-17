import base64
import os
import tempfile

import fitz
from docx2pdf import convert

from mntu_app.config import REQUEST_TIMEOUT
from mntu_app.istu_library import get_parser

def pdf_pages_to_base64(pdf_path: str, max_pages=2) -> list[str]:
    doc = fitz.open(pdf_path)
    if doc.page_count < 1:
        doc.close()
        return []
    if doc.page_count == 1:
        pages = [doc[0]]
    else:
        pages = [doc[-2], doc[-1]]
    result_images: list[str] = []
    for page in pages:
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        result_images.append(f"data:image/png;base64,{b64}")
    doc.close()
    return result_images

def docx_to_pdf_images(docx_bytes: bytes) -> list[str]:
    temp_docx_path = None
    temp_pdf_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_docx:
            temp_docx.write(docx_bytes)
            temp_docx_path = temp_docx.name

        temp_pdf_path = tempfile.mktemp(suffix=".pdf")

        try:
            convert(temp_docx_path, temp_pdf_path)

            if not os.path.exists(temp_pdf_path) or os.path.getsize(temp_pdf_path) == 0:
                print(f"[WARN] PDF файл не був створений або порожній")
                return []
        except Exception as conv_error:
            print(f"[WARN] Не вдалося конвертувати docx в PDF: {conv_error}")

            return []

        try:
            doc = fitz.open(temp_pdf_path)
        except Exception as pdf_error:
            print(f"[WARN] Не вдалося відкрити PDF: {pdf_error}")
            return []
        images = []
        for page_num in range(doc.page_count):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            images.append(f"data:image/png;base64,{b64}")
        doc.close()

        return images
    except Exception as e:
        print(f"[EXCEPTION] Помилка конвертації docx: {e}")
        return []
    finally:

        try:
            if temp_docx_path and os.path.exists(temp_docx_path):
                os.unlink(temp_docx_path)
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                os.unlink(temp_pdf_path)
        except:
            pass

async def get_last_2_pages_content(file_url: str) -> tuple[list[str], bytes]:
    p = get_parser()
    if p is None:
        return [], None
    try:
        response = p.session.get(file_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        content_disp = response.headers.get("Content-Disposition", "").lower()
        if (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type
            or file_url.lower().endswith(".docx")
            or ".docx" in content_disp
        ):
            return [], response.content
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_pdf.write(response.content)
            temp_pdf_path = temp_pdf.name
        images = pdf_pages_to_base64(temp_pdf_path)
        try:
            os.unlink(temp_pdf_path)
        except:
            pass
        return images, None
    except Exception as e:
        print("[EXCEPTION]", e)
        return [], None

async def get_full_file_content(file_url: str) -> tuple[list[str], bytes]:
    p = get_parser()
    if p is None:
        return [], None
    try:
        response = p.session.get(file_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        content_disp = response.headers.get("Content-Disposition", "").lower()

        if (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type
            or file_url.lower().endswith(".docx")
            or ".docx" in content_disp
        ):
            try:
                images = docx_to_pdf_images(response.content)
                if images:
                    return images, None
                else:

                    return [], response.content
            except Exception as docx_error:
                print(f"[EXCEPTION] Помилка обробки docx: {docx_error}")
                return [], response.content

        temp_pdf_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                temp_pdf.write(response.content)
                temp_pdf_path = temp_pdf.name

            doc = fitz.open(temp_pdf_path)
            images = []
            for page_num in range(doc.page_count):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                images.append(f"data:image/png;base64,{b64}")
            doc.close()

            return images, None
        except Exception as pdf_error:
            print(f"[EXCEPTION] Помилка обробки PDF: {pdf_error}")
            return [], None
        finally:

            try:
                if temp_pdf_path and os.path.exists(temp_pdf_path):
                    os.unlink(temp_pdf_path)
            except:
                pass
    except Exception as e:
        print(f"[EXCEPTION] Помилка завантаження файлу: {e}")
        return [], None
