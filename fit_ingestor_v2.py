import os
import json
from datetime import datetime
import pandas as pd
import db_web_v2
import core_metrics_v2
from deriva_v2 import calcular_deriva_sesion

try:
    import fitdecode
except ImportError:
    raise ImportError("Falta la librería fitdecode. Instálala ejecutando: pip install fitdecode")

class FitIngestor:
    def __init__(self, user_id, carpeta_fit="./ficheros_fit/"):
        self.user_id = user_id
        self.carpeta_fit = carpeta_fit

    def sincronizar(self):
        if not os.path.exists(self.carpeta_fit):
            os.makedirs(self.carpeta_fit)
            print(f"📁 Se ha creado la carpeta '{self.carpeta_fit}'. Coloca ahí tus ficheros .fit y vuelve a ejecutar.")
            return 0

        archivos = [f for f in os.listdir(self.carpeta_fit) if f.lower().endswith('.fit')]
        
        if not archivos:
            print(f"⚠️ No se han encontrado ficheros .fit en la carpeta '{self.carpeta_fit}'.")
            return 0

        print(f"✅ Ficheros .fit detectados para procesar: {len(archivos)}")

        count = 0
        conn = db_web_v2.conectar_db()
        cursor = conn.cursor()

        for archivo in archivos:
            ruta_archivo = os.path.join(self.carpeta_fit, archivo)
            
            resumen_sesion = {}
            vueltas = []
            
            try:
                with fitdecode.FitReader(ruta_archivo) as fit:
                    for frame in fit:
                        if frame.frame_type == fitdecode.FIT_FRAME_DATA:
                            if frame.name == 'session':
                                for field in frame.fields:
                                    if field.name and field.value is not None:
                                        resumen_sesion[field.name] = field.value
                            elif frame.name == 'lap':
                                lap_data = {}
                                for field in frame.fields:
                                    if field.name and field.value is not None:
                                        lap_data[field.name] = field.value
                                vueltas.append(lap_data)
            except Exception as e:
                print(f"❌ [LOG EXCLUSIÓN] Error crítico al leer el fichero FIT con fitdecode en {archivo}: {e}")
                continue

            if not resumen_sesion and vueltas:
                resumen_sesion['sport'] = 'running'  
                resumen_sesion['sub_sport'] = ''
                resumen_sesion['start_time'] = vueltas[0].get('start_time')
                resumen_sesion['total_distance'] = sum([v.get('total_distance', 0.0) or 0.0 for v in vueltas])
                resumen_sesion['total_timer_time'] = sum([v.get('total_timer_time', 0.0) or v.get('total_elapsed_time', 0.0) or 0.0 for v in vueltas])
                resumen_sesion['avg_heart_rate'] = vueltas[0].get('avg_heart_rate', 140) if vueltas else 140

            sport_raw = str(resumen_sesion.get('sport', 'unknown')).lower()
            sub_sport_raw = str(resumen_sesion.get('sub_sport', '')).lower()
            timestamp_inicio = resumen_sesion.get('start_time')

            deportes_excluidos = ['cycling', 'training', 'gym', 'walking']
            if sport_raw in deportes_excluidos:
                print(f"⏭️ [LOG EXCLUSIÓN] El fichero {archivo} corresponde a un deporte excluido ({sport_raw}). Omitiendo.")
                continue

            mapa_deportes = {
                'running': 'Carrera',
                'cycling': 'Ciclismo',
                'swimming': 'Natación',
                'walking': 'Caminata',
                'training': 'Fuerza/Entrenamiento',
                'elliptical': 'Elíptica',
                'fitness_equipment': 'Elíptica',
                'Fitness_equipment': 'Elíptica'
            }
            tipo_str = mapa_deportes.get(sport_raw, sport_raw.capitalize())

            mapa_subsport = {
                'treadmill': 'Cinta',
                'street': 'Asfalto',
                'trail': 'Trail',
                'track': 'Pista',
                'virtual_activity': 'Virtual'
            }
            subtipo_str = mapa_subsport.get(sub_sport_raw, '')

            if timestamp_inicio:
                if isinstance(timestamp_inicio, datetime):
                    act_id = int(timestamp_inicio.timestamp())
                    fecha_dia = timestamp_inicio.strftime('%Y-%m-%d')
                else:
                    act_id = int(datetime.now().timestamp())
                    fecha_dia = datetime.now().strftime('%Y-%m-%d')
            else:
                act_id = abs(hash(archivo)) % (10 ** 8)
                fecha_dia = datetime.now().strftime('%Y-%m-%d')

            cursor.execute("SELECT 1 FROM actividades WHERE user_id = %s AND actividad_id = %s", 
                           (self.user_id, act_id))
            if cursor.fetchone():
                print(f"⏭️ [LOG EXCLUSIÓN] El fichero {archivo} (Deporte: {sport_raw}, ID {act_id}) ya estaba registrado en BBDD. Omitiendo.")
                continue

            distancia_m = resumen_sesion.get('total_distance', 0.0) or 0.0
            distancia_total = distancia_m / 1000.0

            duracion_s = resumen_sesion.get('total_timer_time', 0.0) or resumen_sesion.get('total_elapsed_time', 0.0) or 0.0
            duracion_total = duracion_s / 60.0

            if duracion_total == 0.0:
                print(f"⚠️ [LOG EXCLUSIÓN] Archivo {archivo} descartado por duración cero.")
                continue

            nombre_personalizado = (
                resumen_sesion.get('name') or 
                resumen_sesion.get('wkt_name') or 
                resumen_sesion.get('session_name')
            )
            
            if nombre_personalizado and isinstance(nombre_personalizado, str) and len(nombre_personalizado.strip()) > 2:
                nombre_sesion = nombre_personalizado.strip()
            else:
                sufijo_sub = f" ({subtipo_str})" if subtipo_str else ""
                nombre_sesion = f"{tipo_str}{sufijo_sub} ({distancia_total:.2f} km - {fecha_dia})"

            print(f"🔍 Procesando fichero FIT ID {act_id}: {nombre_sesion}")

            cursor.execute("""
                SELECT fc_maxima, fc_reposo 
                FROM historial_fisiologico 
                WHERE user_id = %s AND fecha_inicio = %s 
                ORDER BY id DESC 
                LIMIT 1
            """, (self.user_id, fecha_dia))
            fisiologia_row = cursor.fetchone()
            
            fc_max_usuario = fisiologia_row[0] if fisiologia_row and fisiologia_row[0] else 199
            fc_reposo_usuario = fisiologia_row[1] if fisiologia_row and fisiologia_row[1] else 46

            cursor.execute("SELECT sexo FROM usuarios WHERE user_id = %s", (self.user_id,))
            user_row = cursor.fetchone()
            sexo_usuario = user_row[0] if user_row and user_row[0] else 'M'

            fc_media_sesion = resumen_sesion.get('avg_heart_rate', 140.0) or 140.0
            
            ritmo_medio_seg = resumen_sesion.get('avg_speed', 0)
            if ritmo_medio_seg and ritmo_medio_seg > 0:
                ritmo_medio_seg = int(1000 / ritmo_medio_seg)
            else:
                ritmo_medio_seg = 300

            trimp = core_metrics_v2.calcular_trimp_dinamico(
                duracion_total, fc_media_sesion, fc_max_usuario, fc_reposo_usuario, sexo=sexo_usuario
            )

            tipo_act = 'running'

            try:
                cursor.execute('''
                    INSERT INTO actividades 
                    (user_id, actividad_id, fecha, nombre, tipo, distancia_km) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, actividad_id) DO NOTHING
                ''', (self.user_id, act_id, fecha_dia, nombre_sesion, tipo_act, distancia_total))

                filas_df_laps = []
                distancia_acumulada_m = 0.0
                
                if vueltas:
                    for idx_lap, lap in enumerate(vueltas):
                        lap_index = idx_lap + 1
                        lap_time_s = lap.get('total_timer_time') or lap.get('total_elapsed_time') or lap.get('time') or 0
                        lap_time_min = lap_time_s / 60.0
                        
                        lap_dist_m = lap.get('total_distance') or lap.get('distance') or 0.0
                        if lap_dist_m == 0 and lap_time_s > 0 and ritmo_medio_seg > 0:
                            lap_dist_m = (lap_time_s / ritmo_medio_seg) * 1000.0
                        
                        distancia_acumulada_m += lap_dist_m
                        lap_dist_km = distancia_acumulada_m / 1000.0

                        if lap_time_min == 0 and lap_dist_m > 0:
                            lap_ritmo_aprox = lap.get('avg_speed', 0)
                            if lap_ritmo_aprox > 0:
                                lap_time_min = (lap_dist_m / lap_ritmo_aprox) / 60.0
                            else:
                                lap_time_min = 1.0

                        lap_fc_media = lap.get('avg_heart_rate', fc_media_sesion) or fc_media_sesion
                        lap_fc_max = lap.get('max_heart_rate', fc_max_usuario) or fc_max_usuario
                        
                        lap_ritmo = lap.get('avg_speed', 0)
                        lap_ritmo_seg = int(1000 / lap_ritmo) if lap_ritmo and lap_ritmo > 0 else ritmo_medio_seg

                        cursor.execute('''
                            INSERT INTO detalle_vueltas 
                            (user_id, actividad_id, lap_index, ritmo_seg_km, fc_media, fc_maxima) 
                            VALUES (%s, %s, %s, %s, %s, %s)
                        ''', (self.user_id, act_id, lap_index, lap_ritmo_seg, lap_fc_media, lap_fc_max))

                        filas_df_laps.append({
                            'lap_index': lap_index,
                            'Distancia_Km': lap_dist_km,
                            'Minutos': lap_time_min,
                            'Ritmo_Seg': lap_ritmo_seg,
                            'FC_Media': lap_fc_media,
                            'FC_max': lap_fc_max
                        })
                else:
                    cursor.execute('''
                        INSERT INTO detalle_vueltas 
                        (user_id, actividad_id, lap_index, ritmo_seg_km, fc_media, fc_maxima) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                    ''', (self.user_id, act_id, 1, ritmo_medio_seg, fc_media_sesion, fc_max_usuario))
                    
                    filas_df_laps.append({
                        'lap_index': 1,
                        'Distancia_Km': distancia_total,
                        'Minutos': duracion_total,
                        'Ritmo_Seg': ritmo_medio_seg,
                        'FC_Media': fc_media_sesion,
                        'FC_max': fc_max_usuario
                    })

                cursor.execute('''
                    INSERT INTO historial_entrenamientos 
                    (user_id, actividad_id, trimp, trimp_min, trimp_km, km, minutos) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    self.user_id, act_id, trimp, 
                    (trimp / duracion_total if duracion_total > 0 else 0), 
                    (trimp / distancia_total if distancia_total > 0 else 0), 
                    distancia_total, duracion_total
                ))

                df_laps = pd.DataFrame(filas_df_laps)
                if not df_laps.empty:
                    if 'Ritmo_Seg' in df_laps.columns:
                        df_laps = df_laps.dropna(subset=['Ritmo_Seg'])
                    if 'Minutos' in df_laps.columns:
                        df_laps['minutos_acumulados'] = df_laps['Minutos'].cumsum()
                    if 'Distancia_Km' in df_laps.columns and 'distancia_km' not in df_laps.columns:
                        df_laps['distancia_km'] = df_laps['Distancia_Km']

                porcentaje_deriva, fc_i, fc_f, tipo_analisis, puntos_json = calcular_deriva_sesion(df_laps, duracion_total, tipo_act)

                cursor.execute('''
                    INSERT INTO historial_derivas 
                    (user_id, actividad_id, porcentaje_deriva, fc_inicial, fc_final, tipo_analisis, ritmo_medio, puntos_deriva_json) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    self.user_id, act_id, porcentaje_deriva, 
                    float(fc_i) if fc_i is not None else 0.0, 
                    float(fc_f) if fc_f is not None else 0.0, 
                    tipo_analisis, 
                    ritmo_medio_seg, puntos_json
                ))

                conn.commit()
                count += 1

                print(f"✅ Archivo {archivo} procesado e importado con éxito como '{nombre_sesion}'.")

            except Exception as db_err:
                conn.rollback()
                print(f"❌ Error de base de datos al guardar {archivo}: {db_err}")
                continue
        
        conn.close()
        return count