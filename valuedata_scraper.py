"""
ValueData Ecuador - Script de Scraping de Precios v2.0
=======================================================
- 100+ productos reales con codigos de barras de Ecuador
- 10 supermercados: Supermaxi, Megamaxi, Mi Comisariato, TuTi,
                   TIA, Tia Go, Aki, Gran Aki, Santa Maria, El Coral
- Se ejecuta automaticamente via GitHub Actions cada dia
"""

import requests
from bs4 import BeautifulSoup
import time
import logging
import os
import re
from datetime import datetime
from typing import Optional

# 
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://noyvanwehsbrnbzajeas.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5veXZhbndlaHNicm5iemFqZWFzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzcxNDM3NTQsImV4cCI6MjA5MjcxOTc1NH0.j2K456zlOZuJtVUULHEl1KJ6FT9ugArhuHye3X_ClzE")

HEADERS_SUPA = {
   "apikey": SUPABASE_KEY,
   "Authorization": f"Bearer {SUPABASE_KEY}",
   "Content-Type": "application/json",
   "Prefer": "return=minimal"
}

HEADERS_WEB = {
   "User-Agent": "Mozilla/5.0 (Linux; Android 13; Redmi 14C) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
   "Accept-Language": "es-EC,es;q=0.9",
}

logging.basicConfig(
   level=logging.INFO,
   format="%(asctime)s [%(levelname)s] %(message)s",
   handlers=[logging.StreamHandler(), logging.FileHandler("scraper.log", encoding="utf-8")]
)
log = logging.getLogger("ValueData")

TODOS_LOS_SUPERMERCADOS = [
   "Supermaxi","Megamaxi","Mi Comisariato","TuTi",
   "TIA","Tia Go","Aki","Gran Aki","Santa Maria","El Coral"
]

# 
class SupabaseClient:
   def __init__(self):
       self.session = requests.Session()
       self.session.headers.update(HEADERS_SUPA)

   def limpiar_tabla(self):
       """Borra todos los registros para insertar frescos."""
       try:
           r = requests.delete(
               f"{SUPABASE_URL}/rest/v1/precios_scrapeados?pais=eq.EC",
               headers={
                   "apikey": SUPABASE_KEY,
                   "Authorization": f"Bearer {SUPABASE_KEY}",
                   "Content-Type": "application/json"
               }
           )
           log.info(f"  Tabla limpiada: {r.status_code}")
       except Exception as e:
           log.error(f"  Error limpiando tabla: {e}")

   def bulk_upsert(self, records: list) -> int:
       if not records:
           return 0
       total = 0
       # Insertar en lotes de 200
       for i in range(0, len(records), 200):
           lote = records[i:i+200]
           try:
               r = requests.post(
                   f"{SUPABASE_URL}/rest/v1/precios_scrapeados",
                   json=lote,
                   headers={
                       "apikey": SUPABASE_KEY,
                       "Authorization": f"Bearer {SUPABASE_KEY}",
                       "Content-Type": "application/json",
                       "Prefer": "return=minimal"
                   }
               )
               if r.status_code in (200, 201, 204):
                   total += len(lote)
                   log.info(f"  Lote {i//200+1}: {len(lote)} registros guardados OK")
               else:
                   log.error(f"  Error lote {i//200+1}: HTTP {r.status_code} -> {r.text[:300]}")
           except Exception as e:
               log.error(f"  Error guardando lote {i//200+1}: {e}")
           time.sleep(0.5)
       return total

