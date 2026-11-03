"""感官 —— 眼睛与耳朵。

1.0 的感官是「新生儿的感官」：她能感到光和声音，但还认不出图里有什么。
那是她出生第一天就会的东西，不需要模型、不需要联网、不需要 API key。

  眼睛  PNG / BMP / PPM / 基线 JPEG → 4×4 的明暗与冷暖（光从哪来、亮不亮、是暖的还是冷的）
  耳朵  WAV PCM → 响度、起伏、时长（声音大不大、是不是一阵一阵的）

原则：
- 本模块只读文件快照；感知入口把原件保存在生命包，再单独记录像素/声音分析与模型解释。
- 离线、确定性、零第三方依赖。
- 「看懂图里是什么」（识别层）属于 1.1 的可插拔感官；1.0 只有光感与声感。
"""

from __future__ import annotations

from .i18n import t
import hashlib
import math
import struct
import wave
import zlib
from pathlib import Path

from .util import SeedError

# 她眼里的世界被压成 4×4 的明暗块 —— 多了她也记不住。
GRID_COLS = 4
GRID_ROWS = 4

# 太大的图/太长的声音不硬解，直接告诉她「太大了，看不清」。
MAX_PIXELS = 60_000_000
MAX_SOUND_SECONDS = 120.0
# 解压/解码的上限，防止小文件被放大成内存炸弹（PNG 的 IDAT 可以 1000 倍膨胀）。
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_SOUND_BYTES = 64 * 1024 * 1024
MAX_DECODED_BYTES = 200 * 1024 * 1024
# BMP / PPM 是纯 Python 逐像素解码，像素数要收得更紧，否则一张大图会卡几分钟。
MAX_BMP_PIXELS = 4_000_000
MAX_PPM_PIXELS = 16_000_000

