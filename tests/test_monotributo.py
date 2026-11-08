import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monotributo.calculo import (  # noqa: E402
    categoria_para,
    estado_de,
    facturacion_mensual,
    resumen_cliente,
    ventana_12_meses,
)
from monotributo.comprobantes import leer_comprobantes  # noqa: E402
from monotributo.escalas import cargar_escalas  # noqa: E402

ESCALAS = cargar_escalas()
EJEMPLOS = Path(__file__).resolve().parent.parent / "data" / "ejemplos"


def _df(filas):
    return pd.DataFrame({"fecha": pd.to_datetime([f[0] for f in filas]), "importe": [f[1] for f in filas]})


def test_escalas_ordenadas_y_completas():
    assert list(ESCALAS["categoria"]) == list("ABCDEFGHIJK")
    assert ESCALAS["tope_anual"].is_monotonic_increasing


def test_ventana_12_meses():
    inicio, fin = ventana_12_meses("2026-10-15")
    assert inicio == pd.Timestamp("2025-11-01")
    assert fin == pd.Timestamp("2026-10-31")


def test_categoria_para():
    assert categoria_para(0, ESCALAS) == "A"
    assert categoria_para(12_009_410.45, ESCALAS) == "A"
    assert categoria_para(12_009_410.46, ESCALAS) == "B"
    assert categoria_para(126_610_838.75, ESCALAS) == "K"
    assert categoria_para(126_610_838.76, ESCALAS) is None


def test_estado_de():
    assert estado_de(0.5) == "En rango"
    assert estado_de(0.75) == "Atención"
    assert estado_de(0.9) == "Alerta"
    assert estado_de(1.0) == "Alerta"
    assert estado_de(1.01) == "Superado"


def test_facturacion_ignora_fuera_de_ventana_y_rellena_meses():
    df = _df([("2025-10-31", 999), ("2025-11-01", 100), ("2026-10-31", 50), ("2026-11-01", 999)])
    mensual = facturacion_mensual(df, "2026-10-20")
    assert len(mensual) == 12
    assert mensual.sum() == 150
    assert mensual.iloc[0] == 100 and mensual.iloc[-1] == 50


def test_facturacion_sin_movimientos():
    mensual = facturacion_mensual(_df([("2020-01-01", 10)]), "2026-10-20")
    assert len(mensual) == 12 and mensual.sum() == 0


def test_lectura_notas_de_credito_recibos_y_decimales():
    csv = (
        "Fecha de Emisión;Tipo de Comprobante;Imp. Total\n"
        "2026-09-01;11 - Factura C;1.000,50\n"
        "2026-09-02;13 - Nota de Crédito C;200,25\n"
        "2026-09-03;15 - Recibo C;5000,00\n"
        "no-es-fecha;11 - Factura C;10,00\n"
    ).encode("utf-8")
    df, avisos = leer_comprobantes(csv)
    assert len(df) == 2
    assert round(df["importe"].sum(), 2) == 800.25
    assert any("recibos" in a for a in avisos) and any("ilegible" in a for a in avisos)


def test_lectura_decimales_con_punto_y_separador_coma():
    csv = "Fecha,Tipo,Total\n05/10/2026,11,1234.56\n".encode("utf-8")
    df, _ = leer_comprobantes(csv)
    assert df.loc[0, "fecha"] == pd.Timestamp("2026-10-05")
    assert df.loc[0, "importe"] == 1234.56


def test_lectura_falla_si_faltan_columnas():
    try:
        leer_comprobantes("a;b\n1;2\n".encode("utf-8"))
    except ValueError as error:
        assert "obligatorias" in str(error)
    else:
        raise AssertionError("debería fallar")


def test_ejemplos_dan_los_estados_esperados():
    esperado = {
        "cliente_ejemplo_1_en_rango.csv": ("A", "En rango"),
        "cliente_ejemplo_2_en_alerta.csv": ("D", "Alerta"),
        "cliente_ejemplo_3_superado.csv": ("F", "Superado"),
    }
    for nombre, (categoria, estado) in esperado.items():
        df, _ = leer_comprobantes((EJEMPLOS / nombre).read_bytes())
        resumen = resumen_cliente(df, ESCALAS, categoria, df["fecha"].max())
        assert resumen.estado == estado, (nombre, resumen)


def _mensual(valores):
    meses = pd.period_range("2025-11", periods=12, freq="M")
    return pd.Series([float(v) for v in valores], index=meses)


def test_proyeccion_ritmo_constante_no_supera():
    from monotributo.calculo import proyeccion

    p = proyeccion(_mensual([100] * 12), tope=1500, tope_maximo=3000)
    assert p.ritmo_mensual == 100
    assert p.meses_hasta_superar is None and p.mes_superacion is None
    assert all(abs(v - 1200) < 1e-9 for v in p.acumulado_proyectado)
    assert str(p.acumulado_proyectado.index[0]) == "2026-11"


def test_proyeccion_ritmo_creciente_supera_en_el_mes_esperado():
    from monotributo.calculo import proyeccion

    p = proyeccion(_mensual([100] * 9 + [200] * 3), tope=1750, tope_maximo=2300, meses_ritmo=3)
    assert p.ritmo_mensual == 200
    assert p.meses_hasta_superar == 3
    assert str(p.mes_superacion) == "2027-01"
    assert str(p.mes_exclusion) == "2027-07"
    assert abs(p.acumulado_proyectado.iloc[0] - 1600) < 1e-9


def test_proyeccion_maximo_mensual():
    from monotributo.calculo import proyeccion

    p = proyeccion(_mensual([100] * 12), tope=1500, tope_maximo=3000, horizonte=6)
    assert abs(p.maximo_mensual - 150) < 1e-9


def test_proyeccion_maximo_mensual_no_es_negativo():
    from monotributo.calculo import proyeccion

    p = proyeccion(_mensual([1000] * 12), tope=1500, tope_maximo=3000)
    assert p.maximo_mensual == 0.0