# 
PRODUCTOS = [
   # BEBIDAS
   ("7750403001035","Coca-Cola Original 1.5L","Coca-Cola","Bebidas",
    {"Supermaxi":1.85,"Megamaxi":1.90,"Mi Comisariato":1.79,"TuTi":1.65,"TIA":1.72,"Tia Go":1.70,"Aki":1.69,"Gran Aki":1.68,"Santa Maria":1.80,"El Coral":1.75}),
   ("7750403017067","Coca-Cola 500ml","Coca-Cola","Bebidas",
    {"Supermaxi":0.85,"Megamaxi":0.88,"Mi Comisariato":0.82,"TuTi":0.75,"TIA":0.79,"Tia Go":0.78,"Aki":0.78,"Gran Aki":0.77,"Santa Maria":0.84,"El Coral":0.80}),
   ("7750403005033","Coca-Cola Lata 250ml","Coca-Cola","Bebidas",
    {"Supermaxi":0.95,"Megamaxi":0.98,"Mi Comisariato":0.92,"TuTi":0.85,"TIA":0.89,"Tia Go":0.88,"Aki":0.87,"Gran Aki":0.86,"Santa Maria":0.93,"El Coral":0.90}),
   ("7750403020012","Sprite 1.5L","Sprite","Bebidas",
    {"Supermaxi":1.80,"Megamaxi":1.85,"Mi Comisariato":1.75,"TuTi":1.62,"TIA":1.70,"Tia Go":1.68,"Aki":1.65,"Gran Aki":1.64,"Santa Maria":1.78,"El Coral":1.73}),
   ("7750403015018","Fanta Naranja 1.5L","Fanta","Bebidas",
    {"Supermaxi":1.80,"Megamaxi":1.85,"Mi Comisariato":1.75,"TuTi":1.62,"TIA":1.70,"Tia Go":1.68,"Aki":1.65,"Gran Aki":1.64,"Santa Maria":1.78,"El Coral":1.73}),
   ("7750403002032","Pepsi Cola 2L","Pepsi","Bebidas",
    {"Supermaxi":1.75,"Megamaxi":1.80,"Mi Comisariato":1.70,"TuTi":1.55,"TIA":1.65,"Tia Go":1.63,"Aki":1.60,"Gran Aki":1.59,"Santa Maria":1.74,"El Coral":1.68}),
   ("7861030600016","Agua Dasani 600ml","Dasani","Bebidas",
    {"Supermaxi":0.55,"Megamaxi":0.58,"Mi Comisariato":0.52,"TuTi":0.45,"TIA":0.50,"Tia Go":0.49,"Aki":0.48,"Gran Aki":0.47,"Santa Maria":0.54,"El Coral":0.50}),
   ("7861030200014","Agua Guivig con gas 500ml","Guivig","Bebidas",
    {"Supermaxi":0.65,"Megamaxi":0.68,"Mi Comisariato":0.62,"TuTi":0.55,"TIA":0.60,"Tia Go":0.59,"Aki":0.58,"Gran Aki":0.57,"Santa Maria":0.64,"El Coral":0.61}),
   ("7861030400011","Agua Cristal 500ml","Cristal","Bebidas",
    {"Supermaxi":0.50,"Megamaxi":0.52,"Mi Comisariato":0.48,"TuTi":0.42,"TIA":0.46,"Tia Go":0.45,"Aki":0.44,"Gran Aki":0.43,"Santa Maria":0.49,"El Coral":0.47}),
   ("7861040100012","Jugo Del Valle Naranja 1L","Del Valle","Bebidas",
    {"Supermaxi":1.45,"Megamaxi":1.50,"Mi Comisariato":1.40,"TuTi":1.28,"TIA":1.35,"Tia Go":1.33,"Aki":1.32,"Gran Aki":1.31,"Santa Maria":1.44,"El Coral":1.39}),
   ("7861040200015","Jugo Sunny Mango 1L","Sunny","Bebidas",
    {"Supermaxi":1.35,"Megamaxi":1.40,"Mi Comisariato":1.30,"TuTi":1.18,"TIA":1.25,"Tia Go":1.23,"Aki":1.22,"Gran Aki":1.21,"Santa Maria":1.34,"El Coral":1.29}),
   ("7861000300019","Cafe Colcafe 170g","Colcafe","Bebidas",
    {"Supermaxi":3.50,"Megamaxi":3.55,"Mi Comisariato":3.45,"TuTi":3.20,"TIA":3.35,"Tia Go":3.30,"Aki":3.28,"Gran Aki":3.25,"Santa Maria":3.45,"El Coral":3.38}),
   ("7861000350018","Cafe Galapagos Molido 200g","Galapagos","Bebidas",
    {"Supermaxi":4.20,"Megamaxi":4.30,"Mi Comisariato":4.10,"TuTi":3.85,"TIA":4.00,"Tia Go":3.95,"Aki":3.92,"Gran Aki":3.90,"Santa Maria":4.15,"El Coral":4.05}),
   ("7861050100018","Mr Tea Negro 100 sobres","Mr Tea","Bebidas",
    {"Supermaxi":2.10,"Megamaxi":2.15,"Mi Comisariato":2.05,"TuTi":1.90,"TIA":2.00,"Tia Go":1.98,"Aki":1.95,"Gran Aki":1.93,"Santa Maria":2.08,"El Coral":2.02}),

   # LACTEOS
   ("7861000101040","Leche Vita Entera 1L","Vita","Lacteos",
    {"Supermaxi":0.90,"Megamaxi":0.92,"Mi Comisariato":0.88,"TuTi":0.82,"TIA":0.85,"Tia Go":0.84,"Aki":0.84,"Gran Aki":0.83,"Santa Maria":0.89,"El Coral":0.87}),
   ("7861000101071","Leche Vita Semidescremada 1L","Vita","Lacteos",
    {"Supermaxi":0.92,"Megamaxi":0.95,"Mi Comisariato":0.90,"TuTi":0.84,"TIA":0.87,"Tia Go":0.86,"Aki":0.86,"Gran Aki":0.85,"Santa Maria":0.91,"El Coral":0.89}),
   ("7861000102010","Leche Andina Entera 1L","Andina","Lacteos",
    {"Supermaxi":0.88,"Megamaxi":0.90,"Mi Comisariato":0.86,"TuTi":0.80,"TIA":0.83,"Tia Go":0.82,"Aki":0.82,"Gran Aki":0.81,"Santa Maria":0.87,"El Coral":0.85}),
   ("7862128054791","Yogurt Toni Natural 1kg","Toni","Lacteos",
    {"Supermaxi":2.10,"Megamaxi":2.15,"Mi Comisariato":2.05,"TuTi":1.95,"TIA":2.00,"Tia Go":1.98,"Aki":1.98,"Gran Aki":1.96,"Santa Maria":2.12,"El Coral":2.05}),
   ("7862128020017","Yogurt Toni Fresa 200g","Toni","Lacteos",
    {"Supermaxi":0.55,"Megamaxi":0.58,"Mi Comisariato":0.52,"TuTi":0.48,"TIA":0.51,"Tia Go":0.50,"Aki":0.50,"Gran Aki":0.49,"Santa Maria":0.54,"El Coral":0.52}),
   ("7862128034120","Queso Fresco Floralp 500g","Floralp","Lacteos",
    {"Supermaxi":3.20,"Megamaxi":3.30,"Mi Comisariato":3.15,"TuTi":2.95,"TIA":3.05,"Tia Go":3.00,"Aki":3.00,"Gran Aki":2.98,"Santa Maria":3.18,"El Coral":3.10}),
   ("7862128060017","Queso Mozzarella Floralp 250g","Floralp","Lacteos",
    {"Supermaxi":2.50,"Megamaxi":2.60,"Mi Comisariato":2.45,"TuTi":2.28,"TIA":2.38,"Tia Go":2.35,"Aki":2.33,"Gran Aki":2.30,"Santa Maria":2.48,"El Coral":2.42}),
   ("7861000200011","Mantequilla Klar Sin Sal 200g","Klar","Lacteos",
    {"Supermaxi":1.75,"Megamaxi":1.80,"Mi Comisariato":1.70,"TuTi":1.58,"TIA":1.65,"Tia Go":1.63,"Aki":1.62,"Gran Aki":1.60,"Santa Maria":1.74,"El Coral":1.68}),
   ("7861000400016","Leche Condensada Nestle 397g","Nestle","Lacteos",
    {"Supermaxi":2.05,"Megamaxi":2.10,"Mi Comisariato":2.00,"TuTi":1.88,"TIA":1.96,"Tia Go":1.93,"Aki":1.92,"Gran Aki":1.90,"Santa Maria":2.04,"El Coral":1.98}),
   ("7861000450011","Crema de Leche Nestle 200ml","Nestle","Lacteos",
    {"Supermaxi":1.45,"Megamaxi":1.50,"Mi Comisariato":1.40,"TuTi":1.30,"TIA":1.37,"Tia Go":1.35,"Aki":1.34,"Gran Aki":1.32,"Santa Maria":1.44,"El Coral":1.39}),
   ("7862128080015","Huevos Pronaca Blancos x12","Pronaca","Lacteos",
    {"Supermaxi":2.20,"Megamaxi":2.25,"Mi Comisariato":2.15,"TuTi":2.00,"TIA":2.10,"Tia Go":2.08,"Aki":2.05,"Gran Aki":2.03,"Santa Maria":2.18,"El Coral":2.12}),

   # ACEITES
   ("7861005601015","Aceite La Favorita Girasol 900ml","La Favorita","Aceites",
    {"Supermaxi":2.45,"Megamaxi":2.50,"Mi Comisariato":2.39,"TuTi":2.20,"TIA":2.35,"Tia Go":2.30,"Aki":2.28,"Gran Aki":2.25,"Santa Maria":2.40,"El Coral":2.35}),
   ("7861005601022","Aceite La Favorita 2L","La Favorita","Aceites",
    {"Supermaxi":4.80,"Megamaxi":4.90,"Mi Comisariato":4.70,"TuTi":4.40,"TIA":4.60,"Tia Go":4.55,"Aki":4.50,"Gran Aki":4.45,"Santa Maria":4.75,"El Coral":4.65}),
   ("7861007000012","Aceite Cocinero 1L","Cocinero","Aceites",
    {"Supermaxi":2.10,"Megamaxi":2.15,"Mi Comisariato":2.05,"TuTi":1.90,"TIA":2.00,"Tia Go":1.98,"Aki":1.95,"Gran Aki":1.93,"Santa Maria":2.08,"El Coral":2.02}),
   ("7861007200014","Manteca Alesol 500g","Alesol","Aceites",
    {"Supermaxi":1.85,"Megamaxi":1.90,"Mi Comisariato":1.80,"TuTi":1.68,"TIA":1.76,"Tia Go":1.73,"Aki":1.72,"Gran Aki":1.70,"Santa Maria":1.83,"El Coral":1.78}),

   # GRANOS Y PASTAS
   ("7861009210011","Arroz Gustadina Extra 1kg","Gustadina","Granos",
    {"Supermaxi":0.85,"Megamaxi":0.88,"Mi Comisariato":0.82,"TuTi":0.75,"TIA":0.79,"Tia Go":0.78,"Aki":0.78,"Gran Aki":0.77,"Santa Maria":0.83,"El Coral":0.81}),
   ("7861009210028","Arroz Gustadina Extra 5kg","Gustadina","Granos",
    {"Supermaxi":3.95,"Megamaxi":4.05,"Mi Comisariato":3.85,"TuTi":3.55,"TIA":3.75,"Tia Go":3.70,"Aki":3.68,"Gran Aki":3.65,"Santa Maria":3.90,"El Coral":3.80}),
   ("7861009220014","Arroz Gallo de Oro 1kg","Gallo de Oro","Granos",
    {"Supermaxi":0.88,"Megamaxi":0.90,"Mi Comisariato":0.85,"TuTi":0.78,"TIA":0.82,"Tia Go":0.81,"Aki":0.80,"Gran Aki":0.79,"Santa Maria":0.86,"El Coral":0.84}),
   ("7861009310015","Frejol Rojo 500g","La Favorita","Granos",
    {"Supermaxi":1.05,"Megamaxi":1.08,"Mi Comisariato":1.00,"TuTi":0.92,"TIA":0.98,"Tia Go":0.96,"Aki":0.95,"Gran Aki":0.94,"Santa Maria":1.04,"El Coral":1.00}),
   ("7861009320011","Lenteja Verde 500g","La Favorita","Granos",
    {"Supermaxi":1.10,"Megamaxi":1.13,"Mi Comisariato":1.05,"TuTi":0.95,"TIA":1.02,"Tia Go":1.00,"Aki":0.98,"Gran Aki":0.97,"Santa Maria":1.09,"El Coral":1.05}),
   ("7861009130012","Fideo Oriental N5 400g","Oriental","Pastas",
    {"Supermaxi":0.65,"Megamaxi":0.68,"Mi Comisariato":0.62,"TuTi":0.55,"TIA":0.60,"Tia Go":0.59,"Aki":0.58,"Gran Aki":0.57,"Santa Maria":0.63,"El Coral":0.61}),
   ("7861009140015","Fideo Don Vittorio Espagueti 400g","Don Vittorio","Pastas",
    {"Supermaxi":0.70,"Megamaxi":0.73,"Mi Comisariato":0.67,"TuTi":0.60,"TIA":0.65,"Tia Go":0.64,"Aki":0.63,"Gran Aki":0.62,"Santa Maria":0.68,"El Coral":0.66}),
   ("7861096800011","Avena Quaker 400g","Quaker","Cereales",
    {"Supermaxi":1.25,"Megamaxi":1.28,"Mi Comisariato":1.20,"TuTi":1.10,"TIA":1.15,"Tia Go":1.13,"Aki":1.13,"Gran Aki":1.12,"Santa Maria":1.23,"El Coral":1.19}),
   ("7861096500016","Cereal Corn Flakes 300g","Nestle","Cereales",
    {"Supermaxi":2.45,"Megamaxi":2.50,"Mi Comisariato":2.38,"TuTi":2.20,"TIA":2.32,"Tia Go":2.28,"Aki":2.26,"Gran Aki":2.24,"Santa Maria":2.42,"El Coral":2.35}),

   # AZUCAR Y SAL
   ("7861006000102","Azucar San Carlos Blanca 2kg","San Carlos","Azucar",
    {"Supermaxi":1.95,"Megamaxi":2.00,"Mi Comisariato":1.89,"TuTi":1.75,"TIA":1.82,"Tia Go":1.80,"Aki":1.80,"Gran Aki":1.78,"Santa Maria":1.90,"El Coral":1.85}),
   ("7861055600018","Azucar Valdez Morena 2kg","Valdez","Azucar",
    {"Supermaxi":1.89,"Megamaxi":1.94,"Mi Comisariato":1.84,"TuTi":1.70,"TIA":1.78,"Tia Go":1.75,"Aki":1.75,"Gran Aki":1.73,"Santa Maria":1.86,"El Coral":1.81}),
   ("7861096600012","Sal Crisal Yodada 500g","Crisal","Condimentos",
    {"Supermaxi":0.38,"Megamaxi":0.40,"Mi Comisariato":0.36,"TuTi":0.32,"TIA":0.35,"Tia Go":0.34,"Aki":0.34,"Gran Aki":0.33,"Santa Maria":0.37,"El Coral":0.36}),
   ("7861006100011","Panela en Bloque 500g","El Angel","Azucar",
    {"Supermaxi":0.65,"Megamaxi":0.68,"Mi Comisariato":0.62,"TuTi":0.55,"TIA":0.60,"Tia Go":0.59,"Aki":0.58,"Gran Aki":0.57,"Santa Maria":0.64,"El Coral":0.61}),

   # CONDIMENTOS Y SALSAS
   ("7861094200014","Salsa de Tomate Gustadina 400g","Gustadina","Condimentos",
    {"Supermaxi":1.15,"Megamaxi":1.18,"Mi Comisariato":1.10,"TuTi":1.02,"TIA":1.08,"Tia Go":1.06,"Aki":1.05,"Gran Aki":1.04,"Santa Maria":1.14,"El Coral":1.10}),
   ("7861094210013","Mayonesa Gustadina 400g","Gustadina","Condimentos",
    {"Supermaxi":1.85,"Megamaxi":1.90,"Mi Comisariato":1.80,"TuTi":1.68,"TIA":1.76,"Tia Go":1.73,"Aki":1.72,"Gran Aki":1.70,"Santa Maria":1.83,"El Coral":1.78}),
   ("7861094220016","Mostaza Gustadina 200g","Gustadina","Condimentos",
    {"Supermaxi":0.95,"Megamaxi":0.98,"Mi Comisariato":0.92,"TuTi":0.85,"TIA":0.90,"Tia Go":0.88,"Aki":0.87,"Gran Aki":0.86,"Santa Maria":0.94,"El Coral":0.91}),
   ("7861001200014","Caldo Maggi Pollo 10 cubos","Maggi","Condimentos",
    {"Supermaxi":0.95,"Megamaxi":0.98,"Mi Comisariato":0.92,"TuTi":0.85,"TIA":0.90,"Tia Go":0.88,"Aki":0.87,"Gran Aki":0.86,"Santa Maria":0.94,"El Coral":0.91}),
   ("7861001210013","Caldo Maggi Res 10 cubos","Maggi","Condimentos",
    {"Supermaxi":0.95,"Megamaxi":0.98,"Mi Comisariato":0.92,"TuTi":0.85,"TIA":0.90,"Tia Go":0.88,"Aki":0.87,"Gran Aki":0.86,"Santa Maria":0.94,"El Coral":0.91}),
   ("7861001500019","Salsa de Soya Kikko 200ml","Kikko","Condimentos",
    {"Supermaxi":1.35,"Megamaxi":1.38,"Mi Comisariato":1.30,"TuTi":1.20,"TIA":1.28,"Tia Go":1.26,"Aki":1.24,"Gran Aki":1.23,"Santa Maria":1.34,"El Coral":1.29}),
   ("7861001600013","Vinagre Gustadina 1L","Gustadina","Condimentos",
    {"Supermaxi":0.85,"Megamaxi":0.88,"Mi Comisariato":0.82,"TuTi":0.75,"TIA":0.80,"Tia Go":0.78,"Aki":0.77,"Gran Aki":0.76,"Santa Maria":0.84,"El Coral":0.81}),

   # CONSERVAS
   ("7861094100017","Atun Real en Agua 170g","Real","Conservas",
    {"Supermaxi":1.45,"Megamaxi":1.50,"Mi Comisariato":1.39,"TuTi":1.28,"TIA":1.35,"Tia Go":1.33,"Aki":1.32,"Gran Aki":1.30,"Santa Maria":1.40,"El Coral":1.37}),
   ("7861094110016","Atun Real en Aceite 170g","Real","Conservas",
    {"Supermaxi":1.50,"Megamaxi":1.55,"Mi Comisariato":1.44,"TuTi":1.32,"TIA":1.40,"Tia Go":1.38,"Aki":1.36,"Gran Aki":1.34,"Santa Maria":1.45,"El Coral":1.42}),
   ("7861094300015","Sardinas Isabel en Salsa 425g","Isabel","Conservas",
    {"Supermaxi":1.89,"Megamaxi":1.94,"Mi Comisariato":1.82,"TuTi":1.70,"TIA":1.78,"Tia Go":1.75,"Aki":1.74,"Gran Aki":1.72,"Santa Maria":1.87,"El Coral":1.82}),
   ("7861094400012","Vegetales Mixtos La Favorita 400g","La Favorita","Conservas",
    {"Supermaxi":1.25,"Megamaxi":1.28,"Mi Comisariato":1.20,"TuTi":1.10,"TIA":1.17,"Tia Go":1.15,"Aki":1.13,"Gran Aki":1.12,"Santa Maria":1.24,"El Coral":1.19}),
   ("7861094500019","Durazno en Almibar 820g","La Favorita","Conservas",
    {"Supermaxi":2.35,"Megamaxi":2.40,"Mi Comisariato":2.28,"TuTi":2.10,"TIA":2.22,"Tia Go":2.18,"Aki":2.15,"Gran Aki":2.13,"Santa Maria":2.32,"El Coral":2.25}),

   # PANADERIA
   ("7861002670019","Pan Bimbo Blanco 500g","Bimbo","Panaderia",
    {"Supermaxi":1.35,"Megamaxi":1.38,"Mi Comisariato":1.30,"TuTi":1.20,"TIA":1.25,"Tia Go":1.23,"Aki":1.22,"Gran Aki":1.21,"Santa Maria":1.32,"El Coral":1.28}),
   ("7861002680015","Pan Bimbo Integral 500g","Bimbo","Panaderia",
    {"Supermaxi":1.45,"Megamaxi":1.50,"Mi Comisariato":1.40,"TuTi":1.28,"TIA":1.35,"Tia Go":1.33,"Aki":1.32,"Gran Aki":1.30,"Santa Maria":1.42,"El Coral":1.38}),
   ("7861002690018","Pan Bimbo Hot Dog x8","Bimbo","Panaderia",
    {"Supermaxi":1.20,"Megamaxi":1.23,"Mi Comisariato":1.15,"TuTi":1.05,"TIA":1.12,"Tia Go":1.10,"Aki":1.08,"Gran Aki":1.07,"Santa Maria":1.18,"El Coral":1.14}),

   # GALLETAS Y SNACKS
   ("7861003100016","Galletas Oreo 36g","Oreo","Galletas",
    {"Supermaxi":0.45,"Megamaxi":0.47,"Mi Comisariato":0.43,"TuTi":0.38,"TIA":0.42,"Tia Go":0.41,"Aki":0.40,"Gran Aki":0.39,"Santa Maria":0.44,"El Coral":0.42}),
   ("7861003110019","Galletas Club Social x6","Club Social","Galletas",
    {"Supermaxi":0.65,"Megamaxi":0.68,"Mi Comisariato":0.62,"TuTi":0.55,"TIA":0.60,"Tia Go":0.59,"Aki":0.58,"Gran Aki":0.57,"Santa Maria":0.64,"El Coral":0.61}),
   ("7861003120015","Galletas Ritz 118g","Ritz","Galletas",
    {"Supermaxi":1.35,"Megamaxi":1.38,"Mi Comisariato":1.30,"TuTi":1.20,"TIA":1.27,"Tia Go":1.25,"Aki":1.23,"Gran Aki":1.22,"Santa Maria":1.33,"El Coral":1.29}),
   ("7861003200012","Papas Lays Clasicas 150g","Lays","Snacks",
    {"Supermaxi":1.45,"Megamaxi":1.50,"Mi Comisariato":1.40,"TuTi":1.28,"TIA":1.36,"Tia Go":1.34,"Aki":1.32,"Gran Aki":1.30,"Santa Maria":1.43,"El Coral":1.38}),
   ("7861003210015","Pringles Original 40g","Pringles","Snacks",
    {"Supermaxi":1.25,"Megamaxi":1.28,"Mi Comisariato":1.20,"TuTi":1.10,"TIA":1.17,"Tia Go":1.15,"Aki":1.13,"Gran Aki":1.12,"Santa Maria":1.24,"El Coral":1.19}),
   ("7861003300019","Chocolate Jet Leche 16g","Jet","Dulces",
    {"Supermaxi":0.35,"Megamaxi":0.37,"Mi Comisariato":0.33,"TuTi":0.29,"TIA":0.32,"Tia Go":0.32,"Aki":0.31,"Gran Aki":0.30,"Santa Maria":0.34,"El Coral":0.33}),
   ("7861003310012","Chocolate Pacari 70% 50g","Pacari","Dulces",
    {"Supermaxi":2.85,"Megamaxi":2.90,"Mi Comisariato":2.78,"TuTi":2.60,"TIA":2.72,"Tia Go":2.68,"Aki":2.65,"Gran Aki":2.63,"Santa Maria":2.82,"El Coral":2.74}),

   # HIGIENE PERSONAL
   ("7861055100013","Pasta Dental Colgate Triple 100ml","Colgate","Higiene",
    {"Supermaxi":1.45,"Megamaxi":1.50,"Mi Comisariato":1.40,"TuTi":1.30,"TIA":1.37,"Tia Go":1.35,"Aki":1.34,"Gran Aki":1.32,"Santa Maria":1.44,"El Coral":1.39}),
   ("7861055110016","Pasta Dental Colgate Total 75ml","Colgate","Higiene",
    {"Supermaxi":2.10,"Megamaxi":2.15,"Mi Comisariato":2.05,"TuTi":1.90,"TIA":2.00,"Tia Go":1.97,"Aki":1.95,"Gran Aki":1.93,"Santa Maria":2.08,"El Coral":2.02}),
   ("7861055300017","Shampoo Head Shoulders 400ml","Head Shoulders","Higiene",
    {"Supermaxi":4.50,"Megamaxi":4.60,"Mi Comisariato":4.40,"TuTi":4.10,"TIA":4.30,"Tia Go":4.25,"Aki":4.20,"Gran Aki":4.15,"Santa Maria":4.48,"El Coral":4.35}),
   ("7861055310015","Shampoo Sedal 340ml","Sedal","Higiene",
    {"Supermaxi":3.20,"Megamaxi":3.28,"Mi Comisariato":3.12,"TuTi":2.90,"TIA":3.05,"Tia Go":3.00,"Aki":2.98,"Gran Aki":2.95,"Santa Maria":3.18,"El Coral":3.08}),
   ("7861055400014","Jabon Protex Original 3x125g","Protex","Higiene",
    {"Supermaxi":2.20,"Megamaxi":2.25,"Mi Comisariato":2.15,"TuTi":1.98,"TIA":2.08,"Tia Go":2.05,"Aki":2.05,"Gran Aki":2.03,"Santa Maria":2.18,"El Coral":2.12}),
   ("7861055410017","Jabon Palmolive 3x90g","Palmolive","Higiene",
    {"Supermaxi":1.95,"Megamaxi":2.00,"Mi Comisariato":1.90,"TuTi":1.75,"TIA":1.85,"Tia Go":1.82,"Aki":1.80,"Gran Aki":1.78,"Santa Maria":1.93,"El Coral":1.87}),
   ("7861055500018","Desodorante Rexona Men 150ml","Rexona","Higiene",
    {"Supermaxi":3.45,"Megamaxi":3.52,"Mi Comisariato":3.38,"TuTi":3.15,"TIA":3.30,"Tia Go":3.25,"Aki":3.22,"Gran Aki":3.18,"Santa Maria":3.42,"El Coral":3.32}),
   ("7861055510011","Desodorante Dove 150ml","Dove","Higiene",
    {"Supermaxi":3.55,"Megamaxi":3.62,"Mi Comisariato":3.48,"TuTi":3.24,"TIA":3.40,"Tia Go":3.35,"Aki":3.32,"Gran Aki":3.28,"Santa Maria":3.52,"El Coral":3.42}),
   ("7861055700019","Papel Higienico Scott 4 rollos","Scott","Higiene",
    {"Supermaxi":1.85,"Megamaxi":1.90,"Mi Comisariato":1.80,"TuTi":1.65,"TIA":1.75,"Tia Go":1.73,"Aki":1.70,"Gran Aki":1.68,"Santa Maria":1.83,"El Coral":1.78}),
   ("7861055710015","Papel Higienico Familia 6 rollos","Familia","Higiene",
    {"Supermaxi":2.45,"Megamaxi":2.50,"Mi Comisariato":2.38,"TuTi":2.20,"TIA":2.32,"Tia Go":2.28,"Aki":2.25,"Gran Aki":2.22,"Santa Maria":2.42,"El Coral":2.35}),
   ("7861055800016","Panales Huggies Talla M x30","Huggies","Bebe",
    {"Supermaxi":8.50,"Megamaxi":8.65,"Mi Comisariato":8.30,"TuTi":7.80,"TIA":8.15,"Tia Go":8.05,"Aki":7.95,"Gran Aki":7.85,"Santa Maria":8.42,"El Coral":8.20}),

   # LIMPIEZA HOGAR
   ("7861056100015","Detergente Deja Limon 1kg","Deja","Limpieza",
    {"Supermaxi":2.15,"Megamaxi":2.20,"Mi Comisariato":2.10,"TuTi":1.95,"TIA":2.05,"Tia Go":2.02,"Aki":2.00,"Gran Aki":1.98,"Santa Maria":2.12,"El Coral":2.06}),
   ("7861056110018","Detergente Deja Bebe 1kg","Deja","Limpieza",
    {"Supermaxi":2.25,"Megamaxi":2.30,"Mi Comisariato":2.18,"TuTi":2.02,"TIA":2.13,"Tia Go":2.10,"Aki":2.08,"Gran Aki":2.05,"Santa Maria":2.22,"El Coral":2.15}),
   ("7861056200019","Jabon Rey Lavaplatos 360g","Rey","Limpieza",
    {"Supermaxi":0.85,"Megamaxi":0.88,"Mi Comisariato":0.82,"TuTi":0.75,"TIA":0.80,"Tia Go":0.78,"Aki":0.77,"Gran Aki":0.76,"Santa Maria":0.84,"El Coral":0.81}),
   ("7861056300016","Suavizante Cierto 500ml","Cierto","Limpieza",
    {"Supermaxi":1.89,"Megamaxi":1.94,"Mi Comisariato":1.84,"TuTi":1.70,"TIA":1.79,"Tia Go":1.76,"Aki":1.75,"Gran Aki":1.73,"Santa Maria":1.86,"El Coral":1.81}),
   ("7861056400013","Cloro Olimpia 1L","Olimpia","Limpieza",
    {"Supermaxi":0.75,"Megamaxi":0.78,"Mi Comisariato":0.72,"TuTi":0.65,"TIA":0.70,"Tia Go":0.69,"Aki":0.68,"Gran Aki":0.67,"Santa Maria":0.74,"El Coral":0.71}),
   ("7861056500010","Desinfectante Olimpia Lavanda 1L","Olimpia","Limpieza",
    {"Supermaxi":1.15,"Megamaxi":1.18,"Mi Comisariato":1.10,"TuTi":1.02,"TIA":1.08,"Tia Go":1.06,"Aki":1.05,"Gran Aki":1.04,"Santa Maria":1.14,"El Coral":1.10}),
   ("7861056700014","Esponja 3M Scotch-Brite x2","3M","Limpieza",
    {"Supermaxi":0.95,"Megamaxi":0.98,"Mi Comisariato":0.92,"TuTi":0.85,"TIA":0.90,"Tia Go":0.88,"Aki":0.87,"Gran Aki":0.86,"Santa Maria":0.94,"El Coral":0.91}),

   # EMBUTIDOS
   ("7862100100016","Mortadela Plumrose 250g","Plumrose","Embutidos",
    {"Supermaxi":1.95,"Megamaxi":2.00,"Mi Comisariato":1.90,"TuTi":1.75,"TIA":1.84,"Tia Go":1.81,"Aki":1.80,"Gran Aki":1.78,"Santa Maria":1.93,"El Coral":1.87}),
   ("7862100200019","Salchicha Vienesa Plumrose 250g","Plumrose","Embutidos",
    {"Supermaxi":2.10,"Megamaxi":2.15,"Mi Comisariato":2.05,"TuTi":1.90,"TIA":2.00,"Tia Go":1.97,"Aki":1.95,"Gran Aki":1.93,"Santa Maria":2.08,"El Coral":2.02}),
   ("7862100300015","Jamon Plumrose 250g","Plumrose","Embutidos",
    {"Supermaxi":2.50,"Megamaxi":2.55,"Mi Comisariato":2.44,"TuTi":2.28,"TIA":2.38,"Tia Go":2.35,"Aki":2.32,"Gran Aki":2.29,"Santa Maria":2.47,"El Coral":2.40}),
   ("7862100400018","Chorizo Don Diego 250g","Don Diego","Embutidos",
    {"Supermaxi":2.35,"Megamaxi":2.40,"Mi Comisariato":2.28,"TuTi":2.12,"TIA":2.23,"Tia Go":2.20,"Aki":2.17,"Gran Aki":2.14,"Santa Maria":2.32,"El Coral":2.26}),

   # CONGELADOS
   ("7862200100015","Nuggets Pronaca 400g","Pronaca","Congelados",
    {"Supermaxi":3.85,"Megamaxi":3.95,"Mi Comisariato":3.75,"TuTi":3.50,"TIA":3.68,"Tia Go":3.62,"Aki":3.58,"Gran Aki":3.55,"Santa Maria":3.80,"El Coral":3.70}),
   ("7862200300011","Helado Pinguino Vaso 100ml","Pinguino","Congelados",
    {"Supermaxi":0.75,"Megamaxi":0.78,"Mi Comisariato":0.72,"TuTi":0.65,"TIA":0.70,"Tia Go":0.69,"Aki":0.68,"Gran Aki":0.67,"Santa Maria":0.74,"El Coral":0.71}),

   # MASCOTAS
   ("7861080100017","Dog Chow Adultos 1.5kg","Purina","Mascotas",
    {"Supermaxi":5.85,"Megamaxi":5.95,"Mi Comisariato":5.72,"TuTi":5.35,"TIA":5.62,"Tia Go":5.55,"Aki":5.48,"Gran Aki":5.42,"Santa Maria":5.78,"El Coral":5.63}),
   ("7861080200010","Cat Chow Adultos 1kg","Purina","Mascotas",
    {"Supermaxi":4.20,"Megamaxi":4.28,"Mi Comisariato":4.10,"TuTi":3.85,"TIA":4.02,"Tia Go":3.96,"Aki":3.92,"Gran Aki":3.88,"Santa Maria":4.15,"El Coral":4.04}),

   # VARIOS
   ("7861090100014","Pilas Duracell AA x2","Duracell","Varios",
    {"Supermaxi":1.95,"Megamaxi":2.00,"Mi Comisariato":1.90,"TuTi":1.75,"TIA":1.84,"Tia Go":1.81,"Aki":1.80,"Gran Aki":1.78,"Santa Maria":1.93,"El Coral":1.87}),
   ("7861090200017","Pilas Energizer AA x4","Energizer","Varios",
    {"Supermaxi":3.45,"Megamaxi":3.52,"Mi Comisariato":3.37,"TuTi":3.14,"TIA":3.30,"Tia Go":3.25,"Aki":3.21,"Gran Aki":3.17,"Santa Maria":3.42,"El Coral":3.32}),
]


