import sqlite3
import pandas as pd
import math
import db_web_v2  # <-- Usamos tu gestor de base de datos unificado de la app web

def calcular_trimp_dinamico(minutos, fc_media, fc_max, fc_reposo, sexo='M'):
    if fc_max <= fc_reposo or fc_media <= fc_reposo:
        return 0
        
    fc_reserva = fc_max - fc_reposo
    reserva_utilizada = (fc_media - fc_reposo) / fc_reserva
    
    # Coeficiente de Banister según el sexo ('M' para masculino, 'F' para femenino)
    if sexo and sexo.upper() in ['F', 'FEMENINO', 'WOMAN']:
        y = 1.67
        factor_base = 0.86  # Coeficiente multiplicador estándar para mujeres
    else:
        y = 1.92
        factor_base = 0.64  # Coeficiente multiplicador estándar para hombres
        
    trimp = minutos * reserva_utilizada * factor_base * math.exp(y * reserva_utilizada)
    return round(trimp, 2)

def procesar_curvas_acumuladas(user_id):
    """Calcula las curvas de Banister filtrando estrictamente por el user_id activo."""
    conn = db_web_v2.conectar_db()
    
    # Nota: Como la fecha está normalizada en la tabla 'actividades' o 'historial_entrenamientos',
    # aseguramos la consulta cruzando con actividades para obtener la fecha filtrando por user_id.
    query = '''
        SELECT a.fecha, h.trimp 
        FROM historial_entrenamientos h
        JOIN actividades a ON h.actividad_id = a.actividad_id
        WHERE h.user_id = ?
        ORDER BY a.fecha ASC
    '''
    df_trimp = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    
    if df_trimp.empty:
        return pd.DataFrame()

    df_trimp['fecha'] = pd.to_datetime(df_trimp['fecha'], format='mixed')
    df_diario = df_trimp.groupby('fecha')['trimp'].sum().reset_index()
    df_diario = df_diario.rename(columns={'fecha': 'Fecha', 'trimp': 'trimp_diario'})
    df_diario.set_index('Fecha', inplace=True)
    
    # Asignamos el resultado de la función para asegurar los cálculos
    df_diario = calcular_metricas_banister(df_diario)

    return df_diario

def calcular_metricas_banister(df):
    tau_atl = 7
    tau_ctl = 42
    
    # Creamos las columnas
    df['ATL_Fatiga'] = 0.0
    df['CTL_Forma'] = 0.0
    
    atl = 0.0
    ctl = 0.0
    
    # Cálculo iterativo
    for i in range(len(df)):
        trimp_hoy = df['trimp_diario'].iloc[i]
        atl = atl + (trimp_hoy - atl) / tau_atl
        ctl = ctl + (trimp_hoy - ctl) / tau_ctl
        
        df.iloc[i, df.columns.get_loc('ATL_Fatiga')] = atl
        df.iloc[i, df.columns.get_loc('CTL_Forma')] = ctl
        
    df['TSB_Frescura'] = df['CTL_Forma'] - df['ATL_Fatiga']
    
    # Evitamos división por cero en el ACWR si CTL es 0
    df['ACWR'] = df['ATL_Fatiga'] / df['CTL_Forma'].replace(0, 1)
    
    return df