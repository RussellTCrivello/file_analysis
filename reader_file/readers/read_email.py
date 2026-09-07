"""
Email file readers - Enhanced Version
Aligned with database design principles - all functions within class
- Supports all file sizes and types
- Merges all message content into single message
- Preserves attachment extraction logic
"""

from email import policy
import email
from email.parser import BytesParser
import json
import os
import time
from typing import Dict, Any, Optional, Set
from pathlib import Path

from core.detect_binanry_utils import detect_file_type , get_filename_with_correct_extension
from core.file_utils import sanitize_filename
from core.path_utils import get_extraction_name_file

from .base_reader import BaseReader

from Hdg_Err_Ex_Log import (
    handle_error,
    ErrorCategory,
    ErrorSeverity,
    format_validation_error
)

import logging
logger = logging.getLogger(__name__)


class EmailFileReader(BaseReader):
    """
    Reader for email files.
    
    Follows database design principles:
    - All functions are within the class
    - Inherits from BaseReader
    - Consistent error handling
    - Proper resource management
    """
    
    def get_supported_extensions(self) -> Set[str]:
        """Return set of supported email extensions"""
        return {
            '.eml',
            '.msg',
            '.mbox',
            '.pst'
        }
    
    def read_file(self, file_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Read email file and extract content with improved error handling
        
        Args:
            file_info: Dictionary containing file information with 'path' key
        
        Returns:
            Dictionary with email content or error information
        """
        # Validate file info using base class method
        is_valid, error_msg = self.validate_file_info(file_info)
        if not is_valid:
            return self.create_error_result(error_msg or "Invalid file info", file_info.get("path", "unknown"))
        
        file_path = str(file_info.get("path"))
        file_lower = file_path.lower()
        
        try:
            result = None
            
            if file_lower.endswith('.msg'):
                result = self.extract_msg(file_path)
                if result and 'error' not in result:
                    result["email_type"] = "msg"
                    
            elif file_lower.endswith('.eml'):
                result = self.extract_eml(file_path)
                if result and 'error' not in result:
                    result["email_type"] = "eml"
                
            elif file_lower.endswith('.mbox'):
                result = self.extract_mbox(file_path)
                if result and 'error' not in result:
                    result["email_type"] = "mbox"
                    
            elif file_lower.endswith('.pst'):
                result = self.extract_pst_pypff(file_path)
                if result and 'error' not in result:
                    result["email_type"] = "pst"
            else:
                error_msg = f"Unsupported email type: {file_path}"
                return self.handle_read_error(ValueError(error_msg), file_path, "read_file")
            
            # If extraction failed, ensure we have an error result
            if not result or 'error' in result:
                if not result:
                    result = {"error": "Email extraction failed", "path": file_path}
            
            return result
            
        except Exception as e:
            return self.handle_read_error(e, file_path, "read_file")
    
    def extract_eml(self, filepath):
        """
        Extract EML file with complete separation:
        - Message content returned directly with metadata (no file created)
        - ALL content parts merged into single message
        - Attachments saved as separate physical files for independent processing
        Returns dict with message data and extraction path for attachments
        """
        try:
            if not os.path.exists(filepath):
                return {"error": "File not found", "filepath": filepath}

            with open(filepath, 'rb') as f:
                msg = BytesParser(policy=policy.default).parse(f)

            # Create extraction folder for attachments only
            extract_to = get_extraction_name_file(filepath, '.eml')
            os.makedirs(extract_to, exist_ok=True)

            # -----------------------------------------
            # 1. EXTRACT MESSAGE METADATA + ALL BODY CONTENT (MERGED)
            # -----------------------------------------
            message = {
                "source_filepath": filepath,
                "from": msg.get('From', ''),
                "to": msg.get('To', ''),
                "subject": msg.get('Subject', ''),
                "date": msg.get('Date', ''),
                "cc": msg.get('Cc', ''),
                "bcc": msg.get('Bcc', ''),
                "message_id": msg.get('Message-ID', ''),
                "content": ""  # Single merged content string
            }

            # Collect all text content parts
            content_parts = []
            
            # Import resource coordinator for CPU management
            try:
                from core.resource_coordinator import should_yield, get_yield_duration
                resource_monitoring_available = True
            except ImportError:
                resource_monitoring_available = False
                should_yield = lambda *args: False
                get_yield_duration = lambda: 0.0
            
            for part in msg.walk():
                content_type = part.get_content_type()
                
                # Only process text content (not attachments)
                if content_type in ['text/plain', 'text/html']:
                    disposition = part.get_content_disposition()
                    # Skip if it's an attachment
                    if disposition not in ['attachment', 'inline']:
                        try:
                            raw_content = part.get_payload(decode=True)
                            if raw_content:
                                text_content = raw_content.decode('utf-8', errors='ignore')
                                
                                # Convert HTML to plaintext if needed
                                if content_type == "text/html":
                                    try:
                                        import html2text
                                        text_content = html2text.html2text(text_content)
                                    except ImportError:
                                        import re
                                        text_content = re.sub('<[^<]+?>', '', text_content)
                                
                                if text_content.strip():
                                    content_parts.append(text_content.strip())
                                    
                                    # Yield periodically during content extraction to prevent CPU spikes
                                    if resource_monitoring_available and len(content_parts) % 10 == 0:
                                        if should_yield():
                                            time.sleep(get_yield_duration())
                        except Exception as e:
                            print(f"  ⚠ Could not decode text part: {str(e)}")
                            continue

            # Merge all content parts with double newline separator
            message["content"] = "\n\n".join(content_parts) if content_parts else ""

            # -----------------------------------------
            # 2. PROCESS ATTACHMENTS
            # - HTML attachments: Extract content directly and add to message
            # - Other attachments: Save as separate files
            # -----------------------------------------
            attachment_count = 0
            html_attachments_content = []  # Store HTML attachment content

            for part in msg.walk():
                disposition = part.get_content_disposition()

                if disposition in ['attachment', 'inline']:
                    original_filename = part.get_filename() or "unnamed"
                    payload = part.get_payload(decode=True)
                    
                    if not payload:
                        continue
                    
                    # Detect file type
                    filename = sanitize_filename(original_filename)
                    filename = get_filename_with_correct_extension(filename, payload)
                    detected_type = detect_file_type(payload)
                    
                    # Check if attachment is HTML
                    content_type = part.get_content_type()
                    is_html = (filename.lower().endswith(('.html', '.htm')) or 
                              detected_type == 'HTML' or
                              'html' in content_type.lower())
                    
                    if is_html:
                        # Extract HTML content directly and add to message
                        try:
                            html_content = payload.decode('utf-8', errors='ignore')
                            if html_content.strip():
                                # Try to convert HTML to text for readability
                                try:
                                    import html2text
                                    html_text = html2text.html2text(html_content)
                                    html_attachments_content.append(f"\n\n--- HTML Attachment: {original_filename} ---\n{html_text.strip()}")
                                except Exception:
                                    # If html2text fails, add raw HTML (limited)
                                    html_attachments_content.append(f"\n\n--- HTML Attachment: {original_filename} ---\n{html_content[:5000]}")
                                print(f"  ✓ Extracted HTML attachment: {original_filename} (content added to message)")
                                attachment_count += 1
                        except Exception as e:
                            print(f"  ⚠ Warning: Failed to extract HTML from {original_filename}: {str(e)}")
                            # Fall through to save as file
                            is_html = False
                    
                    if not is_html:
                        # Save non-HTML attachments as separate files
                        # Save attachment as physical file
                        filepath_attach = os.path.join(extract_to, filename)
                        
                        # Handle duplicate filenames
                        counter = 1
                        base_name = Path(filename).stem
                        extension = Path(filename).suffix
                        while os.path.exists(filepath_attach):
                            filename = f"{base_name}_{counter}{extension}"
                            filepath_attach = os.path.join(extract_to, filename)
                            counter += 1

                        # Write attachment to disk
                        try:
                            with open(filepath_attach, 'wb') as f:
                                f.write(payload)
                                f.flush()  # Ensure data is written to OS buffer
                                os.fsync(f.fileno())  # Force write to disk
                            
                            # Verify file was written correctly
                            if not os.path.exists(filepath_attach):
                                print(f"  ⚠ Warning: File {filename} was not found after writing")
                                continue
                            if os.path.getsize(filepath_attach) != len(payload):
                                print(f"  ⚠ Warning: File {filename} size mismatch (expected {len(payload)}, got {os.path.getsize(filepath_attach)})")
                                continue
                            
                            attachment_count += 1
                            detected_type = detect_file_type(payload)
                        except Exception as e:
                            print(f"  ✗ Error writing attachment {filename}: {str(e)}")
                            continue
                        if original_filename != filename:
                            print(f"  ✓ Saved attachment: {filename} ({len(payload)} bytes) [detected: {detected_type}]")
                        else:
                            print(f"  ✓ Saved attachment: {filename} ({len(payload)} bytes)")
                        
                        # Yield to prevent CPU overload during batch attachment processing
                        if resource_monitoring_available:
                            if should_yield(aggressive=True):
                                yield_duration = get_yield_duration()
                                if yield_duration > 0:
                                    time.sleep(yield_duration)

            # Add HTML attachments content to message
            if html_attachments_content:
                if message.get("content"):
                    message["content"] += "\n".join(html_attachments_content)
                else:
                    message["content"] = "\n".join(html_attachments_content)

            # -----------------------------------------
            # RETURN MESSAGE DATA + EXTRACTION PATH
            # -----------------------------------------
            if attachment_count > 0:
                print(f"✓ Extracted {attachment_count} attachment(s) from {filepath}")
            else:
                print(f"✓ No attachments found in {filepath}")
            
            if attachment_count > 0:
                print(f"✓ Attachments saved to: {extract_to}/")
            
            return {
                "message": message,                    # Message content with metadata (merged content)
                "extraction_path": extract_to,         # Path to attachments folder
                "attachment_count": attachment_count,
                "has_attachments": attachment_count > 0
            }

        except Exception as e:
            print(f"✗ Error extracting {filepath}: {str(e)}")
            return {"error": str(e), "filepath": filepath}
    
    def extract_msg(self, file_path):
        """
        Extract MSG file with complete separation:
        - Message metadata returned directly with merged content
        - Attachments saved as separate physical files for processing
        """
        try:
            import extract_msg
        except ImportError:
            print("⚠ extract-msg not installed. Install with: pip install extract-msg")
            return {"error": "extract-msg package not installed"}
        
        extract_to = get_extraction_name_file(file_path, '.msg')
        os.makedirs(extract_to, exist_ok=True)
        
        try:
            msg = extract_msg.Message(file_path)
            

            content_parts = []
            
            # Add main body
            if msg.body:
                content_parts.append(msg.body.strip())
            
            # Add HTML body if different (converted to text)
            if hasattr(msg, 'htmlBody') and msg.htmlBody:
                try:
                    import html2text
                    html_text = html2text.html2text(msg.htmlBody)
                    if html_text.strip() and html_text.strip() != content_parts[0] if content_parts else True:
                        content_parts.append(html_text.strip())
                except Exception:
                    pass
            
            message = {
                "source_filepath": file_path,
                "from": msg.sender or '',
                "to": msg.to or '',
                "subject": msg.subject or '',
                "date": msg.date or '',
                "cc": msg.cc or '',
                "bcc": msg.bcc or '',
                "content": "\n\n".join(content_parts) if content_parts else ""
            }
            
            # -----------------------------------------
            # 2. PROCESS ATTACHMENTS
            # - HTML attachments: Extract content directly and add to message
            # - Other attachments: Save as separate files
            # -----------------------------------------
            attachment_count = 0
            html_attachments_content = []  # Store HTML attachment content
            
            # Import resource coordinator for CPU management (for PST/OST files)
            try:
                from core.resource_coordinator import should_yield, get_yield_duration
                resource_monitoring_available_pst = True
            except ImportError:
                resource_monitoring_available_pst = False
                def should_yield(*args):
                    return False
                def get_yield_duration():
                    return 0.0
            
            for attachment in msg.attachments:
                original_filename = attachment.longFilename or attachment.shortFilename or "unnamed"
                filename = sanitize_filename(original_filename)
                
                # Detect correct file type and update filename
                filename = get_filename_with_correct_extension(filename, attachment.data)
                detected_type = detect_file_type(attachment.data)
                
                # Check if attachment is HTML
                is_html = (filename.lower().endswith(('.html', '.htm')) or 
                          detected_type == 'HTML' or
                          (hasattr(attachment, 'mimeType') and 'html' in attachment.mimeType.lower()))
                
                if is_html:
                    # Extract HTML content directly and add to message
                    try:
                        html_content = attachment.data.decode('utf-8', errors='ignore')
                        if html_content.strip():
                            # Try to convert HTML to text for readability
                            try:
                                import html2text
                                html_text = html2text.html2text(html_content)
                                html_attachments_content.append(f"\n\n--- HTML Attachment: {original_filename} ---\n{html_text.strip()}")
                            except Exception:
                                # If html2text fails, add raw HTML
                                html_attachments_content.append(f"\n\n--- HTML Attachment: {original_filename} ---\n{html_content[:5000]}")  # Limit to 5000 chars
                            print(f"  ✓ Extracted HTML attachment: {original_filename} (content added to message)")
                            attachment_count += 1
                    except Exception as e:
                        print(f"  ⚠ Warning: Failed to extract HTML from {original_filename}: {str(e)}")
                        # Fall through to save as file
                        is_html = False
                
                if not is_html:
                    # Save non-HTML attachments as separate files
                    filepath_attach = os.path.join(extract_to, filename)
                    
                    counter = 1
                    base_name = Path(filename).stem
                    extension = Path(filename).suffix
                    while os.path.exists(filepath_attach):
                        filename = f"{base_name}_{counter}{extension}"
                        filepath_attach = os.path.join(extract_to, filename)
                        counter += 1
                    
                    try:
                        with open(filepath_attach, 'wb') as f:
                            f.write(attachment.data)
                            f.flush()  # Ensure data is written to OS buffer
                            os.fsync(f.fileno())  # Force write to disk
                        
                        # Verify file was written correctly
                        if not os.path.exists(filepath_attach):
                            print(f"  ⚠ Warning: File {filename} was not found after writing")
                            continue
                        if os.path.getsize(filepath_attach) != len(attachment.data):
                            print(f"  ⚠ Warning: File {filename} size mismatch")
                            continue
                        
                        attachment_count += 1
                    except Exception as e:
                        print(f"  ✗ Error writing attachment {filename}: {str(e)}")
                        continue
                    
                    if original_filename != filename:
                        print(f"  ✓ Saved attachment: {filename} [detected: {detected_type}]")
                    else:
                        print(f"  ✓ Saved attachment: {filename}")
                    
                    # Yield to prevent CPU overload during batch attachment processing
                    if resource_monitoring_available_pst:
                        if should_yield(aggressive=True):
                            yield_duration = get_yield_duration()
                            if yield_duration > 0:
                                time.sleep(yield_duration)
            
            # Add HTML attachments content to message
            if html_attachments_content:
                if message.get("content"):
                    message["content"] += "\n".join(html_attachments_content)
                else:
                    message["content"] = "\n".join(html_attachments_content)
            
            try:
                msg.close()
            except:
                pass
            
            if attachment_count > 0:
                print(f"✓ Extracted {attachment_count} attachment(s) from {file_path}")
                print(f"✓ Attachments saved to: {extract_to}/")
            else:
                print(f"✓ No attachments found in {file_path}")
            
            return {
                "message": message,
                "extraction_path": extract_to,
                "attachment_count": attachment_count,
                "has_attachments": attachment_count > 0
            }
            
        except Exception as e:
            print(f"✗ Error extracting {file_path}: {str(e)}")
            return {"error": str(e), "filepath": file_path}
    
    def extract_mbox(self, file_path):
        """
        Extract MBOX file with complete separation:
        - Each message's metadata returned with merged content
        - Attachments saved as separate physical files in subfolders
        """
        import mailbox
        
        extract_to = get_extraction_name_file(file_path, '.mbox')
        os.makedirs(extract_to, exist_ok=True)
        
        total_attachments = 0
        messages_data = []
        
        try:
            mbox = mailbox.mbox(file_path)
            
            for idx, message in enumerate(mbox):
                subject = message.get('Subject', 'No Subject')
                safe_subject = sanitize_filename(subject)[:50]
                
                message_folder = os.path.join(extract_to, f"msg_{idx:03d}_{safe_subject}")
                
                # -----------------------------------------
                # 1. EXTRACT MESSAGE METADATA + MERGED BODY CONTENT
                # -----------------------------------------
                content_parts = []
                
                # Extract all text content
                for part in message.walk():
                    if part.get_content_type() in ['text/plain', 'text/html']:
                        disposition = part.get_content_disposition()
                        # Skip attachments
                        if disposition not in ['attachment', 'inline']:
                            try:
                                content = part.get_payload(decode=True)
                                if content:
                                    text_content = content.decode('utf-8', errors='ignore')
                                    
                                    # Convert HTML to plain text
                                    if part.get_content_type() == 'text/html':
                                        try:
                                            import html2text
                                            text_content = html2text.html2text(text_content)
                                        except ImportError:
                                            import re
                                            text_content = re.sub('<[^<]+?>', '', text_content)
                                    
                                    if text_content.strip():
                                        content_parts.append(text_content.strip())
                            except Exception as e:
                                continue
                
                msg_data = {
                    "source_filepath": file_path,
                    "message_index": idx,
                    "from": message.get('From', ''),
                    "to": message.get('To', ''),
                    "subject": subject,
                    "date": message.get('Date', ''),
                    "cc": message.get('Cc', ''),
                    "message_id": message.get('Message-ID', ''),
                    "content": "\n\n".join(content_parts) if content_parts else ""
                }
                
                # -----------------------------------------
                # 2. PROCESS ATTACHMENTS
                # - HTML attachments: Extract content directly and add to message
                # - Other attachments: Save as separate files
                # -----------------------------------------
                message_attachment_count = 0
                html_attachments_content = []  # Store HTML attachment content for this message
                
                for part in message.walk():
                    if part.get_content_disposition() in ['attachment', 'inline']:
                        original_filename = part.get_filename()
                        if original_filename:
                            payload = part.get_payload(decode=True)
                            if not payload:
                                continue
                            
                            filename = sanitize_filename(original_filename)
                            # Detect correct file type and update filename
                            filename = get_filename_with_correct_extension(filename, payload)
                            detected_type = detect_file_type(payload)
                            
                            # Check if attachment is HTML
                            content_type = part.get_content_type()
                            is_html = (filename.lower().endswith(('.html', '.htm')) or 
                                      detected_type == 'HTML' or
                                      'html' in content_type.lower())
                            
                            if is_html:
                                # Extract HTML content directly and add to message
                                try:
                                    html_content = payload.decode('utf-8', errors='ignore')
                                    if html_content.strip():
                                        # Try to convert HTML to text for readability
                                        try:
                                            import html2text
                                            html_text = html2text.html2text(html_content)
                                            html_attachments_content.append(f"\n\n--- HTML Attachment: {original_filename} ---\n{html_text.strip()}")
                                        except Exception:
                                            # If html2text fails, add raw HTML (limited)
                                            html_attachments_content.append(f"\n\n--- HTML Attachment: {original_filename} ---\n{html_content[:5000]}")
                                        message_attachment_count += 1
                                        total_attachments += 1
                                except Exception as e:
                                    # Fall through to save as file
                                    is_html = False
                            
                            if not is_html:
                                # Save non-HTML attachments as separate files
                                # Create message folder only if it has attachments
                                if message_attachment_count == 0:
                                    os.makedirs(message_folder, exist_ok=True)
                                
                                filepath_attach = os.path.join(message_folder, filename)
                                
                                counter = 1
                                base_name = Path(filename).stem
                                extension = Path(filename).suffix
                                while os.path.exists(filepath_attach):
                                    filename = f"{base_name}_{counter}{extension}"
                                    filepath_attach = os.path.join(message_folder, filename)
                                    counter += 1
                                
                                try:
                                    with open(filepath_attach, 'wb') as f:
                                        f.write(payload)
                                        f.flush()  # Ensure data is written to OS buffer
                                        os.fsync(f.fileno())  # Force write to disk
                                    
                                    # Verify file was written correctly
                                    if not os.path.exists(filepath_attach):
                                        continue
                                    if os.path.getsize(filepath_attach) != len(payload):
                                        continue
                                    
                                    message_attachment_count += 1
                                    total_attachments += 1
                                except Exception as e:
                                    continue
                
                # Add HTML attachments content to message
                if html_attachments_content:
                    if msg_data.get("content"):
                        msg_data["content"] += "\n".join(html_attachments_content)
                    else:
                        msg_data["content"] = "\n".join(html_attachments_content)
                
                # Add attachment info to message data
                msg_data["attachment_count"] = message_attachment_count
                msg_data["has_attachments"] = message_attachment_count > 0
                if message_attachment_count > 0:
                    msg_data["attachments_folder"] = message_folder
                
                messages_data.append(msg_data)
            
            if total_attachments > 0:
                print(f"✓ Extracted {total_attachments} attachment(s) from {file_path}")
                print(f"✓ Attachments saved to: {extract_to}/")
            else:
                print(f"✓ No attachments found in {file_path}")
            
            return {
                "messages": messages_data,
                "extraction_path": extract_to,
                "total_messages": len(messages_data),
                "total_attachments": total_attachments
            }
            
        except Exception as e:
            print(f"✗ Error extracting {file_path}: {str(e)}")
            return {"error": str(e), "filepath": file_path}
    

    def extract_pst_pypff(self, file_path):
        """
        Extract PST file with message content extraction:
        - Message metadata and merged content extracted
        - Attachments saved as separate physical files for processing
        - Fixed to prevent attachment loss
        """
        try:
            import pypff
        except ImportError:
            print("✗ pypff library not installed. Install with: pip install libpff-python")
            return {"error": "pypff package not installed"}
        
        extract_to = get_extraction_name_file(file_path, '.pst')
        os.makedirs(extract_to, exist_ok=True)
        
        total_attachments = 0
        attachment_counter = 0
        messages_data = []
        message_counter = 0
        
        try:
            pst = pypff.file()
            pst.open(file_path)
            root = pst.get_root_folder()

            # Optional: RTF conversion
            try:
                from striprtf.striprtf import rtf_to_text
                STRIP_RTF_AVAILABLE = True
            except ImportError:
                STRIP_RTF_AVAILABLE = False
                print("⚠ striprtf not installed. RTF bodies will be skipped.")

            import html2text
            h2t = html2text.HTML2Text()
            h2t.ignore_links = True





            def process_folder(folder):
                nonlocal total_attachments, attachment_counter, message_counter
                
                # Process messages
                for i in range(folder.get_number_of_sub_messages()):
                    if message_counter >= 50000000:
                        return

                    try:
                        message = folder.get_sub_message(i)
                    except Exception as e:
                        print(f"⚠ Cannot access message {i}: {e}")
                        continue

                    message_counter += 1

                    # --- Metadata extraction ---
                    try:
                        from_name = message.get_sender_name() or message.get_sender_email_address() or ""
                    except Exception:
                        from_name = ""
                    try:
                        to_name = message.get_transport_headers() or message.get_recipient_name() or ""
                    except Exception:
                        to_name = ""
                    try:
                        subject = message.get_subject() or ""
                    except Exception:
                        subject = ""
                    try:
                        date = str(message.get_delivery_time() or "")
                    except Exception:
                        date = ""

                    msg_data = {
                        "source_filepath": file_path,
                        "message_index": message_counter,
                        "from": from_name,
                        "to": to_name,
                        "subject": subject,
                        "date": date,
                        "content": "",
                        "attachment_count": 0,
                        "has_attachments": False
                    }

                    recipients = []
                    try:
                        for i in range(message.get_number_of_recipients()):
                            recipient = message.get_recipient(i)
                            if recipient:
                                name = recipient.get_name() or recipient.get_email_address() or ""
                                recipients.append(name)
                    except Exception:
                        pass
                    # --- Body extraction ---
                    content_parts = []

                    # Plain text
                    try:
                        body = message.get_plain_text_body()
                        if isinstance(body, bytes):
                            body = body.decode(errors="replace")
                        if body and body.strip():
                            content_parts.append(body.strip())
                    except Exception as e:
                        print(f"⚠ Plain text error (msg {message_counter}): {e}")

                    # HTML
                    try:
                        body = message.get_html_body()
                        if isinstance(body, bytes):
                            body = body.decode(errors="replace")
                        if body and body.strip():
                            text = h2t.handle(body).strip()
                            if text and (not content_parts or text != content_parts[0]):
                                content_parts.append(text)
                    except Exception as e:
                        print(f"⚠ HTML error (msg {message_counter}): {e}")

                    # RTF
                    if STRIP_RTF_AVAILABLE:
                        try:
                            body = message.get_rtf_body()
                            # Check if body exists before decoding
                            if body is not None:
                                # Decode safely to avoid charmap/encoding issues
                                body = self._decode_rtf_body(body)
                                if body and body.strip():
                                    text = self._safe_rtf_to_text(body)
                                    if text:
                                        content_parts.append(text)
                        except Exception as e:
                            print(f"⚠ RTF error (msg {message_counter}): {e}")

                    # Combine all content parts
                    msg_data["content"] = "\n\n".join(content_parts) if content_parts else ""
                    
                    # Log warning if no content was extracted (helps diagnose issues)
                    if not msg_data["content"]:
                        print(f"  ⚠ Message {message_counter} has no extractable content (subject: {subject[:500] if subject else 'N/A'})")
                    
                    msg_data["to"] = ", ".join(recipients)


                    message_attachment_count = 0
                    
                    try:
                        num_attachments = message.get_number_of_attachments()
                    except Exception:
                        num_attachments = 0
                    
                    if num_attachments > 0:
                        for j in range(num_attachments):
                            try:
                                attachment = message.get_attachment(j)
                                attachment_counter += 1
                                
                                data = None
                                try:
                                    data = attachment.read_buffer(attachment.get_size())
                                except Exception:
                                    try:
                                        data = attachment.read()
                                    except Exception:
                                        try:
                                            data = attachment.data
                                        except Exception:
                                            print(f"  ⚠ Could not read data for attachment {attachment_counter}")
                                            continue
                                
                                if not data:
                                    continue
                                
                                # Get original filename before processing
                                original_filename = None
                                try:
                                    original_filename = attachment.get_name()
                                except Exception:
                                    pass
                                
                                if not original_filename:
                                    extension = detect_file_type(data)
                                    filename = f"attachment_{attachment_counter:05d}{extension}"
                                else:
                                    filename = sanitize_filename(original_filename)
                                    # Always detect and correct the extension based on actual file content
                                    filename = get_filename_with_correct_extension(filename, data)
                                
                                filepath = os.path.join(extract_to, filename)
                                
                                counter = 1
                                base_name = Path(filename).stem
                                extension = Path(filename).suffix
                                while os.path.exists(filepath):
                                    filename = f"{base_name}_{counter}{extension}"
                                    filepath = os.path.join(extract_to, filename)
                                    counter += 1
                                
                                try:
                                    with open(filepath, 'wb') as f:
                                        f.write(data)
                                        f.flush()  # Ensure data is written to OS buffer
                                        os.fsync(f.fileno())  # Force write to disk
                                    
                                    # Verify file was written correctly
                                    if not os.path.exists(filepath):
                                        print(f"  ⚠ Warning: File {filename} was not found after writing")
                                        continue
                                    if os.path.getsize(filepath) != len(data):
                                        print(f"  ⚠ Warning: File {filename} size mismatch")
                                        continue
                                    
                                    total_attachments += 1
                                    message_attachment_count += 1
                                except Exception as e:
                                    print(f"  ⚠ Could not write attachment {filename}: {str(e)[:80]}")
                                    continue
                                detected_type = detect_file_type(data)
                                # Show detection info if filename was changed
                                if original_filename and filename != original_filename:
                                    print(f"  Extracted: {filename} ({len(data)} bytes) [detected: {detected_type}, was: {Path(original_filename).suffix or 'no ext'}]")
                                else:
                                    print(f"  Extracted: {filename} ({len(data)} bytes)")
                                
                            except Exception as e:
                                print(f"  ⚠ Could not extract attachment {attachment_counter}: {str(e)[:80]}")
                                continue
                    
                    # Add attachment info to message data
                    msg_data["attachment_count"] = message_attachment_count
                    msg_data["has_attachments"] = message_attachment_count > 0
                    
                    messages_data.append(msg_data)
                
                # Process subfolders
                for i in range(folder.get_number_of_sub_folders()):
                    try:
                        subfolder = folder.get_sub_folder(i)
                        process_folder(subfolder)
                    except Exception:
                        continue
            
            print(f"Processing PST file: {file_path}")
            print(f"Extracting to: {extract_to}/")
            print()
            process_folder(root)
            pst.close()
            
            print()
            if total_attachments > 0:
                print(f"✓ Successfully extracted {total_attachments} attachment(s)")
                print(f"✓ Saved to: {extract_to}/")
            else:
                print(f"✓ No attachments found in {file_path}")
            
            print(f"✓ Processed {message_counter} message(s)")
            
            return {
                "messages": messages_data,
                "extraction_path": extract_to,
                "total_messages": message_counter,
                "attachment_count": total_attachments,
                "has_attachments": total_attachments > 0
            }
        
        except Exception as e:
            print(f"✗ pypff Error: {str(e)[:200]}")
            return {"error": str(e), "filepath": file_path}
        
        
    
    def _decode_rtf_body(self, raw_body):
        """Decode RTF body bytes using several encodings with fallbacks."""
        if raw_body is None:
            return None
        if isinstance(raw_body, str):
            return raw_body
        if not isinstance(raw_body, bytes):
            return None
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return raw_body.decode(enc)
            except UnicodeDecodeError:
                continue
        try:
            return raw_body.decode(errors="replace")
        except Exception:
            return ""

    def _safe_rtf_to_text(self, body: str):
        """Convert RTF to text with graceful degradation."""
        if not body:
            return None
        try:
            from striprtf.striprtf import rtf_to_text
            text_val = rtf_to_text(body).strip()
            if text_val:
                return text_val
        except Exception:
            pass
        # Fallback: basic control-word stripping
        try:
            import re
            text_basic = re.sub(r'\\[a-z]+\\d*\\s?', '', body)
            text_basic = re.sub(r'\{[^}]*\}', '', text_basic)
            text_basic = text_basic.replace('\\par', '\n').replace('\\line', '\n')
            text_basic = ' '.join(text_basic.split()).strip()
            return text_basic or None
        except Exception:
            return None