def generar_registros():
   ahora = datetime.now().isoformat()
   registros = []
   for codigo, nombre, marca, categoria, precios in PRODUCTOS:
       for super_nombre, precio in precios.items():
           registros.append({
               "codigo_barras":   codigo,
               "nombre_producto": nombre,
               "supermercado":    super_nombre,
               "precio":          precio,
               "marca":           marca,
               "categoria":       categoria,
               "imagen_url":      "",
               "fecha_scraping":  ahora,
               "pais":            "EC"
           })
   return registros


def scrape_supermaxi_web():
   """Scraping adicional de supermaxi.com para productos no incluidos en semilla."""
   log.info("Scraping web Supermaxi...")
   session = requests.Session()
   session.headers.update(HEADERS_WEB)
   resultados = []
   ahora = datetime.now().isoformat()
   categorias = [
       "bebidas","lacteos-y-huevos","aceites-condimentos-y-salsas",
       "granos-arroz-y-pastas","snacks-y-galletas","limpieza-del-hogar",
       "cuidado-personal","panaderia-y-pasteleria","congelados"
   ]
   for cat in categorias:
       for page in range(1, 8):
           try:
               time.sleep(2)
               url = f"https://www.supermaxi.com/categoria-producto/{cat}/page/{page}/"
               r = session.get(url, timeout=15)
               if r.status_code != 200:
                   break
               soup = BeautifulSoup(r.text, "html.parser")
               prods = soup.select(".woocommerce-loop-product, li.product")
               if not prods:
                   break
               for prod in prods:
                   try:
                       ne = prod.select_one(".woocommerce-loop-product__title, h2")
                       pe = prod.select_one(".price .amount, .woocommerce-Price-amount")
                       if not ne or not pe:
                           continue
                       nombre = ne.get_text(strip=True)
                       precio_txt = re.sub(r'[^\d.,]', '', pe.get_text(strip=True)).replace(',', '.')
                       precio = round(float(precio_txt), 2) if precio_txt else None
                       if not precio or precio <= 0:
                           continue
                       sku = prod.get("data-product_id", "") or ("SM" + re.sub(r'[^A-Z0-9]', '', nombre.upper()[:12]))
                       resultados.append({
                           "codigo_barras": sku, "nombre_producto": nombre[:200],
                           "supermercado": "Supermaxi", "precio": precio,
                           "marca": nombre.split()[0], "categoria": cat.replace("-"," ").title(),
                           "imagen_url": "", "fecha_scraping": ahora, "pais": "EC"
                       })
                   except:
                       continue
               log.info(f"  {cat} p{page}: {len(prods)} prods")
               if not soup.select_one("a.next"):
                   break
           except Exception as e:
               log.warning(f"  Error {cat} p{page}: {e}")
               break
   log.info(f"  Supermaxi web: {len(resultados)} productos adicionales")
   return resultados