PNG_SIG = b"\x89PNG\r\n\x1a\n"
JPEG_SIG = b"\xff\xd8\xff"
BMP_SIG = b"BM"
PPM_SIG = b"P6"
PGM_SIG = b"P5"
# WebP 是 RIFF 容器：前 4 字节 "RIFF"，第 8~12 字节 "WEBP"。
# 原生眼睛不认 WebP（1.0 的格式表里没有），但 1.9 的视觉翻译官可以把它转给有视觉的脑。
WEBP_SIG = b"RIFF"


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clamp8(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def image_mime(data) -> str:
    """按文件头认出「可以交给视觉脑翻译」的图：PNG / JPEG / WebP。

    只做识别、不解码。原生眼睛看不见 WebP，但视觉翻译官可以。
    认不出（BMP / PPM / 陌生格式）返回空串，由调用方决定降级方式。
    """
    if isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    else:
        try:
            raw = Path(data).read_bytes()
        except OSError:
            return ""
    if raw.startswith(PNG_SIG):
        return "image/png"
    if raw.startswith(JPEG_SIG):
        return "image/jpeg"
    if len(raw) >= 12 and raw.startswith(WEBP_SIG) and raw[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _stdev(values) -> float:
    values = list(values)
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    return math.sqrt(sum((v - average) ** 2 for v in values) / len(values))


class _Cells:
    """把整张图按位置累加成 4×4 的格子，不把每个像素都留在内存里。"""

    def __init__(self, width: int, height: int):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.sums = [[[0.0, 0.0, 0.0, 0] for _ in range(GRID_COLS)] for _ in range(GRID_ROWS)]

    def add(self, x: int, y: int, r: float, g: float, b: float) -> None:
        gx = min(GRID_COLS - 1, int(x * GRID_COLS / self.width))
        gy = min(GRID_ROWS - 1, int(y * GRID_ROWS / self.height))
        cell = self.sums[gy][gx]
        cell[0] += r
        cell[1] += g
        cell[2] += b
        cell[3] += 1

    def cells(self) -> list[list[tuple[float, float, float]]]:
        out = []
        for row in self.sums:
            line = []
            for r, g, b, n in row:
                line.append((r / n, g / n, b / n) if n else (0.0, 0.0, 0.0))
            out.append(line)
        return out


# ---------------------------------------------------------------------------
# 眼睛：离线解码（只取明暗，不取细节）
# ---------------------------------------------------------------------------

def _png_unfilter(ftype: int, line: bytearray, prev: bytearray, bpp: int) -> None:
    n = len(line)
    if ftype == 0:
        return
    if ftype == 1:  # Sub
        for i in range(bpp, n):
            line[i] = (line[i] + line[i - bpp]) & 0xFF
    elif ftype == 2:  # Up
        for i in range(n):
            line[i] = (line[i] + prev[i]) & 0xFF
    elif ftype == 3:  # Average
        for i in range(n):
            left = line[i - bpp] if i >= bpp else 0
            line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
    elif ftype == 4:  # Paeth
        for i in range(n):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            pa = abs(b - c)
            pb = abs(a - c)
            pc = abs(a + b - 2 * c)
            pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            line[i] = (line[i] + pred) & 0xFF
    else:
        raise SeedError(t("这张 PNG 的行过滤方式她看不懂（{ftype}）。", ftype=ftype))


def _decode_png(data: bytes) -> tuple[int, int, _Cells]:
    pos = 8
    width = height = 0
    bit_depth = color_type = interlace = 0
    palette = b""
    idat = bytearray()
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            if len(chunk) < 13:
                raise SeedError(t("这张 PNG 的头部坏了。"))
            width = int.from_bytes(chunk[0:4], "big")
            height = int.from_bytes(chunk[4:8], "big")
            bit_depth = chunk[8]
            color_type = chunk[9]
            interlace = chunk[12]
        elif ctype == b"PLTE":
            palette = chunk
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
    if width <= 0 or height <= 0:
        raise SeedError(t("这张 PNG 没有尺寸。"))
    if width * height > MAX_PIXELS:
        raise SeedError(t("这张图太大了，她的眼睛装不下。"))
    if interlace:
        raise SeedError(t("这是交错 PNG，她的眼睛现在还看不清。"))
    if bit_depth not in (8, 16):
        raise SeedError(t("这张 PNG 的位深她看不清（{bit_depth} 位）。", bit_depth=bit_depth))
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise SeedError(t("这张 PNG 的颜色类型她看不清（{color_type}）。", color_type=color_type))
    if color_type == 3 and bit_depth != 8:
        raise SeedError(t("这张调色板 PNG 的位深她看不清。"))

    # 先算「解压后应该有多大」，再带上限解压：防止 IDAT 被压缩成炸弹。
    expected = height * (1 + (width * channels * bit_depth + 7) // 8)
    if expected > MAX_DECODED_BYTES:
        raise SeedError(t("这张图解压后太大了，她的眼睛装不下。"))
    try:
        decomp = zlib.decompressobj()
        raw = bytearray()
        pending = bytes(idat)
        while pending:
            room = max(1, expected + 1 - len(raw))
            piece = decomp.decompress(pending, room)
            raw += piece
            if len(raw) > expected:
                raise SeedError(t("这张 PNG 的压缩数据不正常（解压后比图还大）。"))
            pending = decomp.unconsumed_tail
            if decomp.eof:
                break
        if not decomp.eof:
            raw += decomp.flush(max(1, expected + 1 - len(raw)))
            if len(raw) > expected:
                raise SeedError(t("这张 PNG 的压缩数据不正常（解压后比图还大）。"))
    except zlib.error as error:
        raise SeedError(t("这张 PNG 解不开：{error}", error=error)) from error

    bytes_per_channel = bit_depth // 8
    bpp = max(1, channels * bytes_per_channel)
    stride = (width * channels * bit_depth + 7) // 8
    if len(raw) < height * (stride + 1):
        raise SeedError(t("这张 PNG 的数据不完整。"))

    cells = _Cells(width, height)
    prev = bytearray(stride)
    offset = 0
    for y in range(height):
        ftype = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        offset += stride
        _png_unfilter(ftype, line, prev, bpp)
        prev = line
        if color_type == 3:
            for x in range(width):
                index = line[x] * 3
                if index + 2 < len(palette):
                    cells.add(x, y, palette[index], palette[index + 1], palette[index + 2])
        elif color_type in (0, 4):
            for x in range(width):
                i = x * channels * bytes_per_channel
                value = line[i]
                cells.add(x, y, value, value, value)
        else:
            for x in range(width):
                i = x * channels * bytes_per_channel
                cells.add(x, y, line[i], line[i + bytes_per_channel], line[i + 2 * bytes_per_channel])
    return width, height, cells


def _decode_ppm(data: bytes, gray: bool) -> tuple[int, int, _Cells]:
    tokens = []
    idx = 0
    n = len(data)
    while len(tokens) < 4 and idx < n:
        while idx < n and data[idx:idx + 1].isspace():
            idx += 1
        if idx < n and data[idx:idx + 1] == b"#":
            while idx < n and data[idx:idx + 1] != b"\n":
                idx += 1
            continue
        start = idx
        while idx < n and not data[idx:idx + 1].isspace():
            idx += 1
        if start == idx:
            raise SeedError(t("这张 PPM 的头部坏了。"))
        tokens.append(data[start:idx])
    if len(tokens) < 4:
        raise SeedError(t("这张 PPM 的头部不完整。"))
    try:
        width = int(tokens[1])
        height = int(tokens[2])
        max_value = int(tokens[3])
    except ValueError:
        raise SeedError(t("这张 PPM 的头部坏了（尺寸不是数字）。")) from None
    if width <= 0 or height <= 0 or max_value <= 0:
        raise SeedError(t("这张图的尺寸她看不清。"))
    if width * height > MAX_PPM_PIXELS:
        raise SeedError(t("这张 PPM 太大了，她的眼睛装不下（换张 PNG/JPEG 吧）。"))
    idx += 1  # 头部后正好一个空白
    channels = 1 if gray else 3
    need = width * height * channels
    if len(data) - idx < need:
        raise SeedError(t("这张图的像素数据不完整。"))
    cells = _Cells(width, height)
    p = idx
    for y in range(height):
        for x in range(width):
            if gray:
                v = data[p]
                cells.add(x, y, v, v, v)
                p += 1
            else:
                cells.add(x, y, data[p], data[p + 1], data[p + 2])
                p += 3
    return width, height, cells


def _decode_bmp(data: bytes) -> tuple[int, int, _Cells]:
    if len(data) < 54:
        raise SeedError(t("这张 BMP 太小了。"))
    offset = int.from_bytes(data[10:14], "little")
    width = int.from_bytes(data[18:22], "little", signed=True)
    height_raw = int.from_bytes(data[22:26], "little", signed=True)
    bpp = int.from_bytes(data[28:30], "little")
    compression = int.from_bytes(data[30:34], "little")
    if compression != 0:
        raise SeedError(t("这是压缩 BMP，她的眼睛现在还看不清。"))
    if bpp not in (24, 32):
        raise SeedError(t("这张 BMP 的位深她看不清（{bpp} 位）。", bpp=bpp))
    if width <= 0 or height_raw == 0:
        raise SeedError(t("这张 BMP 没有尺寸。"))
    bottom_up = height_raw > 0
    height = abs(height_raw)
    if width * height > MAX_BMP_PIXELS:
        raise SeedError(t("这张 BMP 太大了（她的眼睛暂时读不完纯 Python 的大 BMP），换张 PNG/JPEG 吧。"))
    row_bytes = width * bpp // 8
    stride = ((row_bytes + 3) // 4) * 4
    if len(data) < offset + stride * height:
        raise SeedError(t("这张 BMP 的数据不完整。"))
    cells = _Cells(width, height)
    for row in range(height):
        y = (height - 1 - row) if bottom_up else row
        start = offset + row * stride
        for x in range(width):
            i = start + x * bpp // 8
            b, g, r = data[i], data[i + 1], data[i + 2]
            cells.add(x, y, r, g, b)
    return width, height, cells


def _build_huffman(counts: list[int], symbols: list[int]) -> dict:
    codes = {}
    code = 0
    k = 0
    for length in range(1, 17):
        for _ in range(counts[length - 1]):
            if k >= len(symbols):
                raise SeedError(t("这张 JPEG 的霍夫曼表坏了。"))
            codes[(length, code)] = symbols[k]
            k += 1
            code += 1
        code <<= 1
    return codes


class _JpegReader:
    """JPEG 熵数据位的读取器（处理 0xFF00 填充与重启标记）。"""

    def __init__(self, data: bytes, pos: int):
        self.data = data
        self.pos = pos
        self.buf = 0
        self.count = 0

    def read_bit(self) -> int:
        if self.count == 0:
            if self.pos >= len(self.data):
                raise SeedError(t("这张 JPEG 的数据不完整。"))
            byte = self.data[self.pos]
            self.pos += 1
            if byte == 0xFF:
                if self.pos >= len(self.data):
                    raise SeedError(t("这张 JPEG 的数据不完整。"))
                nxt = self.data[self.pos]
                if nxt == 0x00:
                    self.pos += 1
                elif 0xD0 <= nxt <= 0xD7:
                    self.pos += 1
                else:
                    raise SeedError(t("这张 JPEG 的数据提前结束了。"))
            self.buf = byte
            self.count = 8
        self.count -= 1
        return (self.buf >> self.count) & 1

    def read_bits(self, n: int) -> int:
        value = 0
        for _ in range(n):
            value = (value << 1) | self.read_bit()
        return value

    def receive_extend(self, n: int) -> int:
        if n == 0:
            return 0
        value = self.read_bits(n)
        if value < (1 << (n - 1)):
            value -= (1 << n) - 1
        return value

    def restart(self) -> None:
        self.count = 0
        while (self.pos + 1 < len(self.data) and self.data[self.pos] == 0xFF
               and 0xD0 <= self.data[self.pos + 1] <= 0xD7):
            self.pos += 2


def _huffman_symbol(reader: _JpegReader, table: dict) -> int:
    code = 0
    for length in range(1, 17):
        code = (code << 1) | reader.read_bit()
        symbol = table.get((length, code))
        if symbol is not None:
            return symbol
    raise SeedError(t("这张 JPEG 她没能解开（霍夫曼编码不对）。"))


def _skip_ac(reader: _JpegReader, table: dict) -> None:
    while True:
        rs = _huffman_symbol(reader, table)
        run, size = rs >> 4, rs & 15
        if size == 0:
            if run == 15:
                continue
            return
        reader.read_bits(size)


def _cell_mean(plane: list[list[float]], gx: int, gy: int, cols: int, rows: int) -> float:
    height = len(plane)
    width = len(plane[0]) if height else 1
    x0 = min(width - 1, int(gx * width / cols))
    x1 = max(x0 + 1, min(width, int((gx + 1) * width / cols)))
    y0 = min(height - 1, int(gy * height / rows))
    y1 = max(y0 + 1, min(height, int((gy + 1) * height / rows)))
    total = 0.0
    count = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            total += plane[y][x]
            count += 1
    return total / count if count else 128.0


def _decode_jpeg(data: bytes) -> tuple[int, int, _Cells]:
    """基线 JPEG：只解直流系数（= 每 8×8 块的平均明暗），不解细节。

    渐进式 JPEG 需要多层扫描，她的眼睛现在还看不清 —— 由调用方记成「一片模糊」。
    """
    pos = 2
    qtables: dict[int, list[int]] = {}
    huff: dict[tuple[int, int], dict] = {}
    comps: list[dict] = []
    width = height = 0
    restart_interval = 0
    scan: list[dict] = []
    entropy_off = -1
    marker = 0
    while pos + 1 < len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        pos += 2
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xD9:
            break
        if pos + 2 > len(data):
            break
        seg_len = int.from_bytes(data[pos:pos + 2], "big")
        if seg_len < 2:
            raise SeedError(t("这张 JPEG 的段落坏了。"))
        seg = data[pos + 2:pos + seg_len]
        pos += seg_len
        if marker == 0xDB:  # DQT
            i = 0
            while i < len(seg):
                pq, tq = seg[i] >> 4, seg[i] & 15
                i += 1
                if pq == 0:
                    if i + 64 > len(seg):
                        raise SeedError(t("这张 JPEG 的量化表坏了。"))
                    qtables[tq] = list(seg[i:i + 64])
                    i += 64
                else:
                    if i + 128 > len(seg):
                        raise SeedError(t("这张 JPEG 的量化表坏了。"))
                    qtables[tq] = [int.from_bytes(seg[j:j + 2], "big") for j in range(i, i + 128, 2)]
                    i += 128
        elif marker == 0xC4:  # DHT
            i = 0
            while i < len(seg):
                tc, th = seg[i] >> 4, seg[i] & 15
                i += 1
                if i + 16 > len(seg):
                    raise SeedError(t("这张 JPEG 的霍夫曼表坏了。"))
                counts = list(seg[i:i + 16])
                i += 16
                total = sum(counts)
                symbols = list(seg[i:i + total])
                i += total
                huff[(tc, th)] = _build_huffman(counts, symbols)
        elif marker in (0xC0, 0xC1):  # 基线 / 扩展顺序
            if len(seg) < 6:
                raise SeedError(t("这张 JPEG 的帧头坏了。"))
            precision = seg[0]
            if precision != 8:
                raise SeedError(t("这张 JPEG 不是 8 位色深，她看不清。"))
            height = int.from_bytes(seg[1:3], "big")
            width = int.from_bytes(seg[3:5], "big")
            ncomp = seg[5]
            comps = []
            i = 6
            for _ in range(ncomp):
                if i + 3 > len(seg):
                    raise SeedError(t("这张 JPEG 的帧头坏了。"))
                comps.append({"id": seg[i], "h": seg[i + 1] >> 4, "v": seg[i + 1] & 15, "tq": seg[i + 2]})
                i += 3
        elif marker == 0xC2:  # 渐进式
            raise SeedError("progressive")
        elif marker == 0xDD:  # DRI
            if len(seg) >= 2:
                restart_interval = int.from_bytes(seg[0:2], "big")
        elif marker == 0xDA:  # SOS
            if not comps:
                raise SeedError(t("这张 JPEG 缺少帧头。"))
            if len(seg) < 1:
                raise SeedError(t("这张 JPEG 的扫描头坏了。"))
            ns = seg[0]
            scan = []
            i = 1
            for _ in range(ns):
                if i + 2 > len(seg):
                    raise SeedError(t("这张 JPEG 的扫描头坏了。"))
                scan.append({"id": seg[i], "td": seg[i + 1] >> 4, "ta": seg[i + 1] & 15})
                i += 2
            entropy_off = pos
            break
        # 其他段落（APPn、COM …）跳过

    if width <= 0 or height <= 0:
        raise SeedError(t("这张 JPEG 没有尺寸。"))
    if width * height > MAX_PIXELS:
        raise SeedError(t("这张图太大了，她的眼睛装不下。"))
    if entropy_off < 0 or not scan:
        raise SeedError(t("这张 JPEG 里没有图像数据。"))
    if len(scan) != len(comps):
        raise SeedError(t("这张 JPEG 分了几次扫描，她的眼睛现在还看不清。"))

    max_h = max(c["h"] for c in comps)
    max_v = max(c["v"] for c in comps)
    if max_h <= 0 or max_v <= 0:
        raise SeedError(t("这张 JPEG 的采样参数坏了，她看不清。"))
    mcu_w = max_h * 8
    mcu_h = max_v * 8
    mcus_x = (width + mcu_w - 1) // mcu_w
    mcus_y = (height + mcu_h - 1) // mcu_h

    planes = {
        c["id"]: [[0.0] * (mcus_x * c["h"]) for _ in range(mcus_y * c["v"])]
        for c in comps
    }
    predictions = {c["id"]: 0 for c in comps}
    by_id = {c["id"]: c for c in comps}
    reader = _JpegReader(data, entropy_off)
    for my in range(mcus_y):
        for mx in range(mcus_x):
            index = my * mcus_x + mx
            if restart_interval and index and index % restart_interval == 0:
                reader.restart()
                predictions = {c["id"]: 0 for c in comps}
            for item in scan:
                comp = by_id[item["id"]]
                dc_table = huff.get((0, item["td"]))
                ac_table = huff.get((1, item["ta"]))
                if dc_table is None or ac_table is None:
                    raise SeedError(t("这张 JPEG 少了一张霍夫曼表。"))
                qtable = qtables.get(comp["tq"])
                if not qtable:
                    raise SeedError(t("这张 JPEG 少了一张量化表。"))
                for vy in range(comp["v"]):
                    for hx in range(comp["h"]):
                        size = _huffman_symbol(reader, dc_table)
                        prediction = predictions[item["id"]] + reader.receive_extend(size)
                        predictions[item["id"]] = prediction
                        _skip_ac(reader, ac_table)
                        dc = prediction * qtable[0]
                        planes[item["id"]][my * comp["v"] + vy][mx * comp["h"] + hx] = dc / 8.0 + 128.0

    y_plane = planes[comps[0]["id"]]
    cb_plane = planes[comps[1]["id"]] if len(comps) >= 2 else None
    cr_plane = planes[comps[2]["id"]] if len(comps) >= 3 else None
    cells = _Cells(width, height)
    for gy in range(GRID_ROWS):
        for gx in range(GRID_COLS):
            y = _cell_mean(y_plane, gx, gy, GRID_COLS, GRID_ROWS)
            if cb_plane is not None and cr_plane is not None:
                cb = _cell_mean(cb_plane, gx, gy, GRID_COLS, GRID_ROWS)
                cr = _cell_mean(cr_plane, gx, gy, GRID_COLS, GRID_ROWS)
                r = y + 1.402 * (cr - 128.0)
                g = y - 0.344136 * (cb - 128.0) - 0.714136 * (cr - 128.0)
                b = y + 1.772 * (cb - 128.0)
            else:
                r = g = b = y
            cells.add(min(width - 1, int((gx + 0.5) * width / GRID_COLS)),
                      min(height - 1, int((gy + 0.5) * height / GRID_ROWS)),
                      _clamp8(r), _clamp8(g), _clamp8(b))
    return width, height, cells


# ---------------------------------------------------------------------------
# 眼睛：把格子读成一句话
# ---------------------------------------------------------------------------

def _summarize(width: int, height: int, cells_doc: list[list[tuple[float, float, float]]]) -> dict:
    flat = [cell for row in cells_doc for cell in row]
    lums = [(r + g + b) / 3.0 / 255.0 for r, g, b in flat]
    brightness = _mean(lums)
    contrast = _stdev(lums)
    redness = _mean(c[0] for c in flat) / 255.0
    blueness = _mean(c[2] for c in flat) / 255.0
    left = _mean(lums[y * GRID_COLS + x] for y in range(GRID_ROWS) for x in range(GRID_COLS // 2))
    right = _mean(lums[y * GRID_COLS + x] for y in range(GRID_ROWS) for x in range(GRID_COLS // 2, GRID_COLS))
    top = _mean(lums[y * GRID_COLS + x] for y in range(GRID_ROWS // 2) for x in range(GRID_COLS))
    bottom = _mean(lums[y * GRID_COLS + x] for y in range(GRID_ROWS // 2, GRID_ROWS) for x in range(GRID_COLS))
    return {
        "brightness": brightness,
        "contrast": contrast,
        "warmth": redness - blueness,
        "leftRight": left - right,
        "topBottom": top - bottom,
    }


def analyze_image(path) -> dict:
    """Analyze a file snapshot; the sensory intake owns original retention."""
    file = Path(path)
    if not file.is_file():
        raise SeedError(t("找不到这张图：{file}", file=file))
    if file.stat().st_size > MAX_IMAGE_BYTES:
        raise SeedError(t("这张图太大了（超过 {value}MB），她的眼睛装不下。", value=MAX_IMAGE_BYTES // (1024 * 1024)))
    data = file.read_bytes()
    if not data:
        raise SeedError(t("这张图是空的。"))
    fmt = ""
    try:
        if data.startswith(PNG_SIG):
            fmt = "png"
            width, height, cells = _decode_png(data)
        elif data.startswith(JPEG_SIG):
            fmt = "jpeg"
            width, height, cells = _decode_jpeg(data)
        elif data.startswith(BMP_SIG):
            fmt = "bmp"
            width, height, cells = _decode_bmp(data)
        elif data.startswith(PPM_SIG):
            fmt = "ppm"
            width, height, cells = _decode_ppm(data, gray=False)
        elif data.startswith(PGM_SIG):
            fmt = "pgm"
            width, height, cells = _decode_ppm(data, gray=True)
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return {"kind": "image", "format": "webp", "width": 0, "height": 0,
                    "bytes": len(data), "sha256": _sha256(data), "readable": False,
                    "note": "当前像素分析器不解析 WebP；可另用视觉模型解释"}
        else:
            raise SeedError(t("她的眼睛认不出这种文件（支持 PNG / JPEG / BMP / PPM）。"))
    except SeedError as error:
        if str(error) == "progressive":
            return {
                "kind": "image",
                "format": "jpeg",
                "width": 0,
                "height": 0,
                "bytes": len(data),
                "sha256": _sha256(data),
                "readable": False,
                "note": "渐进式 JPEG，她的眼睛还看不清，只感到一片模糊",
            }
        raise
    cells_doc = cells.cells()
    stats = _summarize(width, height, cells_doc)
    return {
        "kind": "image",
        "format": fmt,
        "width": width,
        "height": height,
        "bytes": len(data),
        "sha256": _sha256(data),
        "readable": True,
        "cells": cells_doc,
        **stats,
    }


def describe_image(analysis: dict) -> list[str]:
    """把指标变成她的世界语言（1~2 句）。"""
    if not analysis.get("readable", True):
        return [f"她看不清这张图：{analysis.get('note') or '只感到一片模糊'}。"]
    brightness = analysis["brightness"]
    if brightness < 0.08:
        tone = "几乎没有光，只剩一点很淡的轮廓"
    elif brightness < 0.25:
        tone = "光很暗"
    elif brightness < 0.5:
        tone = "光不亮也不暗"
    elif brightness < 0.78:
        tone = "光很亮"
    else:
        tone = "光很亮，亮得有点晃眼"

    warmth = analysis["warmth"]
    if warmth > 0.08:
        color = "是暖的"
    elif warmth < -0.08:
        color = "是冷的"
    else:
        color = "说不上冷暖"

    where = ""
    left_right = analysis["leftRight"]
    if left_right > 0.12:
        where = "光从左边来。"
    elif left_right < -0.12:
        where = "光从右边来。"
    elif analysis["topBottom"] > 0.12:
        where = "光从上面下来。"
    elif analysis["topBottom"] < -0.12:
        where = "光从下面浮上来。"

    texture = "有的地方亮，有的地方暗。" if analysis["contrast"] > 0.12 else "光很匀。"
    return [f"{tone}，{color}。{where}{texture}".strip()]


# ---------------------------------------------------------------------------
# 耳朵：WAV
# ---------------------------------------------------------------------------

def _pcm_samples(raw: bytes, width: int) -> list[float]:
    if width == 1:
        return [(b - 128) / 128.0 for b in raw]
    if width == 2:
        count = len(raw) // 2
        return [v / 32768.0 for v in struct.unpack("<%dh" % count, raw[:count * 2])]
    if width == 3:
        out = []
        for i in range(0, len(raw) - 2, 3):
            value = int.from_bytes(raw[i:i + 3], "little", signed=True)
            out.append(value / 8388608.0)
        return out
    if width == 4:
        count = len(raw) // 4
        return [v / 2147483648.0 for v in struct.unpack("<%di" % count, raw[:count * 4])]
    raise SeedError(t("这种位深的声音她听不清（{value} 位）。", value=width * 8))


def analyze_sound(path) -> dict:
    """听一段声音（WAV PCM）。返回响度、起伏、次数、时长。"""
    file = Path(path)
    if not file.is_file():
        raise SeedError(t("找不到这段声音：{file}", file=file))
    if file.stat().st_size > MAX_SOUND_BYTES:
        raise SeedError(t("这段声音太大了（超过 {value}MB），她的耳朵装不下。", value=MAX_SOUND_BYTES // (1024 * 1024)))
    data = file.read_bytes()
    if not data:
        raise SeedError(t("这段声音是空的。"))
    try:
        with wave.open(str(file), "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            frames = wf.getnframes()
            if rate <= 0 or frames <= 0:
                raise SeedError(t("这段声音是空的。"))
            duration = frames / float(rate)
            if duration > MAX_SOUND_SECONDS:
                raise SeedError(t("这段声音太长了，她的耳朵听不完。"))
            raw = wf.readframes(frames)
    except (wave.Error, EOFError, RuntimeError, struct.error, ValueError) as error:
        raise SeedError(t("这段声音她听不清（只支持 WAV PCM）：{error}", error=error)) from error
    if rate <= 0 or frames <= 0 or not raw:
        raise SeedError(t("这段声音是空的。"))
    duration = frames / float(rate)

    samples = _pcm_samples(raw, width)
    if channels > 1:
        mono = []
        for i in range(0, len(samples) - channels + 1, channels):
            mono.append(sum(samples[i:i + channels]) / channels)
        samples = mono
    if not samples:
        raise SeedError(t("这段声音是空的。"))

    window = max(1, int(rate * 0.05))
    windows = []
    for start in range(0, len(samples), window):
        chunk = samples[start:start + window]
        if chunk:
            windows.append(math.sqrt(sum(v * v for v in chunk) / len(chunk)))
    rms = math.sqrt(sum(v * v for v in samples) / len(samples))
    peak = max(abs(v) for v in samples)
    low, high = (min(windows), max(windows)) if windows else (0.0, 0.0)
    average_window = _mean(windows) if windows else 0.0
    variation = 0.0 if average_window <= 1e-6 else (high - low) / average_window
    threshold = max(high * 0.35, 0.02)
    bursts = 0
    in_burst = False
    for value in windows:
        if value >= threshold and not in_burst:
            bursts += 1
            in_burst = True
        elif value < threshold and in_burst:
            in_burst = False

    return {
        "kind": "sound",
        "format": "wav",
        "channels": channels,
        "rate": rate,
        "duration": duration,
        "bytes": len(data),
        "sha256": _sha256(data),
        "readable": True,
        "rms": rms,
        "peak": peak,
        "variation": variation,
        "bursts": bursts,
    }


def describe_sound(analysis: dict) -> list[str]:
    """把声音变成她的世界语言。"""
    rms = analysis["rms"]
    duration = analysis["duration"]
    if rms < 0.004:
        return [f"几乎没有声音，房间里很静。（{duration:.1f} 秒）"]
    if rms < 0.03:
        loud = "很轻"
    elif rms < 0.10:
        loud = "不大"
    else:
        loud = "很响"
    variation = analysis["variation"]
    if variation > 0.8:
        shape = "断断续续的"
    elif variation > 0.45:
        shape = "一阵一阵的"
    else:
        shape = "一直是那样"
    bursts = int(analysis.get("bursts") or 0)
    if bursts >= 2:
        return [f"有声音，{loud}，{shape}，响了 {bursts} 次。（{duration:.1f} 秒）"]
    return [f"有声音，{loud}，{shape}。（{duration:.1f} 秒）"]
