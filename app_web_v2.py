import streamlit as st
import os
import pandas as pd
from datetime import datetime
import db_web_v2
import auth_manager_v2
from garmin_ingestor_v2 import GarminIngestor
from coros_ingestor_v2 import CorosIngestor
from fit_ingestor_v2 import FitIngestor
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_searchbox import st_searchbox


# 1. Configuración de página (ancho completo para dar protagonismo a los datos)
st.set_page_config(page_title="Athletics Analytics Web", layout="wide")

# 2. Inicialización de la BBDD (Solo una vez)
db_web_v2.inicializar_db_web()

# 3. Funciones auxiliares
# Función para sincronizar fisiología
def sincronizar_fisiologia_usuario(user_id):
    """Lógica para actualizar datos de Garmin tras loguearse."""
    try:
        ingestor = GarminIngestor(user_id)
        if ingestor.actualizar_datos_fisiologicos_garmin():
            st.success("✅ Perfil fisiológico sincronizado con Garmin.")
        else:
            st.warning("⚠️ No se pudieron obtener datos fisiológicos de Garmin.")
    except Exception as e:
        st.error(f"Error técnico sincronizando fisiología: {e}")


# Función para configurar estilo de KPIs
def obtener_configuracion_kpi(nombre, valor):
    """Lógica de semáforo personalizada"""
    if nombre == "TRIMP":
        if valor < 50: return "#d4edda", "green", "<b>Muy Ligero</b><br>Regenerativo, < 12h recup."
        elif valor < 100: return "#d4edda", "green", "<b>Moderado</b><br>Mantenimiento aeróbico, 12-24h"
        elif valor < 180: return "#fff3cd", "orange", "<b>Alto</b><br>Sesión de calidad, 24-48h"
        elif valor < 250: return "#f8d7da", "red", "<b>Muy Alto</b><br>Volumen extremo, 48-72h"
        else: return "#f8d7da", "red", "<b>Extremo</b><br>Agotamiento alto, +72h"
    
    elif nombre == "TRIMP_min":
        if valor < 1.4: return "#d4edda", "green", "<b>Zona 1 (Recup/Base)</b>"
        elif valor < 2.0: return "#fff3cd", "orange", "<b>Zona 2 (Umbral/Tempo)</b>"
        else: return "#f8d7da", "red", "<b>Zona 3 (Alta Int.)</b>"

    elif nombre == "ACWR":
        if valor < 1.3: return "#d4edda", "green", "<b>Seguro</b><br>Progresión óptima."
        elif valor < 1.5: return "#fff3cd", "orange", "<b>Riesgo</b><br>Fatiga creciendo rápido."
        else: return "#f8d7da", "red", "<b>Peligro</b><br>Alto riesgo lesión."

    elif nombre == "TSB":
        if 5 <= valor <= 25: return "#d4edda", "green", "<b>Objetivo</b><br>Ideal para competir."
        elif valor < -20: return "#f8d7da", "red", "<b>Agotado</b><br>Descarga urgente."
        else: return "#fff3cd", "orange", "<b>Fatiga</b><br>Entrenamiento estándar."
    
    return "#f0f2f6", "black", "Valor estándar"

# Diccionario con los significados detallados de cada KPI
DEFINICIONES_KPI = {
    "ATL": "<b>ATL (Fatiga):</b> Acute Training Load o Carga Aguda de Entrenamiento. Se define como el promedio ponderado de la carga de entrenamiento de los últimos 7 días. Refleja el grado actual de fatiga. <a href =https://www.trainingpeaks.com/coach-blog/una-guia-para-entrenadores-de-atl-ctl-y-tsb/>ATL</a>",
    "CTL": "<b>CTL (Forma):</b> Chronic Training Load o Carga Crónica de Entrenamiento. Se define como el promedio ponderado de la carga de entrenamiento de los últimos 42 días (6 semanas). Representa el nivel de forma física o resistencia acumulada. <a href =https://www.trainingpeaks.com/coach-blog/una-guia-para-entrenadores-de-atl-ctl-y-tsb/>CTL</a>",
    "TSB": "<b>TSB (Balance):</b> Training Stress Balance o Balance de Estrés del Entrenamiento. Se define como la diferencia entre la Carga Crónica (CTL) y la Carga Aguda (ATL) del día anterior. Representa el estado de frescura o fatiga acumulada actual. <a href =https://www.trainingpeaks.com/coach-blog/una-guia-para-entrenadores-de-atl-ctl-y-tsb/>TSB</a>",
    "ACWR": "<b>ACWR (Ratio de Carga):</b> Acute Chronic Workload Ratio o Ratio de Carga de Trabajo Aguda Crónica. Compara la carga de entrenamiento a corto plazo con la carga a largo plazo para evaluar el riesgo de lesiones y optimizar el rendimiento. <a href =https://www.bycoachmanu.com/post/ratio-acwr-carga-aguda---carga-cr%C3%B3nica-en-el-entrenamiento-deportivo>ACWR</a>",
    "TRIMP": "<b>TRIMP (Impulso):</b> Training Impulse o Impulso de Entrenamiento. Carga interna de la sesión basada en el volumen y la frecuencia cardíaca. <a href =https://www.iamcoach.ai/blog/trimp-training-load-explained>TRIMP</a> ",
    "TRIMP/m": "<b>TRIMP/min:</b> Intensidad media de esfuerzo por minuto de entrenamiento.",
    "TRIMP/km": "<b>TRIMP/km:</b> Carga de esfuerzo acumulada por cada kilómetro recorrido.",
    "Dist": "<b>Distancia:</b> Kilómetros totales completados en la sesión.",
    "Tiempo": "<b>Tiempo:</b> Duración total de la actividad.",
    "FC media": "<b>FC Media:</b> Promedio de pulsaciones por minuto durante el entrenamiento.",
    "DES":"<b>Deriva cardiaca:</b> La deriva cardíaca (Pa:HR) —conocida en inglés como Aerobic Decoupling— es una métrica que mide la estabilidad de tu sistema cardiovascular durante un entrenamiento de resistencia a intensidad constante. Fisiológicamente, evalúa la deriva cardíaca (cardiovascular drift). Cuando corres a un ritmo fijo, el pulso tiende a subir con el paso de los minutos debido a la fatiga muscular, la deshidratación y el aumento de la temperatura corporal. El desacople mide exactamente en qué porcentaje se pierde esa eficiencia a lo largo de la sesión.<a href =https://docs.goodcoach.app/es/advanced-usage/cardiac-drift/>Deriva</a>",
    "DER":"<b>Diferencia de frecuencias:</b> Mide la diferencia de frecuencias cardíacas, en % entre la frecuencia cardíaca media de la segunda mitad y la de la primera.",
    "FCI":"<b>FC media inicial:</b> Este indicador es la frecuencia cardíaca media de la primera mitad de la sesión.",
    "FCF":"<b>FC media final:</b> Este indicador es la frecuencia cardíaca media de la segunda mitad de la sesión.",
    "Ritmo": "<b>Ritmo:</b> Velocidad media expresada en minutos por kilómetro (min/km)."
}

