# Analizador de Extracto de Tarjeta (ueno bank)

Sistema simple en Python (Flask) para subir el PDF del extracto de tarjeta y
obtener:

- **Resumen estado financiero** (extraído tal cual del PDF).
- **Gastos agrupados por comercio**, ordenados de mayor a menor monto, con
  cantidad de operaciones por comercio.
- **Total general** de gasto en comercios.

## Requisitos

- Python 3.9+

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecutar

```bash
python app.py
```

Luego abrí en el navegador: http://localhost:5055

Subí el PDF del extracto y obtené el análisis.

## Notas

- Se excluyen automáticamente: pagos (`SU PAGO`), intereses de cuotas,
  IVA Ley 6380, seguros y mantenimientos, para que el total refleje
  únicamente el gasto en comercios.
- Los comercios se normalizan (se quitan prefijos como `PGP*`, `PAYPAL*`,
  `GOOGLE*`, `DLOCAL*`, sufijos de cuotas `01/12`, etc.) para que distintas
  variantes del mismo negocio se sumen.
