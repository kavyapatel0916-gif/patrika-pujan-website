from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from io import BytesIO
import re
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

BASE = Path(__file__).resolve().parent
PDF_PATH = BASE / 'assets' / 'Patrika_Pujan_Original.pdf'
FONT_PATH = BASE / 'assets' / 'NotoSerifGujarati-Medium.ttf'
HTML_PATH = BASE / 'index.html'
HOST, PORT = '0.0.0.0', 5000

# ── Coordinate map ────────────────────────────────────────────────────────────
# Each entry: (page_index, x, y_from_top, max_width, label)
# y_from_top uses the same coordinate system as PyMuPDF (origin = top-left).
# Adjust these values if text needs to shift up/down on the actual printout.
PLACEMENTS = {
    # Page 1 (index 0) — confirmed via calibration grid
    'name_p0': dict(page=0, x=505,  y=1150, max_w=750),
    'city_p0': dict(page=0, x=505,  y=1250, max_w=750),
    # Page 5 (index 4) — confirmed via calibration grid
    'name_p4': dict(page=4, x=235,  y=450,  max_w=1150),
    'city_p4': dict(page=4, x=235,  y=550,  max_w=1150),
}
# ─────────────────────────────────────────────────────────────────────────────


def clean_name(value):
    value = re.sub(r'[\x00-\x1f\x7f]', '', value or '')
    return value.strip()[:120]


def render_text_png(text, max_width, font_size=34):
    """Render *text* as a transparent RGBA PNG using the Gujarati font."""
    font = ImageFont.truetype(str(FONT_PATH), font_size)
    probe = Image.new('RGBA', (max_width, 100), (255, 255, 255, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = max(1, min(max_width, bbox[2] - bbox[0] + 8))
    height = max(60, bbox[3] - bbox[1] + 12)
    img = Image.new('RGBA', (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.text((4 - bbox[0], 4 - bbox[1]), text, font=font, fill=(84, 12, 35, 255))
    return img


def fit_text_image(text, max_width, max_font=34):
    """Shrink font size until the rendered text fits within max_width."""
    for size in range(max_font, 14, -1):
        img = render_text_png(text, max_width, size)
        if img.width <= max_width:
            return img
    return img


def make_overlay(page_w, page_h, img, x, y_top):
    """
    Build a single-page transparent PDF overlay with *img* placed at
    (x, y_top) where y_top is measured from the top of the page.
    reportlab uses a bottom-left origin, so we convert.
    """
    pil_bytes = BytesIO()
    img.save(pil_bytes, format='PNG')
    pil_bytes.seek(0)

    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_w, page_h))
    img_w, img_h = img.size
    rl_y = page_h - y_top - img_h          # convert to bottom-left origin
    c.drawImage(ImageReader(pil_bytes), x, rl_y, width=img_w, height=img_h, mask='auto')
    c.save()
    packet.seek(0)
    return PdfReader(packet)


def stamp_page(writer, pl, text):
    """Stamp *text* onto the page described by placement dict *pl*."""
    page = writer.pages[pl['page']]
    pw = float(page.mediabox.width)
    ph = float(page.mediabox.height)
    img = fit_text_image(text, pl['max_w'])
    overlay = make_overlay(pw, ph, img, pl['x'], pl['y'])
    writer.pages[pl['page']].merge_page(overlay.pages[0])


def make_pdf(name, city=''):
    name = clean_name(name)
    city = clean_name(city)
    if not name:
        raise ValueError('Guest name is required')

    reader = PdfReader(str(PDF_PATH))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    # Stamp name on both pages
    stamp_page(writer, PLACEMENTS['name_p0'], name)
    stamp_page(writer, PLACEMENTS['name_p4'], name)

    # Stamp city only when provided
    if city:
        stamp_page(writer, PLACEMENTS['city_p0'], city)
        stamp_page(writer, PLACEMENTS['city_p4'], city)

    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out.getvalue()


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, data, content_type, status=200, download_name=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        if download_name:
            self.send_header('Content-Disposition', f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        try:
            if path == '/':
                self.send_bytes(HTML_PATH.read_bytes(), 'text/html; charset=utf-8')
                return

            if path in ('/preview', '/download'):
                name = clean_name(qs.get('name', [''])[0])
                city = clean_name(qs.get('city', [''])[0])
                if not name:
                    self.send_bytes(b'Please enter the guest name.', 'text/plain; charset=utf-8', 400)
                    return
                pdf = make_pdf(name, city)
                safe = re.sub(r'[^A-Za-z0-9_\-]+', '_', name).strip('_') or 'Guest'
                filename = f'Patrika_Pujan_{safe}.pdf'
                self.send_bytes(pdf, 'application/pdf', 200,
                                filename if path == '/download' else None)
                return

            if path.startswith('/assets/'):
                rel = path[len('/assets/'):]
                if '/' in rel or '\\' in rel or rel.startswith('.'):
                    self.send_bytes(b'Not found', 'text/plain', 404)
                    return
                file = BASE / 'assets' / rel
                if not file.exists() or not file.is_file():
                    self.send_bytes(b'Not found', 'text/plain', 404)
                    return
                types = {'.pdf': 'application/pdf', '.ttf': 'font/ttf'}
                self.send_bytes(file.read_bytes(),
                                types.get(file.suffix.lower(), 'application/octet-stream'))
                return

            if path.startswith('/static/'):
                rel = path[len('/static/'):]
                if '/' in rel or '\\' in rel or rel.startswith('.'):
                    self.send_bytes(b'Not found', 'text/plain', 404)
                    return
                file = BASE / 'static' / rel
                if not file.exists() or not file.is_file():
                    self.send_bytes(b'Not found', 'text/plain', 404)
                    return
                self.send_bytes(file.read_bytes(), 'application/octet-stream')
                return

            self.send_bytes(b'Not found', 'text/plain; charset=utf-8', 404)

        except Exception as exc:
            self.send_bytes(('Server error: ' + str(exc)).encode('utf-8'),
                            'text/plain; charset=utf-8', 500)

    def log_message(self, fmt, *args):
        print(fmt % args)


if __name__ == '__main__':
    print(f'Patrika Pujan website running at http://127.0.0.1:{PORT}')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
