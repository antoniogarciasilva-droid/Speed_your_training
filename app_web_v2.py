import os
import calendar
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import base64

import dash
from dash import Dash, html, dcc, Input, Output, State, callback_context, MATCH, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# Importar módulos propios de tu backend
import db_web_v2
import auth_manager_v2
from garmin_ingestor_v2 import GarminIngestor
from coros_ingestor_v2 import CorosIngestor
from fit_ingestor_v2 import FitIngestor
import core_metrics_v2
import io  

# 1. Inicializar la BBDD
db_web_v2.inicializar_db_web()

# Inicializar Dash con un tema moderno de Bootstrap
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
app.title = "Athletics Analytics - Speed your training"

# --- FUNCIONES AUXILIARES ---
def segundos_a_min_km(segundos):
    try:
        segundos = float(segundos)
        if segundos <= 0:
            return "0:00"
        minutos = int(segundos // 60)
        restantes = int(segundos % 60)
        return f"{minutos}:{restantes:02d}"
    except:
        return "0:00"

def obtener_configuracion_kpi(nombre, valor):
    if nombre == "TRIMP":
        if valor < 50: return "#d4edda", "green", "Muy Ligero - Regenerativo, < 12h recup."
        elif valor < 100: return "#d4edda", "green", "Moderado - Mantenimiento aeróbico, 12-24h"
        elif valor < 180: return "#fff3cd", "orange", "Alto - Sesión de calidad, 24-48h"
        elif valor < 250: return "#f8d7da", "red", "Muy Alto - Volumen extremo, 48-72h"
        else: return "#f8d7da", "red", "Extremo - Agotamiento alto, +72h"
    elif nombre == "TRIMP_min":
        if valor < 1.4: return "#d4edda", "green", "Zona 1 (Recup/Base)"
        elif valor < 2.0: return "#fff3cd", "orange", "Zona 2 (Umbral/Tempo)"
        else: return "#f8d7da", "red", "Zona 3 (Alta Int.)"
    elif nombre == "ACWR":
        if valor < 1.3: return "#d4edda", "green", "Seguro - Progresión óptima."
        elif valor < 1.5: return "#fff3cd", "orange", "Riesgo - Fatiga creciendo rápido."
        else: return "#f8d7da", "red", "Peligro - Alto riesgo lesión."
    elif nombre == "TSB":
        if 5 <= valor <= 25: return "#d4edda", "green", "Objetivo - Ideal para competir."
        elif valor < -20: return "#f8d7da", "red", "Agotado - Descarga urgente."
        else: return "#fff3cd", "orange", "Fatiga - Entrenamiento estándar."
    elif nombre == "CTL":
        return "#f0f2f6", "#166534", "Carga Crónica (Forma física acumulada)"
    elif nombre == "ATL":
        return "#f0f2f6", "#991b1b", "Carga Aguda (Fatiga a corto plazo)"
    return "#f0f2f6", "black", "Valor estándar"

DEFINICIONES_KPI = {
    "ATL": "**ATL (Fatiga):** Acute Training Load o Carga Aguda de Entrenamiento. Se define como el promedio ponderado de la carga de entrenamiento de los últimos 7 días. Refleja el grado actual de fatiga. [ATL](https://www.trainingpeaks.com/coach-blog/una-guia-para-entrenadores-de-atl-ctl-y-tsb/)",
    "CTL": "**CTL (Forma):** Chronic Training Load o Carga Crónica de Entrenamiento. Se define como el promedio ponderado de la carga de entrenamiento de los últimos 42 días (6 semanas). Representa el nivel de forma física o resistencia acumulada. [CTL](https://www.trainingpeaks.com/coach-blog/una-guia-para-entrenadores-de-atl-ctl-y-tsb/)",
    "TSB": "**TSB (Balance):** Training Stress Balance o Balance de Estrés del Entrenamiento. Se define como la diferencia entre la Carga Crónica (CTL) y la Carga Aguda (ATL) del día anterior. Representa el estado de frescura o fatiga acumulada actual. [TSB](https://www.trainingpeaks.com/coach-blog/una-guia-para-entrenadores-de-atl-ctl-y-tsb/)",
    "ACWR": "**ACWR (Ratio de Carga):** Acute Chronic Workload Ratio o Ratio de Carga de Trabajo Aguda Crónica. Compara la carga de entrenamiento a corto plazo con la carga a largo plazo para evaluar el riesgo de lesiones y optimizar el rendimiento. [ACWR](https://www.bycoachmanu.com/post/ratio-acwr-carga-aguda---carga-cr%C3%B3nica-en-el-entrenamiento-deportivo)",
    "TRIMP": "**TRIMP (Impulso):** Training Impulse o Impulso de Entrenamiento. Carga interna de la sesión basada en el volumen y la frecuencia cardíaca. [TRIMP](https://www.iamcoach.ai/blog/trimp-training-load-explained)",
    "TRIMP/m": "**TRIMP/min:** Intensidad media de esfuerzo por minuto de entrenamiento.",
    "TRIMP/km": "**TRIMP/km:** Carga de esfuerzo acumulada por cada kilómetro recorrido.",
    "Dist": "**Distancia:** Kilómetros totales completados en la sesión.",
    "Tiempo": "**Tiempo:** Duración total de la actividad.",
    "FC media": "**FC Media:** Promedio de pulsaciones por minuto durante el entrenamiento.",
    "DES": "**Deriva cardíaca:** La deriva cardíaca (Pa:HR) —conocida en inglés como Aerobic Decoupling— es una métrica que mide la estabilidad de tu sistema cardiovascular durante un entrenamiento de resistencia a intensidad constante. [Deriva](https://docs.goodcoach.app/es/advanced-usage/cardiac-drift/)",
    "DER": "**Diferencia de frecuencias:** Mide la diferencia de frecuencias cardíacas, en % entre la frecuencia cardíaca media de la segunda mitad y la de la primera.",
    "FCI": "**FC media inicial:** Este indicador es la frecuencia cardíaca media de la primera mitad de la sesión.",
    "FCF": "**FC media final:** Este indicador es la frecuencia cardíaca media de la segunda mitad de la sesión.",
    "Ritmo": "**Ritmo:** Velocidad media expresada en minutos por kilómetro (min/km).",
    "SES": "**Sesión:** Nombre o tipo de la sesión de entrenamiento realizada."
}

def crear_tarjeta_kpi(etiqueta, valor, nombre_metrica):
    try:
        val_float = float(valor)
    except:
        val_float = 0.0
        
    fondo, color, _ = obtener_configuracion_kpi(nombre_metrica, val_float)
    texto_valor = valor if isinstance(valor, str) else f"{val_float:.2f}"
    tooltip_desc = DEFINICIONES_KPI.get(nombre_metrica, etiqueta)

    safe_id = f"kpi-tip-{nombre_metrica.lower().replace('/', '_').replace(' ', '-')}"

    return html.Div([
        html.Div([
            html.P(etiqueta, style={"margin": "0", "color": "#444", "fontSize": "0.75rem", "fontWeight": "bold", "display": "inline-block"}),
            html.Span(" ⓘ", id=safe_id, style={
                "fontSize": "0.75rem", 
                "color": "#2563eb", 
                "cursor": "pointer", 
                "marginLeft": "3px", 
                "fontWeight": "bold"
            }),
            dbc.Popover(
                dbc.PopoverBody(
                    dcc.Markdown(
                        tooltip_desc, 
                        style={"fontSize": "0.78rem", "margin": "0", "color": "#f8fafc", "textAlign": "left"},
                        link_target="_blank"
                    )
                ),
                target=safe_id,
                trigger="click",
                placement="top",
                style={
                    "backgroundColor": "#0f172a", 
                    "color": "#f8fafc", 
                    "border": "1px solid #334155",
                    "boxShadow": "0 10px 15px -3px rgba(0, 0, 0, 0.3)"
                }
            )
        ], style={"display": "flex", "alignItems": "center", "justifyContent": "center"}),
        html.H5(texto_valor, style={"margin": "3px 0 0 0", "color": color, "fontSize": "1.1rem"}),
    ], style={
        "backgroundColor": fondo, "padding": "8px", "borderRadius": "8px", 
        "textAlign": "center", "border": "1px solid #ddd", "boxShadow": "0 2px 4px rgba(0,0,0,0.05)",
        "position": "relative"
    })

# --- 2. LAYOUT PRINCIPAL Y CONTROL DE SESIÓN ---
app.layout = html.Div([
    dcc.Store(id='store-user-id', data=None, storage_type='session'),
    dcc.Store(id='store-menu', data="Sesión Individual", storage_type='session'),
    dcc.Store(id='store-activa', data=None, storage_type='session'),
    dcc.Store(id='store-cal-anho', data=datetime.today().year, storage_type='session'),
    dcc.Store(id='store-cal-mes', data=datetime.today().month, storage_type='session'),
    html.Div(id='dummy-scroll-div', style={'display': 'none'}),
    html.Div(id='main-container')
])

# Pantalla de Login / Registro
login_layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.Div([
                html.H2("🔐 Acceso al sistema", className="text-center mb-4 text-primary fw-bold"),
                dbc.Tabs([
                    dbc.Tab([
                        dbc.Input(id="login-email", placeholder="Email", type="email", className="mb-3 mt-3"),
                        dbc.Input(id="login-pwd", placeholder="Contraseña", type="password", className="mb-3"),
                        dbc.Button("Entrar", id="btn-login", color="primary", className="w-100"),
                        html.Div(id="login-alert", className="mt-3")
                    ], label="Iniciar Sesión", tab_id="tab-login"),
                    dbc.Tab([
                        dbc.Input(id="reg-email", placeholder="Email", type="email", className="mb-3 mt-3"),
                        dbc.Input(id="reg-nombre", placeholder="Nombre", type="text", className="mb-3"),
                        dbc.Select(id="reg-sexo", options=[{"label": "Masculino", "value": "Masculino"}, {"label": "Femenino", "value": "Femenino"}], value="Masculino", className="mb-3"),
                        dbc.Input(id="reg-pwd", placeholder="Contraseña", type="password", className="mb-3"),
                        dbc.Button("Crear cuenta", id="btn-reg", color="success", className="w-100"),
                        html.Div(id="reg-alert", className="mt-3")
                    ], label="Registrarse", tab_id="tab-reg")
                ], active_tab="tab-login")
            ], className="p-5 bg-white shadow rounded-4 border")
        ], width=6, className="mx-auto mt-5")
    ])
], fluid=True, style={"backgroundColor": "#f8fafc", "height": "100vh", "paddingTop": "5rem"})

