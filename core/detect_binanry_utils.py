from pathlib import Path
from typing import Union


def detect_file_type(data: Union[bytes, bytearray, memoryview]) -> str:
    if not data:
        return '.bin'  
    if isinstance(data, (bytearray, memoryview)):
        data = bytes(data) 
    if len(data) < 2 :
        return '.bin'  
    
    # Offset checks
    if len(data) > 132 and data[128:132] == b'DICM':
        return '.dcm'
    if len(data) > 262 and data[257:262] == b'ustar':
        return '.tar'
    if len(data) > 0x8806 and (data[0x8001:0x8006] == b'CD001' or data[0x8801:0x8806] == b'CD001'):
        return '.iso'
    
    # Signatures: (bytes, ext, len)
    sigs = [
        (b'\xE4\x52\x5C\x7B\x8C\xD8\xA7\x4D\xAE\xB1\x53\x78\xD0\x29\x96\xD3','.one',16),(b'%PDF','.pdf',4),(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1','.ole',8),
        (b'{\\rtf','.rtf',4),(b'\xDB\xA5-\x00\x00\x00','.wp',6),(b'\x00\x01\x00\x00Standard ACE DB','.accdb',19),(b'\x00\x01\x00\x00Standard Jet DB','.mdb',19),
        (b'SQLite format 3\x00','.sqlite',16),(b'ITSF','.chm',4),(b'!BDN','.pst',4),(b'\x21\x42\x4E\x41','.ost',4),(b'\x4C\x00\x00\x00\x01\x14\x02\x00','.lnk',8),
        (b'regf','.hiv',4),(b'MSCF','.cab',4),(b'ISc(','.cab',4),(b'MSWIM\x00\x00\x00','.wim',8),(b'conectix','.vhd',8),(b'vhdxfile','.vhdx',8),
        (b'KDMV','.vmdk',4),(b'\xD7\xCD\xC6\x9A','.wmf',4),(b'LfLe','.evt',4),(b'ElfFile\x00','.evtx',8),(b'7z\xBC\xAF\x27\x1C','.7z',6),
        (b'Rar!\x1A\x07\x01\x00','.rar',8),(b'Rar!\x1A\x07\x00','.rar',7),(b'Rar!\x1A\x07','.rar',6),(b'\xFD7zXZ\x00','.xz',6),(b'\x1F\x8B','.gz',2),
        (b'BZh','.bz2',3),(b'PK\x07\x08','.zip',4),(b'PK\x05\x06','.zip',4),(b'PK\x03\x04','.zip',4),(b'\x1F\x9D','.Z',2),(b'\x89PNG\r\n\x1a\n','.png',8),
        (b'\xFF\xD8\xFF\xDB','.jpg',4),(b'\xFF\xD8\xFF\xE0\x00\x10JFIF','.jpg',11),(b'\xFF\xD8\xFF\xE1','.jpg',4),(b'\xFF\xD8\xFF\xE0','.jpg',4),
        (b'\xFF\xD8\xFF','.jpg',3),(b'GIF89a','.gif',6),(b'GIF87a','.gif',6),(b'BM','.bmp',2),(b'RIFF','.webp',4),(b'MM\x00*','.tiff',4),
        (b'II*\x00','.tiff',4),(b'\x00\x00\x01\x00','.ico',4),(b'8BPS','.psd',4),(b'ID3','.mp3',3),(b'\xFF\xFB','.mp3',2),(b'OggS','.ogg',4),
        (b'fLaC','.flac',4),(b'MThd','.midi',4),(b'\x00\x00\x00\x20ftyp','.mp4',8),(b'\x00\x00\x00\x1Cftyp','.mp4',8),(b'\x00\x00\x00\x18ftyp','.mp4',8),
        (b'\x1A\x45\xDF\xA3','.mkv',4),(b'FLV\x01','.flv',4),(b'\x30\x26\xB2\x75\x8E\x66\xCF\x11','.wmv',8),(b'\x00\x00\x01\xBA','.mpeg',4),
        (b'\x7FELF','.elf',4),(b'\xCA\xFE\xBA\xBE','.mach-o',4),(b'MZ','.exe',2),(b'#!','.sh',2),(b'wOFF','.woff',4),(b'\x00\x01\x00\x00\x00','.ttf',5),
    ]
    
    for sig, ext, ml in sigs:
        if len(data) >= ml and data.startswith(sig):
            if sig == b'PK\x03\x04' and len(data) > 500:
                s = data[:4096].decode('latin-1', errors='ignore').lower()
                if 'word/' in s:
                     return '.docx'
                if 'xl/' in s or 'worksheets/' in s:
                     return '.xlsx'
                if 'ppt/' in s or 'slides/' in s:
                     return '.pptx'
                if 'epub' in s:
                     return '.epub'
                return '.zip'
            elif sig == b'RIFF' and len(data) > 12:
                t = data[8:12]
                if t == b'WEBP':
                     return '.webp'
                if t == b'WAVE':
                     return '.wav'
                if t == b'AVI ':
                     return '.avi'
            elif sig == b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1' and len(data) > 512:
                s = data[:8192].lower()
                if b'worddocument' in s:
                    return '.doc'
                if b'workbook' in s:
                    return '.xls'
                if b'powerpoint' in s:
                    return '.ppt'
                if b'__substg1.0_' in s:
                    return '.msg'
                return '.ole'
            return ext
    
    if len(data) > 10:
        try:
            t = data[:500].decode('utf-8', errors='ignore').lstrip().lower()
            if t.startswith('<?xml'):
                return '.svg' if '<svg' in t else '.xml'
            if t.startswith('<!doctype html') or t.startswith('<html'):
                return '.html'
            if t.startswith('{') and '"' in t:
                return '.json'
        except Exception : 
            pass
    
    return '.bin'



def get_filename_with_correct_extension(filename: str, data: Union[bytes, bytearray, memoryview]) -> str:
    """
    Ensure a filename has the correct extension based on file content detection.
    If the filename already has an extension that matches the detected type, keep it.
    Otherwise, replace or add the correct extension.
    
    Args:
        filename: Original filename (may have wrong or no extension)
        data: File content bytes
    
    Returns:
        Filename with correct extension
    """
    if not filename:
        detected_ext = detect_file_type(data)
        return f"attachment{detected_ext}"
    
    path = Path(filename)
    current_ext = path.suffix.lower()
    detected_ext = detect_file_type(data)
    
    # If no extension or extension is .bin, use detected extension
    if not current_ext or current_ext == '.bin':
        return f"{path.stem}{detected_ext}"
    
    # If current extension matches detected, keep it
    if current_ext == detected_ext:
        return filename
    
    # If detected type is more specific than .bin, use it
    if detected_ext != '.bin':
        # Check if current extension is a generic one
        generic_extensions = {'.bin', '.dat', '.tmp', '.file', '.attachment'}
        if current_ext in generic_extensions:
            return f"{path.stem}{detected_ext}"
        # If both are specific but different, prefer detected (it's from magic bytes)
        # But keep original if it's a known good extension
        known_good = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', 
                     '.jpg', '.jpeg', '.png', '.gif', '.zip', '.rar', '.7z'}
        if current_ext not in known_good and detected_ext != '.bin':
            return f"{path.stem}{detected_ext}"
    
    # Default: keep original filename
    return filename
