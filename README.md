# Control de Monotributo

Tablero en Streamlit para estudios contables: muestra, para cada cliente monotributista, cuánto facturó en los últimos 12 meses frente al tope de su categoría, lo clasifica con un semáforo y proyecta en qué mes superaría el tope al ritmo actual.

> Versión inicial. Los datos de ejemplo incluidos son **ficticios**.

## Capturas

![Resumen de clientes](docs/captura-resumen.png)
![Detalle de un cliente](docs/captura-detalle.png)
![Proyección](docs/captura-proyeccion.png)

## Qué hace

- Lee los CSV de **Mis Comprobantes (emitidos)** de ARCA: uno por cliente, varios a la vez.
- Calcula la facturación neta de los **12 meses completos** que terminan en la fecha de corte (las notas de crédito restan y los recibos se excluyen).
- Muestra el porcentaje usado del tope, un estado (En rango, Atención, Alerta, Superado) y la categoría que correspondería por facturación, con su cuota mensual.
- **Proyecta** la ventana de 12 meses móviles según el promedio de los últimos 3, 6 o 12 meses: en qué mes superaría el tope y cuánto podría facturar por mes sin superarlo.
- Exporta el resumen a CSV.

Todo se procesa en memoria: la app no guarda los archivos que se suben.

## Tecnologías

Python, Pandas, Streamlit y Plotly. Lógica de cálculo separada de la interfaz y cubierta con tests.

## Cómo correrlo

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (cmd). En Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Para probar sin datos reales, activá **"Usar datos de ejemplo"** en la barra lateral. Los ejemplos se regeneran con `python data/generar_ejemplos.py`. Tests: `pytest`.

## Estructura

```
app.py                       # interfaz Streamlit
monotributo/
  escalas.py                 # carga la tabla de categorías
  comprobantes.py            # lee el CSV de Mis Comprobantes
  calculo.py                 # ventana de 12 meses, estado y proyección
data/
  escalas_monotributo.csv    # topes y cuotas vigentes
  generar_ejemplos.py        # genera CSV ficticios
  ejemplos/                  # CSV ficticios de demo
tests/test_monotributo.py
```

## Límites y mantenimiento

- Evalúa solo los **ingresos brutos**: la categoría también depende de superficie, energía eléctrica consumida y alquileres.
- La proyección es una estimación basada en el promedio reciente; no considera estacionalidad.
- Las escalas se actualizan cada semestre: hay que editar `data/escalas_monotributo.csv` con la tabla oficial de ARCA (la cargada rige desde el 01/08/2026).

---

Desarrollado por **Prisma DS**, consultoría de datos.
