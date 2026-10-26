"""Minimal PDF bytes for offer-guard tests. No third-party writer."""

from __future__ import annotations


def build_text_pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 11 Tf"]
    y = 740
    for line in lines:
        safe = line.encode("latin-1", "replace").decode("latin-1")
        safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"1 0 0 1 48 {y} Tm ({safe}) Tj")
        y -= 16
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    return _pdf([stream])


def build_blank_pdf() -> bytes:
    """A one-page PDF with no text operators, standing in for a scan without OCR output."""
    return _pdf([b""])


def _pdf(streams: list[bytes]) -> bytes:
    objects: list[bytes] = []
    page_ids = []
    font_id = 3 + len(streams) * 2
    # Objects: 1 catalog, 2 pages, then for each page a page object and a content object, then font.
    next_id = 3
    content_ids = []
    for stream in streams:
        content_id = next_id
        page_id = next_id + 1
        next_id += 2
        content_ids.append(content_id)
        page_ids.append(page_id)
        objects.append((content_id, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
        objects.append((
            page_id,
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode(),
        ))
    font_object = (font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages = (
        2,
        f"<< /Type /Pages /Count {len(streams)} /Kids [{' '.join(f'{page} 0 R' for page in page_ids)}] >>".encode(),
    )
    catalog = (1, b"<< /Type /Catalog /Pages 2 0 R >>")
    ordered = [catalog, pages, *objects, font_object]
    ordered.sort(key=lambda item: item[0])
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (ordered[-1][0] + 1)
    for number, body in ordered:
        offsets[number] = len(out)
        out.extend(f"{number} 0 obj\n".encode())
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref = len(out)
    size = ordered[-1][0] + 1
    out.extend(f"xref\n0 {size}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for number in range(1, size):
        out.extend(f"{offsets[number]:010d} 00000 n \n".encode())
    out.extend(f"trailer << /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return bytes(out)
