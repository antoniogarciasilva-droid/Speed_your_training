import os
import json
import sqlite3
import requests
from datetime import datetime
import pandas as pd
import db_web_v2
import core_metrics_v2
from deriva_v2 import calcular_deriva_sesion

class CorosIngestor:
    def __init__(self, user_id, region="eu"):
        self.user_id = user_id
        # Selección de endpoint MCP oficial según la región especificada en la documentación de COROS
        endpoints = {
            "china": "https://mcpcn.coros.com/mcp",
            "eu": "https://mcpeu.coros.com/mcp",
            "us": "https://mcpus.coros.com/mcp",
            "global": "https://mcp.coros.com/mcp"
        }
        self.mcp_endpoint = endpoints.get(region.lower(), "https://mcp.coros.com/mcp")

    def sincronizar(self, limite=5, ruta_archivo_local="coros_activities.json"):
        """
        Sincroniza actividades consumiendo el servidor MCP oficial de COROS 
        mediante JSON-RPC (herramienta 'querySportRecords').
        """
        print(f"🔄 Conectando con COROS MCP ({self.mcp_endpoint}) para el usuario {self.user_id} (Límite: {limite})...")
        
        # 1. Obtener el token de acceso OAuth/Bearer de la base de datos o entorno
        conn = db_web.conectar_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT password_token 
            FROM credenciales_plataformas 
            WHERE user_id = ? AND plataforma = 'Coros'
        """, (self.user_id,))
        cred = cursor.fetchone()
        conn.close()

        token = cred[0] if cred and cred[0] else os.getenv("COROS_ACCESS_TOKEN")

        if not token or len(token) < 20:
            print("⚠️ No se encontró un token Bearer válido en la base de datos.")
            if os.path.exists(ruta_archivo_local):
                print(f"📂 Usando archivo de respaldo local: {ruta_archivo_local}")
                actividades_raw = self._cargar_actividades_locales(ruta_archivo_local, limite)
            else:
                raise ValueError(
                    "Error de autenticación MCP: Se requiere un token de acceso OAuth 2.0 válido "
                    "o el archivo local de respaldo 'coros_activities.json'."
                )
        else:
            # 2. Consultar al servidor MCP oficial usando la herramienta 'querySportRecords'
            actividades_raw = self._consultar_mcp_query_sport_records(token, limite)

        if not actividades_raw:
            print("⚠️ No se obtuvieron actividades desde el servidor MCP de COROS.")
            return 0

        conn = db_web.conectar_db()
        cursor = conn.cursor()
        count = 0

        for act in actividades_raw:
            try:
                act_id = act.get('sportId') or act.get('id') or act.get('uploadId')
                if not act_id:
                    continue
                
                try:
                    act_id_int = int(act_id)
                except:
                    act_id_int = abs(hash(str(act_id))) % (10 ** 8)

                cursor.execute("SELECT 1 FROM actividades WHERE user_id = ? AND actividad_id = ?", 
                               (self.user_id, act_id_int))
                if cursor.fetchone():
                    continue

                timestamp_ms = act.get('startTime') or act.get('time')
                if timestamp_ms:
                    if isinstance(timestamp_ms, (int, float)) and timestamp_ms > 10**10:
                        timestamp_ms = timestamp_ms / 1000.0
                    fecha_obj = datetime.fromtimestamp(timestamp_ms)
                    fecha_dia = fecha_obj.strftime('%Y-%m-%d')
                else:
                    fecha_dia = datetime.now().strftime('%Y-%m-%d')

                distancia_m = act.get('distance', 0.0) or act.get('dist', 0.0) or 0.0
                distancia_total = distancia_m / 1000.0 if distancia_m > 100 else distancia_m

                duracion_s = act.get('time', 0.0) or act.get('duration', 0.0) or 0.0
                duracion_total = duracion_s / 60.0 if duracion_s > 100 else duracion_s

                if distancia_total == 0.0 or duracion_total == 0.0:
                    continue

                tipo_str = str(act.get('sportType', 'Running')).capitalize()
                nombre_sesion = f"{tipo_str} ({distancia_total:.2f} km - {fecha_dia})"

                cursor.execute("""
                    SELECT fc_maxima, fc_reposo 
                    FROM historial_fisiologico 
                    WHERE user_id = ? AND fecha_inicio = ? 
                    ORDER BY id DESC 
                    LIMIT 1
                """, (self.user_id, fecha_dia))
                fisiologia_row = cursor.fetchone()
                
                fc_max_usuario = fisiologia_row[0] if fisiologia_row and fisiologia_row[0] else 195
                fc_reposo_usuario = fisiologia_row[1] if fisiologia_row and fisiologia_row[1] else 45

                cursor.execute("SELECT sexo FROM usuarios WHERE user_id = ?", (self.user_id,))
                user_row = cursor.fetchone()
                sexo_usuario = user_row[0] if user_row and user_row[0] else 'M'

                fc_media_sesion = act.get('avgHR', 140.0) or 140.0
                fc_max_sesion = act.get('maxHR', fc_max_usuario) or fc_max_usuario
                ritmo_medio_seg = act.get('avgPace', 300)

                trimp = core_metrics.calcular_trimp_dinamico(
                    duracion_total, fc_media_sesion, fc_max_usuario, fc_reposo_usuario, sexo=sexo_usuario
                )

                cursor.execute('''
                    INSERT OR REPLACE INTO actividades 
                    (user_id, actividad_id, fecha, nombre, tipo, distancia_km) 
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (self.user_id, act_id_int, fecha_dia, nombre_sesion, 'running', distancia_total))

                vueltas = act.get('lapList', []) or act.get('laps', [])
                filas_df_laps = []

                if vueltas:
                    for idx_lap, lap in enumerate(vueltas):
                        lap_index = idx_lap + 1
                        lap_time_s = lap.get('time') or 0
                        lap_time_min = lap_time_s / 60.0
                        lap_fc_media = lap.get('avgHR', fc_media_sesion) or fc_media_sesion
                        lap_fc_max = lap.get('maxHR', fc_max_sesion) or fc_max_sesion
                        lap_ritmo_seg = lap.get('pace', ritmo_medio_seg) or ritmo_medio_seg

                        cursor.execute('''
                            INSERT OR REPLACE INTO detalle_vueltas 
                            (user_id, actividad_id, lap_index, ritmo_seg_km, fc_media, fc_maxima) 
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (self.user_id, act_id_int, lap_index, lap_ritmo_seg, lap_fc_media, lap_fc_max))

                        filas_df_laps.append({
                            'lap_index': lap_index,
                            'Minutos': lap_time_min,
                            'Ritmo_Seg': lap_ritmo_seg,
                            'FC_Media': lap_fc_media,
                            'FC_max': lap_fc_max
                        })
                else:
                    cursor.execute('''
                        INSERT OR REPLACE INTO detalle_vueltas 
                        (user_id, actividad_id, lap_index, ritmo_seg_km, fc_media, fc_maxima) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (self.user_id, act_id_int, 1, ritmo_medio_seg, fc_media_sesion, fc_max_sesion))
                    
                    filas_df_laps.append({
                        'lap_index': 1,
                        'Minutos': duracion_total,
                        'Ritmo_Seg': ritmo_medio_seg,
                        'FC_Media': fc_media_sesion,
                        'FC_max': fc_max_sesion
                    })

                cursor.execute('''
                    INSERT OR REPLACE INTO historial_entrenamientos 
                    (user_id, actividad_id, trimp, trimp_min, trimp_km, km, minutos) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    self.user_id, act_id_int, trimp, 
                    (trimp / duracion_total if duracion_total > 0 else 0), 
                    (trimp / distancia_total if distancia_total > 0 else 0), 
                    distancia_total, duracion_total
                ))

                df_laps = pd.DataFrame(filas_df_laps)
                if not df_laps.empty and 'Minutos' in df_laps.columns:
                    df_laps['minutos_acumulados'] = df_laps['Minutos'].cumsum()

                porcentaje_deriva, fc_i, fc_f, tipo_analisis, puntos_json = calcular_deriva_sesion(df_laps, duracion_total, tipo_str)

                cursor.execute('''
                    INSERT OR REPLACE INTO historial_derivas 
                    (user_id, actividad_id, porcentaje_deriva, fc_inicial, fc_final, tipo_analisis, ritmo_medio, puntos_deriva_json) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    self.user_id, act_id_int, porcentaje_deriva, 
                    float(fc_i), float(fc_f), tipo_analisis, 
                    ritmo_medio_seg, puntos_json
                ))

                conn.commit()
                count += 1
                print(f"✅ Actividad procesada e inserción correcta: {nombre_sesion}")

            except Exception as item_err:
                conn.rollback()
                print(f"⚠️ Error procesando actividad individual: {item_err}")
                continue

        conn.close()
        return count

    def _consultar_mcp_query_sport_records(self, token, limite):
        """
        Invoca la herramienta oficial 'querySportRecords' expuesta por el servidor MCP de COROS.
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Estructura JSON-RPC requerida por el protocolo MCP para invocar herramientas
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "querySportRecords",
                "arguments": {
                    "limit": limite
                }
            },
            "id": 1
        }

        try:
            print(f"🔌 Enviando solicitud JSON-RPC 'querySportRecords' a {self.mcp_endpoint}")
            response = requests.post(self.mcp_endpoint, json=payload, headers=headers, timeout=20)
            print(f"📥 Estado HTTP recibido del MCP: {response.status_code}")

            if response.status_code == 200:
                resultado = response.json()
                
                # Extracción del contenido devuelto por la herramienta MCP
                if "result" in resultado:
                    content = resultado["result"].get("content", [])
                    for item in content:
                        if item.get("type") == "text":
                            try:
                                parsed_text = json.loads(item.get("text", "[]"))
                                if isinstance(parsed_text, list):
                                    return parsed_text[:limite]
                                elif isinstance(parsed_text, dict):
                                    return (parsed_text.get("dataList", []) or 
                                            parsed_text.get("records", []) or 
                                            parsed_text.get("data", []))[:limite]
                            except json.JSONDecodeError:
                                pass
                
                # Formato alternativo plano
                fallback_data = resultado.get("data", []) or resultado.get("records", [])
                if fallback_data:
                    return fallback_data[:limite]
            else:
                print(f"⚠️ Error en respuesta MCP: Status {response.status_code} - {response.text[:250]} ")
        except Exception as e:
            print(f"⚠️ Excepción al conectar con el servidor MCP: {e}")

        return []

    def _cargar_actividades_locales(self, ruta_archivo, limite):
        try:
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                contenido = json.load(f)
                if isinstance(contenido, list):
                    return contenido[:limite]
                elif isinstance(contenido, dict):
                    return (contenido.get("data", {}).get("dataList", []) or 
                            contenido.get("records", []) or
                            contenido.get("data", []))[:limite]
        except Exception as e:
            print(f"⚠️ Error al leer el fichero local de respaldo: {e}")
        return []