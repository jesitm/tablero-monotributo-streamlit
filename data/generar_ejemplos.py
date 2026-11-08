"""Genera CSV ficticios con el formato de "Mis Comprobantes" (emitidos).

Uso:  python data/generar_ejemplos.py
Crea tres clientes de ejemplo en data/ejemplos/ (datos inventados).
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

DESTINO = Path(__file__).resolve().parent / "ejemplos"
ENCABEZADO = [
    "Fecha de Emisión", "Tipo de Comprobante", "Punto de Venta", "Número Desde", "Número Hasta",
    "Cód. Autorización", "Tipo Doc. Receptor", "Nro. Doc. Receptor", "Denominación Receptor",
    "Tipo Cambio", "Moneda", "Imp. Neto Gravado", "Imp. Neto No Gravado", "Imp. Op. Exentas",
    "Otros Tributos", "IVA", "Imp. Total",
]

# nombre de archivo, facturación mensual objetivo, decimal con coma?, ¿viene creciendo?
CLIENTES = [
    ("cliente_ejemplo_1_en_rango.csv", 700_000, True, False),
    ("cliente_ejemplo_2_en_alerta.csv", 2_500_000, True, True),
    ("cliente_ejemplo_3_superado.csv", 5_000_000, False, False),
]
MESES = [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 11)]  # sep-2025 a oct-2026


def formato(valor: float, coma: bool) -> str:
    texto = f"{valor:.2f}"
    return texto.replace(".", ",") if coma else texto


def generar(nombre: str, objetivo_mensual: float, coma: bool, crece: bool, semilla: int) -> None:
    azar = random.Random(semilla)
    filas, numero = [], 1
    for indice, (anio, mes) in enumerate(MESES):
        factor = 0.75 + 0.5 * indice / (len(MESES) - 1) if crece else 1.0  # tendencia creciente
        for _ in range(azar.randint(3, 6)):
            dia = azar.randint(1, 28)
            monto = round(azar.uniform(0.6, 1.4) * objetivo_mensual * factor / 4.5, 2)
            filas.append((date(anio, mes, dia), "11 - Factura C", monto, numero))
            numero += 1
        if indice % 5 == 4:  # una nota de crédito de vez en cuando
            filas.append((date(anio, mes, 28), "13 - Nota de Crédito C", round(objetivo_mensual * 0.03, 2), numero))
            numero += 1
        if indice == 6:  # un recibo, que no debe contar
            filas.append((date(anio, mes, 15), "15 - Recibo C", 50_000.0, numero))
            numero += 1

    filas.sort(key=lambda f: f[0])
    with open(DESTINO / nombre, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo, delimiter=";")
        escritor.writerow(ENCABEZADO)
        for fecha, tipo, monto, nro in filas:
            importe = formato(monto, coma)
            escritor.writerow([
                fecha.isoformat(), tipo, 1, nro, nro, f"{70000000000000 + nro}", 80, "30000000007",
                "Cliente de ejemplo", formato(1.0, coma), "$", importe, formato(0, coma),
                formato(0, coma), formato(0, coma), formato(0, coma), importe,
            ])


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    for i, (nombre, objetivo, coma, crece) in enumerate(CLIENTES):
        generar(nombre, objetivo, coma, crece, semilla=7 + i)
        print("generado", DESTINO / nombre)
