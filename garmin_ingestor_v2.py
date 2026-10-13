from garminconnect import Garmin
from datetime import datetime
import db_web_v2
import pandas as pd
import core_metrics_v2
from deriva_v2 import calcular_deriva_sesion
import json

class GarminIngestor:
    def __init__(self, user_id):
        self.user_id = user_id
        self.client = None
        self.email, self.password = self._cargar_credenciales()

    def _cargar_credenciales(self):
        """Busca las credenciales de Garmin en la tabla unificada para este usuario."""
        conn = db_web_v2.conectar_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT usuario_email, password_token FROM credenciales_plataformas WHERE user_id = %s AND plataforma = 'Garmin'",
            (self.user_id,)
        )
        creds = cursor.fetchone()
        conn.close()

        if not creds:
            raise Exception("No hay credenciales de Garmin configuradas para este usuario.")
        
        return creds[0], creds[1]

    def conectar(self):
        if not self.email or not self.password:
            self.email, self.password = self._cargar_credenciales()
           
        self.client = Garmin(self.email, self.password)
        self.client.login()

    def actualizar_datos_fisiologicos_garmin(self):
            if not self.client:
                self.conectar()
                
            today = datetime.now().strftime('%Y-%m-%d')
            
            conn = db_web_v2.conectar_db()
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT 1 FROM historial_fisiologico WHERE user_id = %s AND fecha_inicio = %s", 
                            (self.user_id, today))
                if cursor.fetchone():
                    return True 
                    
                fc_max = None
                fc_reposo = None
                
                try:
                    stats = self.client.get_user_summary(today) if hasattr(self.client, 'get_user_summary') else {}
                    fc_reposo = stats.get('restingHeartRate')
                except Exception:
                    pass

                try:
                    user_settings = self.client.get_user_settings() or {}
                    fc_max = user_settings.get('maxHeartRate') or user_settings.get('userMetrics', {}).get('maxHeartRate')
                except Exception:
                    pass

                if not fc_max:
                    cursor.execute("SELECT fc_maxima FROM historial_fisiologico WHERE user_id = %s AND fc_maxima IS NOT NULL ORDER BY fecha_inicio DESC LIMIT 1", (self.user_id,))
                    ultimo_registro = cursor.fetchone()
                    if ultimo_registro:
                        fc_max = int(ultimo_registro[0]) if ultimo_registro[0] is not None else None

                if fc_reposo or fc_max:
                    cursor.execute('''
                        INSERT INTO historial_fisiologico (user_id, fecha_inicio, fc_maxima, fc_reposo) 
                        VALUES (%s, %s, %s, %s)
                    ''', (
                        int(self.user_id), 
                        str(today), 
                        int(fc_max) if fc_max is not None else None, 
                        int(fc_reposo) if fc_reposo is not None else None
                    ))
                    conn.commit()
                    
            except Exception as e:
                print(f"Aviso al sincronizar fisiología: {e}")
            finally:
                conn.close()
                
            return True

    def sincronizar(self, limite=5):
        if not self.client:
            self.conectar()
            
        try:
            self.actualizar_datos_fisiologicos_garmin()
        except Exception as e:
            print(f"Aviso: No se pudo actualizar el perfil fisiológico: {e}")

        actividades = self.client.get_activities(0, limite)
        
        count = 0
        conn = db_web_v2.conectar_db()
        cursor = conn.cursor()

        for act in actividades:
            tipo_act = act.get('activityType', {}).get('typeKey')
            nombre_sesion = act.get('activityName')
            act_id = str(act.get('activityId'))
            fecha_completa = act.get('startTimeLocal')
            fecha_dia = fecha_completa.split()[0] if fecha_completa else None

            cursor.execute("SELECT 1 FROM actividades WHERE user_id = %s AND actividad_id = %s", 
                           (self.user_id, act_id))
            existe = cursor.fetchone()

            if existe:
                print(f"⏭️ Saltando: {nombre_sesion} ({act_id}) (Ya existe en BD)")
                continue

            if tipo_act not in ['running', 'track_running', 'elliptical']:
                continue
            
            print(f"🔍 Procesando: {nombre_sesion} ({fecha_dia})")

            try:
                splits = self.client.get_activity_splits(act_id)
                laps_raw = splits.get('lapDTOs', [])
            except Exception as e:
                print(f"   ⚠️ No se pudieron obtener splits: {e}")
                continue
                
            if not laps_raw: continue
                
            laps_data = []
            for lap in laps_raw:
                d_m = float(lap.get('distance', 0.0) or 0.0)
                dur_s = float(lap.get('duration', 0.0) or 0.0)
                laps_data.append({
                    'lap_index': int(lap.get('lapIndex', 0) or 0),
                    'Minutos': dur_s / 60.0,
                    'FC_Media': float(lap.get('averageHR', 0) or 0),
                    'FC_max': float(lap.get('maxHR', 0) or 0),
                    'Ritmo_Seg': (dur_s / (d_m / 1000.0)) if d_m > 100 else None,
                    'Distancia_Km': d_m / 1000.0
                })
            
            df_laps = pd.DataFrame(laps_data)
            if tipo_act != 'elliptical':
                df_laps = df_laps.dropna(subset=['Ritmo_Seg'])

            distancia_total = float(df_laps['Distancia_Km'].sum()) if not df_laps.empty else 0.0
            duracion_total = float(df_laps['Minutos'].sum()) if not df_laps.empty else 0.0
            fc_media_sesion = float(df_laps['FC_Media'].mean()) if not df_laps.empty else 0.0

            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT fc_maxima, fc_reposo 
                FROM historial_fisiologico 
                WHERE user_id = %s AND fecha_inicio = %s 
                ORDER BY id DESC 
                LIMIT 1
            """, (self.user_id, today))
            fisiologia_row = cursor.fetchone()
            
            fc_max_usuario = int(fisiologia_row[0]) if fisiologia_row and fisiologia_row[0] else 185
            fc_reposo_usuario = int(fisiologia_row[1]) if fisiologia_row and fisiologia_row[1] else 45

            cursor.execute("SELECT sexo FROM usuarios WHERE user_id = %s", (self.user_id,))
            user_row = cursor.fetchone()
            sexo_usuario = str(user_row[0]) if user_row and user_row[0] else 'M'

            trimp = float(core_metrics_v2.calcular_trimp_dinamico(
                duracion_total, 
                fc_media_sesion, 
                fc_max_usuario, 
                fc_reposo_usuario, 
                sexo=sexo_usuario
            ) or 0.0)

            cursor.execute('''
                INSERT INTO actividades 
                (user_id, actividad_id, fecha, nombre, tipo, distancia_km) 
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, actividad_id) DO NOTHING
            ''', (
                int(self.user_id), 
                str(act_id), 
                str(fecha_dia) if fecha_dia else None, 
                str(nombre_sesion) if nombre_sesion else "", 
                str(tipo_act), 
                float(distancia_total)
            ))
            
            for _, row in df_laps.iterrows():
                cursor.execute('''
                    INSERT INTO detalle_vueltas 
                    (user_id, actividad_id, lap_index, ritmo_seg_km, fc_media, fc_maxima) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (
                    int(self.user_id), 
                    str(act_id), 
                    int(row.get('lap_index', 0)), 
                    float(row.get('Ritmo_Seg')) if pd.notna(row.get('Ritmo_Seg')) else None, 
                    float(row.get('FC_Media', 0)), 
                    float(row.get('FC_max', 0))
                ))

            cursor.execute('''
                INSERT INTO historial_entrenamientos 
                (user_id, actividad_id, trimp, trimp_min, trimp_km, km, minutos) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (
                int(self.user_id), 
                str(act_id), 
                float(trimp), 
                float(trimp / duracion_total if duracion_total > 0 else 0), 
                float(trimp / distancia_total if distancia_total > 0 else 0), 
                float(distancia_total), 
                float(duracion_total)
            ))

            df_laps = pd.DataFrame(laps_data)
            if not df_laps.empty and 'Minutos' in df_laps.columns:
                df_laps['minutos_acumulados'] = df_laps['Minutos'].cumsum()
            
            porcentaje_deriva, fc_i, fc_f, tipo_analisis, puntos_json = calcular_deriva_sesion(df_laps, duracion_total, tipo_act)
            
            vel_ms = float(act.get("averageSpeed", 0.0) or 0.0)
            if vel_ms > 0:
                ritmo_medio_seg = float(1000.0 / vel_ms)  
            else:
                ritmo_medio_seg = float(act.get("avgPace", act.get("pace", 300)) or 300)

            cursor.execute('''
                INSERT INTO historial_derivas 
                (user_id, actividad_id, porcentaje_deriva, fc_inicial, fc_final, tipo_analisis, ritmo_medio, puntos_deriva_json) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                int(self.user_id), 
                str(act_id), 
                float(porcentaje_deriva) if porcentaje_deriva is not None else 0.0, 
                float(fc_i) if fc_i is not None else 0.0, 
                float(fc_f) if fc_f is not None else 0.0, 
                str(tipo_analisis) if tipo_analisis else "", 
                float(ritmo_medio_seg), 
                str(puntos_json) if puntos_json else "{}"
            ))

            count += 1
        
        conn.commit()
        conn.close()
        
        return count