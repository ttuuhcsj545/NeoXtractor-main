"""Image conversion functions for various formats."""

import io
import math
from typing import cast, Tuple, Optional
import texture2ddecoder
from PIL import Image, ImageFile

# tga, ico, tiff, dds
def _pillow_image_conversion(data, fmt):
    return Image.open(io.BytesIO(data), "r", (fmt.upper(), "PNG"))

def image_to_png_data(img: Image.Image | ImageFile.ImageFile) -> bytes:
    """Convert an image to PNG data."""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()

def _get_pitch(width):
    return max(1, ((width+3)//4) ) * 16

def _get_astc_file_size(width, height, block_x, block_y):
    return math.ceil(width/block_y) * math.ceil(height/block_x) * 16

def _decode_correct_format(fmt, data, width, height, block_x = 4, block_y = 4):
    match fmt:
        case "ASTC":
            data = texture2ddecoder.decode_astc(data, width, height, block_x, block_y)
        case "BC1":
            data = texture2ddecoder.decode_bc1(data, width, height)
        case "BC3":
            data = texture2ddecoder.decode_bc3(data, width, height)
        case "BC4":
            data = texture2ddecoder.decode_bc4(data, width, height)
        case "ETC1":
            data = texture2ddecoder.decode_etc1(data, width, height)
        case "ETC2":
            data = texture2ddecoder.decode_etc2(data, width, height)
        case "ETC2A1":
            data = texture2ddecoder.decode_etc2a1(data, width, height)
        case "ETC2A8":
            data = texture2ddecoder.decode_etc2a8(data, width, height)
        case "PVRTC":
            data = texture2ddecoder.decode_pvrtc(data, width, height, False)
        case "RGBA8":
            return Image.frombytes("RGBA", (width, height), data, 'raw', ("RGBA"))
    return Image.frombytes("RGBA", (width, height), data, 'raw', ("BGRA"))

# this code was derived from TeaEffTeu's works and he slightly guided me, thank you very much for sharing!!
def compblks_convert(data):
    """Convert CompBlks to Image."""

    fmt = data[8:10]
    width = int.from_bytes(data[16:18], "little")
    height = int.from_bytes(data[18:20], "little")

    image_data = data[28:]
    if fmt == bytes([0xF3, 0x83]):
        return _decode_correct_format("BC3", image_data, width, height)
    if fmt == bytes([0x78, 0x92]):
        return _decode_correct_format("ETC2A8", image_data, width, height)

def pvr_convert(data: bytes):
    """Convert PVR to Image."""
    # 辅助函数：从字节流读取小端32位
    def read_u32(offset):
        return int.from_bytes(data[offset:offset+4], 'little')
    
    # 辅助函数：从字节流读取小端64位
    def read_u64(offset):
        return int.from_bytes(data[offset:offset+8], 'little')

    pixel_format = read_u64(8)
    height = read_u32(24)
    width = read_u32(28)
    depth = read_u32(32)
    meta_data_size = read_u32(44)
    
    image_data_offset = 52 + meta_data_size
    image_data = data[image_data_offset:]
    
    match pixel_format:
        case 3:
            return _decode_correct_format("PVRTC", image_data, width, height)
        case 7:
            return _decode_correct_format("BC1", image_data, width, height)
        case 11:
            return _decode_correct_format("BC3", image_data, width, height)
        case 12:
            return _decode_correct_format("BC4", image_data, width, height)
        case 27:
            return _decode_correct_format("ASTC", image_data, width, height, 4, 4)
        case 28:
            return _decode_correct_format("ASTC", image_data, width, height, 5, 4)
        case 29:
            return _decode_correct_format("ASTC", image_data, width, height, 5, 5)
        case 30:
            return _decode_correct_format("ASTC", image_data, width, height, 6, 5)
        case 31:
            return _decode_correct_format("ASTC", image_data, width, height, 6, 6)
        case 32:
            return _decode_correct_format("ASTC", image_data, width, height, 8, 5)
        case 33:
            return _decode_correct_format("ASTC", image_data, width, height, 8, 6)
        case 34:
            return _decode_correct_format("ASTC", image_data, width, height, 8, 8)
        case 35:
            return _decode_correct_format("ASTC", image_data, width, height, 10, 5)
        case 36:
            return _decode_correct_format("ASTC", image_data, width, height, 10, 6)
        case 37:
            return _decode_correct_format("ASTC", image_data, width, height, 10, 8)
        case 38:
            return _decode_correct_format("ASTC", image_data, width, height, 10, 10)
        case 39:
            return _decode_correct_format("ASTC", image_data, width, height, 12, 10)
        case 40:
            return _decode_correct_format("ASTC", image_data, width, height, 12, 12)
    raise ValueError(f"Unsupported PVR pixel format: {pixel_format}")

# https://registry.khronos.org/KTX/specs/1.0/ktxspec.v1.html
def ktx_convert(data: bytes):
    """Convert KTX to Image (修复版：纯字节读取，修正ASTC映射)"""
    # 辅助函数：读取小端32位无符号整数
    def read_u32(offset):
        return int.from_bytes(data[offset:offset+4], 'little')

    # 1. 验证魔数 (Identifier)
    expected_magic = b'\xAB\x4B\x54\x58\x20\x31\x31\xBB\x0D\x0A\x1A\x0A'
    if data[0:12] != expected_magic:
        raise ValueError("无效的KTX文件：魔数不匹配")

    # 2. 按标准字节偏移读取头信息
    glInternalFormat = read_u32(0x1C)
    width = read_u32(0x24)
    height = read_u32(0x28)
    bytesOfKeyValueData = read_u32(0x3C)

    # 3. 计算图像数据位置
    img_data_offset = 64 + bytesOfKeyValueData  # 固定头(64字节) + 元数据
    image_size = read_u32(img_data_offset)
    image_data = data[img_data_offset + 4 : img_data_offset + 4 + image_size]

    # 4. 完整的格式映射表 (修正了ASTC映射)
    # ASTC格式映射
    astc_formats = {
        0x93B0: (4, 4),
        0x93B1: (5, 4),
        0x93B2: (5, 5),
        0x93B3: (6, 5),
        0x93B4: (6, 6),  # ✅ 修正：0x93B4 是 ASTC 6x6
        0x93B5: (8, 5),
        0x93B6: (8, 6),
        0x93B7: (8, 8),
        0x93B8: (10, 5),
        0x93B9: (10, 6),
        0x93BA: (10, 8),
        0x93BB: (10, 10),
        0x93BC: (12, 10),
        0x93BD: (12, 12),
    }

    # 5. 格式匹配与解码
    if glInternalFormat in astc_formats:
        bx, by = astc_formats[glInternalFormat]
        return _decode_correct_format("ASTC", image_data, width, height, bx, by)
    elif glInternalFormat == 0x8058:
        return _decode_correct_format("RGBA8", image_data, width, height)
    elif glInternalFormat == 0x8D64:
        return _decode_correct_format("ETC1", image_data, width, height)
    elif glInternalFormat == 0x9274:
        return _decode_correct_format("ETC2", image_data, width, height)
    elif glInternalFormat == 0x9276:
        return _decode_correct_format("ETC2A1", image_data, width, height)
    elif glInternalFormat == 0x9278:
        return _decode_correct_format("ETC2A8", image_data, width, height)
    else:
        raise ValueError(f"不支持的KTX格式: 0x{glInternalFormat:08X}")

def astc_convert(data: bytes):
    """Convert ASTC to Image."""
    # 辅助函数：读取小端24位无符号整数
    def read_u24(offset):
        return int.from_bytes(data[offset:offset+3], 'little')

    block_x = data[4]
    block_y = data[5]
    width = read_u24(8)
    height = read_u24(11)
    image_data = data[16:]
    
    return _decode_correct_format("ASTC", image_data, width, height, block_x, block_y)

def convert_image(data, extension):
    """Identify and convert image data to Image."""
    if extension == "dds":
        return _pillow_image_conversion(data, extension)
    if extension == "pvr":
        return pvr_convert(data)
    if extension in ["ktx", "ktx_low"]:
        return ktx_convert(data)
    if extension == "astc":
        return astc_convert(data)
    if extension == "cbk":
        return compblks_convert(data)
    return None