# Barra de Navegación Fija
def generar_navbar(menu_activo):
    opciones = [
        ("🏃‍♂️ Sesión Individual", "nav-sesion"),
        ("📈 Evolución de Temporada", "nav-evolucion"),
        ("⚖️ Comparativa", "nav-comparativa"),
        ("⚙️ Configuración & Sync", "nav-config"),
        ("🚪 Cerrar Sesión", "nav-logout")
    ]
    nav_items = []
    for label, id_name in opciones:
        is_active = (menu_activo == label.replace("🏃‍♂️ ", "").replace("📈 ", "").replace("⚖️ ", "").replace("⚙️ ", "").replace("🚪 ", ""))
        
        if is_active:
            btn_style = {"backgroundColor": "#f97316", "color": "#ffffff", "borderColor": "#f97316"}
        else:
            btn_style = {"backgroundColor": "transparent", "color": "#fb923c", "borderColor": "#fb923c"}
        
        nav_items.append(
            dbc.NavItem(
                dbc.Button(label, id=id_name, className="me-2 fw-bold btn-sm", style=btn_style)
            )
        )
        
    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand("⚡ Speed your training", className="fw-bold text-white fs-4"),
            dbc.Nav(nav_items, className="ms-auto", navbar=True)
        ], fluid=True),
        color="#0f172a",
        dark=True,
        fixed="top",
        className="shadow-sm border-bottom border-secondary py-2"
    )

# --- 3. CALLBACKS GENERALES Y ENRUTAMIENTO ---
@app.callback(
    [Output('store-user-id', 'data'), Output('login-alert', 'children')],
    [Input('btn-login', 'n_clicks'), Input('login-email', 'n_submit'), Input('login-pwd', 'n_submit')],
    [State('login-email', 'value'), State('login-pwd', 'value')],
    prevent_initial_call=True
)
def manejar_login(n_clicks, n_submit_email, n_submit_pwd, email, pwd):
    if not email or not pwd:
        return None, dbc.Alert("Introduce email y contraseña", color="warning")
    user_id = auth_manager_v2.verificar_login(email, pwd)
    if user_id:
        return user_id, None
    return None, dbc.Alert("Email o contraseña incorrectos", color="danger")

@app.callback(
    Output('reg-alert', 'children'),
    Input('btn-reg', 'n_clicks'),
    [State('reg-email', 'value'), State('reg-nombre', 'value'), State('reg-pwd', 'value'), State('reg-sexo', 'value')],
    prevent_initial_call=True
)
def manejar_registro(n_clicks, email, nombre, pwd, sexo):
    if not email or not nombre or not pwd:
        return dbc.Alert("Rellena todos los campos", color="warning")
    if auth_manager_v2.registrar_usuario(email, nombre, pwd, sexo):
        return dbc.Alert("¡Cuenta creada con éxito! Ya puedes iniciar sesión.", color="success")
    return dbc.Alert("El email ya está registrado.", color="danger")

@app.callback(
    [Output('store-menu', 'data'), Output('store-user-id', 'data', allow_duplicate=True)],
    [
        Input('nav-sesion', 'n_clicks'),
        Input('nav-evolucion', 'n_clicks'),
        Input('nav-comparativa', 'n_clicks'),
        Input('nav-config', 'n_clicks'),
        Input('nav-logout', 'n_clicks')
    ],
    prevent_initial_call=True
)
def cambiar_menu(n_sesion, n_evol, n_comp, n_conf, n_logout):
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if button_id == 'nav-logout':
        return "Sesión Individual", None
    elif button_id == 'nav-evolucion':
        return "Evolución de Temporada", dash.no_update
    elif button_id == 'nav-comparativa':
        return "Comparativa", dash.no_update
    elif button_id == 'nav-config':
        return "Configuración & Sync", dash.no_update
    return "Sesión Individual", dash.no_update

