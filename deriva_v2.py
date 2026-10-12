import json
import pandas as pd

def calcular_deriva_sesion(df_laps, duracion_total, tipo_str="running"):
    porcentaje_deriva = 0.0
    fc_i, fc_f = 0.0, 0.0
    tipo_analisis = 'Rodaje Mitades'

    if df_laps.empty:
        return porcentaje_deriva, fc_i, fc_f, 'No aplica (Vacío)', json.dumps([0.0, 0.0])

    is_running = (tipo_str.lower() == 'running')
    distancia_total = df_laps['distancia'].sum() if 'distancia' in df_laps.columns else 0.0
    condicion_distancia = distancia_total >= 4000.0 or (distancia_total == 0.0 and duracion_total >= 15.0)

    if is_running and condicion_distancia and len(df_laps) >= 4:
        mitad_idx = len(df_laps) // 2
        df_mitad1 = df_laps.iloc[:mitad_idx]
        df_mitad2 = df_laps.iloc[mitad_idx:]

        if not df_mitad1.empty and not df_mitad2.empty:
            fc_col = 'fc_media' if 'fc_media' in df_laps.columns else 'FC_Media'
            fc_i = float(df_mitad1[fc_col].mean())
            fc_f = float(df_mitad2[fc_col].mean())
            
            ritmo_col = 'ritmo_seg_km' if 'ritmo_seg_km' in df_laps.columns else 'Ritmo_Seg'
            ritmo_i = float(df_mitad1[ritmo_col].mean())
            ritmo_f = float(df_mitad2[ritmo_col].mean())

            if fc_i > 0 and fc_f > 0 and ritmo_i > 0 and ritmo_f > 0:
                vel_1 = 1000.0 / ritmo_i
                vel_2 = 1000.0 / ritmo_f
                ea_1 = vel_1 / fc_i
                ea_2 = vel_2 / fc_f
                
                decoupled = ((ea_1 - ea_2) / ea_1) * 100
                if -15.0 <= decoupled <= 40.0:
                    porcentaje_deriva = decoupled
    else:
        tipo_analisis = 'No aplica (< 4km)'
        fc_col = 'fc_media' if 'fc_media' in df_laps.columns else 'FC_Media'
        fc_i = float(df_laps[fc_col].mean()) if fc_col in df_laps.columns else 0.0
        fc_f = fc_i


    # Guardamos las dos FC medias para pintar líneas horizontales de referencia
    puntos_json = json.dumps([round(fc_i, 1), round(fc_f, 1)])
    return porcentaje_deriva, fc_i, fc_f, tipo_analisis, puntos_json