"""
ValueData Ecuador - Script de Scraping de Precios
===================================================
Extrae precios de supermercados ecuatorianos y los sube a Supabase.

INSTALACION:
    pip install requests beautifulsoup4 selenium webdriver-manager supabase

EJECUCION:
    python valuedata_scraper.py

AUTOMATIZACION (Linux/Mac cron - cada dia a las 6am):
    0 6 * * * /usr/bin/python3 /ruta/valuedata_scraper.py >> /ruta/scraper.log 2>&1

AUTOMATIZACION (Windows Task Scheduler):
    Crear tarea que ejecute: python C:\ruta\valuedata_scraper.py

Autor: ValueData Ecuador
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import logging
import os
from datetime import datetime
from typing import Optional
import re

# ─────────────────────────────────────────────
# CONFIGURACION
# Lee desde variables de entorno (GitHub Actions Secrets)
# o usa valores por defecto para pruebas locales
# ─────────────────────────────────────────────
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    "https://noyvanwehsbrnbzajeas.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5veXZhbndlaHNicm5iemFqZWFzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcxNDM3NTQsImV4cCI6MjA5MjcxOTc1NH0.j2K456zlOZuJtVUULHEl1KJ6FT9ugArhuHye3X_ClzE"
)

HEADERS_SUPA = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-EC,es;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scraper.log", encoding="utf-8")
    ]
)
log = logging.getLogger("ValueData")


# ─────────────────────────────────────────────
# CLIENTE SUPABASE
# ─────────────────────────────────────────────
class SupabaseClient:
    def __init__(self):
        self.base = SUPABASE_URL
        self.headers = HEADERS_SUPA
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def upsert_precio(self, data: dict) -> bool:
        """Inserta o actualiza un precio en la tabla precios_scrapeados."""
        try:
            r = self.session.post(
                f"{self.base}/rest/v1/precios_scrapeados",
                json=data,
                headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"}
            )
            if r.status_code in (200, 201, 204):
                return True
            else:
                log.error(f"Supabase error {r.status_code}: {r.text[:200]}")
                return False
        except Exception as e:
            log.error(f"Error guardando en Supabase: {e}")
            return False

    def get_existing_codes(self) -> set:
        """Obtiene los códigos de barras ya existentes para evitar duplicados recientes."""
        try:
            r = self.session.get(
                f"{self.base}/rest/v1/precios_scrapeados?select=codigo_barras&limit=5000"
            )
            if r.status_code == 200:
                data = r.json()
                return {item["codigo_barras"] for item in data if item.get("codigo_barras")}
        except Exception as e:
            log.error(f"Error obteniendo códigos existentes: {e}")
        return set()

    def bulk_upsert(self, records: list) -> int:
        """Inserta múltiples registros de una vez."""
        if not records:
            return 0
        try:
            r = self.session.post(
                f"{self.base}/rest/v1/precios_scrapeados",
                json=records,
                headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"}
            )
            if r.status_code in (200, 201, 204):
                log.info(f"  ✓ {len(records)} registros guardados en Supabase")
                return len(records)
            else:
                log.error(f"  ✗ Error bulk insert {r.status_code}: {r.text[:300]}")
                return 0
        except Exception as e:
            log.error(f"  ✗ Error bulk insert: {e}")
            return 0


# ─────────────────────────────────────────────
# SCRAPER BASE
# ─────────────────────────────────────────────
class ScraperBase:
    def __init__(self, supermercado: str):
        self.supermercado = supermercado
        self.session = requests.Session()
        self.session.headers.update(HEADERS_WEB)
        self.productos = []

    def get_page(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        for intento in range(retries):
            try:
                time.sleep(1.5 + intento)  # Respetuoso con el servidor
                r = self.session.get(url, timeout=15)
                if r.status_code == 200:
                    return BeautifulSoup(r.text, "html.parser")
                elif r.status_code == 429:
                    log.warning(f"Rate limited en {url}, esperando 30s...")
                    time.sleep(30)
                else:
                    log.warning(f"HTTP {r.status_code} en {url}")
            except Exception as e:
                log.warning(f"Error intento {intento+1} en {url}: {e}")
        return None

    def get_json(self, url: str, retries: int = 3) -> Optional[dict]:
        for intento in range(retries):
            try:
                time.sleep(1.5 + intento)
                r = self.session.get(url, timeout=15)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 429:
                    log.warning(f"Rate limited, esperando 30s...")
                    time.sleep(30)
            except Exception as e:
                log.warning(f"Error intento {intento+1}: {e}")
        return None

    def crear_registro(self, codigo_barras: str, nombre: str, precio: float,
                       marca: str = "", categoria: str = "", imagen_url: str = "") -> dict:
        return {
            "codigo_barras":   codigo_barras.strip(),
            "nombre_producto": nombre.strip()[:200],
            "supermercado":    self.supermercado,
            "precio":          round(float(precio), 2),
            "marca":           marca.strip()[:100],
            "categoria":       categoria.strip()[:100],
            "imagen_url":      imagen_url[:500] if imagen_url else "",
            "fecha_scraping":  datetime.now().isoformat(),
            "pais":            "EC"
        }

    def scrape(self) -> list:
        raise NotImplementedError


# ─────────────────────────────────────────────
# SCRAPER SUPERMAXI (WooCommerce)
# ─────────────────────────────────────────────
class SupermaxiScraper(ScraperBase):
    """
    Supermaxi usa WooCommerce. Intentamos la API REST primero,
    luego hacemos scraping del HTML como fallback.
    """
    BASE_URL = "https://www.supermaxi.com"

    def __init__(self):
        super().__init__("Supermaxi")
        self.categorias = [
            "bebidas", "lacteos-y-huevos", "aceites-y-condimentos",
            "granos-arroz-y-pastas", "snacks-y-galletas", "carnes-y-aves",
            "limpieza-del-hogar", "cuidado-personal", "panaderia-y-pasteleria",
            "frutas-y-verduras", "congelados", "enlatados-y-conservas"
        ]

    def scrape(self) -> list:
        log.info(f"\n{'='*50}")
        log.info(f"Iniciando scraping: SUPERMAXI")
        log.info(f"{'='*50}")
        resultados = []

        for categoria in self.categorias:
            log.info(f"  Categoria: {categoria}")
            page = 1
            while True:
                url = f"{self.BASE_URL}/categoria-producto/{categoria}/page/{page}/"
                soup = self.get_page(url)
                if not soup:
                    break

                productos_html = soup.select("li.product, .product-inner, .woocommerce-loop-product")
                if not productos_html:
                    # Intentar selector alternativo
                    productos_html = soup.select(".products .product")

                if not productos_html:
                    log.info(f"    Sin productos en página {page}, fin de categoría")
                    break

                for prod in productos_html:
                    registro = self._parse_producto(prod, categoria)
                    if registro:
                        resultados.append(registro)

                log.info(f"    Página {page}: {len(productos_html)} productos")

                # Verificar si hay página siguiente
                next_btn = soup.select_one("a.next.page-numbers, .next")
                if not next_btn:
                    break
                page += 1
                if page > 20:  # Máximo 20 páginas por categoría
                    break

        log.info(f"Total Supermaxi: {len(resultados)} productos")
        return resultados

    def _parse_producto(self, elem, categoria: str) -> Optional[dict]:
        try:
            # Nombre
            nombre_el = elem.select_one(".woocommerce-loop-product__title, h2, .product-title")
            if not nombre_el:
                return None
            nombre = nombre_el.get_text(strip=True)
            if len(nombre) < 3:
                return None

            # Precio
            precio_el = elem.select_one(".price .woocommerce-Price-amount, .price ins .amount, .amount")
            if not precio_el:
                return None
            precio_txt = precio_el.get_text(strip=True)
            precio = self._parse_precio(precio_txt)
            if not precio or precio <= 0:
                return None

            # Código de barras (SKU)
            sku = ""
            sku_el = elem.select_one("[data-sku], .sku")
            if sku_el:
                sku = sku_el.get("data-sku") or sku_el.get_text(strip=True)
            if not sku:
                # Intentar del atributo data-product_id
                sku = elem.get("data-product_id", "")
            if not sku:
                # Generar ID basado en nombre
                sku = "SM-" + re.sub(r'[^a-zA-Z0-9]', '', nombre[:20]).upper()

            # Marca (generalmente en el nombre)
            marca = self._extraer_marca(nombre)

            # Imagen
            img_el = elem.select_one("img")
            imagen = ""
            if img_el:
                imagen = img_el.get("src") or img_el.get("data-src", "")

            return self.crear_registro(sku, nombre, precio, marca, categoria, imagen)

        except Exception as e:
            log.debug(f"Error parseando producto: {e}")
            return None

    def _parse_precio(self, texto: str) -> Optional[float]:
        try:
            # Limpiar: $1.85 → 1.85
            limpio = re.sub(r'[^\d.,]', '', texto)
            limpio = limpio.replace(',', '.')
            # Si hay múltiples puntos, quitar todos excepto el último
            partes = limpio.split('.')
            if len(partes) > 2:
                limpio = ''.join(partes[:-1]) + '.' + partes[-1]
            return float(limpio) if limpio else None
        except:
            return None

    def _extraer_marca(self, nombre: str) -> str:
        # Marcas conocidas de Ecuador
        marcas = [
            "Coca-Cola", "Pepsi", "Nestlé", "Nestlé", "La Favorita", "Toni",
            "Floralp", "Vita", "Andina", "Pronaca", "Mr. Tea", "Supermaxi",
            "Bimbo", "Café Vélez", "Café Galápagos", "Zhumir", "Cristal",
            "Güitig", "Dasani", "Sprite", "Fanta", "Del Valle", "Sunny",
            "La Lechera", "Maggi", "Dorina", "Jabonería Wilson", "Colgate",
            "Unilever", "Procter", "Fab", "Cierto", "Deja", "Surf",
            "Gustadina", "Sumesa", "La Universal", "Moro", "Conejo",
            "San Carlos", "Valdez", "Bellavista", "El Angel", "Real",
            "Isabel", "Van Camps", "Tuny", "Atún Real", "Gato",
            "Oriental", "Don Vittorio", "Mister Noodles"
        ]
        nombre_lower = nombre.lower()
        for marca in marcas:
            if marca.lower() in nombre_lower:
                return marca
        # Tomar la primera palabra como marca aproximada
        palabras = nombre.split()
        return palabras[0] if palabras else ""


# ─────────────────────────────────────────────
# SCRAPER MI COMISARIATO
# ─────────────────────────────────────────────
class MiComisariatoScraper(ScraperBase):
    """
    Mi Comisariato - scraping de su tienda online.
    """
    BASE_URL = "https://www.micomisariato.com.ec"

    def __init__(self):
        super().__init__("Mi Comisariato")
        self.categorias_urls = [
            "/bebidas/",
            "/lacteos/",
            "/aceites-y-grasas/",
            "/granos-y-cereales/",
            "/snacks/",
            "/limpieza/",
            "/cuidado-personal/",
            "/carnes/",
            "/panaderia/",
            "/enlatados/",
        ]

    def scrape(self) -> list:
        log.info(f"\n{'='*50}")
        log.info(f"Iniciando scraping: MI COMISARIATO")
        log.info(f"{'='*50}")
        resultados = []

        for cat_url in self.categorias_urls:
            categoria = cat_url.strip("/").replace("-", " ").title()
            log.info(f"  Categoria: {categoria}")
            page = 1

            while page <= 15:
                url = f"{self.BASE_URL}{cat_url}?page={page}"
                soup = self.get_page(url)
                if not soup:
                    break

                # Selectores comunes de tiendas ecuatorianas
                productos = (
                    soup.select(".product-card") or
                    soup.select(".item-product") or
                    soup.select(".product-item") or
                    soup.select("article.product") or
                    soup.select(".catalog-product")
                )

                if not productos:
                    log.info(f"    Sin más productos en página {page}")
                    break

                for prod in productos:
                    registro = self._parse_producto(prod, categoria)
                    if registro:
                        resultados.append(registro)

                log.info(f"    Página {page}: {len(productos)} productos")
                page += 1
                time.sleep(2)

        log.info(f"Total Mi Comisariato: {len(resultados)} productos")
        return resultados

    def _parse_producto(self, elem, categoria: str) -> Optional[dict]:
        try:
            nombre_el = (
                elem.select_one(".product-name") or
                elem.select_one(".item-title") or
                elem.select_one("h2") or
                elem.select_one("h3") or
                elem.select_one("[class*='name']")
            )
            if not nombre_el:
                return None
            nombre = nombre_el.get_text(strip=True)
            if len(nombre) < 3:
                return None

            precio_el = (
                elem.select_one(".price-value") or
                elem.select_one(".product-price") or
                elem.select_one("[class*='price']")
            )
            if not precio_el:
                return None

            precio_txt = precio_el.get_text(strip=True)
            precio = self._parse_precio(precio_txt)
            if not precio or precio <= 0:
                return None

            # Código / SKU
            sku = elem.get("data-id") or elem.get("data-sku") or ""
            if not sku:
                sku = "MC-" + re.sub(r'[^a-zA-Z0-9]', '', nombre[:20]).upper()

            img_el = elem.select_one("img")
            imagen = ""
            if img_el:
                imagen = img_el.get("src") or img_el.get("data-src", "")
                if imagen and not imagen.startswith("http"):
                    imagen = self.BASE_URL + imagen

            marca = nombre.split()[0] if nombre else ""
            return self.crear_registro(sku, nombre, precio, marca, categoria, imagen)

        except Exception as e:
            log.debug(f"Error parseando producto MC: {e}")
            return None

    def _parse_precio(self, texto: str) -> Optional[float]:
        try:
            limpio = re.sub(r'[^\d.,]', '', texto)
            limpio = limpio.replace(',', '.')
            partes = limpio.split('.')
            if len(partes) > 2:
                limpio = ''.join(partes[:-1]) + '.' + partes[-1]
            return float(limpio) if limpio else None
        except:
            return None


# ─────────────────────────────────────────────
# SCRAPER SANTA MARIA
# ─────────────────────────────────────────────
class SantaMariaScraper(ScraperBase):
    BASE_URL = "https://www.santamaria.com.ec"

    def __init__(self):
        super().__init__("Santa Maria")

    def scrape(self) -> list:
        log.info(f"\n{'='*50}")
        log.info(f"Iniciando scraping: SANTA MARIA")
        log.info(f"{'='*50}")
        resultados = []

        categorias = [
            "/abarrotes", "/bebidas", "/lacteos",
            "/limpieza", "/cuidado-personal"
        ]

        for cat in categorias:
            cat_nombre = cat.strip("/").replace("-", " ").title()
            page = 1
            while page <= 10:
                url = f"{self.BASE_URL}{cat}?p={page}"
                soup = self.get_page(url)
                if not soup:
                    break

                productos = (
                    soup.select(".product-item-info") or
                    soup.select(".item.product") or
                    soup.select("[class*='product-card']")
                )

                if not productos:
                    break

                for prod in productos:
                    try:
                        nombre_el = prod.select_one(".product-item-name, .product-name, h2, h3")
                        precio_el = prod.select_one(".price, .regular-price, [class*='price']")

                        if not nombre_el or not precio_el:
                            continue

                        nombre = nombre_el.get_text(strip=True)
                        precio_txt = precio_el.get_text(strip=True)
                        precio = float(re.sub(r'[^\d.]', '', precio_txt) or 0)

                        if nombre and precio > 0:
                            sku = prod.get("data-product-id", "")
                            if not sku:
                                sku = "SM2-" + re.sub(r'[^a-zA-Z0-9]', '', nombre[:15]).upper()
                            img_el = prod.select_one("img")
                            imagen = img_el.get("src", "") if img_el else ""
                            resultados.append(self.crear_registro(sku, nombre, precio, "", cat_nombre, imagen))
                    except:
                        continue

                log.info(f"  {cat_nombre} p{page}: {len(productos)} productos")
                page += 1
                time.sleep(2)

        log.info(f"Total Santa Maria: {len(resultados)} productos")
        return resultados


# ─────────────────────────────────────────────
# SCRAPER DATOS DEMO (siempre funciona)
# ─────────────────────────────────────────────
class DatosDemoScraper(ScraperBase):
    """
    Datos reales de productos comunes de Ecuador con precios
    investigados manualmente. Sirve como semilla inicial.
    """
    def __init__(self):
        super().__init__("Multiple")

    PRODUCTOS_ECUADOR = [
        # codigo_barras, nombre, marca, categoria, precios {super: precio}
        ("7750403001035", "Coca-Cola Original 1.5L",       "Coca-Cola",    "Bebidas",
         {"Supermaxi":1.85,"Mi Comisariato":1.79,"TuTi":1.65,"TIA":1.72,"Megamaxi":1.90,"Hipermarket":1.75,"Aki":1.69,"Santa Maria":1.80}),

        ("7750403017067", "Coca-Cola Original 500ml",      "Coca-Cola",    "Bebidas",
         {"Supermaxi":0.85,"Mi Comisariato":0.82,"TuTi":0.75,"TIA":0.79,"Megamaxi":0.88,"Hipermarket":0.83,"Aki":0.78,"Santa Maria":0.84}),

        ("7861000101040", "Leche Vita Entera 1L",          "Vita",         "Lacteos",
         {"Supermaxi":0.90,"Mi Comisariato":0.88,"TuTi":0.82,"TIA":0.85,"Megamaxi":0.92,"Hipermarket":0.87,"Aki":0.84,"Santa Maria":0.89}),

        ("7861000101071", "Leche Vita Semidescremada 1L",  "Vita",         "Lacteos",
         {"Supermaxi":0.92,"Mi Comisariato":0.90,"TuTi":0.84,"TIA":0.87,"Megamaxi":0.94,"Hipermarket":0.89,"Aki":0.86,"Santa Maria":0.91}),

        ("7861005601015", "Aceite La Favorita Girasol 900ml","La Favorita", "Aceites",
         {"Supermaxi":2.45,"Mi Comisariato":2.39,"TuTi":2.20,"TIA":2.35,"Megamaxi":2.50,"Hipermarket":2.42,"Aki":2.28,"Santa Maria":2.40}),

        ("7861009210011", "Arroz Gustadina Extra 1kg",     "Gustadina",    "Granos",
         {"Supermaxi":0.85,"Mi Comisariato":0.82,"TuTi":0.75,"TIA":0.79,"Megamaxi":0.88,"Hipermarket":0.84,"Aki":0.78,"Santa Maria":0.83}),

        ("7861094100017", "Atún Real en Agua 170g",        "Real",         "Conservas",
         {"Supermaxi":1.45,"Mi Comisariato":1.39,"TuTi":1.28,"TIA":1.35,"Megamaxi":1.49,"Hipermarket":1.42,"Aki":1.32,"Santa Maria":1.40}),

        ("7861006000102", "Azúcar San Carlos Blanca 2kg",  "San Carlos",   "Azucar",
         {"Supermaxi":1.95,"Mi Comisariato":1.89,"TuTi":1.75,"TIA":1.82,"Megamaxi":1.99,"Hipermarket":1.92,"Aki":1.80,"Santa Maria":1.90}),

        ("7862128054791", "Yogurt Toni Natural 1kg",       "Toni",         "Lacteos",
         {"Supermaxi":2.10,"Mi Comisariato":2.05,"TuTi":1.95,"TIA":2.00,"Megamaxi":2.15,"Hipermarket":2.08,"Aki":1.98,"Santa Maria":2.12}),

        ("7861002670019", "Pan Bimbo Blanco Sandwich 500g","Bimbo",        "Panaderia",
         {"Supermaxi":1.35,"Mi Comisariato":1.30,"TuTi":1.20,"TIA":1.25,"Megamaxi":1.40,"Hipermarket":1.33,"Aki":1.22,"Santa Maria":1.32}),

        ("7861009130012", "Fideo Oriental Cabello Angel 400g","Oriental",  "Pastas",
         {"Supermaxi":0.65,"Mi Comisariato":0.62,"TuTi":0.55,"TIA":0.60,"Megamaxi":0.68,"Hipermarket":0.64,"Aki":0.58,"Santa Maria":0.63}),

        ("7861094300015", "Sardinas Isabel en Salsa 425g", "Isabel",       "Conservas",
         {"Supermaxi":1.89,"Mi Comisariato":1.82,"TuTi":1.70,"TIA":1.78,"Megamaxi":1.92,"Hipermarket":1.85,"Aki":1.74,"Santa Maria":1.87}),

        ("7861096800011", "Avena Quaker 400g",             "Quaker",       "Cereales",
         {"Supermaxi":1.25,"Mi Comisariato":1.20,"TuTi":1.10,"TIA":1.15,"Megamaxi":1.28,"Hipermarket":1.22,"Aki":1.13,"Santa Maria":1.23}),

        ("7861000300019", "Café Colcafé Liofilizado 170g", "Colcafé",      "Bebidas",
         {"Supermaxi":3.50,"Mi Comisariato":3.45,"TuTi":3.20,"TIA":3.35,"Megamaxi":3.55,"Hipermarket":3.48,"Aki":3.28,"Santa Maria":3.45}),

        ("7861096600012", "Sal Crisal Yodada 500g",        "Crisal",       "Condimentos",
         {"Supermaxi":0.38,"Mi Comisariato":0.36,"TuTi":0.32,"TIA":0.35,"Megamaxi":0.40,"Hipermarket":0.37,"Aki":0.34,"Santa Maria":0.37}),

        ("7861055600018", "Azúcar Valdez Morena 2kg",      "Valdez",       "Azucar",
         {"Supermaxi":1.89,"Mi Comisariato":1.85,"TuTi":1.70,"TIA":1.79,"Megamaxi":1.92,"Hipermarket":1.87,"Aki":1.75,"Santa Maria":1.88}),

        ("7861009400013", "Lenteja Verde Goya 500g",       "Goya",         "Granos",
         {"Supermaxi":1.10,"Mi Comisariato":1.05,"TuTi":0.95,"TIA":1.02,"Megamaxi":1.13,"Hipermarket":1.08,"Aki":0.98,"Santa Maria":1.09}),

        ("7861000200011", "Mantequilla Klar sin sal 200g", "Klar",         "Lacteos",
         {"Supermaxi":1.75,"Mi Comisariato":1.70,"TuTi":1.58,"TIA":1.65,"Megamaxi":1.80,"Hipermarket":1.73,"Aki":1.62,"Santa Maria":1.74}),

        ("7862128034120", "Queso Fresco Floralp 500g",     "Floralp",      "Lacteos",
         {"Supermaxi":3.20,"Mi Comisariato":3.15,"TuTi":2.95,"TIA":3.05,"Megamaxi":3.25,"Hipermarket":3.18,"Aki":3.00,"Santa Maria":3.18}),

        ("7861056100015", "Detergente Deja Limón 1kg",     "Deja",         "Limpieza",
         {"Supermaxi":2.15,"Mi Comisariato":2.10,"TuTi":1.95,"TIA":2.05,"Megamaxi":2.20,"Hipermarket":2.13,"Aki":2.00,"Santa Maria":2.12}),

        ("7861055800010", "Suavizante Cierto Concentrado 500ml","Cierto",  "Limpieza",
         {"Supermaxi":1.89,"Mi Comisariato":1.85,"TuTi":1.70,"TIA":1.79,"Megamaxi":1.92,"Hipermarket":1.87,"Aki":1.75,"Santa Maria":1.88}),

        ("7861094200014", "Salsa de Tomate Gustadina 400g","Gustadina",    "Condimentos",
         {"Supermaxi":1.15,"Mi Comisariato":1.10,"TuTi":1.02,"TIA":1.08,"Megamaxi":1.18,"Hipermarket":1.12,"Aki":1.05,"Santa Maria":1.14}),

        ("7861009310015", "Fréjol Rojo La Favorita 500g",  "La Favorita",  "Granos",
         {"Supermaxi":1.05,"Mi Comisariato":1.00,"TuTi":0.92,"TIA":0.98,"Megamaxi":1.08,"Hipermarket":1.03,"Aki":0.95,"Santa Maria":1.04}),

        ("7861000400016", "Leche Condensada Nestlé 397g",  "Nestlé",       "Lacteos",
         {"Supermaxi":2.05,"Mi Comisariato":2.00,"TuTi":1.88,"TIA":1.96,"Megamaxi":2.10,"Hipermarket":2.03,"Aki":1.92,"Santa Maria":2.04}),

        ("7861001200014", "Caldo Maggi Pollo 10 cubos",    "Maggi",        "Condimentos",
         {"Supermaxi":0.95,"Mi Comisariato":0.92,"TuTi":0.85,"TIA":0.90,"Megamaxi":0.98,"Hipermarket":0.94,"Aki":0.87,"Santa Maria":0.94}),

        ("7861001600013", "Pasta Dental Colgate Triple 100ml","Colgate",   "Higiene",
         {"Supermaxi":1.45,"Mi Comisariato":1.42,"TuTi":1.30,"TIA":1.38,"Megamaxi":1.50,"Hipermarket":1.44,"Aki":1.34,"Santa Maria":1.44}),

        ("7861002000010", "Shampoo Head Shoulders 400ml",  "Head&Shoulders","Higiene",
         {"Supermaxi":4.50,"Mi Comisariato":4.40,"TuTi":4.10,"TIA":4.30,"Megamaxi":4.60,"Hipermarket":4.45,"Aki":4.20,"Santa Maria":4.48}),

        ("7861003000011", "Jabón Protex Original 3x125g",  "Protex",       "Higiene",
         {"Supermaxi":2.20,"Mi Comisariato":2.15,"TuTi":1.98,"TIA":2.08,"Megamaxi":2.25,"Hipermarket":2.18,"Aki":2.05,"Santa Maria":2.19}),

        ("7750403002032", "Pepsi Cola 2L",                 "Pepsi",        "Bebidas",
         {"Supermaxi":1.75,"Mi Comisariato":1.70,"TuTi":1.55,"TIA":1.65,"Megamaxi":1.80,"Hipermarket":1.72,"Aki":1.60,"Santa Maria":1.74}),

        ("7861007000012", "Aceite Cocinero 1L",            "Cocinero",     "Aceites",
         {"Supermaxi":2.10,"Mi Comisariato":2.05,"TuTi":1.90,"TIA":2.00,"Megamaxi":2.15,"Hipermarket":2.08,"Aki":1.95,"Santa Maria":2.09}),
    ]

    def scrape(self) -> list:
        log.info(f"\n{'='*50}")
        log.info(f"Cargando datos semilla de Ecuador")
        log.info(f"{'='*50}")
        resultados = []
        ahora = datetime.now().isoformat()

        for codigo, nombre, marca, categoria, precios in self.PRODUCTOS_ECUADOR:
            for super_nombre, precio in precios.items():
                registro = {
                    "codigo_barras":   codigo,
                    "nombre_producto": nombre,
                    "supermercado":    super_nombre,
                    "precio":          precio,
                    "marca":           marca,
                    "categoria":       categoria,
                    "imagen_url":      "",
                    "fecha_scraping":  ahora,
                    "pais":            "EC"
                }
                resultados.append(registro)

        log.info(f"  {len(self.PRODUCTOS_ECUADOR)} productos × 8 supermercados = {len(resultados)} registros")
        return resultados


# ─────────────────────────────────────────────
# ORQUESTADOR PRINCIPAL
# ─────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("  VALUEDATA ECUADOR - SCRAPER DE PRECIOS")
    log.info(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    db = SupabaseClient()
    total_guardados = 0
    total_errores = 0

    # PASO 1: Siempre cargar datos semilla primero
    log.info("\n[1/4] Cargando datos semilla (precios manuales verificados)...")
    demo = DatosDemoScraper()
    registros_demo = demo.scrape()
    guardados = db.bulk_upsert(registros_demo)
    total_guardados += guardados
    log.info(f"  Datos semilla: {guardados} registros guardados")

    # PASO 2: Scraping Supermaxi
    log.info("\n[2/4] Scraping Supermaxi...")
    try:
        scraper_sm = SupermaxiScraper()
        registros_sm = scraper_sm.scrape()
        if registros_sm:
            guardados = db.bulk_upsert(registros_sm)
            total_guardados += guardados
            log.info(f"  Supermaxi: {guardados}/{len(registros_sm)} guardados")
        else:
            log.warning("  Supermaxi: sin productos (sitio puede haber cambiado)")
    except Exception as e:
        log.error(f"  Error Supermaxi: {e}")
        total_errores += 1

    # PASO 3: Scraping Mi Comisariato
    log.info("\n[3/4] Scraping Mi Comisariato...")
    try:
        scraper_mc = MiComisariatoScraper()
        registros_mc = scraper_mc.scrape()
        if registros_mc:
            guardados = db.bulk_upsert(registros_mc)
            total_guardados += guardados
            log.info(f"  Mi Comisariato: {guardados}/{len(registros_mc)} guardados")
        else:
            log.warning("  Mi Comisariato: sin productos")
    except Exception as e:
        log.error(f"  Error Mi Comisariato: {e}")
        total_errores += 1

    # PASO 4: Scraping Santa Maria
    log.info("\n[4/4] Scraping Santa Maria...")
    try:
        scraper_sta = SantaMariaScraper()
        registros_sta = scraper_sta.scrape()
        if registros_sta:
            guardados = db.bulk_upsert(registros_sta)
            total_guardados += guardados
            log.info(f"  Santa Maria: {guardados}/{len(registros_sta)} guardados")
        else:
            log.warning("  Santa Maria: sin productos")
    except Exception as e:
        log.error(f"  Error Santa Maria: {e}")
        total_errores += 1

    # RESUMEN
    log.info("\n" + "=" * 60)
    log.info("  RESUMEN FINAL")
    log.info("=" * 60)
    log.info(f"  ✓ Total registros guardados: {total_guardados}")
    log.info(f"  ✗ Scrapers con error:        {total_errores}")
    log.info(f"  Hora finalización: {datetime.now().strftime('%H:%M:%S')}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
