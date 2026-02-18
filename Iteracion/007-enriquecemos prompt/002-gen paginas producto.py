#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
002 / Script:
catalogo_enriquecido.json -> páginas HTML de producto

- Funciona con cualquier temática (3D, electrónica, ropa, etc.)
- Respeta el nombre de salida del JSON:
    si existe "enlace": "busto.html" => genera ese archivo (en OUT_DIR)
- Si no existe "enlace", usa "slug" o "nombre" => <slug>.html

Incluye:
- Autorutas reales: desde OUT_DIR hacia SITE_ROOT_DIR (index.php, static/...)
- Minibloque anti-repetidos: limpia bullets/tags para que NO se repita info del meta/desc

Salida:
  OUT_DIR/*.html
"""

from __future__ import annotations

import json
import re
import html
import os
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher


# =========================
# CONFIG (EDITA AQUÍ)
# =========================
INPUT_JSON = "out/catalogo_enriquecido.json"   # JSON del 001
OUT_DIR = "out_pages"                         # carpeta donde se escriben los HTML

# Carpeta "raíz" del sitio (donde está index.php y static/)
# Ej: en tu caso: 005-probamos tienda 3d/
SITE_ROOT_DIR = "."

# Título / branding (solo visual)
SITE_TITLE = "Pierodev"
HEADER_TITLE = "Pierodev | Impresiones 3D"    # puede ser cualquier tema

NAV_LINKS = [
    ("index.php", "Inicio"),
    ("nosotros.php", "Nosotros"),
    ("contacto.php", "Contacto"),
]

# Página a la que vuelve el botón "Volver"
BACK_LINK = "index.php"

# Moneda (solo visual)
CURRENCY = "€"

# Si tu "imagen" en JSON ya viene como "static/..." déjalo tal cual.
# NO pongas "../" aquí: el script ya lo resuelve automáticamente con autorutas.
IMG_PREFIX = ""

# ✅ Footer (editable). Si vacío, pone uno por defecto.
FOOTER_TEXT = ""

# Minibloque de limpieza
MINIBLOCK_ENABLED = True


# =========================
# HELPERS
# =========================
def h(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


def slugify(text: str, maxlen: int = 80) -> str:
    text = (text or "").strip().lower()
    repl = str.maketrans("áéíóúüñ", "aeiouun")
    text = text.translate(repl)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return (text or "item")[:maxlen]


def safe_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return ""
    return Path(name).name


def load_catalog(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        return data

    if isinstance(data, dict) and "products" in data and isinstance(data["products"], list):
        return data["products"]

    raise ValueError("No encuentro lista de productos. Esperaba clave 'products' o una lista JSON.")


def pick_output_filename(p: dict) -> str:
    enlace = safe_filename(p.get("enlace", ""))
    if enlace:
        if "." not in enlace:
            enlace += ".html"
        return enlace

    slug = safe_filename(p.get("slug", ""))
    if slug:
        if "." not in slug:
            slug += ".html"
        return slug

    nombre = p.get("nombre", "producto")
    return f"{slugify(nombre)}.html"


def is_empty(v) -> bool:
    return v is None or str(v).strip() == ""


def resolve_footer_text() -> str:
    if str(FOOTER_TEXT).strip():
        return str(FOOTER_TEXT).strip()
    return f"© {datetime.now().year} {SITE_TITLE}"


def is_absolute_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return (
        u.startswith("http://")
        or u.startswith("https://")
        or u.startswith("//")
        or u.startswith("mailto:")
        or u.startswith("tel:")
        or u.startswith("#")
        or u.startswith("/")
    )


def to_posix(p: str) -> str:
    return str(p).replace("\\", "/")


def rel_to_site_root(from_dir: Path) -> str:
    """
    Devuelve el prefijo relativo desde from_dir hacia SITE_ROOT_DIR.
    Ej: from_dir=out_pages, root=.  => ".."
    """
    root = Path(SITE_ROOT_DIR).resolve()
    fd = from_dir.resolve()
    rel = os.path.relpath(root, start=fd)
    rel = to_posix(rel)
    if rel == ".":
        return ""
    return rel


def resolve_url_from_page(target: str, page_dir: Path) -> str:
    """
    Convierte 'index.php' en '../index.php' si la página está en out_pages.
    Si target ya es absoluto (http, /, #, mailto, etc.), lo respeta.
    """
    target = (target or "").strip()
    if not target:
        return ""
    if is_absolute_url(target):
        return target

    prefix = rel_to_site_root(page_dir)
    if not prefix:
        return to_posix(target.lstrip("./"))

    out = Path(prefix) / target.lstrip("./")
    return to_posix(out)


def resolve_asset_path(asset: str, page_dir: Path) -> str:
    """
    Para imágenes tipo 'static/...' genera '../static/...'
    """
    asset = (asset or "").strip()
    if not asset:
        return ""
    if is_absolute_url(asset):
        return asset

    # aplica IMG_PREFIX si lo usas (normalmente vacío)
    asset = (IMG_PREFIX + asset).lstrip("./")

    prefix = rel_to_site_root(page_dir)
    if not prefix:
        return to_posix(asset)

    out = Path(prefix) / asset
    return to_posix(out)


# =========================
# MINIBLOQUE (anti repetidos)
# =========================
def _norm(s: str) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _sim(a: str, b: str) -> float:
    a = _norm(a); b = _norm(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def dedupe_near(items: list[str], threshold: float = 0.88) -> list[str]:
    out = []
    for it in items:
        it = str(it).strip()
        if not it:
            continue
        if any(_sim(it, prev) >= threshold for prev in out):
            continue
        out.append(it)
    return out


def clean_tags(tags: list, max_tags: int = 10) -> list[str]:
    if not isinstance(tags, list):
        return []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    seen = set()
    out = []
    for t in tags:
        k = _norm(t)
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out[:max_tags]


def clean_bullets(bullets: list, meta_pairs: list[tuple[str, str]], desc: str, max_bullets: int = 3) -> list[str]:
    if not isinstance(bullets, list):
        return []

    original = [str(b).strip() for b in bullets if str(b).strip()]
    if not original:
        return []

    # 1) dedupe “casi iguales”
    original = dedupe_near(original, threshold=0.90)

    # 2) blacklist de meta (valores) + palabras típicas
    meta_values = [_norm(v) for _, v in meta_pairs if str(v).strip()]
    banned_words = {"material", "tamaño", "tamano", "categoría", "categoria", "marca", "modelo", "precio", "garantía", "garantia"}

    cleaned = []
    for b in original:
        bn = _norm(b)

        # si parece “campo: valor” => fuera
        if ":" in b and any(w in bn for w in banned_words):
            continue

        # si menciona palabras de meta y valor meta => fuera
        if any(w in bn for w in banned_words) and any(v and v in bn for v in meta_values):
            continue

        # si es demasiado parecido a la descripción => fuera
        if desc and _sim(b, desc) >= 0.82:
            continue

        cleaned.append(b)

    cleaned = dedupe_near(cleaned, threshold=0.88)

    if not cleaned:
        cleaned = original

    return cleaned[:max_bullets]


# =========================
# HTML
# =========================
def common_css() -> str:
    return """
    body, html {
      padding: 0;
      margin: 0;
      font-family: 'Century Gothic', CenturyGothic, AppleGothic, sans-serif;
      background: #f3f4f6dc;
      color: #0f172a;
    }

    header {
      background: linear-gradient(135deg, #1e3a8a, #0ea5e9);
      color: white;
      display: flex;
      align-items: center;
      padding: 10px 20px;
      gap: 18px;
      flex-wrap: wrap;
    }
    header h1 {
      margin: 0;
      font-size: 1.5rem;
      white-space: nowrap;
    }

    header nav {
      flex-grow: 1;
      display: flex;
      justify-content: center;
      min-width: 250px;
    }

    header nav ul {
      display: flex;
      gap: 20px;
      list-style: none;
      padding: 0;
      margin: 0;
      flex-wrap: wrap;
      justify-content: center;
    }

    header a {
      color: inherit;
      text-decoration: none;
      font-size: 1.05em;
      font-weight: 600;
    }

    .wrap {
      max-width: 1100px;
      margin: 0 auto;
      padding: 22px 16px 40px;
      box-sizing: border-box;
    }

    .card {
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      box-shadow: 0 2px 6px rgba(15, 23, 42, 0.08);
      overflow: hidden;
    }

    .top {
      display: grid;
      grid-template-columns: 1fr 1.2fr;
      gap: 18px;
      padding: 18px;
      align-items: start;
    }

    @media (max-width: 900px) {
      .top { grid-template-columns: 1fr; }
    }

    .media {
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 12px;
    }

    .media img {
      width: 100%;
      height: 360px;
      object-fit: cover;
      border-radius: 10px;
      display: block;
    }

    @media (max-width: 900px) {
      .media img { height: 280px; }
    }

    .title {
      margin: 0 0 8px;
      font-size: 1.6rem;
      color: #0f172a;
    }

    .desc {
      margin: 0 0 12px;
      color: #6b7280;
      line-height: 1.6;
      font-size: 0.98rem;
    }

    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 10px 0 0;
    }

    .pill {
      padding: 5px 10px;
      border-radius: 999px;
      background: #f3f4f6;
      border: 1px solid #e5e7eb;
      font-size: .85rem;
      color: #111827;
      white-space: nowrap;
    }

    .pill b {
      color: #1e3a8a;
    }

    .priceRow {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid #e5e7eb;
    }

    .price {
      font-weight: bold;
      font-size: 1.1rem;
      color: #1e3a8a;
    }

    .btn {
      display: inline-block;
      padding: 8px 14px;
      border-radius: 999px;
      background: linear-gradient(135deg, #1e3a8a, #0ea5e9);
      color: #ffffff;
      text-decoration: none;
      font-size: 0.9rem;
      font-weight: bold;
      border: none;
    }

    .btn:hover { filter: brightness(1.05); }
    .btn:focus { outline: 2px solid #0ea5e9; outline-offset: 2px; }

    .section {
      padding: 0 18px 18px;
    }

    .section h2 {
      margin: 18px 0 10px;
      font-size: 1.1rem;
      color: #1e3a8a;
    }

    ul.bullets {
      margin: 0;
      padding-left: 18px;
      color: #111827;
    }

    .tech {
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
    }

    .tech td {
      padding: 10px 12px;
      border-bottom: 1px solid #e5e7eb;
      font-size: 0.95rem;
    }

    .tech tr:last-child td { border-bottom: none; }

    .tech td:first-child {
      width: 34%;
      font-weight: bold;
      color: #0f172a;
      background: #f8fafc;
    }

    footer {
      text-align: center;
      padding: 12px 0px;
      margin-top: 20px;
      font-size: 0.9rem;
      background: linear-gradient(135deg, #152a60, #0a70a0);
      color: white;
    }
    """


def build_product_page(p: dict, page_dir: Path) -> str:
    nombre = p.get("nombre", "Producto")
    desc = p.get("short_desc") or p.get("descripcion") or ""
    precio = p.get("precio", "")

    seo_title = p.get("seo_title") or f"{nombre} | {SITE_TITLE}"
    seo_desc = p.get("seo_description") or (p.get("descripcion") or desc or nombre)

    raw_bullets = p.get("bullets") if isinstance(p.get("bullets"), list) else []
    raw_tags = p.get("tags") if isinstance(p.get("tags"), list) else []

    # meta pills: muestra campos comunes si existen
    meta_keys = ["categoria", "material", "tamano", "tamaño", "marca", "modelo", "color", "conectividad", "conexion"]
    meta: list[tuple[str, str]] = []
    for k in meta_keys:
        if k in p and not is_empty(p[k]):
            label = k.replace("_", " ").replace("-", " ")
            label = label[:1].upper() + label[1:]
            meta.append((label, str(p[k]).strip()))

    # minibloque: limpia repetidos
    if MINIBLOCK_ENABLED:
        bullets = clean_bullets(raw_bullets, meta, desc, max_bullets=3)
        tags = clean_tags(raw_tags, max_tags=10)
    else:
        bullets = raw_bullets
        tags = raw_tags

    # ficha técnica: campos extra que existan (excluye los principales)
    exclude = {
        "nombre", "descripcion", "imagen", "enlace", "precio",
        "slug", "short_desc", "bullets", "tags",
        "seo_title", "seo_description", "faq",
        "_meta"
    }
    exclude.update(meta_keys)

    tech_rows = []
    for k, v in p.items():
        if k in exclude:
            continue
        if is_empty(v):
            continue
        label = k.replace("_", " ").replace("-", " ")
        label = label[:1].upper() + label[1:]
        tech_rows.append((label, str(v).strip()))

    # rutas resueltas desde la página (out_pages) hacia root
    nav_html = "".join([
        f"<li><a href='{h(resolve_url_from_page(url, page_dir))}'>{h(text)}</a></li>"
        for url, text in NAV_LINKS
    ])
    back_href = resolve_url_from_page(BACK_LINK, page_dir)

    # imagen con autoruta
    img_src = resolve_asset_path((p.get("imagen") or ""), page_dir)

    bullets_html = ""
    if bullets:
        li = "".join([f"<li>{h(x)}</li>" for x in bullets if str(x).strip()])
        if li:
            bullets_html = f"<ul class='bullets'>{li}</ul>"

    tags_html = ""
    if tags:
        pills = "".join([f"<span class='pill'>{h(str(t))}</span>" for t in tags if str(t).strip()])
        if pills:
            tags_html = f"<div class='meta'>{pills}</div>"

    tech_html = ""
    if tech_rows:
        rows = "".join([f"<tr><td>{h(k)}</td><td>{h(v)}</td></tr>" for k, v in tech_rows])
        tech_html = "<h2>Ficha técnica</h2><table class='tech'>" + rows + "</table>"

    meta_html = ""
    if meta:
        pills = "".join([f"<span class='pill'><b>{h(k)}:</b> {h(v)}</span>" for k, v in meta])
        meta_html = f"<div class='meta'>{pills}</div>"

    img_block = f"<img src='{h(img_src)}' alt='{h(nombre)}'>" if img_src else "<img src='' alt='' style='display:none;'>"

    price_text = f"{precio} {CURRENCY}".strip() if str(precio).strip() else "Consultar"
    footer_text = resolve_footer_text()

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(seo_title)}</title>
  <meta name="description" content="{h(str(seo_desc)[:160])}">
  <style>{common_css()}</style>
</head>
<body>

<header>
  <h1>{h(HEADER_TITLE)}</h1>
  <nav>
    <ul>
      {nav_html}
    </ul>
  </nav>
  <a class="btn" href="{h(back_href)}">Volver</a>
</header>

<div class="wrap">
  <div class="card">

    <div class="top">
      <div class="media">
        {img_block}
      </div>

      <div>
        <h2 class="title">{h(nombre)}</h2>
        <p class="desc">{h(desc)}</p>

        {meta_html}

        <div class="priceRow">
          <span class="price">Precio: {h(price_text)}</span>
          <a class="btn" href="{h(back_href)}">Seguir viendo productos</a>
        </div>
      </div>
    </div>

    <div class="section">
      {"<h2>Características</h2>" + bullets_html if bullets_html else ""}
      {tags_html if tags_html else ""}
      {tech_html if tech_html else ""}
    </div>

  </div>
</div>

<footer>
  {h(footer_text)}
</footer>

</body>
</html>
"""


# =========================
# MAIN
# =========================
def main():
    in_path = Path(INPUT_JSON)
    if not in_path.exists():
        raise FileNotFoundError(f"No existe el JSON: {in_path.resolve()}")

    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    products = load_catalog(in_path)
    if not products:
        print("No hay productos en el JSON.")
        return

    total = 0
    for p in products:
        filename = pick_output_filename(p)
        out_path = out_dir / filename

        # page_dir es el directorio donde vive el HTML generado (para autorutas)
        html_page = build_product_page(p, page_dir=out_path.parent)

        out_path.write_text(html_page, encoding="utf-8")
        total += 1
        print(f"OK -> {out_path.name}")

    print("\nDONE")
    print(f"- Productos generados: {total}")
    print(f"- Carpeta salida: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
