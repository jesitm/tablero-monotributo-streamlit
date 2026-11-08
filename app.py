"""Tablero de control de Monotributo para estudios contables (Streamlit).

El contador sube los CSV de "Mis Comprobantes" (emitidos) de sus clientes y ve,
para cada uno, cuánto facturó en los últimos 12 meses frente al tope de su
categoría. Todo se procesa en memoria: no se guarda ningún archivo.
"""
import hashlib
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from monotributo.calculo import (
    categoria_para,
    facturacion_mensual,
    proyeccion,
    resumen_cliente,
    ventana_12_meses,
)
from monotributo.comprobantes import leer_comprobantes
from monotributo.escalas import cargar_escalas

EJEMPLOS = Path(__file__).parent / "data" / "ejemplos"
ICONOS = {"En rango": "🟢 En rango", "Atención": "🟡 Atención", "Alerta": "🟠 Alerta", "Superado": "🔴 Superado"}

HORIZONTE_MESES = 6

st.set_page_config(page_title="Control de Monotributo", page_icon="📊", layout="wide")


def ars(valor: float) -> str:
    texto = f"{abs(valor):,.0f}".replace(",", ".")
    return f"-$ {texto}" if valor < 0 else f"$ {texto}"


def etiqueta_mes(periodo) -> str:
    return f"{periodo.month:02d}/{periodo.year}"


def texto_superacion(r, p) -> str:
    """Texto corto para la tabla: cuándo superaría el tope de su categoría al ritmo actual."""
    if r.uso > 1:
        return "Ya lo superó"
    if p.mes_superacion is None:
        return "No en 12 meses"
    return f"{etiqueta_mes(p.mes_superacion)} (en {p.meses_hasta_superar} m.)"


@st.cache_data(show_spinner=False)
def leer_archivo(contenido: bytes):
    return leer_comprobantes(contenido)


@st.cache_data
def escalas_vigentes() -> pd.DataFrame:
    return cargar_escalas()


def mostrar_mensaje(r, escalas: pd.DataFrame) -> None:
    sugerida = r.categoria_sugerida
    if r.excluido:
        st.error("Superó el tope de la categoría K: corresponde pasar al Régimen General (exclusión del Monotributo).")
    elif r.estado == "Superado":
        st.error(
            f"Supera el tope de su categoría actual ({r.categoria_actual}). Corresponde recategorizarse en el "
            f"próximo período habilitado (enero o julio). Por facturación le correspondería la categoría {sugerida}."
        )
    elif r.estado == "Alerta":
        st.warning(f"Ya usó el {r.uso * 100:.0f} % del tope. Margen restante: {ars(r.margen)}. Conviene controlar los próximos meses.")
    elif r.estado == "Atención":
        st.info(f"Usó el {r.uso * 100:.0f} % del tope. Margen restante: {ars(r.margen)}.")
    else:
        st.success(f"Dentro de su categoría. Margen restante: {ars(r.margen)}.")

    if sugerida and sugerida != r.categoria_actual:
        fila = escalas[escalas["categoria"] == sugerida].iloc[0]
        st.caption(
            f"Categoría {sugerida}: cuota mensual {ars(fila['cuota_servicios'])} (servicios) "
            f"o {ars(fila['cuota_bienes'])} (venta de bienes)."
        )


escalas = escalas_vigentes()
categorias = list(escalas["categoria"])

st.title("📊 Control de Monotributo")
st.caption(
    "Subí los CSV de «Mis Comprobantes» (comprobantes emitidos) de tus clientes. "
    "Los archivos se procesan en memoria y no se guardan."
)

with st.sidebar:
    st.header("Datos")
    subidos = st.file_uploader("CSV de comprobantes emitidos", type=["csv"], accept_multiple_files=True)
    usar_ejemplo = st.checkbox("Usar datos de ejemplo (ficticios)", value=False)

if subidos:
    archivos = [(f.name, f.getvalue()) for f in subidos]
elif usar_ejemplo:
    archivos = [(p.name, p.read_bytes()) for p in sorted(EJEMPLOS.glob("*.csv"))]
else:
    st.info("Subí uno o más archivos desde la barra lateral, o activá «Usar datos de ejemplo» para ver cómo funciona.")
    st.stop()

analizados = []
for nombre, contenido in archivos:
    try:
        df, avisos = leer_archivo(contenido)
    except ValueError as error:
        st.error(f"**{nombre}**: {error}")
        continue
    analizados.append({"nombre": nombre, "df": df, "avisos": avisos})

if not analizados:
    st.stop()

con_avisos = [a for a in analizados if a["avisos"]]
if con_avisos:
    with st.expander("Avisos de lectura"):
        for a in con_avisos:
            st.write(f"**{a['nombre']}**: " + " ".join(a["avisos"]))