# --- 4. RENDERIZADO DE CONTENIDO PRINCIPAL ---
@app.callback(
    Output('main-container', 'children'),
    [Input('store-user-id', 'data'), Input('store-menu', 'data'),
     Input('store-cal-anho', 'data'), Input('store-cal-mes', 'data')]
)
def renderizar_app(user_id, menu_seleccionado, cal_anho, cal_mes):
    if not user_id:
        return login_layout
    
    if not cal_anho:
        cal_anho = datetime.today().year
    if not cal_mes:
        cal_mes = datetime.today().month
        
    navbar = generar_navbar(menu_seleccionado)
    content = html.Div()
    
    if menu_seleccionado == "Sesión Individual":
        conn = db_web_v2.conectar_db()
        query_acts = """
            SELECT a.actividad_id, a.fecha, a.tipo, a.nombre, a.distancia_km, h.minutos, h.trimp 
            FROM actividades a
            LEFT JOIN historial_entrenamientos h ON a.actividad_id = h.actividad_id AND a.user_id = h.user_id
            WHERE a.user_id = %s 
            ORDER BY a.fecha DESC
        """
        df_actividades = pd.read_sql_query(query_acts, conn, params=(user_id,))
        conn.close()

        if df_actividades.empty:
            content = dbc.Container([
                navbar,
                dbc.Alert("ℹ️ No hay actividades sincronizadas. Ve a 'Configuración & Sync'.", color="info", className="mt-5")
            ], fluid=True, style={"marginTop": "5rem", "padding": "2rem"})
        else:
            df_actividades['nombre_sesion'] = df_actividades['nombre'].fillna(df_actividades['tipo']).fillna("Entrenamiento")
            
            meses_nombres = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
            cal = calendar.Calendar(firstweekday=0)
            matriz_semanas = cal.monthdatescalendar(cal_anho, cal_mes)

            meses_options = [{"label": m, "value": i+1} for i, m in enumerate(meses_nombres)]
            anios_options = [{"label": str(a), "value": a} for a in range(2023, 2033)]

            header_calendario = html.Div([
                html.H3("📅 Calendario de Entrenamientos", className="mb-0", style={"fontSize": "1.3rem"}),
                html.Div([
                    dbc.Button("◀", id="btn-prev-mes", color="secondary", size="sm", className="me-2", style={"fontWeight": "bold"}),
                    dcc.Dropdown(
                        id="dropdown-cal-mes",
                        options=meses_options,
                        value=cal_mes,
                        clearable=False,
                        style={"width": "135px", "display": "inline-block", "marginRight": "8px", "fontSize": "13px"}
                    ),
                    dcc.Dropdown(
                        id="dropdown-cal-anho",
                        options=anios_options,
                        value=cal_anho,
                        clearable=False,
                        style={"width": "95px", "display": "inline-block", "marginRight": "8px", "fontSize": "13px"}
                    ),
                    dbc.Button("▶", id="btn-next-mes", color="secondary", size="sm", style={"fontWeight": "bold"})
                ], style={"display": "flex", "alignItems": "center"})
            ], style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "marginBottom": "15px", "flexWrap": "wrap", "gap": "10px"})

            dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo", "Totales Semanales"]
            header_cols = html.Div([
                html.Div(
                    d, 
                    style={
                        "textAlign": "center", 
                        "fontWeight": "bold", 
                        "backgroundColor": "#f1f5f9", 
                        "padding": "5px",
                        "fontSize": "11px", 
                        "color": "#334155",
                        "borderRight": "1px solid #cbd5e1" if i < 7 else "none",
                        "boxSizing": "border-box"
                    }
                )
                for i, d in enumerate(dias_semana)
            ], style={
                "display": "grid", 
                "gridTemplateColumns": "repeat(7, 1fr) 1.2fr",
                "backgroundColor": "#f1f5f9",
                "borderBottom": "1px solid #cbd5e1",
                "boxSizing": "border-box"
            })

            df_actividades['dt_fecha'] = pd.to_datetime(df_actividades['fecha'])
            semanas_rows = []

            trimp_semana_anterior = None
            if matriz_semanas:
                primera_fecha_matriz = matriz_semanas[0][0]
                fechas_sem_anterior = [primera_fecha_matriz - timedelta(days=i) for i in range(1, 8)]
                acts_sem_ant = df_actividades[df_actividades['dt_fecha'].dt.date.isin(fechas_sem_anterior)]
                if not acts_sem_ant.empty and 'trimp' in acts_sem_ant.columns:
                    trimp_semana_anterior = acts_sem_ant['trimp'].sum()

            num_semanas = len(matriz_semanas)
            for idx_sem, semana in enumerate(matriz_semanas):
                acts_semana = df_actividades[df_actividades['dt_fecha'].dt.date.isin(semana)]
                sem_km = acts_semana['distancia_km'].sum() if 'distancia_km' in acts_semana.columns else 0.0
                sem_min = acts_semana['minutos'].sum() if 'minutos' in acts_semana.columns else 0.0
                sem_trimp = acts_semana['trimp'].sum() if 'trimp' in acts_semana.columns else 0.0

                h_sem = int(sem_min // 60)
                m_sem = int(sem_min % 60)

                diff_pct_trimp = None
                if trimp_semana_anterior is not None and trimp_semana_anterior > 0:
                    diff_pct_trimp = ((sem_trimp - trimp_semana_anterior) / trimp_semana_anterior) * 100
                trimp_semana_anterior = sem_trimp

                if diff_pct_trimp is not None:
                    signo = "+" if diff_pct_trimp >= 0 else ""
                    texto_ratio = f"Δ TRIMP: {signo}{diff_pct_trimp:.1f}%"
                    if diff_pct_trimp > 10.0:
                        color_ratio = "#dc2626"
                        fw_ratio = "bold"
                    else:
                        color_ratio = "#16a34a" if diff_pct_trimp <= 0 else "#2563eb"
                        fw_ratio = "normal"
                    div_ratio = html.Div(texto_ratio, style={"fontSize": "9px", "color": color_ratio, "fontWeight": fw_ratio, "marginTop": "2px"})
                else:
                    div_ratio = html.Div("Δ TRIMP: N/A", style={"fontSize": "9px", "color": "#94a3b8", "marginTop": "2px"})

                celdas_dia = []
                for i, fecha_celda in enumerate(semana):
                    es_mes_actual = (fecha_celda.month == cal_mes)
                    opacidad_celda = "1" if es_mes_actual else "0.4"
                    bg_celda = "#ffffff" if es_mes_actual else "#f9fafb"

                    acts_dia = df_actividades[df_actividades['dt_fecha'].dt.date == fecha_celda]
                    
                    elementos_dia = [html.Div(str(fecha_celda.day), style={"fontSize": "11px", "fontWeight": "bold", "color": "#64748b", "marginBottom": "3px"})]
                    
                    if not acts_dia.empty:
                        for _, act in acts_dia.iterrows():
                            nombre_corto = str(act['nombre_sesion'])[:12]
                            dist_v = act['distancia_km'] if pd.notna(act['distancia_km']) else 0.0
                            
                            tipo_s = str(act.get('tipo', '')).lower()
                            color_bg = "#dbeafe" if "series" in tipo_s else "#dcfce7"
                            color_txt = "#1e40af" if "series" in tipo_s else "#166534"
                            
                            btn_id = {'type': 'act-btn-cal', 'index': int(act['actividad_id'])}
                            elementos_dia.append(
                                dbc.Button(
                                    f"{nombre_corto} ({dist_v:.1f}k)",
                                    id=btn_id,
                                    size="sm",
                                    style={
                                        "fontSize": "9.5px", "fontWeight": "600", "width": "100%", 
                                        "backgroundColor": color_bg, "color": color_txt, 
                                        "border": "none", "borderRadius": "3px", 
                                        "padding": "2px 5px", "marginBottom": "2px", 
                                        "textAlign": "left", "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"
                                    }
                                )
                            )
                    
                    celdas_dia.append(html.Div(elementos_dia, style={
                        "backgroundColor": bg_celda, 
                        "opacity": opacidad_celda,
                        "padding": "5px", 
                        "minHeight": "90px",
                        "borderRight": "1px solid #f1f5f9",
                        "boxSizing": "border-box"
                    }))

                celdas_dia.append(html.Div([
                    html.Div("Totales", style={"fontWeight": "bold", "color": "#475569", "borderBottom": "1px solid #e2e8f0", "marginBottom": "4px", "paddingBottom": "2px"}),
                    html.Div(f"Dist: {sem_km:.1f} km", style={"fontSize": "9.5px"}),
                    html.Div(f"Tiempo: {h_sem}h {m_sem:02d}m", style={"fontSize": "9.5px"}),
                    html.Div(f"TRIMP: {sem_trimp:.0f}", style={"fontSize": "9.5px"}),
                    div_ratio
                ], style={
                    "backgroundColor": "#f8fafc", 
                    "padding": "5px 8px", 
                    "fontSize": "10px", 
                    "color": "#334155",
                    "boxSizing": "border-box"
                }))

                es_ultima_semana = (idx_sem == num_semanas - 1)
                border_bottom_fila = "none" if es_ultima_semana else "1px solid #e2e8f0"

                semanas_rows.append(html.Div(
                    celdas_dia, 
                    style={
                        "display": "grid", 
                        "gridTemplateColumns": "repeat(7, 1fr) 1.2fr",
                        "borderBottom": border_bottom_fila,
                        "boxSizing": "border-box"
                    }
                ))

            grid_calendario_completo = html.Div([
                header_cols,
                html.Div(semanas_rows)
            ], style={
                "border": "1px solid #cbd5e1",
                "borderRadius": "6px",
                "overflow": "hidden",
                "boxShadow": "0 1px 3px 0 rgba(0, 0, 0, 0.05)",
                "backgroundColor": "#ffffff"
            })

            content = dbc.Container([
                navbar,
                html.Div([
                    header_calendario,
                    grid_calendario_completo,
                    html.Div(id='detalle-sesion-wrapper', children=[html.Div(id='resumen-sesion-anchor')])
                ], style={"marginTop": "6rem", "paddingBottom": "3rem"})
            ], fluid=True)

    elif menu_seleccionado == "Evolución de Temporada":
        df_plot = core_metrics_v2.procesar_curvas_acumuladas(user_id)
        fig_ev = go.Figure()
        estado_actual_div = html.Div()
        
        if not df_plot.empty:
            df_plot.index = pd.to_datetime(df_plot.index)
            
            fig_ev = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                row_heights=[0.65, 0.35], 
                vertical_spacing=0.1,
                specs=[[{"secondary_y": True}], [{}]]
            )
            
            fig_ev.add_trace(
                go.Scatter(x=df_plot.index, y=df_plot['CTL_Forma'], name='Forma (CTL)', line=dict(color='green', width=3)),
                row=1, col=1, secondary_y=False
            )
            fig_ev.add_trace(
                go.Scatter(x=df_plot.index, y=df_plot['ATL_Fatiga'], name='Fatiga (ATL)', line=dict(color='red', width=2, dash='dot')),
                row=1, col=1, secondary_y=False
            )
            
            tsb_vals = df_plot['TSB_Frescura']
            fig_ev.add_trace(
                go.Scatter(x=df_plot.index, y=tsb_vals, name='Balance (TSB)', line=dict(color='blue', width=1.5)),
                row=1, col=1, secondary_y=True
            )
            
            tsb_pos = tsb_vals.copy()
            tsb_pos[tsb_pos < 0] = 0
            tsb_neg = tsb_vals.copy()
            tsb_neg[tsb_neg > 0] = 0
            
            fig_ev.add_trace(
                go.Scatter(x=df_plot.index, y=tsb_pos, name='TSB Positivo', fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.2)', line=dict(width=0), showlegend=False),
                row=1, col=1, secondary_y=True
            )
            fig_ev.add_trace(
                go.Scatter(x=df_plot.index, y=tsb_neg, name='TSB Negativo', fill='tozeroy', fillcolor='rgba(239, 68, 68, 0.2)', line=dict(width=0), showlegend=False),
                row=1, col=1, secondary_y=True
            )

            fig_ev.add_trace(
                go.Scatter(x=df_plot.index, y=df_plot['ACWR'], name='ACWR', line=dict(color='purple', width=2), showlegend=False),
                row=2, col=1
            )
            
            fig_ev.add_hrect(
                y0=0.8, y1=1.3, fillcolor="green", opacity=0.1, layer="below", line_width=0,
                row=2, col=1, annotation_text="Zona Óptima", annotation_position="top left"
            )
            fig_ev.add_hline(
                y=1.5, line_dash="dash", line_color="red", line_width=1.5,
                row=2, col=1, annotation_text="Peligro Sobrecarga", annotation_position="top left"
            )

            fig_ev.update_layout(
                height=750,
                template="plotly_white",
                title="Evolución de Carga, Fatiga, Balance y Ratio ACWR",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=40, r=40, t=50, b=40)
            )
            
            fig_ev.update_xaxes(
                rangeselector=dict(
                    buttons=list([
                        dict(count=3, label="3m", step="month", stepmode="backward"),
                        dict(count=6, label="6m", step="month", stepmode="backward"),
                        dict(count=1, label="1y", step="year", stepmode="backward"),
                        dict(step="all", label="Todo")
                    ])
                ),
                type="date",
                row=2, col=1
            )
            
            fig_ev.update_yaxes(title_text="<b>Carga / Fatiga (CTL/ATL)</b>", secondary_y=False, row=1, col=1)
            fig_ev.update_yaxes(title_text="<b>Balance (TSB)</b>", secondary_y=True, row=1, col=1)
            fig_ev.update_yaxes(title_text="<b>ACWR</b>", range=[0.5, 2.0], autorange=False, row=2, col=1)

            ctl_curr = df_plot['CTL_Forma'].iloc[-1]
            atl_curr = df_plot['ATL_Fatiga'].iloc[-1]
            tsb_curr = df_plot['TSB_Frescura'].iloc[-1]
            acwr_curr = df_plot['ACWR'].iloc[-1]

            estado_actual_div = html.Div([
                html.H4("Estado Actual", className="mb-3 text-dark fw-bold"),
                dbc.Row([
                    dbc.Col(crear_tarjeta_kpi("Forma Actual (CTL)", ctl_curr, "CTL")),
                    dbc.Col(crear_tarjeta_kpi("Fatiga Actual (ATL)", atl_curr, "ATL")),
                    dbc.Col(crear_tarjeta_kpi("Balance (TSB)", tsb_curr, "TSB")),
                    dbc.Col(crear_tarjeta_kpi("Ratio Carga (ACWR)", acwr_curr, "ACWR")),
                ], className="g-3")
            ], className="mt-4 p-4 bg-white border rounded shadow-sm")

        content = dbc.Container([
            navbar,
            html.Div([
                html.H3("📈 Evolución de Temporada", className="mb-4"),
                dcc.Graph(figure=fig_ev),
                estado_actual_div
            ], style={"marginTop": "6rem", "paddingBottom": "3rem"})
        ], fluid=True)

    elif menu_seleccionado == "Comparativa":
        conn = db_web_v2.conectar_db()
        df_acts_comp = pd.read_sql_query(
            "SELECT actividad_id, nombre, fecha, tipo, distancia_km FROM actividades WHERE user_id = %s ORDER BY fecha DESC", 
            conn, params=(user_id,)
        )
        conn.close()

        options_acts = []
        if not df_acts_comp.empty:
            df_acts_comp['label'] = df_acts_comp['nombre'].fillna(df_acts_comp['tipo']).fillna("Sesión") + " (" + df_acts_comp['fecha'].astype(str) + ")"
            options_acts = [{"label": row['label'], "value": int(row['actividad_id'])} for _, row in df_acts_comp.iterrows()]

        content = dbc.Container([
            navbar,
            html.Div([
                html.H3("⚖️ Comparativa de Sesiones", className="mb-4 fw-bold text-dark"),
                dbc.Row([
                    dbc.Col([
                        html.Label("Sesión 1 (Base):", className="fw-bold mb-1"),
                        dcc.Dropdown(id='comp-sesion-1', options=options_acts, placeholder="Selecciona la primera sesión...", className="mb-3")
                    ], width=6),
                    dbc.Col([
                        html.Label("Sesión 2 (Comparar):", className="fw-bold mb-1"),
                        dcc.Dropdown(id='comp-sesion-2', options=options_acts, placeholder="Selecciona la segunda sesión...", className="mb-3")
                    ], width=6),
                ]),
                dbc.Button("Comparar Sesiones", id="btn-ejecutar-comparativa", color="primary", className="mb-4 fw-bold"),
                html.Div(id="resultado-comparativa-div")
            ], style={"marginTop": "6rem", "paddingBottom": "3rem"})
        ], fluid=True)

    elif menu_seleccionado == "Configuración & Sync":
        conn = db_web_v2.conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT origen_tipo, fecha_inicio FROM configuracion_origen WHERE user_id = %s ORDER BY fecha_inicio DESC LIMIT 1", (user_id,))
        actual_disp = cursor.fetchone()
        
        dispositivo_actual = actual_disp[0] if actual_disp else "Garmin"
        fecha_ini_disp = actual_disp[1] if actual_disp else str(datetime.today().date())

        cursor.execute("SELECT usuario_email FROM credenciales_plataformas WHERE user_id = %s AND plataforma = %s", (user_id, dispositivo_actual))
        res_email = cursor.fetchone()
        email_plat = res_email[0] if res_email else ""

        today_str = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("SELECT fc_maxima, fc_reposo FROM historial_fisiologico WHERE user_id = %s AND fecha_inicio = %s ORDER BY id DESC LIMIT 1", (user_id, today_str))
        fisio_today = cursor.fetchone()
        conn.close()

        fc_max_today = int(fisio_today[0]) if (fisio_today and fisio_today[0]) else 185
        fc_rep_today = int(fisio_today[1]) if (fisio_today and fisio_today[1]) else 45

        if dispositivo_actual == "Garmin":
            alerta_fisio_auto = dbc.Alert("💡 Puedes sincronizar automáticamente tu perfil fisiológico desde tus servidores Garmin.", color="info", className="mb-3")
            btn_fisio_disabled = False
        else:
            alerta_fisio_auto = dbc.Alert("⚠️ La sincronización automática del perfil fisiológico solo está disponible para dispositivos Garmin. Para otros dispositivos, puedes actualizarlo manualmente abajo.", color="warning", className="mb-3")
            btn_fisio_disabled = True

        content = dbc.Container([
            navbar,
            html.Div([
                html.H3("⚙️ Panel de Configuración y Sincronización", className="mb-4 fw-bold text-dark"),
                
                dbc.Card([
                    dbc.CardHeader("📱 Configuración de tu Dispositivo Principal", className="fw-bold bg-light"),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Label("Dispositivo Activo:"),
                                dbc.Select(id="cfg-select-dispositivo", options=[{"label": "Garmin", "value": "Garmin"}, {"label": "Coros", "value": "Coros"}], value=dispositivo_actual, className="mb-3")
                            ], width=6),
                            dbc.Col([
                                html.Label("Fecha de inicio con este dispositivo:"),
                                dbc.Input(id="cfg-fecha-dispositivo", type="date", value=fecha_ini_disp, className="mb-3")
                            ], width=6)
                        ]),
                        dbc.Button("Guardar Dispositivo", id="btn-save-dispositivo", color="primary", size="sm", className="fw-bold"),
                        html.Div(id="alert-save-dispositivo", className="mt-2")
                    ])
                ], className="mb-4 shadow-sm"),

                dbc.Card([
                    dbc.CardHeader(f"🔑 Credenciales de Acceso ({dispositivo_actual})", className="fw-bold bg-light"),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Label("Email / Usuario:"),
                                dbc.Input(id="cfg-user-email", type="email", value=email_plat, placeholder="email@ejemplo.com", className="mb-3")
                            ], width=6),
                            dbc.Col([
                                html.Label("Contraseña:"),
                                dbc.Input(id="cfg-user-pwd", type="password", placeholder="••••••••", className="mb-3")
                            ], width=6)
                        ]),
                        dbc.Button(f"Guardar Credenciales {dispositivo_actual}", id="btn-save-creds", color="primary", size="sm", className="fw-bold"),
                        html.Div(id="alert-save-creds", className="mt-2")
                    ])
                ], className="mb-4 shadow-sm"),

                dbc.Card([
                    dbc.CardHeader("❤️ Control de Perfil Fisiológico de Hoy", className="fw-bold bg-light"),
                    dbc.CardBody([
                        alerta_fisio_auto,
                        dbc.Row([
                            dbc.Col([
                                html.Label("FC Máxima (bpm):"),
                                dbc.Input(id="cfg-fc-max", type="number", value=fc_max_today, min=100, max=220, className="mb-3")
                            ], width=6),
                            dbc.Col([
                                html.Label("FC Reposo (bpm):"),
                                dbc.Input(id="cfg-fc-rep", type="number", value=fc_rep_today, min=30, max=100, className="mb-3")
                            ], width=6)
                        ]),
                        html.Div([
                            dbc.Button("Sincronizar Fisiología con Garmin", id="btn-sync-fisio-garmin", color="info", className="me-2 text-white fw-bold", disabled=btn_fisio_disabled),
                            dbc.Button("Guardar Fisiología Manualmente", id="btn-save-fisio-manual", color="success", className="fw-bold")
                        ]),
                        html.Div(id="alert-fisio-res", className="mt-2")
                    ])
                ], className="mb-4 shadow-sm"),

                dbc.Card([
                    dbc.CardHeader("🔄 Sincronización de Actividades", className="fw-bold bg-light"),
                    dbc.CardBody([
                        dbc.Tabs([
                            dbc.Tab([
                                html.P(f"Descarga directamente tus últimas actividades desde los servidores de {dispositivo_actual}.", className="mt-3 text-muted"),
                                dbc.Row([
                                    dbc.Col([
                                        html.Label("Número de actividades a sincronizar:"),
                                        dbc.Input(id="cfg-num-act-sync", type="number", value=5, min=1, max=1000, className="mb-3")
                                    ], width=4)
                                ]),
                                dbc.Button(f"Sincronizar con {dispositivo_actual}", id="btn-run-sync-auto", color="primary", className="fw-bold"),
                                html.Div(id="alert-sync-auto-res", className="mt-3")
                            ], label="⚡ Sincronización Automática", tab_id="tab-auto"),

                            dbc.Tab([
                                html.P("Importa ficheros .FIT guardados localmente o subidos desde tu ordenador.", className="mt-3 text-muted"),
                                dcc.Upload(
                                    id='upload-fit-files',
                                    children=html.Div(['Arrastra o ', html.A('selecciona tus archivos .FIT')]),
                                    style={
                                        'width': '100%', 'height': '80px', 'lineHeight': '80px',
                                        'borderWidth': '2px', 'borderStyle': 'dashed', 'borderRadius': '8px',
                                        'textAlign': 'center', 'backgroundColor': '#f8fafc', 'cursor': 'pointer'
                                    },
                                    multiple=True,
                                    className="mb-3"
                                ),
                                dbc.Button("Procesar Archivos .FIT Subidos", id="btn-process-fit-uploads", color="success", className="me-2 fw-bold"),
                                dbc.Button("Procesar Carpeta Local ('./ficheros_fit/')", id="btn-process-fit-local", color="secondary", className="fw-bold"),
                                html.Div(id="alert-fit-import-res", className="mt-3")
                            ], label="📁 Carga Manual (.FIT)", tab_id="tab-manual")
                        ], active_tab="tab-auto")
                    ])
                ], className="mb-4 shadow-sm")

            ], style={"marginTop": "6rem", "paddingBottom": "3rem"})
        ], fluid=True)

    return content