# Función para pintar KPIs
def pintar_kpi(col, etiqueta, valor, nombre_metrica):
    try:
        val_float = float(valor)
    except:
        val_float = 0.0
        
    fondo, color, tooltip = obtener_configuracion_kpi(nombre_metrica, val_float)
    if isinstance(valor, str):
        texto_valor = valor
    else:
        texto_valor = f"{val_float:.2f}"

    significado = DEFINICIONES_KPI.get(nombre_metrica, f"Información detallada sobre {etiqueta}.")

    with col:
        st.markdown(f"""
            <style>
              .info-container {{
                position: absolute;
                top: 6px;
                right: 6px;
                cursor: help;
              }}
              .info-tooltip {{
                visibility: hidden;
                position: absolute;
                right: 0;
                top: 20px;
                background: white;
                color: #333;
                padding: 8px;
                border-radius: 6px;
                border: 1px solid #ccc;
                width: 180px;
                text-align: left;
                font-size: 0.7em;
                z-index: 99;
                box-shadow: 0px 4px 8px rgba(0,0,0,0.15);
              }}
              .info-container:hover .info-tooltip {{
                visibility: visible;
              }}
            </style>
            
            <div style="background-color: {fondo}; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid #ddd; position: relative;">
                <div class="info-container">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="16" x2="12" y2="12"></line>
                        <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                    <div class="info-tooltip">
                        {significado}
                    </div>
                </div>
                <p style="margin: 0; color: #444; font-size: 0.75em; font-weight: bold;">{etiqueta}</p>
                <h4 style="margin: 3px 0 0 0; color: {color};">{texto_valor}</h4>
            </div>
        """, unsafe_allow_html=True)
        
        if tooltip != "Valor estándar":
            tooltip_limpio = tooltip.replace("<b>", "").replace("</b>", "").replace("<br>", " - ")
            st.caption(f"ℹ️ {tooltip_limpio}")


