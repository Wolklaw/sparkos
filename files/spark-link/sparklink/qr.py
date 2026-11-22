"""A small QR code encoder (byte mode, versions 1-40, all four error-correction levels), so the
pairing link can be shown without a third-party library. It follows ISO/IEC 18004 the way
Project Nayuki's public-domain reference does. encode('text') returns rows of booleans
(True = dark), without the quiet zone."""

from typing import List, Sequence

# error-correction level -> (format bits, index into the tables below)
LEVELS = {'L': (1, 0), 'M': (0, 1), 'Q': (3, 2), 'H': (2, 3)}

ECC_PER_BLOCK = (
    (-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28,
     30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26,
     28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28,
     30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30,
     24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
)
NUM_BLOCKS = (
    (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12,
     13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),
    (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21,
     23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),
    (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27,
     29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32,
     35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),
)


def _raw_modules(ver: int) -> int:
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        num_align = ver // 7 + 2
        result -= (25 * num_align - 10) * num_align - 55
        if ver >= 7:
            result -= 36
    return result


def _data_codewords(ver: int, li: int) -> int:
    return _raw_modules(ver) // 8 - ECC_PER_BLOCK[li][ver] * NUM_BLOCKS[li][ver]


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> List[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data: Sequence[int], divisor: Sequence[int]) -> List[int]:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _alignment_positions(ver: int) -> List[int]:
    if ver == 1:
        return []
    num_align = ver // 7 + 2
    step = (ver * 8 + num_align * 3 + 5) // (num_align * 4 - 4) * 2
    size = ver * 4 + 17
    result = [size - 7 - i * step for i in range(num_align - 1)]
    return [6] + sorted(result)


class _Grid:
    def __init__(self, ver: int):
        self.ver = ver
        self.size = ver * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.func = [[False] * self.size for _ in range(self.size)]

    def set_func(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.func[y][x] = True

    def draw_function_patterns(self) -> None:
        size = self.size
        for i in range(size):
            self.set_func(6, i, i % 2 == 0)
            self.set_func(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        self.set_func(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _alignment_positions(self.ver)
        last = len(pos) - 1
        for i, ay in enumerate(pos):
            for j, ax in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set_func(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0, 0)      # reserve the areas; drawn for real after masking
        self.draw_version()

    def draw_format(self, fmt_bits: int, mask: int) -> None:
        data = fmt_bits << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        size = self.size

        def bit(i):
            return (bits >> i) & 1 != 0

        for i in range(6):
            self.set_func(8, i, bit(i))
        self.set_func(8, 7, bit(6))
        self.set_func(8, 8, bit(7))
        self.set_func(7, 8, bit(8))
        for i in range(9, 15):
            self.set_func(14 - i, 8, bit(i))
        for i in range(8):
            self.set_func(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set_func(8, size - 15 + i, bit(i))
        self.set_func(8, size - 8, True)

    def draw_version(self) -> None:
        if self.ver < 7:
            return
        rem = self.ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = self.ver << 12 | rem
        for i in range(18):
            dark = (bits >> i) & 1 != 0
            a, b = self.size - 11 + i % 3, i // 3
            self.set_func(a, b, dark)
            self.set_func(b, a, dark)

    def draw_codewords(self, data: Sequence[int]) -> None:
        size, i, total = self.size, 0, len(data) * 8
        right = size - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(size):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = size - 1 - vert if upward else vert
                    if not self.func[y][x] and i < total:
                        self.dark[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 != 0
                        i += 1
            right -= 2

    def apply_mask(self, mask: int) -> None:
        for y in range(self.size):
            for x in range(self.size):
                if self.func[y][x]:
                    continue
                if mask == 0:
                    invert = (x + y) % 2 == 0
                elif mask == 1:
                    invert = y % 2 == 0
                elif mask == 2:
                    invert = x % 3 == 0
                elif mask == 3:
                    invert = (x + y) % 3 == 0
                elif mask == 4:
                    invert = (x // 3 + y // 2) % 2 == 0
                elif mask == 5:
                    invert = x * y % 2 + x * y % 3 == 0
                elif mask == 6:
                    invert = (x * y % 2 + x * y % 3) % 2 == 0
                else:
                    invert = ((x + y) % 2 + x * y % 3) % 2 == 0
                if invert:
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self) -> int:
        """ISO's rules 1, 2 and 4 plus a simple rule 3: lower is easier to read."""
        size, dark, score = self.size, self.dark, 0
        lines = [row for row in dark] + [[dark[y][x] for y in range(size)] for x in range(size)]
        for line in lines:
            run, colour = 0, None
            for v in line:
                if v == colour:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run, colour = 1, v
            if run >= 5:
                score += run - 2
            text = ''.join('1' if v else '0' for v in line)
            score += 40 * (text.count('1011101' + '0000') + text.count('0000' + '1011101'))
        for y in range(size - 1):
            for x in range(size - 1):
                c = dark[y][x]
                if c == dark[y][x + 1] == dark[y + 1][x] == dark[y + 1][x + 1]:
                    score += 3
        total = sum(sum(1 for v in row if v) for row in dark)
        k = (abs(total * 20 - size * size * 10) + size * size - 1) // (size * size) - 1
        score += max(0, k) * 10
        return score


def encode(text: str, level: str = 'M', min_version: int = 1, mask: int = -1) -> List[List[bool]]:
    data = text.encode('utf-8')
    fmt_bits, li = LEVELS[level]
    for ver in range(min_version, 41):
        count_bits = 8 if ver <= 9 else 16
        if 4 + count_bits + 8 * len(data) <= _data_codewords(ver, li) * 8:
            break
    else:
        raise ValueError('too much data for a QR code')
    capacity = _data_codewords(ver, li)

    bits: List[int] = []

    def put(value: int, n: int) -> None:
        bits.extend((value >> i) & 1 for i in reversed(range(n)))

    put(0b0100, 4)
    put(len(data), count_bits)
    for b in data:
        put(b, 8)
    put(0, min(4, capacity * 8 - len(bits)))
    put(0, (-len(bits)) % 8)
    codewords = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(codewords) < capacity:
        codewords.append(pad)
        pad ^= 0xEC ^ 0x11

    num_blocks, ecc_len = NUM_BLOCKS[li][ver], ECC_PER_BLOCK[li][ver]
    raw = _raw_modules(ver) // 8
    num_short = num_blocks - raw % num_blocks
    short_len = raw // num_blocks
    divisor = _rs_divisor(ecc_len)
    blocks, k = [], 0
    for i in range(num_blocks):
        n = short_len - ecc_len + (0 if i < num_short else 1)
        dat = codewords[k:k + n]
        k += n
        ecc = _rs_remainder(dat, divisor)
        if i < num_short:
            dat = dat + [0]
        blocks.append(dat + ecc)
    stream = []
    for i in range(len(blocks[0])):
        for j, block in enumerate(blocks):
            if i != short_len - ecc_len or j >= num_short:
                stream.append(block[i])

    grid = _Grid(ver)
    grid.draw_function_patterns()
    grid.draw_codewords(stream)
    if mask < 0:
        best, best_score = 0, None
        for m in range(8):
            grid.apply_mask(m)
            grid.draw_format(fmt_bits, m)
            score = grid.penalty()
            if best_score is None or score < best_score:
                best, best_score = m, score
            grid.apply_mask(m)          # XOR again undoes it
        mask = best
    grid.apply_mask(mask)
    grid.draw_format(fmt_bits, mask)
    return grid.dark


def to_text(matrix: List[List[bool]], border: int = 2) -> str:
    """Two rows per line with half blocks, light modules drawn (for a dark terminal)."""
    size = len(matrix)

    def at(x, y):
        return not (0 <= x < size and 0 <= y < size and matrix[y][x])

    lines = []
    for y in range(-border, size + border, 2):
        line = ''
        for x in range(-border, size + border):
            top, bottom = at(x, y), at(x, y + 1)
            line += ('█' if top and bottom else '▀' if top else '▄' if bottom else ' ')
        lines.append(line)
    return '\n'.join(lines)