# --- 5. CALLBACKS DE INTERACTIVIDAD ---

# Callback dedicado para actualizar el detalle de la sesión sin recargar el calendario
@app.callback(
    Output('detalle-sesion-wrapper', 'children'),
    Input('store-activa', 'data'),
    State('store-user-id', 'data')
)
def actualizar_detalle_sesion(actividad_activa, user_id):
    if not actividad_activa or not user_id:
        return [html.Div(id='resumen-sesion-anchor')]
    
    conn = db_web_v2.conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT actividad_id, nombre, fecha, tipo, distancia_km FROM actividades WHERE user_id = %s and actividad_id = %s", (user_id, actividad_activa))
    cabecera = cursor.fetchone()
    
    if not cabecera:
        conn.close()
        return [html.Div(id='resumen-sesion-anchor')]
        
    act_id_r, nom_a, fec_a, tipo_a, dist_k = cabecera[0], cabecera[1], cabecera[2], cabecera[3], cabecera[4]
    cursor.execute("SELECT trimp, minutos FROM historial_entrenamientos WHERE user_id = %s AND actividad_id = %s", (user_id, act_id_r))
    m_carga = cursor.fetchone()
    cursor.execute("SELECT porcentaje_deriva, fc_inicial, fc_final FROM historial_derivas WHERE user_id = %s AND actividad_id = %s", (user_id, act_id_r))
    d_deriva = cursor.fetchone()
    
    df_vueltas = pd.read_sql_query("SELECT lap_index, ritmo_seg_km, fc_media FROM detalle_vueltas WHERE user_id = %s AND actividad_id = %s ORDER BY lap_index ASC", conn, params=(user_id, act_id_r))
    conn.close()

    dist_val = dist_k if dist_k else 0.0
    trimp_val = m_carga[0] if (m_carga and m_carga[0]) else 0.0
    min_val = m_carga[1] if (m_carga and m_carga[1]) else 0.0
    
    df_banister = core_metrics_v2.procesar_curvas_acumuladas(user_id)
    atl_v, ctl_v, tsb_v, acwr_v = 0.0, 0.0, 0.0, 0.0
    if not df_banister.empty and fec_a:
        try:
            f_dt = pd.to_datetime(fec_a).normalize()
            if f_dt in df_banister.index:
                row_b = df_banister.loc[f_dt]
                atl_v, ctl_v, tsb_v, acwr_v = row_b['ATL_Fatiga'], row_b['CTL_Forma'], row_b['TSB_Frescura'], row_b['ACWR']
        except:
            pass

    t_min = trimp_val / min_val if min_val > 0 else 0.0
    t_km = trimp_val / dist_val if dist_val > 0 else 0.0
    fc_m = df_vueltas['fc_media'].mean() if not df_vueltas.empty else 0.0
    ritmo_str = segundos_a_min_km(min_val * 60 / dist_val) if dist_val > 0 else "0:00"

    kpis_row1 = dbc.Row([
        dbc.Col(crear_tarjeta_kpi("ATL", atl_v, "ATL")),
        dbc.Col(crear_tarjeta_kpi("CTL", ctl_v, "CTL")),
        dbc.Col(crear_tarjeta_kpi("TSB", tsb_v, "TSB")),
        dbc.Col(crear_tarjeta_kpi("ACWR", acwr_v, "ACWR")),
        dbc.Col(crear_tarjeta_kpi("TRIMP", trimp_val, "TRIMP")),
        dbc.Col(crear_tarjeta_kpi("TRIMP/m", t_min, "TRIMP/m")),
        dbc.Col(crear_tarjeta_kpi("TRIMP/km", t_km, "TRIMP/km")),
        dbc.Col(crear_tarjeta_kpi("Dist (km)", dist_val, "Dist")),
        dbc.Col(crear_tarjeta_kpi("Tiempo", min_val, "Tiempo")),
        dbc.Col(crear_tarjeta_kpi("FC media", fc_m, "FC media")),
        dbc.Col(crear_tarjeta_kpi("Ritmo", ritmo_str, "Ritmo")),
    ], className="g-2 mb-3")

    desac = d_deriva[0] if (d_deriva and d_deriva[0]) else 0.0
    fci = float(d_deriva[1]) if (d_deriva and d_deriva[1]) else 0.0
    fcf = float(d_deriva[2]) if (d_deriva and d_deriva[2]) else 0.0
    porc_der = ((fcf - fci) / fcf) * 100 if fcf > 0 else 0.0

    kpis_row2 = dbc.Row([
        dbc.Col(crear_tarjeta_kpi("Deriva cardíaca", desac, "DES")),
        dbc.Col(crear_tarjeta_kpi("Dif. frecuencias", porc_der, "DER")),
        dbc.Col(crear_tarjeta_kpi("FC inicial", fci if fci > 0 else "N/D", "FCI")),
        dbc.Col(crear_tarjeta_kpi("FC final", fcf if fcf > 0 else "N/D", "FCF")),
        dbc.Col(crear_tarjeta_kpi("Sesión", nom_a or tipo_a or "Rodaje", "SES")),
    ], className="g-2 mb-3")

    if desac < 5:
        alerta_deriva = html.Div([
            html.Span("🟢 ", style={"fontSize": "1.1rem"}),
            html.Strong("El ritmo está consolidado y tu base aeróbica sostiene el esfuerzo sin fatiga cardiovascular sobreañadida.")
        ], style={"backgroundColor": "#f0fdf4", "border": "1px solid #bbf7d0", "padding": "10px 15px", "borderRadius": "6px", "marginBottom": "15px", "color": "#166534", "fontSize": "0.9rem"})
    elif desac > 8:
        alerta_deriva = html.Div([
            html.Span("🔴 ", style={"fontSize": "1.1rem"}),
            html.Strong("El sistema se desacopla de forma acusada; indica que el ritmo o el volumen exigen un trabajo de base aeróbica superior.")
        ], style={"backgroundColor": "#fef2f2", "border": "1px solid #fecaca", "padding": "10px 15px", "borderRadius": "6px", "marginBottom": "15px", "color": "#991b1b", "fontSize": "0.9rem"})
    else:
        alerta_deriva = html.Div([
            html.Span("🟡 ", style={"fontSize": "1.1rem"}),
            html.Strong("Estás rozando el umbral; el cuerpo comienza a encarecer el coste energético en la segunda mitad.")
        ], style={"backgroundColor": "#fefce8", "border": "1px solid #fef08a", "padding": "10px 15px", "borderRadius": "6px", "marginBottom": "15px", "color": "#854d0e", "fontSize": "0.9rem"})

    fig_vueltas = make_subplots(specs=[[{"secondary_y": True}]])
    if not df_vueltas.empty:
        df_vueltas['ritmo_mmss'] = df_vueltas['ritmo_seg_km'].apply(segundos_a_min_km)
        
        fig_vueltas.add_trace(
            go.Scatter(
                x=df_vueltas['lap_index'], 
                y=df_vueltas['fc_media'], 
                name="FC Media", 
                line=dict(color="#b71c1c", width=3)
            ), 
            secondary_y=False
        )
        
        fig_vueltas.add_trace(
            go.Scatter(
                x=df_vueltas['lap_index'], 
                y=df_vueltas['ritmo_seg_km'], 
                name="Ritmo", 
                line=dict(color="#2962ff", width=2),
                text=df_vueltas['ritmo_mmss'],
                hovertemplate="Lap %{x}<br>Ritmo: %{text}<extra></extra>"
            ), 
            secondary_y=True
        )

        if fci > 0:
            fig_vueltas.add_hline(
                y=fci, 
                line_dash="dash", 
                line_color="#e11d48", 
                line_width=1.5,
                annotation_text=f"FC Ini ({fci:.1f})", 
                annotation_position="bottom left",
                annotation_font_size=9,
                annotation_font_color="#e11d48",
                secondary_y=False
            )
        if fcf > 0:
            fig_vueltas.add_hline(
                y=fcf, 
                line_dash="dot", 
                line_color="#e11d48", 
                line_width=1.5,
                annotation_text=f"FC Fin ({fcf:.1f})", 
                annotation_position="top left",
                annotation_font_size=9,
                annotation_font_color="#e11d48",
                secondary_y=False
            )

        min_seg = df_vueltas['ritmo_seg_km'].min()
        max_seg = df_vueltas['ritmo_seg_km'].max()
        
        if min_seg == max_seg:
            tick_vals = [min_seg]
        else:
            tick_vals = np.linspace(min_seg, max_seg, num=5)
        
        tick_texts = [segundos_a_min_km(val) for val in tick_vals]

        amplitud_real = max_seg - min_seg
        margen = max(amplitud_real * 0.1, 10)
        rango_y2 = [max_seg + margen, min_seg - margen]

        fig_vueltas.update_layout(
            title="Evolución de la Sesión por Vueltas", 
            template="plotly_white", 
            height=380,
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        fig_vueltas.update_yaxes(title_text="<b>FC Media (ppm)</b>", secondary_y=False)
        fig_vueltas.update_yaxes(
            title_text="<b>Ritmo (min/km)</b>", 
            range=rango_y2,
            autorange=False,
            tickvals=tick_vals,
            ticktext=tick_texts,
            secondary_y=True
        )

    return [
        html.Div(id='resumen-sesion-anchor'),
        html.Div([
            html.Hr(),
            html.H4("📋 Resumen de la Sesión Seleccionada", className="mb-3 text-dark"),
            kpis_row1,
            kpis_row2,
            alerta_deriva,
            dcc.Graph(figure=fig_vueltas)
        ], className="mt-4 p-3 bg-white border rounded shadow-sm")
    ]


@app.callback(
    Output("alert-save-dispositivo", "children"),
    Input("btn-save-dispositivo", "n_clicks"),
    [State("store-user-id", "data"), State("cfg-select-dispositivo", "value"), State("cfg-fecha-dispositivo", "value")],
    prevent_initial_call=True
)
def guardar_dispositivo(n_clicks, user_id, dispositivo, fecha):
    if not user_id: return dash.no_update
    conn = db_web_v2.conectar_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO configuracion_origen (user_id, origen_tipo, fecha_inicio) VALUES (%s, %s, %s)", (user_id, dispositivo, str(fecha)))
    conn.commit()
    conn.close()
    return dbc.Alert(f"✅ Dispositivo {dispositivo} configurado correctamente.", color="success")

@app.callback(
    Output("alert-save-creds", "children"),
    Input("btn-save-creds", "n_clicks"),
    [State("store-user-id", "data"), State("cfg-select-dispositivo", "value"), State("cfg-user-email", "value"), State("cfg-user-pwd", "value")],
    prevent_initial_call=True
)
def guardar_credenciales(n_clicks, user_id, dispositivo, email, pwd):
    if not user_id or not email or not pwd:
        return dbc.Alert("Rellena todos los campos de credenciales.", color="warning")
    conn = db_web_v2.conectar_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO credenciales_plataformas (user_id, plataforma, usuario_email, password_token) 
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, plataforma) 
        DO UPDATE SET usuario_email = EXCLUDED.usuario_email, password_token = EXCLUDED.password_token
    """, (user_id, dispositivo, email, pwd))
    conn.commit()
    conn.close()
    return dbc.Alert(f"✅ Credenciales de {dispositivo} guardadas con éxito.", color="success")

@app.callback(
    Output("alert-fisio-res", "children"),
    [Input("btn-sync-fisio-garmin", "n_clicks"), Input("btn-save-fisio-manual", "n_clicks")],
    [State("store-user-id", "data"), State("cfg-fc-max", "value"), State("cfg-fc-rep", "value")],
    prevent_initial_call=True
)
def gestionar_fisiologia(n_garmin, n_manual, user_id, fc_max, fc_rep):
    ctx = callback_context
    if not ctx.triggered: return dash.no_update
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == "btn-sync-fisio-garmin":
        try:
            ingestor = GarminIngestor(user_id)
            if ingestor.actualizar_datos_fisiologicos_garmin():
                return dbc.Alert("✅ Perfil fisiológico sincronizado con éxito desde Garmin.", color="success")
            else:
                return dbc.Alert("⚠️ No se pudieron sincronizar los datos de Garmin.", color="warning")
        except Exception as e:
            return dbc.Alert(f"Error al sincronizar con Garmin: {e}", color="danger")
            
    elif button_id == "btn-save-fisio-manual":
        today_str = datetime.now().strftime('%Y-%m-%d')
        conn = db_web_v2.conectar_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO historial_fisiologico (user_id, fecha_inicio, fc_maxima, fc_reposo) VALUES (%s, %s, %s, %s)",
                       (user_id, today_str, fc_max, fc_rep))
        conn.commit()
        conn.close()
        return dbc.Alert("✅ Perfil fisiológico actualizado manualmente.", color="success")

@app.callback(
    Output("alert-sync-auto-res", "children"),
    Input("btn-run-sync-auto", "n_clicks"),
    [State("store-user-id", "data"), State("cfg-select-dispositivo", "value"), State("cfg-num-act-sync", "value")],
    prevent_initial_call=True
)
def sincronizar_actividades_auto(n_clicks, user_id, dispositivo, num_act):
    if not user_id: return dash.no_update
    limite = min(int(num_act), 1000)
    try:
        if dispositivo == "Garmin":
            ingestor = GarminIngestor(user_id)
            cant = ingestor.sincronizar(limite=limite)
        elif dispositivo == "Coros":
            ingestor = CorosIngestor(user_id)
            cant = ingestor.sincronizar(limite=limite)
        else:
            return dbc.Alert("Plataforma no soportada.", color="danger")
        return dbc.Alert(f"✅ Se han sincronizado {cant} actividades desde {dispositivo}.", color="success")
    except Exception as e:
        return dbc.Alert(f"❌ Error al sincronizar: {e}", color="danger")

@app.callback(
    Output("alert-fit-import-res", "children"),
    [Input("btn-process-fit-uploads", "n_clicks"), Input("btn-process-fit-local", "n_clicks")],
    [State("store-user-id", "data"), State("upload-fit-files", "contents"), State("upload-fit-files", "filename")],
    prevent_initial_call=True
)
def procesar_ficheros_fit(n_upload, n_local, user_id, contents_list, filenames_list):
    ctx = callback_context
    if not ctx.triggered: return dash.no_update
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    carpeta_temp = "./ficheros_fit/"
    os.makedirs(carpeta_temp, exist_ok=True)

    if button_id == "btn-process-fit-uploads":
        if not contents_list:
            return dbc.Alert("Selecciona o arrastra al menos un archivo .FIT primero.", color="warning")
        try:
            for content, name in zip(contents_list, filenames_list):
                header, content_string = content.split(',')
                decoded = base64.b64decode(content_string)
                file_path = os.path.join(carpeta_temp, name)
                with open(file_path, 'wb') as f:
                    f.write(decoded)
            ingestor = FitIngestor(user_id=user_id, carpeta_fit=carpeta_temp)
            cant = ingestor.sincronizar()
            return dbc.Alert(f"✅ Importadas {cant} actividades desde los ficheros subidos.", color="success")
        except Exception as e:
            return dbc.Alert(f"Error procesando archivos subidos: {e}", color="danger")

    elif button_id == "btn-process-fit-local":
        try:
            ingestor = FitIngestor(user_id=user_id, carpeta_fit=carpeta_temp)
            cant = ingestor.sincronizar()
            return dbc.Alert(f"✅ Importadas {cant} actividades desde la carpeta local `./ficheros_fit/`.", color="success")
        except Exception as e:
            return dbc.Alert(f"Error procesando carpeta local: {e}", color="danger")

# Callbacks para el Módulo de Comparativa
@app.callback(
    Output("resultado-comparativa-div", "children"),
    Input("btn-ejecutar-comparativa", "n_clicks"),
    [State("store-user-id", "data"), State("comp-sesion-1", "value"), State("comp-sesion-2", "value")],
    prevent_initial_call=True
)
def generar_comparativa_sesiones(n_clicks, user_id, aid1, aid2):
    if not aid1 or not aid2:
        return dbc.Alert("Selecciona dos sesiones para comparar.", color="warning")
    
    conn = db_web_v2.conectar_db()
    
    cursor = conn.cursor()
    cursor.execute("SELECT nombre, fecha, tipo, distancia_km FROM actividades WHERE user_id = %s AND actividad_id = %s", (user_id, aid1))
    act1_info = cursor.fetchone()
    cursor.execute("SELECT nombre, fecha, tipo, distancia_km FROM actividades WHERE user_id = %s AND actividad_id = %s", (user_id, aid2))
    act2_info = cursor.fetchone()

    nom1 = (act1_info[0] or act1_info[2] or "Sesión 1") if act1_info else "Sesión 1"
    fec1 = str(act1_info[1]) if act1_info else ""
    dist1 = act1_info[3] if (act1_info and act1_info[3]) else 0.0

    nom2 = (act2_info[0] or act2_info[2] or "Sesión 2") if act2_info else "Sesión 2"
    fec2 = str(act2_info[1]) if act2_info else ""
    dist2 = act2_info[3] if (act2_info and act2_info[3]) else 0.0

    def cargar_datos_comparativa(aid):
        q_vueltas = "SELECT lap_index, ritmo_seg_km, fc_media FROM detalle_vueltas WHERE user_id = %s AND actividad_id = %s ORDER BY lap_index ASC"
        df_vueltas = pd.read_sql_query(q_vueltas, conn, params=(user_id, aid))
        
        q_deriva = "SELECT porcentaje_deriva, fc_inicial, fc_final FROM historial_derivas WHERE user_id = %s AND actividad_id = %s"
        df_deriva = pd.read_sql_query(q_deriva, conn, params=(user_id, aid))
        
        q_metricas = "SELECT trimp, minutos, trimp_min, trimp_km FROM historial_entrenamientos WHERE user_id = %s AND actividad_id = %s"
        df_metricas = pd.read_sql_query(q_metricas, conn, params=(user_id, aid))
        
        return df_vueltas, df_deriva, df_metricas

    vueltas1, deriva1, met1 = cargar_datos_comparativa(aid1)
    vueltas2, deriva2, met2 = cargar_datos_comparativa(aid2)
    conn.close()

    def get_val(df, col):
        return float(df[col].iloc[0]) if (not df.empty and col in df.columns and pd.notna(df[col].iloc[0])) else 0.0

    d1, d2 = get_val(deriva1, 'porcentaje_deriva'), get_val(deriva2, 'porcentaje_deriva')
    t_min1, t_min2 = get_val(met1, 'trimp_min'), get_val(met2, 'trimp_min')
    t_km1, t_km2 = get_val(met1, 'trimp_km'), get_val(met2, 'trimp_km')
    
    min1 = get_val(met1, 'minutos')
    min2 = get_val(met2, 'minutos')

    # Cálculo del ritmo medio en segundos por km
    ritmo_seg1 = (min1 * 60 / dist1) if dist1 > 0 else 0.0
    ritmo_seg2 = (min2 * 60 / dist2) if dist2 > 0 else 0.0
    
    ritmo_str1 = segundos_a_min_km(ritmo_seg1)
    ritmo_str2 = segundos_a_min_km(ritmo_seg2)
    diff_ritmo_seg = ritmo_seg2 - ritmo_seg1
    diff_ritmo_str = f"{abs(diff_ritmo_seg):.0f}s" if abs(diff_ritmo_seg) < 60 else f"{diff_ritmo_seg/60:.1f}m"
    if diff_ritmo_seg < 0:
        diff_ritmo_text = f"-{segundos_a_min_km(abs(diff_ritmo_seg))}"
        color_ritmo_diff = "green"
    elif diff_ritmo_seg > 0:
        diff_ritmo_text = f"+{segundos_a_min_km(diff_ritmo_seg)}"
        color_ritmo_diff = "red"
    else:
        diff_ritmo_text = "0:00"
        color_ritmo_diff = "black"

    tabla_kpis = dbc.Table([
        html.Thead(html.Tr([
            html.Th("Métrica"), 
            html.Th(f"{nom1} ({fec1})"), 
            html.Th(f"{nom2} ({fec2})"), 
            html.Th("Diferencia (Δ)")
        ], style={"textAlign": "center"})),
        html.Tbody([
            html.Tr([html.Td("Deriva cardíaca (%)", className="fw-bold"), html.Td(f"{d1:.1f}%"), html.Td(f"{d2:.1f}%"), html.Td(f"{d2 - d1:+.1f}%", style={"color": "red" if d2 > d1 else "green"})]),
            html.Tr([html.Td("Ritmo medio", className="fw-bold"), html.Td(ritmo_str1), html.Td(ritmo_str2), html.Td(diff_ritmo_text, style={"color": color_ritmo_diff})]),
            html.Tr([html.Td("TRIMP / min", className="fw-bold"), html.Td(f"{t_min1:.2f}"), html.Td(f"{t_min2:.2f}"), html.Td(f"{t_min2 - t_min1:+.2f}", style={"color": "red" if t_min2 > t_min1 else "green"})]),
            html.Tr([html.Td("TRIMP / km", className="fw-bold"), html.Td(f"{t_km1:.2f}"), html.Td(f"{t_km2:.2f}"), html.Td(f"{t_km2 - t_km1:+.2f}", style={"color": "red" if t_km2 > t_km1 else "green"})]),
        ])
    ], bordered=True, hover=True, className="bg-white shadow-sm mb-4")

    # Controles para seleccionar métrica en la gráfica superior de comparativa
    control_metrica_grafica = html.Div([
        html.Label("Métrica a comparar:", className="fw-bold me-3", style={"fontSize": "0.9rem"}),
        dcc.RadioItems(
            id='radio-metrica-comp',
            options=[
                {"label": " Frecuencia Cardíaca (ppm)", "value": "fc"},
                {"label": " Ritmo (min/km)", "value": "ritmo"}
            ],
            value="fc",
            inline=True,
            inputStyle={"marginRight": "5px", "marginLeft": "15px"}
        )
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "10px"})

    # Guardamos los dataframes serializados o en stores/divs auxiliares o generamos el gráfico inicial por defecto (FC)
    fig_comp_fc = go.Figure()
    if not vueltas1.empty:
        fig_comp_fc.add_trace(go.Scatter(x=vueltas1['lap_index'], y=vueltas1['fc_media'], name=f"{nom1} ({fec1})", line=dict(color="#2563eb", width=3)))
    if not vueltas2.empty:
        fig_comp_fc.add_trace(go.Scatter(x=vueltas2['lap_index'], y=vueltas2['fc_media'], name=f"{nom2} ({fec2})", line=dict(color="#dc2626", width=3, dash="dot")))

    fig_comp_fc.update_layout(
        title="Comparativa por Vuelta", 
        template="plotly_white", 
        height=380,
        legend=dict(title=dict(text="<b>Sesiones Comparadas</b>"), orientation="v", yanchor="top", y=1, xanchor="right", x=1)
    )
    fig_comp_fc.update_yaxes(title_text="<b>FC Media (ppm)</b>")

    def crear_fig_eficiencia(df_vueltas, titulo):
        if df_vueltas.empty:
            return go.Figure()
        
        df_valid = df_vueltas.dropna(subset=['ritmo_seg_km', 'fc_media']).sort_values('lap_index')
        if df_valid.empty:
            return go.Figure()

        df_valid['ritmo_mmss'] = df_valid['ritmo_seg_km'].apply(segundos_a_min_km)
        
        fig = px.scatter(
            df_valid, x='ritmo_seg_km', y='fc_media', color='lap_index',
            trendline="ols", title=titulo,
            color_continuous_scale="Viridis",
            hover_data={'ritmo_mmss': True, 'ritmo_seg_km': False}
        )
        
        min_seg = int(df_valid['ritmo_seg_km'].min())
        max_seg = int(df_valid['ritmo_seg_km'].max())
        
        ticks_seg = np.linspace(min_seg, max_seg, num=max(3, min(6, len(df_valid)))).astype(int)
        ticks_text = [segundos_a_min_km(s) for s in ticks_seg]

        fig.update_xaxes(
            title="<b>Ritmo (min/km)</b>", 
            autorange="reversed",
            tickvals=ticks_seg,
            ticktext=ticks_text
        )
        fig.update_yaxes(title="<b>FC Media (ppm)</b>")
        fig.update_layout(template="plotly_white", height=380)
        return fig

    fig_eff1 = crear_fig_eficiencia(vueltas1, f"Eficiencia: {nom1} ({fec1})")
    fig_eff2 = crear_fig_eficiencia(vueltas2, f"Eficiencia: {nom2} ({fec2})")

    return html.Div([
        tabla_kpis,
        control_metrica_grafica,
        dcc.Graph(id='graph-comp-metrica', figure=fig_comp_fc),
        html.Hr(),
        html.H5("🎯 Comparativa de Eficiencia Aeróbica", className="fw-bold my-3 text-dark"),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig_eff1), width=6),
            dbc.Col(dcc.Graph(figure=fig_eff2), width=6),
        ]),
        # Stores ocultos para mantener los datos de las dos sesiones seleccionadas para el selector de gráfica
        dcc.Store(id='store-comp-s1', data=vueltas1.to_json(date_format='iso', orient='split') if not vueltas1.empty else None),
        dcc.Store(id='store-comp-s2', data=vueltas2.to_json(date_format='iso', orient='split') if not vueltas2.empty else None),
        dcc.Store(id='store-comp-meta', data={"nom1": nom1, "fec1": fec1, "nom2": nom2, "fec2": fec2})
    ])


# Callback interactivo para cambiar la gráfica superior entre Frecuencia Cardíaca y Ritmo
@app.callback(
    Output('graph-comp-metrica', 'figure'),
    Input('radio-metrica-comp', 'value'),
    [State('store-comp-s1', 'data'), State('store-comp-s2', 'data'), State('store-comp-meta', 'data')]
)
def actualizar_grafica_comparativa_metrica(metrica_tipo, json_s1, json_s2, meta):
    fig = go.Figure()
    nom1 = meta['nom1'] if meta else "Sesión 1"
    fec1 = meta['fec1'] if meta else ""
    nom2 = meta['nom2'] if meta else "Sesión 2"
    fec2 = meta['fec2'] if meta else ""

    df1 = pd.read_json(io.StringIO(json_s1), orient='split') if json_s1 else pd.DataFrame()
    df2 = pd.read_json(io.StringIO(json_s2), orient='split') if json_s2 else pd.DataFrame()

    if metrica_tipo == "ritmo":
        if not df1.empty:
            df1['ritmo_mmss'] = df1['ritmo_seg_km'].apply(segundos_a_min_km)
            fig.add_trace(go.Scatter(
                x=df1['lap_index'], y=df1['ritmo_seg_km'], name=f"{nom1} ({fec1})",
                line=dict(color="#2563eb", width=3),
                text=df1['ritmo_mmss'],
                hovertemplate="Lap %{x}<br>Ritmo: %{text}<extra></extra>"
            ))
        if not df2.empty:
            df2['ritmo_mmss'] = df2['ritmo_seg_km'].apply(segundos_a_min_km)
            fig.add_trace(go.Scatter(
                x=df2['lap_index'], y=df2['ritmo_seg_km'], name=f"{nom2} ({fec2})",
                line=dict(color="#dc2626", width=3, dash="dot"),
                text=df2['ritmo_mmss'],
                hovertemplate="Lap %{x}<br>Ritmo: %{text}<extra></extra>"
            ))
        
        all_ritmos = []
        if not df1.empty: all_ritmos.extend(df1['ritmo_seg_km'].dropna().tolist())
        if not df2.empty: all_ritmos.extend(df2['ritmo_seg_km'].dropna().tolist())
        
        if all_ritmos:
            min_seg, max_seg = min(all_ritmos), max(all_ritmos)
            margen = max((max_seg - min_seg) * 0.1, 10)
            rango_y = [max_seg + margen, min_seg - margen]
            
            if min_seg == max_seg:
                tick_vals = [min_seg]
            else:
                tick_vals = np.linspace(min_seg, max_seg, num=5)
            tick_texts = [segundos_a_min_km(val) for val in tick_vals]
        else:
            rango_y = None
            tick_vals, tick_texts = None, None

        fig.update_layout(
            title="Comparativa de Ritmo por Vuelta",
            template="plotly_white",
            height=380,
            legend=dict(title=dict(text="<b>Sesiones Comparadas</b>"), orientation="v", yanchor="top", y=1, xanchor="right", x=1)
        )
        fig.update_yaxes(
            title_text="<b>Ritmo (min/km)</b>",
            range=rango_y,
            autorange=False if rango_y else True,
            tickvals=tick_vals,
            ticktext=tick_texts
        )
    else:
        if not df1.empty:
            fig.add_trace(go.Scatter(x=df1['lap_index'], y=df1['fc_media'], name=f"{nom1} ({fec1})", line=dict(color="#2563eb", width=3)))
        if not df2.empty:
            fig.add_trace(go.Scatter(x=df2['lap_index'], y=df2['fc_media'], name=f"{nom2} ({fec2})", line=dict(color="#dc2626", width=3, dash="dot")))

        fig.update_layout(
            title="Comparativa de Frecuencia Cardíaca por Vuelta",
            template="plotly_white",
            height=380,
            legend=dict(title=dict(text="<b>Sesiones Comparadas</b>"), orientation="v", yanchor="top", y=1, xanchor="right", x=1)
        )
        fig.update_yaxes(title_text="<b>FC Media (ppm)</b>")

    return fig


# Callbacks de Navegación e Interacción del Calendario (Soporte para flechas y desplegables de mes/año)
@app.callback(
    [Output('store-cal-mes', 'data'), Output('store-cal-anho', 'data')],
    [
        Input('btn-prev-mes', 'n_clicks'), 
        Input('btn-next-mes', 'n_clicks'),
        Input('dropdown-cal-mes', 'value'),
        Input('dropdown-cal-anho', 'value')
    ],
    [State('store-cal-mes', 'data'), State('store-cal-anho', 'data')],
    prevent_initial_call=True
)
def cambiar_mes(n_prev, n_next, mes_sel, anho_sel, mes_actual, anho_actual):
    ctx = callback_context
    if not ctx.triggered: 
        return dash.no_update, dash.no_update
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id in ['btn-prev-mes', 'btn-next-mes']:
        trigger_value = ctx.triggered[0]['value']
        if trigger_value in [None, 0]:
            return dash.no_update, dash.no_update

    if not mes_actual: mes_actual = datetime.today().month
    if not anho_actual: anho_actual = datetime.today().year

    if trigger_id == 'btn-prev-mes':
        if mes_actual == 1:
            return 12, anho_actual - 1
        else:
            return mes_actual - 1, anho_actual
    elif trigger_id == 'btn-next-mes':
        if mes_actual == 12:
            return 1, anho_actual + 1
        else:
            return mes_actual + 1, anho_actual
    elif trigger_id == 'dropdown-cal-mes':
        if mes_sel is not None and mes_sel != mes_actual:
            return mes_sel, anho_actual
    elif trigger_id == 'dropdown-cal-anho':
        if anho_sel is not None and anho_sel != anho_actual:
            return mes_actual, anho_sel
            
    return dash.no_update, dash.no_update

@app.callback(
    Output('store-activa', 'data', allow_duplicate=True),
    Input({'type': 'act-btn-cal', 'index': dash.ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def seleccionar_actividad_calendario(n_clicks):
    ctx = callback_context
    if not ctx.triggered or ctx.triggered[0]['value'] in [None, 0]:
        return dash.no_update
    
    import json
    try:
        dict_id = json.loads(ctx.triggered[0]['prop_id'].split('.')[0])
        return dict_id['index']
    except:
        return dash.no_update

app.clientside_callback(
    """
    function(actividad_id) {
        if (actividad_id) {
            setTimeout(function() {
                const el = document.getElementById('resumen-sesion-anchor');
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }, 250);
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('dummy-scroll-div', 'children'),
    Input('store-activa', 'data'),
    prevent_initial_call=True
)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=8050)