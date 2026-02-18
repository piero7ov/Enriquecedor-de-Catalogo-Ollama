#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
002 / Script:
catalogo_enriquecido.json -> páginas HTML de producto

- Funciona con cualquier temática: impresiones 3D, electrónica, ropa, etc.
- Respeta el nombre de salida del JSON:
    si existe "enlace": "auriculares-bt-anc.html" => genera ese archivo
- Si no existe "enlace", usa el "slug" o nombre y genera: <slug>.html

Salida:
  OUT_DIR/*.html  (un HTML por producto)
"""

from __future__ import annotations

import json
import re
import html
from pathlib import Path
from datetime import datetime


# =========================
# CONFIG (EDITA AQUÍ)
# =========================
INPUT_JSON = "out/catalogo_enriquecido.json"   # tu JSON del 001
OUT_DIR = "out_pages"                         # carpeta donde se escriben los HTML

# Título / branding (solo visual)
SITE_TITLE = "Pierodev"
HEADER_TITLE = "Pierodev | Impresiones 3D"     # puede ser cualquier tema
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
# Si necesitas prefijo (ej: "../"), ponlo aquí:
IMG_PREFIX = ""

# ✅ Footer (editable)
# Si lo dejas vacío, el script pone uno por defecto.
FOOTER_TEXT = ""


# =========================
# HELPERS
# =========================
def h(s: str) -> str:
    """Escape seguro para HTML."""
    return html.escape(str(s or ""), quote=True)


def slugify(text: str, maxlen: int = 80) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return (text or "item")[:maxlen]


def safe_filename(name: str) -> str:
    """
    Evita rutas raras tipo ../ y se queda solo con el nombre de archivo.
    """
    name = (name or "").strip()
    if not name:
        return ""
    return Path(name).name


def load_catalog(path: Path) -> list[dict]:
    """
    Soporta:
    - { "products": [ ... ] }
    - [ ... ]  (lista directa)
    """
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        return data

    if isinstance(data, dict) and "products" in data and isinstance(data["products"], list):
        return data["products"]

    raise ValueError("No encuentro lista de productos. Esperaba clave 'products' o una lista JSON.")


def pick_output_filename(p: dict) -> str:
    """
    1) Si hay enlace => usarlo
    2) Si no hay enlace => slug.html
    3) Si no hay slug => slugify(nombre).html
    """
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
    """
    Devuelve el texto final del footer.
    - Si FOOTER_TEXT está configurado (no vacío), se respeta.
    - Si no, genera uno por defecto con el año y SITE_TITLE.
    """
    if str(FOOTER_TEXT).strip():
        return str(FOOTER_TEXT).strip()
    return f"© {datetime.now().year} {SITE_TITLE}"


# =========================
# HTML TEMPLATE
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


def build_product_page(p: dict) -> str:
    nombre = p.get("nombre", "Producto")
    desc = p.get("short_desc") or p.get("descripcion") or ""
    imagen = (IMG_PREFIX + (p.get("imagen") or "")).strip()
    precio = p.get("precio", "")
    seo_title = p.get("seo_title") or f"{nombre} | {SITE_TITLE}"
    seo_desc = p.get("seo_description") or (p.get("descripcion") or desc or nombre)
    bullets = p.get("bullets") if isinstance(p.get("bullets"), list) else []
    tags = p.get("tags") if isinstance(p.get("tags"), list) else []
    faq = p.get("faq") if isinstance(p.get("faq"), list) else []

    # meta pills: muestra algunos campos comunes si existen
    meta_keys = ["categoria", "material", "tamano", "tamaño", "marca", "modelo", "color", "conectividad", "conexion"]
    meta = []
    for k in meta_keys:
        if k in p and not is_empty(p[k]):
            label = k.replace("_", " ").replace("-", " ")
            label = label[:1].upper() + label[1:]
            meta.append((label, str(p[k]).strip()))

    # ficha técnica: todos los campos "extra" que existan, excluyendo los que ya van en portada
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

    nav_html = "".join([f"<li><a href='{h(url)}'>{h(text)}</a></li>" for url, text in NAV_LINKS])

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

    faq_html = ""
    if faq:
        blocks = []
        for item in faq:
            if not isinstance(item, dict):
                continue
            q = (item.get("q") or "").strip()
            a = (item.get("a") or "").strip()
            if q and a:
                blocks.append(f"<tr><td>{h(q)}</td><td>{h(a)}</td></tr>")
        if blocks:
            faq_html = (
                "<h2>Preguntas frecuentes</h2>"
                "<table class='tech'>"
                + "".join(blocks) +
                "</table>"
            )

    tech_html = ""
    if tech_rows:
        rows = "".join([f"<tr><td>{h(k)}</td><td>{h(v)}</td></tr>" for k, v in tech_rows])
        tech_html = "<h2>Ficha técnica</h2><table class='tech'>" + rows + "</table>"

    meta_html = ""
    if meta:
        pills = "".join([f"<span class='pill'><b>{h(k)}:</b> {h(v)}</span>" for k, v in meta])
        meta_html = f"<div class='meta'>{pills}</div>"

    img_block = ""
    if imagen:
        img_block = f"<img src='{h(imagen)}' alt='{h(nombre)}'>"
    else:
        img_block = "<img src='' alt='' style='display:none;'>"

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
  <a class="btn" href="{h(BACK_LINK)}">Volver</a>
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
          <a class="btn" href="{h(BACK_LINK)}">Seguir viendo productos</a>
        </div>
      </div>
    </div>

    <div class="section">
      {"<h2>Características</h2>" + bullets_html if bullets_html else ""}
      {tags_html if tags_html else ""}
      {tech_html if tech_html else ""}
      {faq_html if faq_html else ""}
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

        html_page = build_product_page(p)
        out_path.write_text(html_page, encoding="utf-8")
        total += 1

        print(f"OK -> {out_path.name}")

    print("\nDONE")
    print(f"- Productos generados: {total}")
    print(f"- Carpeta salida: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
