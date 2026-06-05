"""
ValueData Ecuador - Scraper de Precios REAL v3.0
=================================================
Fuente: tipti.market - Plataforma oficial que tiene precios
reales de percha de todos los supermercados de Ecuador:
Supermaxi, Mi Comisariato, TuTi, TIA, Megamaxi, etc.

Ejecucion automatica via GitHub Actions cada dia.
"""

import requests
import time
import logging
import os
import json
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://noyvanwehsbrnbzajeas.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5veXZhbndlaHNicm5iemFqZWFzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcxNDM3NTQsImV4cCI6MjA5MjcxOTc1NH0.j2K456zlOZuJtVUULHEl1KJ6FT9ugArhuHye3X_ClzE")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("scraper.log", encoding="utf-8")]
)
log = logging.getLogger("ValueData")

# Supermercados en Tipti con sus slugs reales
TIENDAS_TIPTI = [
    {"nombre": "Supermaxi",       "slug": "supermaxi-express"},
    {"nombre": "Mi Comisariato",  "slug": "mi-comisariato"},
    {"nombre": "TuTi",            "slug": "tuti"},
    {"nombre": "Megamaxi",        "slug": "megamaxi"},
    {"nombre": "Santa Maria",     "slug": "santa-maria"},
    {"nombre": "El Coral",        "slug": "el-coral"},
    {"nombre": "Aki",             "slug": "aki"},
]

# Headers que simulan un navegador real en Ecuador
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Redmi 14C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-EC,es;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.tipti.market",
    "Referer": "https://www.tipti.market/",
    "x-app-version": "3.0.0",
    "x-platform": "web",
}

# ─────────────────────────────────────────────
# CLIENTE SUPABASE
# ─────────────────────────────────────────────
class DB:
    def __init__(self):
        self.headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }

    def guardar(self, registros: list) -> int:
        if not registros:
            return 0
        total = 0
        # Lotes de 200
        for i in range(0, len(registros), 200):
            lote = registros[i:i+200]
            try:
                r = requests.post(
                    f"{SUPABASE_URL}/rest/v1/precios_scrapeados",
                    json=lote,
                    headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"}
                )
                if r.status_code in (200, 201, 204):
                    total += len(lote)
                    log.info(f"    Guardados {len(lote)} registros (lote {i//200+1})")
                else:
                    log.error(f"    Error HTTP {r.status_code}: {r.text[:200]}")
            except Exception as e:
                log.error(f"    Error de red: {e}")
            time.sleep(0.3)
        return total

    def limpiar_tienda(self, tienda: str):
        """Borra los precios viejos de una tienda antes de insertar nuevos."""
        try:
            r = requests.delete(
                f"{SUPABASE_URL}/rest/v1/precios_scrapeados?supermercado=eq.{requests.utils.quote(tienda)}",
                headers=self.headers
            )
            log.info(f"    Limpieza {tienda}: HTTP {r.status_code}")
        except Exception as e:
            log.error(f"    Error limpiando {tienda}: {e}")