def segundos_a_min_km(segundos):
    """Convierte segundos totales por km a formato 'M:SS'"""
    try:
        segundos = float(segundos)
        if segundos <= 0:
            return "0:00"
        minutos = int(segundos // 60)
        restantes = int(segundos % 60)
        return f"{minutos}:{restantes:02d}"
    except:
        return "0:00"

def filtrar_sesiones(searchterm: str) -> list:
    """Función de filtrado optimizada para st_searchbox usando session_state."""
    df = st.session_state.get('df_actividades')
    
    if df is None or df.empty:
        return []
    
    if 'nombre' not in df.columns or 'fecha' not in df.columns:
        return []
    
    display_text = df['nombre'].astype(str) + " (" + df['fecha'].astype(str) + ")"
    
    if searchterm:
        resultados = display_text[display_text.str.contains(searchterm, case=False, na=False)].tolist()
    else:
        resultados = display_text.head(20).tolist()
        
    return resultados

# 4. Control de sesión y flujo principal
if 'user_id' not in st.session_state:
    st.title("🔐 Acceso al sistema")
    tab_login, tab_registro = st.tabs(["Iniciar Sesión", "Registrarse"])
    
    with tab_login:
        email = st.text_input("Email", key="login_email")
        pwd = st.text_input("Contraseña", type="password", key="login_pwd")
        if st.button("Entrar"):
            user_id = auth_manager_v2.verificar_login(email, pwd)
            if user_id:
                st.session_state.user_id = user_id
                sincronizar_fisiologia_usuario(user_id)
                st.rerun() 
            else:
                st.error("Email o contraseña incorrectos.")
                
    with tab_registro:
        email_reg = st.text_input("Email", key="reg_email")
        nombre_reg = st.text_input("Nombre", key="reg_nombre")
        sexo_reg = st.selectbox("Sexo", ["Masculino", "Femenino", "Prefiero no decirlo"])
        pwd_reg = st.text_input("Contraseña", type="password", key="reg_pwd")
        
        if st.button("Crear cuenta"):
            if auth_manager_v2.registrar_usuario(email_reg, nombre_reg, pwd_reg, sexo_reg):
                st.success("¡Cuenta creada! Ya puedes iniciar sesión.")
            else:
                st.error("Error: El email ya está registrado.")

    st.stop()

else:
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/running--v1.png", width=50)
        st.title("Athletics Analytics")
        st.markdown(f"Conectado (ID: **{st.session_state.user_id}**)")
        st.markdown("---")
        
        menu_seleccionado = st.radio(
            "Menú de Navegación",
            ["🏃‍♂️ Sesión Individual", "📈 Evolución de Temporada", "⚖️ Comparativa", "⚙️ Configuración & Sync"],
            index=0
        )
        
        st.markdown("---")
        if st.button("Cerrar Sesión", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # --- LÓGICA DE LAS VISTAS SEGÚN EL MENÚ LATERAL ---

    if menu_seleccionado == "🏃‍♂️ Sesión Individual":
        st.title("Laboratorio de Análisis de Sesiones")

        conn = db_web_v2.conectar_db()
        query_acts = """
            SELECT a.actividad_id, a.fecha, a.tipo, a.nombre, a.distancia_km, h.minutos 
            FROM actividades a
            LEFT JOIN historial_entrenamientos h ON a.actividad_id = h.actividad_id AND a.user_id = h.user_id
            WHERE a.user_id = %s 
            ORDER BY a.fecha DESC
        """
        df_actividades = pd.read_sql_query(query_acts, conn, params=(st.session_state.user_id,))
        conn.close()

        st.session_state['df_actividades'] = df_actividades

        if df_actividades.empty:
            st.info("ℹ️ No hay actividades sincronizadas todavía. Ve a la sección 'Configuración & Sync' para sincronizar tu dispositivo.")
        else:
            df_actividades['nombre_sesion'] = df_actividades['nombre'].fillna(df_actividades['tipo']).fillna("Entrenamiento")
            df_actividades['etiqueta_busqueda'] = df_actividades['fecha'] + " | " + df_actividades['nombre_sesion'] + " (" + df_actividades['distancia_km'].astype(str) + " km)"
                
            st.markdown("🔍 **Búsqueda rápida por texto:**")
            col_busq1, col_busq2 = st.columns([4, 1])
            with col_busq1:
                sesion_buscada = st.selectbox(
                    "Selecciona o escribe para buscar una sesión anterior:",
                    options=["-- Selecciona una sesión --"] + df_actividades['etiqueta_busqueda'].tolist(),
                    label_visibility="collapsed"
                )
            with col_busq2:
                btn_visualizar = st.button("Visualizar sesión", use_container_width=True)
                    
                if btn_visualizar and sesion_buscada != "-- Selecciona una sesión --":
                    fila_sel = df_actividades[df_actividades['etiqueta_busqueda'] == sesion_buscada]
                    if not fila_sel.empty:
                        st.session_state.actividad_activa = int(fila_sel.iloc[0]['actividad_id'])
                        st.rerun()

            st.markdown("---")
                
            import calendar
            from datetime import datetime

            st.subheader("📅 Calendario Mensual de Entrenamientos")

            anos_disponibles = list(range(2024, 2031))
            meses_nombres = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

            if 'cal_anho' not in st.session_state:
                st.session_state.cal_anho = 2026
            if 'cal_mes' not in st.session_state:
                st.session_state.cal_mes = datetime.today().month
            if 'cal_mes_nombre' not in st.session_state:
                st.session_state.cal_mes_nombre = meses_nombres[st.session_state.cal_mes - 1]

            col_btn1, col_btn2, _ = st.columns([0.4, 0.4, 4.2])

            with col_btn1:
                if st.button("◀", help="Mes anterior", use_container_width=True, key="btn_prev_mes"):
                    if st.session_state.cal_mes == 1:
                        st.session_state.cal_mes = 12
                        st.session_state.cal_anho -= 1
                    else:
                        st.session_state.cal_mes -= 1
                    st.session_state.cal_mes_nombre = meses_nombres[st.session_state.cal_mes - 1]
                    st.rerun()

            with col_btn2:
                if st.button("▶", help="Mes siguiente", use_container_width=True, key="btn_next_mes"):
                    if st.session_state.cal_mes == 12:
                        st.session_state.cal_mes = 1
                        st.session_state.cal_anho += 1
                    else:
                        st.session_state.cal_mes += 1
                    st.session_state.cal_mes_nombre = meses_nombres[st.session_state.cal_mes - 1]
                    st.rerun()

            col_m1, col_m2, _ = st.columns([1, 1.5, 3])

            with col_m1:
                if st.session_state.cal_anho not in anos_disponibles:
                    st.session_state.cal_anho = 2026
                
                anho_seleccionado = st.selectbox(
                    "Año", 
                    anos_disponibles, 
                    index=anos_disponibles.index(st.session_state.cal_anho),
                    key="cal_anho"
                )

            with col_m2:
                mes_nombre_sel = st.selectbox(
                    "Mes", 
                    meses_nombres, 
                    index=meses_nombres.index(st.session_state.cal_mes_nombre),
                    key="cal_mes_nombre"
                )
                st.session_state.cal_mes = meses_nombres.index(mes_nombre_sel) + 1

            mes_seleccionado = st.session_state.cal_mes
            mes_nombre = meses_nombres[mes_seleccionado - 1]

            cal = calendar.Calendar(firstweekday=0)
            matriz_mes = cal.monthdayscalendar(anho_seleccionado, mes_seleccionado)
            
            st.markdown(f"### {mes_nombre} {anho_seleccionado}")

            if "actividad_activa" not in st.session_state:
                st.session_state.actividad_activa = None    

            dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            cols_cabecera = st.columns(7)
            for i, d_sem in enumerate(dias_semana):
                cols_cabecera[i].markdown(f"<div style='text-align: center; font-weight: bold; background-color: #f0f2f6; padding: 5px; border-radius: 4px;'>{d_sem}</div>", unsafe_allow_html=True)

            st.markdown("""
                <style>
                div[data-testid="stVerticalBlock"] button {
                    font-size: 10px !important;
                    padding: 2px 4px !important;
                    min-height: 24px !important;
                    white-space: nowrap !important;
                    overflow: hidden !important;
                    text-overflow: ellipsis !important;
                }
                </style>
            """, unsafe_allow_html=True)

            df_actividades['dt_fecha'] = pd.to_datetime(df_actividades['fecha'])
                
            for semana in matriz_mes:
                cols_semana = st.columns(7)
                for i, dia in enumerate(semana):
                    with cols_semana[i]:
                        if dia == 0:
                            st.markdown("<div style='color: #ccc; text-align: center; padding: 10px;'>-</div>", unsafe_allow_html=True)
                        else:
                            fecha_celda = datetime(anho_seleccionado, mes_seleccionado, dia).date()
                            acts_dia = df_actividades[df_actividades['dt_fecha'].dt.date == fecha_celda]
                            
                            with st.container(border=True):
                                st.markdown(f"**{dia}**")
                                
                                if not acts_dia.empty:
                                    for _, act in acts_dia.iterrows():
                                        nombre_corto = str(act['nombre_sesion'])[:8]
                                        label_btn = f"{nombre_corto} ({act['distancia_km']}k)"
                                        
                                        if st.button(label_btn, key=f"btn_sesion_{act['actividad_id']}", use_container_width=True):
                                            st.session_state.actividad_activa = int(act['actividad_id'])
                                            st.rerun()

            st.markdown("---")
            st.subheader("📋 Resumen de la Sesión")
            
            id_seleccionado = st.session_state.get("actividad_activa", None)
            user_id = int(st.session_state.get('user_id', 1))

            if id_seleccionado:
                conn = db_web_v2.conectar_db()
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT actividad_id, nombre, fecha, tipo, distancia_km 
                    FROM actividades 
                    WHERE user_id = %s and actividad_id = %s
                """, (user_id, id_seleccionado))
                cabecera = cursor.fetchone()

                if cabecera:
                    actividad_id_real = cabecera[0]
                    nombre_act, fecha_act, tipo_act, dist_km = cabecera[1], cabecera[2], cabecera[3], cabecera[4]
                    
                    cursor.execute("SELECT trimp, minutos FROM historial_entrenamientos WHERE user_id = %s AND actividad_id = %s", (user_id, actividad_id_real,))
                    metricas_carga = cursor.fetchone()
                    
                    cursor.execute("SELECT porcentaje_deriva, fc_inicial, fc_final FROM historial_derivas WHERE user_id = %s AND actividad_id = %s", (user_id, actividad_id_real,))
                    datos_deriva = cursor.fetchone()
                    
                    df_vueltas = pd.DataFrame()
                    try:
                        df_vueltas = pd.read_sql_query("""
                            SELECT lap_index, ritmo_seg_km, fc_media 
                            FROM detalle_vueltas 
                            WHERE user_id = %s AND actividad_id = %s 
                            ORDER BY lap_index ASC
                        """, conn, params=(user_id, actividad_id_real,))
                    except Exception:
                        pass
                        
                conn.close()
                
                if cabecera:
                    dist_val = dist_km if dist_km is not None else 0.0
                    trimp_val = metricas_carga[0] if (metricas_carga and metricas_carga[0] is not None) else 0.0
                    minutos_val = metricas_carga[1] if (metricas_carga and metricas_carga[1] is not None) else 0.0
                    
                    import core_metrics
                    df_banister = core_metrics.procesar_curvas_acumuladas(st.session_state.user_id)
                    
                    atl_val, ctl_val, tsb_val, acwr_val = 0.0, 0.0, 0.0, 0.0
                    if not df_banister.empty and fecha_act:
                        try:
                            fecha_dt = pd.to_datetime(fecha_act).normalize()
                            if fecha_dt in df_banister.index:
                                row_b = df_banister.loc[fecha_dt]
                                atl_val = row_b['ATL_Fatiga']
                                ctl_val = row_b['CTL_Forma']
                                tsb_val = row_b['TSB_Frescura']
                                acwr_val = row_b['ACWR']
                            else:
                                df_prev = df_banister[df_banister.index <= fecha_dt]
                                if not df_prev.empty:
                                    row_b = df_prev.iloc[-1]
                                    atl_val = row_b['ATL_Fatiga']
                                    ctl_val = row_b['CTL_Forma']
                                    tsb_val = row_b['TSB_Frescura']
                                    acwr_val = row_b['ACWR']
                        except Exception:
                            pass

                    trimp_min_val = trimp_val / minutos_val if minutos_val > 0 else 0.0
                    trimp_km_val = trimp_val / dist_val if dist_val > 0 else 0.0
                    fc_media_val = df_vueltas['fc_media'].mean() if not df_vueltas.empty else 0.0
                    ritmo = minutos_val * 60 / dist_val
                    ritmo_val = segundos_a_min_km(ritmo)

                    cols_kpis = st.columns(11)

                    with cols_kpis[0]:
                        pintar_kpi(cols_kpis[0], "ATL", atl_val, "ATL")
                    with cols_kpis[1]:
                        pintar_kpi(cols_kpis[1], "CTL", ctl_val, "CTL")
                    with cols_kpis[2]:
                        pintar_kpi(cols_kpis[2], "TSB", tsb_val, "TSB")
                    with cols_kpis[3]:
                        pintar_kpi(cols_kpis[3], "ACWR", acwr_val, "ACWR")
                    with cols_kpis[4]:
                        pintar_kpi(cols_kpis[4], "TRIMP", trimp_val, "TRIMP")
                    with cols_kpis[5]:
                        pintar_kpi(cols_kpis[5], "TRIMP/m", trimp_min_val, "TRIMP/m")
                    with cols_kpis[6]:
                        pintar_kpi(cols_kpis[6], "TRIMP/km", trimp_km_val, "TRIMP/km")
                    with cols_kpis[7]:
                        pintar_kpi(cols_kpis[7], "Dist (km)", dist_val, "Dist")
                    with cols_kpis[8]:
                        pintar_kpi(cols_kpis[8], "Tiempo", minutos_val, "Tiempo")
                    with cols_kpis[9]:
                        pintar_kpi(cols_kpis[9], "FC media", fc_media_val, "FC media")
                    with cols_kpis[10]:
                        pintar_kpi(cols_kpis[10], "Ritmo", ritmo_val, "Ritmo")

                    desacople = datos_deriva[0] if (datos_deriva and datos_deriva[0] is not None) else 0.0
                    fc_inicial = float(datos_deriva[1]) if (datos_deriva and len(datos_deriva) > 1 and datos_deriva[1] is not None) else 0.0
                    fc_final = float(datos_deriva[2]) if (datos_deriva and len(datos_deriva) > 2 and datos_deriva[2] is not None) else 0.0
                    porcentaje_deriva = ((fc_final - fc_inicial)/fc_final) * 100 if fc_final > 0 else 0.0
                    fc_inicial_str = round(fc_inicial, 1) if fc_inicial > 0 else "N/D"
                    fc_final_str = round(fc_final, 1) if fc_final > 0 else "N/D"
                    tipo_sesion = nombre_act or tipo_act or "Rodaje"

                    cols_kpis = st.columns(5)

                    with cols_kpis[0]:
                        pintar_kpi(cols_kpis[0], "Deriva cardíaca", desacople, "DES") 
                    with cols_kpis[1]:
                        pintar_kpi(cols_kpis[1], "Diferencia de frecuencias", porcentaje_deriva, "DER")
                    with cols_kpis[2]:
                        pintar_kpi(cols_kpis[2], "FC inicial", fc_inicial_str, "FCI")
                    with cols_kpis[3]:
                        pintar_kpi(cols_kpis[3], "FC final", fc_final_str, "FCF")
                    with cols_kpis[4]:
                        pintar_kpi(cols_kpis[4], "Sesión", tipo_sesion, "SES")
                    
                    if desacople < 5:
                        st.markdown("​🟢 **El ritmo está consolidado y tu base aeróbica sostiene el esfuerzo sin fatiga cardiovascular sobreañadida.**")
                    elif desacople > 8:
                        st.markdown("🔴​ **El sistema se desacopla de forma acusada; indica que el ritmo o el volumen exigen un trabajo de base aeróbica superior.**")
                    else:
                        st.markdown("🟡​ **Estás rozando el umbral; el cuerpo comienza a encarecer el coste energético en la segunda mitad.**")

                    st.markdown("---")
                    st.markdown("📈 **Evolución de la sesión**")

                    if not df_vueltas.empty:
                        import numpy as np

                        df_vueltas['ritmo_mmss'] = df_vueltas['ritmo_seg_km'].apply(segundos_a_min_km)

                        fig = make_subplots(specs=[[{"secondary_y": True}]])
                        
                        fig.add_trace(
                            go.Scatter(
                                x=df_vueltas['lap_index'], 
                                y=df_vueltas['fc_media'], 
                                name="FC Media (ppm)", 
                                line=dict(color="#b71c1c", width=3)
                            ),
                            secondary_y=False
                        )

                        fig.add_trace(
                            go.Scatter(
                                x=df_vueltas['lap_index'], 
                                y=df_vueltas['ritmo_seg_km'], 
                                name="Ritmo (min/km)", 
                                line=dict(color="#2962ff", width=2),
                                text=df_vueltas['ritmo_mmss'],
                                hovertemplate="Lap %{x}<br>Ritmo: %{text}<extra></extra>"
                            ),
                            secondary_y=True
                        )

                        shapes_list = []
                        annotations_list = []

                        if fc_inicial > 0:
                            shapes_list.append(dict(
                                type="line",
                                xref="paper", x0=0, x1=1,
                                yref="y", y0=fc_inicial, y1=fc_inicial,
                                line=dict(color="green", width=2, dash="dash")
                            ))
                            annotations_list.append(dict(
                                xref="paper", x=0.02,
                                yref="y", y=fc_inicial,
                                text=f"FC 1.ª Mitad ({fc_inicial})",
                                showarrow=False,
                                xanchor="left",
                                yanchor="bottom",
                                font=dict(color="green", size=11)
                            ))

                        if fc_final > 0:
                            shapes_list.append(dict(
                                type="line",
                                xref="paper", x0=0, x1=1,
                                yref="y", y0=fc_final, y1=fc_final,
                                line=dict(color="orange", width=2, dash="dash")
                            ))
                            annotations_list.append(dict(
                                xref="paper", x=0.02,
                                yref="y", y=fc_final,
                                text=f"FC 2.ª Mitad ({fc_final})",
                                showarrow=False,
                                xanchor="left",
                                yanchor="bottom",
                                font=dict(color="orange", size=11)
                            ))

                        fig.update_layout(
                            shapes=fig.layout.shapes + tuple(shapes_list) if fig.layout.shapes else shapes_list,
                            annotations=fig.layout.annotations + tuple(annotations_list) if fig.layout.annotations else annotations_list
                        )

                        min_seg = df_vueltas['ritmo_seg_km'].min()
                        max_seg = df_vueltas['ritmo_seg_km'].max()

                        amplitud_minima = 40
                        amplitud_real = max_seg - min_seg
                        centro_ritmo = (min_seg + max_seg) / 2

                        if amplitud_real < amplitud_minima:
                            diferencia = amplitud_minima / 2
                            rango_y2 = [centro_ritmo + diferencia, centro_ritmo - diferencia]
                        else:
                            margen = amplitud_real * 0.1
                            rango_y2 = [max_seg + margen, min_seg - margen]

                        if min_seg == max_seg:
                            tick_vals = [min_seg]
                        else:
                            tick_vals = np.linspace(min_seg, max_seg, num=5)

                        tick_texts = [segundos_a_min_km(val) for val in tick_vals]

                        fig.update_layout(
                            height=400,
                            margin=dict(l=20, r=20, t=20, b=20),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                        )

                        fig.update_yaxes(title_text="<b>FC Media (ppm)</b>", secondary_y=False)
                        fig.update_yaxes(
                            title_text="<b>Ritmo (min/km)</b>", 
                            range=rango_y2,
                            autorange=False,
                            tickvals=tick_vals,
                            ticktext=tick_texts,
                            secondary_y=True
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("ℹ️ No hay registros de vueltas detalladas en 'detalle_vueltas' para esta sesión.")
                else:
                    st.warning("⚠️ No se ha encontrado la actividad en la base de datos.")
            else:
                st.warning("👆 Selecciona una sesión desde el buscador superior o haz clic directamente en cualquier entrenamiento dentro del calendario mensual.")

    elif menu_seleccionado == "📈 Evolución de Temporada":

        st.subheader("Tendencia de Carga y Forma Física")
    
        import core_metrics
        df_plot = core_metrics.procesar_curvas_acumuladas(st.session_state.user_id)
        if not df_plot.empty:
            df_plot.index = pd.to_datetime(df_plot.index).date 

            fecha_max = df_plot.index.max()
            fecha_min_default = fecha_max - pd.Timedelta(days=365)

            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.12,
                specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
                row_heights=[0.65, 0.35]
            )

            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot['CTL_Forma'], 
                name='Forma (CTL)', line=dict(color='green', width=3)
            ), row=1, col=1, secondary_y=False)
            
            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot['ATL_Fatiga'], 
                name='Fatiga (ATL)', line=dict(color='red', width=2, dash='dot')
            ), row=1, col=1, secondary_y=False)

            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot['TSB_Frescura'], 
                name='Balance (TSB)', line=dict(color='blue', width=2)
            ), row=1, col=1, secondary_y=True)

            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot['TSB_Frescura'].clip(lower=0), 
                line=dict(width=0), fill='tozeroy', 
                fillcolor='rgba(0,255,0,0.15)', showlegend=False
            ), row=1, col=1, secondary_y=True)

            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot['TSB_Frescura'].clip(upper=0), 
                line=dict(width=0), fill='tozeroy', 
                fillcolor='rgba(255,0,0,0.15)', showlegend=False
            ), row=1, col=1, secondary_y=True)

            fig.add_trace(go.Scatter(
                x=df_plot.index, y=df_plot['ACWR'], 
                name='ACWR', line=dict(color='purple', width=2), showlegend=False
            ), row=2, col=1)
            
            fig.add_hrect(
                y0=0.8, y1=1.3, fillcolor="green", opacity=0.12, 
                line_width=0, annotation_text="Zona Óptima", annotation_position="top left",
                row=2, col=1
            )
            
            fig.add_hline(
                y=1.5, line_dash="dash", line_color="red", 
                annotation_text="Peligro Sobrecarga", annotation_position="top left",
                row=2, col=1
            )

            fig.update_layout(
                title="Evolución de Carga, Fatiga, Balance y Ratio ACWR",
                template="plotly_white",
                hovermode="x unified",
                height=750,
                margin=dict(l=20, r=20, t=40, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis2=dict(
                    range=[fecha_min_default, fecha_max],
                    rangeselector=dict(
                        buttons=list([
                            dict(count=3, label="3m", step="month", stepmode="backward"),
                            dict(count=6, label="6m", step="month", stepmode="backward"),
                            dict(count=1, label="1y", step="year", stepmode="backward"),
                            dict(step="all", label="Todo")
                        ])
                    ),
                    rangeslider=dict(visible=True, thickness=0.06),
                    type="date"
                )
            )

            fig.update_yaxes(title_text="<b>Carga / Fatiga (CTL/ATL)</b>", row=1, col=1, secondary_y=False)
            fig.update_yaxes(title_text="<b>Balance (TSB)</b>", row=1, col=1, secondary_y=True)
            fig.update_yaxes(title_text="<b>ACWR</b>", row=2, col=1, range=[0.4, 2.1])

            st.plotly_chart(fig, use_container_width=True)

            st.write("### Estado Actual")
            ultima_fila = df_plot.iloc[-1]
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Forma Actual (CTL)", f"{ultima_fila['CTL_Forma']:.2f}")
            col_b.metric("Fatiga Actual (ATL)", f"{ultima_fila['ATL_Fatiga']:.2f}")
            col_c.metric("Balance (TSB)", f"{ultima_fila['TSB_Frescura']:.2f}")
            col_d.metric("Ratio Carga (ACWR)", f"{ultima_fila['ACWR']:.2f}")
            
        else:
            st.info("No hay datos de entrenamiento suficientes para calcular las curvas.")
       
    elif menu_seleccionado == "⚖️ Comparativa":
        st.subheader("⚖️ Comparativa de Sesiones")
    
        col_a, col_b = st.columns(2)
        with col_a:
            sesion1 = st_searchbox(filtrar_sesiones, label="Sesión 1 (Base):", key="s1_tab3")
        with col_b:
            sesion2 = st_searchbox(filtrar_sesiones, label="Sesión 2 (Comparar):", key="s2_tab3")
        
        if st.button("Comparar sesiones"):
            if sesion1 and sesion2:
                df_actividades = st.session_state.get('df_actividades')
                
                if df_actividades is not None and not df_actividades.empty:
                    display_text = df_actividades['nombre'].astype(str) + " (" + df_actividades['fecha'].astype(str) + ")"
                    
                    fila1 = df_actividades.loc[display_text == sesion1]
                    fila2 = df_actividades.loc[display_text == sesion2]
                    
                    def cargar_datos_completos(fila_actividad):
                        if fila_actividad.empty:
                            return {'detalles': pd.DataFrame(), 'deriva': pd.DataFrame(), 'metricas': pd.DataFrame(), 'debug': "Fila vacía"}
                        
                        conn = db_web_v2.conectar_db()
                        current_user = st.session_state.get('user_id')
                        
                        posibles_ids = []
                        for col in ['actividad_id', 'id', 'id_garmin']:
                            if col in fila_actividad.columns:
                                val = fila_actividad[col].values[0]
                                if pd.notna(val):
                                    posibles_ids.append(int(val))
                        
                        df_detalles, df_deriva, df_metricas = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
                        aid = posibles_ids[0] if posibles_ids else None
                        debug_log = f"Buscando con User: {current_user}, ID seleccionado: {aid}\n"

                        if aid is not None:
                            try:
                                if current_user is not None:
                                    q = "SELECT lap_index, ritmo_seg_km, fc_media, fc_maxima FROM detalle_vueltas WHERE user_id = %s AND actividad_id = %s ORDER BY lap_index ASC"
                                    df_detalles = pd.read_sql_query(q, conn, params=(current_user, aid))
                                else:
                                    q = "SELECT lap_index, ritmo_seg_km, fc_media, fc_maxima FROM detalle_vueltas WHERE actividad_id = %s ORDER BY lap_index ASC"
                                    df_detalles = pd.read_sql_query(q, conn, params=(aid,))
                                debug_log += f"-> Vueltas encontradas: {len(df_detalles)} filas.\n"
                            except Exception as e:
                                debug_log += f"Error en vueltas: {e}\n"

                            try:
                                if current_user is not None:
                                    q = "SELECT porcentaje_deriva, fc_inicial, fc_final FROM historial_derivas WHERE user_id = %s AND actividad_id = %s"
                                    df_deriva = pd.read_sql_query(q, conn, params=(current_user, aid))
                                else:
                                    q = "SELECT porcentaje_deriva, fc_inicial, fc_final FROM historial_derivas WHERE actividad_id = %s"
                                    df_deriva = pd.read_sql_query(q, conn, params=(aid,))
                                debug_log += f"-> Derivas encontradas: {len(df_deriva)} filas.\n"
                            except Exception as e:
                                debug_log += f"Error en derivas: {e}\n"

                            try:
                                if current_user is not None:
                                    q = "SELECT trimp, minutos, trimp_min, trimp_km, km FROM historial_entrenamientos WHERE user_id = %s AND actividad_id = %s"
                                    df_metricas = pd.read_sql_query(q, conn, params=(current_user, aid))
                                else:
                                    q = "SELECT trimp, minutos, trimp_min, trimp_km, km FROM historial_entrenamientos WHERE actividad_id = %s"
                                    df_metricas = pd.read_sql_query(q, conn, params=(aid,))
                                debug_log += f"-> Métricas encontradas: {len(df_metricas)} filas.\n"
                            except Exception as e:
                                debug_log += f"Error en métricas: {e}\n"

                        conn.close()
                        return {
                            'detalles': df_detalles,
                            'deriva': df_deriva,
                            'metricas': df_metricas,
                            'debug': debug_log
                        }

                    s1_data = cargar_datos_completos(fila1)
                    s2_data = cargar_datos_completos(fila2)
                    
                    st.session_state['s1_data_comp'] = s1_data
                    st.session_state['s2_data_comp'] = s2_data
                    st.session_state['sesion1_nombre'] = sesion1
                    st.session_state['sesion2_nombre'] = sesion2
                else:
                    st.error("No se encontró el registro de actividades en la sesión.")

        if 's1_data_comp' in st.session_state and 's2_data_comp' in st.session_state:
            s1_data = st.session_state['s1_data_comp']
            s2_data = st.session_state['s2_data_comp']
            sesion1 = st.session_state.get('sesion1_nombre', 'Sesión 1')
            sesion2 = st.session_state.get('sesion2_nombre', 'Sesión 2')

            def obtener_valor_seguro(df, columna, defecto=0.0):
                if df is None or df.empty:
                    return defecto
                cols_lower = {c.lower(): c for c in df.columns}
                col_buscada = columna.lower()
                if col_buscada in cols_lower:
                    val = df.iloc[0][cols_lower[col_buscada]]
                    return float(val) if pd.notna(val) else defecto
                return defecto

            met1 = s1_data['metricas']
            m1_trimp = obtener_valor_seguro(met1, 'trimp_min')
            m1_trkm = obtener_valor_seguro(met1, 'trimp_km')

            met2 = s2_data['metricas']
            m2_trimp = obtener_valor_seguro(met2, 'trimp_min')
            m2_trkm = obtener_valor_seguro(met2, 'trimp_km')

            der1 = s1_data['deriva']
            d1_val = obtener_valor_seguro(der1, 'porcentaje_deriva')

            der2 = s2_data['deriva']
            d2_val = obtener_valor_seguro(der2, 'porcentaje_deriva')

            def escribir_valor(col, valor, delta=None):
                color = "green" if delta and float(delta) < 0 else "red" if delta and float(delta) > 0 else "gray"
                delta_str = f" <span style='color:{color}; font-size: 0.8em;'>({delta})</span>" if delta else ""
                col.markdown(f"##### {valor}{delta_str}", unsafe_allow_html=True)

            cols = st.columns([1.5, 2, 2])
            cols[0].write("**Deriva (%)**")
            escribir_valor(cols[1], f"{d1_val:.1f}%")
            escribir_valor(cols[2], f"{d2_val:.1f}%", delta=f"{d2_val - d1_val:.1f}")

            cols[0].write("**TRIMP/min**")
            escribir_valor(cols[1], f"{m1_trimp:.2f}")
            escribir_valor(cols[2], f"{m2_trimp:.2f}", delta=f"{m2_trimp - m1_trimp:.2f}")

            cols[0].write("**TRIMP/km**")
            escribir_valor(cols[1], f"{m1_trkm:.2f}")
            escribir_valor(cols[2], f"{m2_trkm:.2f}", delta=f"{m2_trkm - m1_trkm:.2f}")

            fig = go.Figure()
            if not s1_data['detalles'].empty:
                fig.add_trace(go.Scatter(
                    x=s1_data['detalles']['lap_index'], y=s1_data['detalles']['fc_media'], 
                    name=f"Sesión 1: {sesion1[:40]}", line=dict(color='royalblue', width=2)
                ))
            if not s2_data['detalles'].empty:
                fig.add_trace(go.Scatter(
                    x=s2_data['detalles']['lap_index'], y=s2_data['detalles']['fc_media'], 
                    name=f"Sesión 2: {sesion2[:40]}", line=dict(color='firebrick', width=2, dash='dot')
                ))
            
            fig.update_layout(title="Comparativa FC Media por Vuelta", template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)

            st.write("---")
            st.subheader("🎯 Eficiencia Aeróbica: Comparativa")
            
            col_graf1, col_graf2 = st.columns(2)

            def pintar_scatter_eficiencia(col, data, nombre_sesion):
                if 'detalles' not in data or data['detalles'] is None or data['detalles'].empty:
                    col.warning("No hay datos disponibles para esta sesión.")
                    return
                
                df = data['detalles'].dropna(subset=['ritmo_seg_km', 'fc_media']).sort_values('lap_index')
                if df.empty:
                    col.warning("Datos insuficientes de ritmo o frecuencia cardíaca.")
                    return

                import plotly.express as px
                fig_eff = px.scatter(
                    df, x='ritmo_seg_km', y='fc_media',
                    color='lap_index', color_continuous_scale='Viridis',
                    trendline="ols", title=f"Eficiencia: {nombre_sesion[:35]}"
                )
                
                fig_eff.update_xaxes(
                    showgrid=True, gridcolor='lightgray', gridwidth=0.5, autorange="reversed"
                )
                
                min_val = int(df['ritmo_seg_km'].min())
                max_val = int(df['ritmo_seg_km'].max())
                ticks = list(range((min_val // 20) * 20, (max_val // 20 + 2) * 20, 20))
                
                fig_eff.update_xaxes(
                    title="Ritmo (min/km)",
                    tickvals=ticks,
                    ticktext=[f"{t//60}:{t%60:02d}" for t in ticks]
                )
                fig_eff.update_yaxes(title="FC Media (ppm)")
                col.plotly_chart(fig_eff, use_container_width=True)

            with col_graf1:
                pintar_scatter_eficiencia(col_graf1, s1_data, sesion1)
            with col_graf2:
                pintar_scatter_eficiencia(col_graf2, s2_data, sesion2)
                
            st.caption("Interpretación: Los puntos representan vueltas. La línea de tendencia muestra tu eficiencia. Si la pendiente es muy pronunciada o los puntos se dispersan, vigila la fatiga.")

    elif menu_seleccionado == "⚙️ Configuración & Sync":
        st.title("⚙️ Panel de Configuración y Sincronización")
        
        st.subheader("⚙️ Configuración de tu dispositivo")
        conn = db_web_v2.conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT origen_tipo, fecha_inicio FROM configuracion_origen WHERE user_id = %s ORDER BY fecha_inicio DESC LIMIT 1", 
                    (st.session_state.user_id,))
        actual = cursor.fetchone()
        conn.close()

        if actual:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.info(f"Actualmente registrado: **{actual[0]}** (desde: {actual[1]})")
            with col2:
                if st.button("🔄 Cambiar"):
                    st.session_state.cambiar_dispositivo = True
                    st.rerun()

        if not actual or st.session_state.get("cambiar_dispositivo", False):
            if not actual:
                st.warning("No tienes ningún dispositivo configurado.")
                
            with st.form("form_dispositivo"):
                nuevo_origen = st.selectbox("Selecciona tu dispositivo:", ["Garmin", "Coros"])
                fecha_inicio = st.date_input("¿Desde qué fecha usas este dispositivo?")
                
                col_1, col_2 = st.columns(2)
                with col_1:
                    submitted = st.form_submit_button("Guardar dispositivo")
                with col_2:
                    if actual and st.form_submit_button("Cancelar"):
                        st.session_state.cambiar_dispositivo = False
                        st.rerun()
                
                if submitted:
                    conn = db_web_v2.conectar_db()
                    cursor = conn.cursor()
                    cursor.execute('''INSERT INTO configuracion_origen (user_id, origen_tipo, fecha_inicio) 
                                    VALUES (%s, %s, %s)''', (st.session_state.user_id, nuevo_origen, str(fecha_inicio)))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Dispositivo {nuevo_origen} guardado.")
                    st.session_state.cambiar_dispositivo = False
                    st.rerun()
            
        conn = db_web_v2.conectar_db()
        cursor = conn.cursor()
        cursor.execute("SELECT origen_tipo FROM configuracion_origen WHERE user_id = %s ORDER BY fecha_inicio DESC LIMIT 1", 
                    (st.session_state.user_id,))
        res_dispositivo = cursor.fetchone()
        dispositivo_actual = res_dispositivo[0] if res_dispositivo else "Garmin"

        cursor.execute("SELECT usuario_email, password_token FROM credenciales_plataformas WHERE user_id = %s AND plataforma = %s", 
                    (st.session_state.user_id, dispositivo_actual))
        res_creds = cursor.fetchone()
        email_actual = res_creds[0] if res_creds else ""
        pwd_guardada = res_creds[1] if res_creds else ""
        conn.close()

        st.subheader(f"🔑 Credenciales de {dispositivo_actual}")

        if email_actual and pwd_guardada and not st.session_state.get("modificar_creds", False):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.success(f"✅ Credenciales configuradas correctamente para **{dispositivo_actual}**: **{email_actual}**")
            with col2:
                if st.button("🔄 Cambiar credenciales", key=f"btn_cambiar_{dispositivo_actual.lower()}"):
                    st.session_state.modificar_creds = True
                    st.rerun()
        else:
            if not email_actual:
                st.warning(f"⚠️ No hay credenciales configuradas para {dispositivo_actual}.")
                
            usuario_input = st.text_input(f"Email / Usuario de {dispositivo_actual}", value=email_actual, key=f"input_user_{dispositivo_actual.lower()}")
            pwd_input = st.text_input(f"Contraseña de {dispositivo_actual}", type="password", placeholder="Introduce tu contraseña", key=f"input_pwd_{dispositivo_actual.lower()}")
            
            col_1, col_2 = st.columns(2)
            with col_1:
                guardar_cl = st.button("Guardar credenciales", key=f"btn_save_{dispositivo_actual.lower()}")
            with col_2:
                if email_actual and pwd_guardada:
                    cancelar_cl = st.button("Cancelar", key=f"btn_cancel_{dispositivo_actual.lower()}")
                    if cancelar_cl:
                        st.session_state.modificar_creds = False
                        st.rerun()
                        
            if guardar_cl:
                password_a_guardar = pwd_input if pwd_input else pwd_guardada
                if usuario_input and password_a_guardar:
                    conn = db_web_v2.conectar_db()
                    cursor = conn.cursor()
                    cursor.execute('''INSERT INTO credenciales_plataformas 
                                    (user_id, plataforma, usuario_email, password_token) 
                                    VALUES (%s, %s, %s, %s)
                                    ON CONFLICT (user_id, plataforma) 
                                    DO UPDATE SET usuario_email = EXCLUDED.usuario_email, password_token = EXCLUDED.password_token''', 
                                (st.session_state.user_id, dispositivo_actual, usuario_input, password_a_guardar))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"✅ Credenciales de {dispositivo_actual} guardadas correctamente.")
                    st.session_state.modificar_creds = False
                    st.rerun()
                else:
                    st.error("Por favor, introduce el usuario y la contraseña.")

        st.markdown("---")
        st.subheader("❤️ Control de Perfil Fisiológico de Hoy")

        today = datetime.now().strftime('%Y-%m-%d')
        conn = db_web_v2.conectar_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT fc_maxima, fc_reposo 
            FROM historial_fisiologico 
            WHERE user_id = %s AND fecha_inicio = %s 
            ORDER BY id DESC 
            LIMIT 1
        """, (st.session_state.user_id, today))
        fisiologia_hoy = cursor.fetchone()
        conn.close()

        fc_max_db = fisiologia_hoy[0] if fisiologia_hoy else None
        fc_rep_db = fisiologia_hoy[1] if fisiologia_hoy else None
        
        if not fc_max_db or not fc_rep_db:
            st.warning("⚠️ Faltan datos fisiológicos clave para hoy. Puedes introducirlos manualmente:")
            with st.form("form_fisiologia_manual"):
                col1, col2 = st.columns(2)
                with col1:
                    manual_fc_max = st.number_input("FC Máxima", min_value=100, max_value=220, value=int(fc_max_db) if fc_max_db else 185)
                with col2:
                    manual_fc_rep = st.number_input("FC Reposo", min_value=30, max_value=100, value=int(fc_rep_db) if fc_rep_db else 45)
                    
                if st.form_submit_button("Guardar datos manuales"):
                    conn = db_web_v2.conectar_db()
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO historial_fisiologico (user_id, fecha_inicio, fc_maxima, fc_reposo) 
                        VALUES (%s, %s, %s, %s)
                    ''', (st.session_state.user_id, today, manual_fc_max, manual_fc_rep))
                    conn.commit()
                    conn.close()
                    st.success("✅ Datos fisiológicos actualizados correctamente.")
                    st.rerun()
        else:
            st.info(f"✅ Perfil fisiológico de hoy registrado (FC Máx: **{fc_max_db} bpm** | FC Reposo: **{fc_rep_db} bpm**).")

        st.markdown("---")
        st.subheader(f"🔄 Sincronización de Actividades ({dispositivo_actual})")

        tab_auto, tab_manual = st.tabs(["⚡ Sincronización Automática (Recomendada)", "📁 Carga Manual de Archivos .FIT"])

        with tab_auto:
            st.caption(f"Sincroniza directamente tus últimas actividades desde los servidores de **{dispositivo_actual}**.")
            num_actividades = st.number_input(
                "¿Cuántas actividades quieres sincronizar?", 
                min_value=1, 
                max_value=1000, 
                value=5, 
                key="num_act_auto"
            )

            if st.button(f"Sincronizar automáticamente con {dispositivo_actual}", key="btn_sync_auto", type="primary"):
                limite_seguro = min(int(num_actividades), 1000)
                
                try:
                    with st.spinner(f"Conectando con {dispositivo_actual} (límite: {limite_seguro})..."):
                        if dispositivo_actual == "Garmin":
                            from garmin_ingestor import GarminIngestor
                            ingestor = GarminIngestor(st.session_state.user_id)
                            cantidad = ingestor.sincronizar(limite=limite_seguro)
                            
                        elif dispositivo_actual == "Coros":
                            from coros_ingestor import CorosIngestor
                            ingestor = CorosIngestor(st.session_state.user_id)
                            cantidad = ingestor.sincronizar(limite=limite_seguro)
                            
                        else:
                            raise Exception(f"Plataforma '{dispositivo_actual}' no soportada actualmente.")
                        
                        st.success(f"✅ Se han sincronizado {cantidad} actividades correctamente desde {dispositivo_actual}.")
                        
                except Exception as e:
                    st.error(f"❌ Error durante la sincronización con {dispositivo_actual}: {e}")

        with tab_manual:
            st.caption("Importa archivos `.fit` guardados localmente o subidos de manera manual.")
            
            metodo_manual = st.radio(
                "Selecciona el origen de los archivos:",
                ["Subir archivos directamente", "Procesar carpeta local ('./ficheros_fit/')"],
                key="metodo_manual_fit"
            )

            if metodo_manual == "Subir archivos directamente":
                archivos_fit = st.file_uploader(
                    "Arrastra o selecciona tus ficheros .FIT", 
                    type=["fit"], 
                    accept_multiple_files=True
                )
                
                if archivos_fit and st.button("Procesar archivos subidos", key="btn_process_uploaded"):
                    carpeta_temp = "./ficheros_fit/"
                    os.makedirs(carpeta_temp, exist_ok=True)
                    
                    for fit_file in archivos_fit:
                        path_destino = os.path.join(carpeta_temp, fit_file.name)
                        with open(path_destino, "wb") as f:
                            f.write(fit_file.getbuffer())
                    
                    try:
                        with st.spinner("Procesando archivos subidos..."):
                            from fit_ingestor import FitIngestor
                            ingestor = FitIngestor(user_id=st.session_state.user_id, carpeta_fit=carpeta_temp)
                            cantidad = ingestor.sincronizar()
                            st.success(f"✅ Se han procesado e importado {cantidad} actividades desde los ficheros subidos.")
                    except Exception as e:
                        st.error(f"❌ Error procesando archivos .FIT: {e}")

            else:
                carpeta_fit = "./ficheros_fit/"
                fits_existentes = (
                    [f for f in os.listdir(carpeta_fit) if f.lower().endswith('.fit')] 
                    if os.path.exists(carpeta_fit) else []
                )
                
                if fits_existentes:
                    st.info(f"📁 Se han encontrado **{len(fits_existentes)}** ficheros `.fit` en la carpeta `{carpeta_fit}`.")
                    
                    if st.button("Procesar carpeta local de ficheros .FIT", key="btn_process_local_folder"):
                        try:
                            with st.spinner("Importando ficheros .fit locales..."):
                                from fit_ingestor import FitIngestor
                                ingestor = FitIngestor(user_id=st.session_state.user_id, carpeta_fit=carpeta_fit)
                                cantidad = ingestor.sincronizar()
                                st.success(f"✅ Se han procesado {cantidad} actividades desde la carpeta local.")
                        except Exception as e:
                            st.error(f"❌ Error al procesar la carpeta local: {e}")
                else:
                    st.warning(f"⚠️ No se han encontrado archivos `.fit` en la ruta `{carpeta_fit}`.")