fecha_defecto = max(a["df"]["fecha"].max() for a in analizados).date()
with st.sidebar:
    fecha_corte = pd.Timestamp(
        st.date_input(
            "Fecha de corte",
            value=fecha_defecto,
            help="Se analizan los 12 meses completos que terminan en el mes de esta fecha.",
        )
    )
    meses_ritmo = st.radio(
        "Ritmo para proyectar",
        [3, 6, 12],
        horizontal=True,
        format_func=lambda n: f"{n} meses",
        help="La proyección supone que cada mes futuro se factura el promedio de los últimos N meses.",
    )

# --- 1. Categoría actual de cada cliente (editable) ---------------------------------------
firma = hashlib.md5("|".join(a["nombre"] for a in analizados).encode()).hexdigest()[:8]
base = pd.DataFrame(
    {
        "Archivo": [a["nombre"] for a in analizados],
        "Cliente": [Path(a["nombre"]).stem for a in analizados],
        "Categoría actual": [
            categoria_para(float(facturacion_mensual(a["df"], fecha_defecto).sum()), escalas) or categorias[-1]
            for a in analizados
        ],
    }
)
st.subheader("1. Categoría actual de cada cliente")
st.caption("Se propone la que corresponde por facturación; corregila con la categoría real en la que está inscripto.")
editado = st.data_editor(
    base,
    key=f"categorias_{firma}",
    hide_index=True,
    disabled=["Archivo"],
    column_config={
        "Cliente": st.column_config.TextColumn("Cliente", required=True),
        "Categoría actual": st.column_config.SelectboxColumn("Categoría actual", options=categorias, required=True),
    },
)

# --- 2. Resumen --------------------------------------------------------------------------------
resumenes = [
    resumen_cliente(a["df"], escalas, editado.iloc[i]["Categoría actual"], fecha_corte)
    for i, a in enumerate(analizados)
]
mensuales = [facturacion_mensual(a["df"], fecha_corte) for a in analizados]
tope_maximo = float(escalas["tope_anual"].max())
proyecciones = [
    proyeccion(m, r.tope_actual, tope_maximo, meses_ritmo=meses_ritmo, horizonte=HORIZONTE_MESES)
    for m, r in zip(mensuales, resumenes)
]
orden = sorted(range(len(resumenes)), key=lambda i: resumenes[i].uso, reverse=True)

tabla = pd.DataFrame(
    {
        "Cliente": list(editado["Cliente"]),
        "Categoría actual": [r.categoria_actual for r in resumenes],
        "Facturado 12 meses": [ars(r.acumulado) for r in resumenes],
        "Tope": [ars(r.tope_actual) for r in resumenes],
        "% del tope": [f"{r.uso * 100:.1f} %" for r in resumenes],
        "Estado": [ICONOS[r.estado] for r in resumenes],
        "Superaría el tope": [texto_superacion(r, p) for r, p in zip(resumenes, proyecciones)],
        "Categoría sugerida": [r.categoria_sugerida or "Excluido (supera K)" for r in resumenes],
    }
)
st.subheader("2. Resumen (de mayor a menor uso del tope)")
st.dataframe(tabla.iloc[orden], hide_index=True)

exportable = pd.DataFrame(
    {
        "cliente": list(editado["Cliente"]),
        "categoria_actual": [r.categoria_actual for r in resumenes],
        "facturado_12_meses": [round(r.acumulado, 2) for r in resumenes],
        "tope": [r.tope_actual for r in resumenes],
        "porcentaje_uso": [round(r.uso * 100, 1) for r in resumenes],
        "estado": [r.estado for r in resumenes],
        "superaria_el_tope": [texto_superacion(r, p) for r, p in zip(resumenes, proyecciones)],
        "ritmo_mensual_supuesto": [round(p.ritmo_mensual, 2) for p in proyecciones],
        "categoria_sugerida": [r.categoria_sugerida or "Excluido" for r in resumenes],
        "fecha_corte": fecha_corte.date().isoformat(),
    }
).iloc[orden]
st.download_button(
    "Descargar resumen (CSV)",
    exportable.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
    file_name="resumen_monotributo.csv",
    mime="text/csv",
)

# --- 3. Detalle --------------------------------------------------------------------------------
st.subheader("3. Detalle por cliente")
etiquetas = list(editado["Cliente"])
elegido = st.selectbox("Cliente", options=list(range(len(analizados))), format_func=lambda k: etiquetas[k])
r = resumenes[elegido]
mensual = mensuales[elegido]
p = proyecciones[elegido]
inicio, fin = ventana_12_meses(fecha_corte)
st.caption(f"Ventana analizada: {inicio:%d/%m/%Y} a {fin:%d/%m/%Y}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Facturado en 12 meses", ars(r.acumulado))
c2.metric(f"Tope categoría {r.categoria_actual}", ars(r.tope_actual))
c3.metric("% del tope usado", f"{r.uso * 100:.1f} %")
c4.metric("Margen disponible" if r.margen >= 0 else "Excedido por", ars(abs(r.margen)))
st.progress(min(max(r.uso, 0.0), 1.0))
mostrar_mensaje(r, escalas)

meses = [f"{p.month:02d}/{p.year}" for p in mensual.index]
izquierda, derecha = st.columns(2)

