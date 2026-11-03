"""极小的 PNG 编解码与九宫格拉伸。

1.23 的界面用「皮肤素材」画控件：素材是开发期用 Pillow 渲染好的 PNG
（只有圆角和渐变，很小）；运行时这里用标准库 zlib 解出像素、按 9-slice
拉伸到控件实际大小、合成到背景色上，再交给 tk.PhotoImage 显示。

只用标准库：zlib、struct、base64。不依赖 Pillow。
"""

from __future__ import annotations

import base64
import struct
import zlib

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _unfilter(raw: bytes, width: int, height: int, bpp: int) -> bytearray:
    """PNG 行过滤还原：支持 None/Sub/Up/Average/Paeth。"""
    stride = width * bpp
    out = bytearray(stride * height)
    prev = bytearray(stride)
    pos = 0
    for row in range(height):
        if pos >= len(raw):
            break
        kind = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if len(line) < stride:
            line.extend(b"\x00" * (stride - len(line)))
        if kind == 0:
            pass
        elif kind == 1:  # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif kind == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif kind == 3:  # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif kind == 4:  # Paeth
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[row * stride:(row + 1) * stride] = line
        prev = line
    return out


def decode_png(data: bytes):
    """PNG bytes -> (width, height, bytearray RGBA)。只认 8 位、非隔行。"""
    if not data.startswith(_PNG_SIG):
        raise ValueError("不是 PNG")
    pos = len(_PNG_SIG)
    width = height = bit_depth = color_type = interlace = 0
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
            bit_depth, color_type, _comp, _filter, interlace = struct.unpack(">BBBBB", body[8:13])
        elif kind == b"IDAT":
            idat.extend(body)
        elif kind == b"IEND":
            break
    if bit_depth != 8 or interlace != 0:
        raise ValueError("只支持 8 位非隔行 PNG")
    channels = {2: 3, 6: 4, 0: 1, 4: 2}.get(color_type)
    if channels is None:
        raise ValueError("不支持的 PNG 颜色类型")
    raw = zlib.decompress(bytes(idat))
    pixels = _unfilter(raw, width, height, channels)
    if channels == 4:
        return width, height, pixels
    rgba = bytearray(width * height * 4)
    for index in range(width * height):
        base = index * channels
        out = index * 4
        if channels == 3:
            rgba[out:out + 3] = pixels[base:base + 3]
            rgba[out + 3] = 255
        elif channels == 1:
            rgba[out] = rgba[out + 1] = rgba[out + 2] = pixels[base]
            rgba[out + 3] = 255
        else:
            rgba[out:out + 3] = pixels[base:base + 3]
            rgba[out + 3] = pixels[base + 1]
    return width, height, rgba


def encode_png(width: int, height: int, rgba) -> bytes:
    """RGBA 像素 -> PNG bytes（filter 0，足够小也足够快）。"""
    stride = width * 4
    raw = bytearray()
    for row in range(height):
        raw.append(0)
        raw.extend(rgba[row * stride:(row + 1) * stride])

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (_PNG_SIG + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))


def flatten(width: int, height: int, rgba, background) -> bytearray:
    """把带透明度的像素压到纯色背景上 -> RGB 像素（Tk 素材不需要 alpha）。"""
    bg = tuple(int(v) for v in background)
    out = bytearray(width * height * 3)
    for index in range(width * height):
        src = index * 4
        alpha = rgba[src + 3]
        dst = index * 3
        if alpha >= 255:
            out[dst] = rgba[src]
            out[dst + 1] = rgba[src + 1]
            out[dst + 2] = rgba[src + 2]
        else:
            inv = 255 - alpha
            out[dst] = (rgba[src] * alpha + bg[0] * inv) // 255
            out[dst + 1] = (rgba[src + 1] * alpha + bg[1] * inv) // 255
            out[dst + 2] = (rgba[src + 2] * alpha + bg[2] * inv) // 255
    return out


def _blit(src, sw: int, sx: int, sy: int, swidth: int, sheight: int,
          dst, dw: int, dx: int, dy: int, dwidth: int, dheight: int) -> None:
    """把源图的一块（最近邻缩放）贴进目标 RGBA 像素。"""
    if swidth <= 0 or sheight <= 0 or dwidth <= 0 or dheight <= 0:
        return
    for y in range(dheight):
        src_y = sy + min(sheight - 1, (y * sheight) // dheight)
        row = (src_y * sw + sx) * 4
        out_row = ((dy + y) * dw + dx) * 4
        for x in range(dwidth):
            src_x = min(swidth - 1, (x * swidth) // dwidth)
            src_index = row + src_x * 4
            dst_index = out_row + x * 4
            dst[dst_index:dst_index + 4] = src[src_index:src_index + 4]


def nine_slice(src, sw: int, sh: int, inset: int, width: int, height: int) -> bytearray:
    """把源图按九宫格拉到 width x height。

    目标比「两个圆角」还小时（发送按钮、开关把手这类小圆件），九宫格会切出
    零宽的边角，只剩一块碎图；这种情况直接整图最近邻缩放，圆角仍然平滑。
    """
    inset = max(0, min(inset, sw // 2, sh // 2))
    width = max(1, int(width))
    height = max(1, int(height))
    if inset <= 0 or inset * 2 + 8 >= width or inset * 2 + 8 >= height:
        out = bytearray(width * height * 4)
        _blit(src, sw, 0, 0, sw, sh, out, width, 0, 0, width, height)
        return out
    out = bytearray(width * height * 4)
    left = inset
    top = inset
    right = width - inset
    bottom = height - inset
    if right < left:
        left, right = 0, width
    if bottom < top:
        top, bottom = 0, height
    src_right = sw - inset
    src_bottom = sh - inset
    # 四角
    _blit(src, sw, 0, 0, inset, inset, out, width, 0, 0, inset, inset)
    _blit(src, sw, src_right, 0, inset, inset, out, width, right, 0, width - right, inset)
    _blit(src, sw, 0, src_bottom, inset, inset, out, width, 0, bottom, inset, height - bottom)
    _blit(src, sw, src_right, src_bottom, inset, inset, out, width, right, bottom,
          width - right, height - bottom)
    # 四边
    _blit(src, sw, inset, 0, sw - inset * 2, inset, out, width,
          left, 0, right - left, inset)
    _blit(src, sw, inset, src_bottom, sw - inset * 2, inset, out, width,
          left, bottom, right - left, height - bottom)
    _blit(src, sw, 0, inset, inset, sh - inset * 2, out, width,
          0, top, inset, bottom - top)
    _blit(src, sw, src_right, inset, inset, sh - inset * 2, out, width,
          right, top, width - right, bottom - top)
    # 中间
    _blit(src, sw, inset, inset, sw - inset * 2, sh - inset * 2, out, width,
          left, top, right - left, bottom - top)
    return out


def png_to_rgba(data: bytes):
    return decode_png(data)


def rgba_to_png(width: int, height: int, rgba) -> bytes:
    return encode_png(width, height, rgba)


def photo_data(width: int, height: int, rgb) -> str:
    """RGB 像素 -> tk.PhotoImage(data=...) 能吃的 PNG base64。"""
    stride = width * 3
    raw = bytearray()
    for row in range(height):
        raw.append(0)
        raw.extend(rgb[row * stride:(row + 1) * stride])

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = (_PNG_SIG + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))
    return base64.b64encode(data).decode("ascii")
