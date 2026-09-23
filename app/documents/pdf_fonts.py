"""Local Unicode font resolution and embedding. Never searches OS fonts or the network."""
import ctypes
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from hashlib import sha256

from fontTools.ttLib import TTFont, TTLibError
from fontTools import subset
from pypdfium2 import PdfiumError
import pypdfium2.raw as raw

from app.config.paths import ASSETS_DIR
from app.documents.errors import DocumentError


@lru_cache(maxsize=4)
def font_bytes(path):
    return Path(path).read_bytes()


class FontFace:
    def __init__(self, data):
        self.data = data
        self.font = TTFont(BytesIO(data))
        self.cmap = self.font.getBestCmap() or {}
        self.units = self.font['head'].unitsPerEm

    def covers(self, text):
        return all(ord(c) in self.cmap for c in text if not c.isspace())

    def width(self, text, size):
        metrics = self.font['hmtx'].metrics
        return sum(metrics[self.cmap.get(ord(c), '.notdef')][0] for c in text) / self.units * size

    def vertical(self, text):
        if 'glyf' not in self.font:
            return .9, -.25
        glyphs = self.font['glyf']
        top, bottom = 0, 0
        for character in set(text):
            glyph = glyphs[self.cmap.get(ord(character), '.notdef')]
            top = max(top, getattr(glyph, 'yMax', 0))
            bottom = min(bottom, getattr(glyph, 'yMin', 0))
        return max(.5, top / self.units), min(0, bottom / self.units)


class FontResolver:
    def __init__(self, families=None):
        self.families = families or (ASSETS_DIR / 'fonts/TreeTranslateSans-Regular.ttf',)
        self.faces = {}
        self.native = {}
        self.buffers = []

    def resolve(self, text, original=None):
        if original is not None:
            try:
                font = original.get_font()
                if font.is_embedded:
                    count = ctypes.c_size_t()
                    raw.FPDFFont_GetFontData(font, None, 0, count)
                    if 0 < count.value <= 32 * 1024 * 1024:
                        buffer = (ctypes.c_ubyte * count.value)()
                        if raw.FPDFFont_GetFontData(font, buffer, count.value, count):
                            data = bytes(buffer)
                            key = hash(data)
                            if key not in self.faces:
                                self.faces[key] = FontFace(data)
                            face = self.faces[key]
                            # Re-embedding may not bypass an original embedding restriction.
                            restricted = face.font['OS/2'].fsType & 0x0302 if 'OS/2' in face.font else 0
                            if not restricted and 'glyf' in face.font and face.covers(text):
                                return face
            except (ValueError, KeyError, TTLibError, PdfiumError, OSError):
                # Unsupported embedded font formats use our licensed local fallback.
                # No error text (possibly document data) is logged.
                pass
        for path in self.families:
            key = str(path)
            if key not in self.faces:
                self.faces[key] = FontFace(font_bytes(key))
            if self.faces[key].covers(text):
                return self.faces[key]
        raise DocumentError('Локальные PDF-шрифты не содержат всех символов перевода. Результат не сохранён.')

    def prepare(self, document, requests, cache_key):
        """Build one subset per face for a write batch.

        FontTools parsing is expensive for the large CJK fallback font.  A
        page batch shares one ToUnicode map safely when the subset contains
        every character used by that page's replacement text.
        """
        grouped = {}
        for face, text in requests:
            entry = grouped.setdefault(id(face), [face, set()])
            entry[1].update(text)
        for face, characters in grouped.values():
            self.embed(document, face, ''.join(sorted(characters)), cache_key=cache_key)

    def embed(self, document, face, text, cache_key=None):
        key = (id(face), cache_key if cache_key is not None else frozenset(text))
        if key not in self.native:
            font = TTFont(BytesIO(face.data))
            options = subset.Options()
            options.layout_features = []
            sub = subset.Subsetter(options=options)
            sub.populate(text=text)
            sub.subset(font)
            # PDFium may intern font resources by PostScript name. Different subsets
            # need distinct names or one block's ToUnicode map can corrupt another.
            suffix = sha256(face.data + ''.join(sorted(set(text))).encode('utf-8')).hexdigest()[:12]
            for record in font['name'].names:
                if record.nameID in {3, 4, 6}:
                    record.string = ('TreeTranslateSubset-' + suffix).encode(record.getEncoding())
            output = BytesIO()
            font.save(output)
            font.close()
            data = output.getvalue()
            buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
            native = raw.FPDFText_LoadFont(document, buffer, len(data), raw.FPDF_FONT_TRUETYPE, True)
            if not native:
                raise DocumentError('Не удалось встроить локальный шрифт в PDF.')
            self.buffers.append(buffer)
            self.native[key] = native
        return self.native[key]

    def close(self):
        for font in self.native.values():
            raw.FPDFFont_Close(font)
        self.native.clear()
        self.buffers.clear()
        for face in self.faces.values():
            face.font.close()
        self.faces.clear()