# ─────────────────────────────────────────────
# SCRAPER TIPTI - API INTERNA
# ─────────────────────────────────────────────
class TiptiScraper:
    """
    Tipti expone una API REST interna que podemos usar
    para obtener el catalogo completo de cada supermercado.
    URL base de la API: https://api.tipti.market
    """
    API_BASE = "https://api.tipti.market"
    WEB_BASE = "https://www.tipti.market"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_categorias(self, tienda_slug: str) -> list:
        """Obtiene las categorias de una tienda en Tipti."""
        try:
            url = f"{self.API_BASE}/retailer/{tienda_slug}/categories/"
            r = self.session.get(url, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("results", data.get("categories", data.get("data", [])))
            log.warning(f"  Categorias {tienda_slug}: HTTP {r.status_code}")
        except Exception as e:
            log.warning(f"  Error categorias {tienda_slug}: {e}")
        return []

    def get_productos_categoria(self, tienda_slug: str, categoria_id, pagina: int = 1) -> dict:
        """Obtiene productos de una categoria especifica."""
        try:
            url = f"{self.API_BASE}/retailer/{tienda_slug}/products/"
            params = {
                "category": categoria_id,
                "page": pagina,
                "page_size": 100,
                "ordering": "name"
            }
            r = self.session.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            log.warning(f"  Error productos {tienda_slug} cat {categoria_id} p{pagina}: {e}")
        return {}

    def get_productos_busqueda(self, tienda_slug: str, query: str = "", pagina: int = 1) -> dict:
        """Busqueda general de productos."""
        try:
            url = f"{self.API_BASE}/retailer/{tienda_slug}/products/"
            params = {"search": query, "page": pagina, "page_size": 100}
            r = self.session.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            log.warning(f"  Error busqueda {tienda_slug}: {e}")
        return {}

    def scrape_tienda_completa(self, tienda: dict) -> list:
        """Extrae todos los productos de una tienda."""
        slug = tienda["slug"]
        nombre = tienda["nombre"]
        ahora = datetime.now().isoformat()
        resultados = []

        log.info(f"\n  [{nombre}] Iniciando scraping...")

        # Metodo 1: por categorias
        categorias = self.get_categorias(slug)
        log.info(f"  [{nombre}] {len(categorias)} categorias encontradas")

        if categorias:
            for cat in categorias:
                cat_id = cat.get("id") or cat.get("slug") or cat.get("pk")
                cat_nombre = cat.get("name") or cat.get("nombre") or str(cat_id)
                if not cat_id:
                    continue

                pagina = 1
                while True:
                    data = self.get_productos_categoria(slug, cat_id, pagina)
                    if not data:
                        break

                    prods = (data.get("results") or data.get("products") or
                             data.get("data") or (data if isinstance(data, list) else []))

                    if not prods:
                        break

                    for prod in prods:
                        reg = self._parsear_producto(prod, nombre, cat_nombre, ahora)
                        if reg:
                            resultados.append(reg)

                    # Paginacion
                    total = data.get("count") or data.get("total") or 0
                    if pagina * 100 >= total or not data.get("next"):
                        break
                    pagina += 1
                    time.sleep(0.5)

                log.info(f"    {cat_nombre}: {len([r for r in resultados if r.get('categoria')==cat_nombre])} prods")
                time.sleep(1)

        # Metodo 2 fallback: busqueda general si no hubo categorias
        if not resultados:
            log.info(f"  [{nombre}] Usando busqueda general...")
            pagina = 1
            while pagina <= 50:  # max 5000 productos
                data = self.get_productos_busqueda(slug, "", pagina)
                if not data:
                    break
                prods = (data.get("results") or data.get("products") or
                         data.get("data") or (data if isinstance(data, list) else []))
                if not prods:
                    break
                for prod in prods:
                    reg = self._parsear_producto(prod, nombre, "General", ahora)
                    if reg:
                        resultados.append(reg)
                log.info(f"    Pagina {pagina}: {len(prods)} prods")
                if not data.get("next"):
                    break
                pagina += 1
                time.sleep(0.8)

        log.info(f"  [{nombre}] Total: {len(resultados)} productos")
        return resultados

    def _parsear_producto(self, prod: dict, supermercado: str, categoria: str, ahora: str):
        """Extrae los campos relevantes de un producto de Tipti."""
        try:
            # Nombre
            nombre = (prod.get("name") or prod.get("nombre") or
                      prod.get("product_name") or "").strip()
            if not nombre or len(nombre) < 2:
                return None

            # Precio
            precio = None
            for campo in ["price", "unit_price", "precio", "sale_price",
                           "regular_price", "priceWithDiscount", "current_price"]:
                val = prod.get(campo)
                if val is not None:
                    try:
                        precio = round(float(val), 2)
                        if precio > 0:
                            break
                    except:
                        pass
            if not precio or precio <= 0:
                return None

            # Codigo de barras / SKU
            codigo = (prod.get("barcode") or prod.get("ean") or
                      prod.get("sku") or prod.get("id") or
                      prod.get("product_id") or "")
            codigo = str(codigo).strip()
            if not codigo:
                return None

            # Marca
            marca = ""
            brand = prod.get("brand") or prod.get("marca") or {}
            if isinstance(brand, dict):
                marca = brand.get("name") or brand.get("nombre") or ""
            elif isinstance(brand, str):
                marca = brand

            # Imagen
            imagen = ""
            for campo in ["image", "imagen", "image_url", "photo", "thumbnail"]:
                val = prod.get(campo)
                if val and isinstance(val, str) and val.startswith("http"):
                    imagen = val[:500]
                    break

            return {
                "codigo_barras":   codigo[:50],
                "nombre_producto": nombre[:200],
                "supermercado":    supermercado,
                "precio":          precio,
                "marca":           str(marca)[:100],
                "categoria":       str(categoria)[:100],
                "imagen_url":      imagen,
                "fecha_scraping":  ahora,
                "pais":            "EC"
            }
        except Exception as e:
            log.debug(f"Error parseando producto: {e}")
            return None


# ─────────────────────────────────────────────
# SCRAPER SUPERMAXI DIRECTO (WooCommerce)
# ─────────────────────────────────────────────
class SupermaxiDirectScraper:
    """
    Supermaxi.com usa WooCommerce con REST API publica.
    Endpoint: /wp-json/wc/store/v1/products
    """
    API = "https://www.supermaxi.com/wp-json/wc/store/v1/products"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.supermaxi.com/"
        })

    def scrape(self) -> list:
        ahora = datetime.now().isoformat()
        resultados = []
        pagina = 1

        log.info("\n  [Supermaxi Directo] Scraping via WooCommerce API...")

        while pagina <= 200:  # hasta 20,000 productos
            try:
                r = self.session.get(
                    self.API,
                    params={"per_page": 100, "page": pagina, "_fields": "id,name,sku,prices,categories,images,short_description"},
                    timeout=20
                )
                if r.status_code == 200:
                    prods = r.json()
                    if not prods:
                        break

                    for prod in prods:
                        try:
                            nombre = prod.get("name", "").strip()
                            if not nombre:
                                continue

                            precio_data = prod.get("prices", {})
                            precio_raw = (precio_data.get("price") or
                                          precio_data.get("regular_price") or "0")
                            # WooCommerce devuelve en centavos
                            try:
                                precio = round(float(precio_raw) / 100, 2)
                            except:
                                precio = 0

                            if precio <= 0:
                                continue

                            sku = prod.get("sku") or str(prod.get("id", ""))
                            if not sku:
                                continue

                            cats = prod.get("categories", [])
                            categoria = cats[0].get("name", "General") if cats else "General"

                            imgs = prod.get("images", [])
                            imagen = imgs[0].get("src", "") if imgs else ""

                            resultados.append({
                                "codigo_barras":   str(sku)[:50],
                                "nombre_producto": nombre[:200],
                                "supermercado":    "Supermaxi",
                                "precio":          precio,
                                "marca":           nombre.split()[0] if nombre else "",
                                "categoria":       categoria[:100],
                                "imagen_url":      imagen[:500],
                                "fecha_scraping":  ahora,
                                "pais":            "EC"
                            })
                        except:
                            continue

                    log.info(f"    Pagina {pagina}: {len(prods)} productos ({len(resultados)} total)")

                    # Ver si hay mas paginas
                    total_pages = int(r.headers.get("X-WP-TotalPages", 1))
                    if pagina >= total_pages:
                        break
                    pagina += 1
                    time.sleep(1)

                elif r.status_code == 429:
                    log.warning("    Rate limited, esperando 30s...")
                    time.sleep(30)
                else:
                    log.warning(f"    HTTP {r.status_code} en pagina {pagina}")
                    break

            except Exception as e:
                log.error(f"    Error pagina {pagina}: {e}")
                break

        log.info(f"  [Supermaxi Directo] Total: {len(resultados)} productos")
        return resultados


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    inicio = datetime.now()
    log.info("=" * 60)
    log.info("  VALUEDATA ECUADOR - SCRAPER REAL v3.0")
    log.info(f"  {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("  Fuente: tipti.market + supermaxi.com")
    log.info("=" * 60)

    db = DB()
    tipti = TiptiScraper()
    supermaxi_direct = SupermaxiDirectScraper()
    total_global = 0

    # ── Paso 1: Tipti (todos los supermercados) ──
    log.info("\n[FASE 1] Scraping via Tipti.market")
    for tienda in TIENDAS_TIPTI:
        try:
            prods = tipti.scrape_tienda_completa(tienda)
            if prods:
                log.info(f"  Guardando {len(prods)} productos de {tienda['nombre']}...")
                db.limpiar_tienda(tienda["nombre"])
                guardados = db.guardar(prods)
                total_global += guardados
                log.info(f"  OK: {guardados}/{len(prods)} guardados")
            else:
                log.warning(f"  {tienda['nombre']}: sin productos (API puede haber cambiado)")
        except Exception as e:
            log.error(f"  Error {tienda['nombre']}: {e}")
        time.sleep(3)

    # ── Paso 2: Supermaxi directo via WooCommerce ──
    log.info("\n[FASE 2] Scraping Supermaxi.com directo (WooCommerce)")
    try:
        prods_sm = supermaxi_direct.scrape()
        if prods_sm:
            log.info(f"  Guardando {len(prods_sm)} productos de Supermaxi...")
            if total_global == 0:
                # Solo limpiar si Tipti no dio productos de Supermaxi
                db.limpiar_tienda("Supermaxi")
            guardados_sm = db.guardar(prods_sm)
            total_global += guardados_sm
            log.info(f"  OK: {guardados_sm}/{len(prods_sm)} guardados")
    except Exception as e:
        log.error(f"  Error Supermaxi directo: {e}")

    # ── Resumen ──
    fin = datetime.now()
    duracion = (fin - inicio).seconds
    log.info("\n" + "=" * 60)
    log.info("  RESUMEN FINAL")
    log.info(f"  Total registros en Supabase: {total_global}")
    log.info(f"  Duracion: {duracion}s ({duracion//60}min {duracion%60}s)")
    log.info(f"  Hora fin: {fin.strftime('%H:%M:%S')}")
    log.info("=" * 60)

    if total_global == 0:
        log.error("  ALERTA: 0 registros guardados.")
        log.error("  Las APIs pueden requerir autenticacion o haber cambiado.")
        log.error("  Revisa los logs y ajusta los endpoints si es necesario.")


if __name__ == "__main__":
    main()