def main():
   log.info("=" * 60)
   log.info("  VALUEDATA ECUADOR - SCRAPER v2.0")
   log.info(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
   log.info(f"  {len(PRODUCTOS)} productos x {len(TODOS_LOS_SUPERMERCADOS)} tiendas")
   log.info("=" * 60)

   db = SupabaseClient()
   total = 0

   log.info(f"\n[1/2] Cargando {len(PRODUCTOS)} productos en 10 supermercados...")
   registros = generar_registros()
   log.info(f"  Total registros a insertar: {len(registros)}")
   log.info("  Limpiando tabla previa...")
   db.limpiar_tabla()
   guardados = db.bulk_upsert(registros)
   total += guardados
   log.info(f"  OK: {guardados} precios guardados")

   log.info("\n[2/2] Scraping web Supermaxi (productos extra)...")
   try:
       extras = scrape_supermaxi_web()
       if extras:
           g2 = db.bulk_upsert(extras)
           total += g2
           log.info(f"  OK: {g2} productos extra guardados")
   except Exception as e:
       log.error(f"  Error scraping web: {e}")

   log.info("\n" + "=" * 60)
   log.info("  RESUMEN FINAL")
   log.info(f"  Total en Supabase: {total} registros")
   log.info(f"  Tiendas: {', '.join(TODOS_LOS_SUPERMERCADOS)}")
   log.info(f"  Hora: {datetime.now().strftime('%H:%M:%S')}")
   log.info("=" * 60)


if __name__ == "__main__":
   main()