# Cada barra se divide en dos tramos: hasta el tope ÷ 12 (azul) y lo que lo supera (rojo).
umbral_mensual = r.tope_actual / 12
valores_mensuales = [float(v) for v in mensual.values]
hasta_umbral = [min(v, umbral_mensual) for v in valores_mensuales]
sobre_umbral = [max(v - umbral_mensual, 0.0) for v in valores_mensuales]
detalle_barras = [f"{mes}<br>Facturado: {ars(v)}" for mes, v in zip(meses, valores_mensuales)]

grafico_mensual = go.Figure()
grafico_mensual.add_bar(
    x=meses, y=hasta_umbral, name="Hasta el tope ÷ 12", marker_color="#0068C9",
    hovertext=detalle_barras, hoverinfo="text",
)
grafico_mensual.add_bar(
    x=meses, y=sobre_umbral, name="Por encima del tope ÷ 12", marker_color="#D62728",
    hovertext=detalle_barras, hoverinfo="text",
)
grafico_mensual.add_hline(
    y=umbral_mensual,
    line_dash="dash",
    annotation_text=f"Tope ÷ 12 ({ars(umbral_mensual)})",
    annotation_position="top left",
)
grafico_mensual.update_layout(
    title="Facturación por mes",
    yaxis_title="Pesos",
    barmode="stack",
    legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="left", x=0),
    margin=dict(t=50, b=80),
)
izquierda.plotly_chart(grafico_mensual)

grafico_acumulado = go.Figure(go.Scatter(x=meses, y=mensual.cumsum().values, mode="lines+markers", name="Acumulado"))
grafico_acumulado.add_hline(
    y=r.tope_actual,
    line_dash="dash",
    annotation_text=f"Tope categoría {r.categoria_actual}",
    annotation_position="top left",
)
grafico_acumulado.update_layout(title="Acumulado dentro de la ventana", yaxis_title="Pesos", margin=dict(t=50, b=20))
derecha.plotly_chart(grafico_acumulado)

st.subheader("4. Proyección")
st.caption(
    f"Supone que cada mes futuro se factura {ars(p.ritmo_mensual)} (promedio de los últimos {meses_ritmo} meses). "
    "Es una estimación, no una predicción: si cambia el ritmo, cambia el resultado."
)
p1, p2 = st.columns(2)
p1.metric("Ritmo mensual asumido", ars(p.ritmo_mensual))
p2.metric(
    f"Máximo mensual sin superar el tope ({p.horizonte} meses)",
    ars(p.maximo_mensual),
    help="Facturación mensual constante más alta que mantiene la ventana de 12 meses dentro del tope de la categoría actual.",
)
if r.uso > 1:
    st.error("Ya supera el tope de su categoría actual: la proyección de abajo muestra cómo evoluciona la ventana.")
elif p.mes_superacion is not None:
    st.warning(
        f"Al ritmo actual, superaría el tope de la categoría {r.categoria_actual} en {etiqueta_mes(p.mes_superacion)} "
        f"(dentro de {p.meses_hasta_superar} meses). Para evitarlo en los próximos {p.horizonte} meses, "
        f"no debería facturar más de {ars(p.maximo_mensual)} por mes."
    )
else:
    st.success(f"Al ritmo actual, se mantiene dentro del tope de la categoría {r.categoria_actual} durante los próximos 12 meses.")
if p.mes_exclusion is not None:
    st.error(f"Al ritmo actual, superaría el tope de la categoría K en {etiqueta_mes(p.mes_exclusion)}: quedaría excluido del Monotributo.")

meses_futuros = [etiqueta_mes(x) for x in p.acumulado_proyectado.index]
grafico_proyeccion = go.Figure(
    go.Scatter(
        x=[etiqueta_mes(mensual.index[-1])] + meses_futuros,
        y=[r.acumulado] + list(p.acumulado_proyectado.values),
        mode="lines+markers",
        name="Facturación 12 meses móviles",
    )
)
grafico_proyeccion.add_hline(
    y=r.tope_actual,
    line_dash="dash",
    annotation_text=f"Tope categoría {r.categoria_actual}",
    annotation_position="top left",
)
if p.mes_exclusion is not None:
    grafico_proyeccion.add_hline(
        y=tope_maximo,
        line_dash="dot",
        line_color="red",
        annotation_text="Tope categoría K (exclusión)",
        annotation_position="top left",
    )
grafico_proyeccion.update_layout(
    title="Proyección de la facturación de 12 meses móviles",
    yaxis_title="Pesos",
    margin=dict(t=50, b=20),
)
st.plotly_chart(grafico_proyeccion)

st.divider()
st.caption(
    f"Escalas vigentes desde {escalas['vigencia_desde'].max():%d/%m/%Y} (archivo data/escalas_monotributo.csv); "
    "actualizalas cada semestre con la tabla oficial de ARCA. Esta herramienta evalúa solo los ingresos brutos: "
    "la categoría también depende de superficie, energía eléctrica consumida y alquileres."
)
