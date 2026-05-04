import os, re, io
from collections import defaultdict
from flask import Flask, request, render_template, redirect, url_for, flash
import pdfplumber

app = Flask(__name__)
app.secret_key = "extracto-secret"
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Detalles que NO son compras de comercios (pagos, intereses, IVA, etc.)
EXCLUIR = [
    "SU PAGO", "INTERES CUOTA", "IVA LEY", "SEG. DE CANC", "MANTENIMIENTO MENSUAL",
]

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
MONTO_RE = re.compile(r"^-?[\d\.,]+$")

def parse_int(s):
    s = s.replace(".", "").replace(",", "").strip()
    try:
        return int(s)
    except:
        return 0

def normalizar_comercio(detalle: str) -> str:
    d = detalle.upper().strip()
    # quitar sufijos de cuotas como "05/12", "01/08"
    d = re.sub(r"\s+\d{2}/\d{2}\s*$", "", d)
    # quitar prefijos comunes
    d = re.sub(r"^(PGP\s*\*?|PAYPAL\s*\*|GOOGLE\s*\*|DLOCAL\s*\*|UPAY\s+|TL\s+\d+\s+)", "", d)
    # colapsar variantes locales (dejar nombre principal antes de "-" o "LOC")
    d = re.split(r"\s+LOC\.:", d)[0]
    d = d.strip()
    return d

def extraer_resumen(text: str):
    """Extrae bloque 'Resumen estado financiero' tal cual."""
    items = []
    patrones = [
        ("Deuda Anterior", r"Deuda Anterior\s+([\d\.,]+)"),
        ("(-) Pagos", r"\(-\)\s*Pagos\s+([\d\.,]+)"),
        ("(=) Saldo Financiado", r"\(=\)\s*Saldo Financiado\s+([\d\.,]+)"),
        ("(+) Compras y cargos del mes", r"\(\+\)\s*Compras y cargos del mes\s+([\d\.,]+)"),
        ("(=) Deuda total del periodo", r"\(=\)\s*Deuda total del periodo\s+([\d\.,]+)"),
        ("(+) Deuda en cuotas a facturar", r"\(\+\)\s*Deuda en cuotas a facturar\s+([\d\.,]+)"),
        ("(+) Int/Cargos Deveng. en susp.", r"\(\+\)\s*Int/Cargos Deveng\.?\s*en susp\.?\s+([\d\.,]+)"),
        ("(=) Deuda total", r"\(=\)\s*Deuda total\s+([\d\.,]+)"),
        ("Línea de Crédito", r"L[íi]nea de Cr[ée]dito\s+([\d\.,]+)"),
        ("Disponible", r"Disponible\s+([\d\.,]+)"),
        ("Pago mínimo", r"El pago m[íi]nimo[:\s]*Gs\s+([\d\.,]+)"),
    ]
    for label, pat in patrones:
        m = re.search(pat, text)
        if m:
            items.append((label, m.group(1)))
    # tarjeta y titular
    titular = None
    m = re.search(r"^([A-ZÁÉÍÓÚÑ ]{10,})\s*\n\s*\d+", text, re.M)
    if m:
        titular = m.group(1).strip()
    tarjeta = None
    m = re.search(r"Tarjeta:\s*([\d\*]+)", text)
    if m:
        tarjeta = m.group(1)
    return items, titular, tarjeta

def extraer_transacciones(pdf_path):
    """Recorre páginas y extrae filas (fecha, detalle, monto). Detecta líneas con fecha al inicio."""
    transacciones = []
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            full_text += t + "\n"
            for line in t.split("\n"):
                tokens = line.strip().split()
                if len(tokens) < 4:
                    continue
                if not DATE_RE.match(tokens[0]):
                    continue
                if not DATE_RE.match(tokens[1]):
                    continue
                # último token: monto
                monto_tok = tokens[-1]
                if not MONTO_RE.match(monto_tok):
                    continue
                monto = parse_int(monto_tok)
                # detalle: tokens entre cupon y FIN/IVA. Buscamos token cupón (numérico largo) si existe
                # Estructura típica: fecha_op fecha_proc cupon? detalle... FIN IVA? monto
                medio = tokens[2:-1]
                # quitar último(s) que sean letras únicas (FIN=S/N, IVA=10)
                while medio and (medio[-1] in ("S", "N") or medio[-1].isdigit() and len(medio[-1]) <= 2):
                    medio.pop()
                # quitar cupón inicial si es numérico largo
                if medio and medio[0].isdigit() and len(medio[0]) >= 7:
                    medio.pop(0)
                detalle = " ".join(medio).strip()
                if not detalle:
                    continue
                if any(x in detalle.upper() for x in EXCLUIR):
                    continue
                transacciones.append({"fecha": tokens[0], "detalle": detalle, "monto": monto})
    return transacciones, full_text

def agrupar(transacciones):
    grupos = defaultdict(lambda: {"total": 0, "count": 0, "items": []})
    for t in transacciones:
        key = normalizar_comercio(t["detalle"])
        grupos[key]["total"] += t["monto"]
        grupos[key]["count"] += 1
        grupos[key]["items"].append({
            "fecha": t["fecha"],
            "detalle": t["detalle"],
            "monto": t["monto"],
        })
    lista = []
    for k, v in grupos.items():
        items = sorted(v["items"], key=lambda x: x["monto"], reverse=True)
        lista.append({"comercio": k, "total": v["total"], "count": v["count"], "items": items})
    lista.sort(key=lambda x: x["total"], reverse=True)
    return lista

def fmt(n):
    return f"{n:,}".replace(",", ".")

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/analizar", methods=["POST"])
def analizar():
    f = request.files.get("pdf")
    if not f or not f.filename.lower().endswith(".pdf"):
        flash("Por favor subí un PDF válido.")
        return redirect(url_for("index"))
    path = os.path.join(UPLOAD_DIR, f.filename)
    f.save(path)
    transacciones, text = extraer_transacciones(path)
    resumen, titular, tarjeta = extraer_resumen(text)
    agrupado = agrupar(transacciones)
    total = sum(x["total"] for x in agrupado)
    return render_template("resultado.html",
                           agrupado=agrupado,
                           total=total,
                           resumen=resumen,
                           titular=titular,
                           tarjeta=tarjeta,
                           num_trans=len(transacciones),
                           fmt=fmt)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5055, debug=False)
