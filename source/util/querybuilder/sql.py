from config.db_connection import DatabaseManager
from util.color import LogColor
from typing import Optional
from datetime import datetime
import pandas as pd
from loguru import logger

config = DatabaseManager()

class FetchSQLQuery:
    def __init__(self):
        self.PG_CONNECTION = None

    def _get_conn(self):
        if self.PG_CONNECTION is None:
            self.PG_CONNECTION = config.get_pg_conn()
        return self.PG_CONNECTION

    def _build_query_from_param(self, param: dict, query):
        from_time = param['timeframe'].get('from')
        to_time = param['timeframe'].get('to')

        if param['timeframe'] != None:
            from_time = param['timeframe'].get('from')
            to_time = param['timeframe'].get('to')  
        
            query = query.replace("start_time >= '2024-12-29 00:00:00' and end_time <= '2025-01-24 00:00:00'", f"start_time::date >= '{from_time}' and end_time::date <= '{to_time}'")
            query = query.replace("start_time = '2024-12-29 00:00:00' AND end_time = '2025-01-24 00:00:00'", f"start_time::date = '{from_time}' AND end_time::date = '{to_time}'")
        
        if param['satuanWilayah'] != None:
            query = query.replace("satuan_wilayah = filter", f"satuan_wilayah = '{param['satuanWilayah']}'")            
            query = query.replace("GROUP BY filter", f"GROUP BY {param['satuanWilayah']}")

            alias = param["satuanWilayah"].capitalize()
            query = query.replace("filter AS filter",f"{param['satuanWilayah']} AS \"{alias}\"")
        
        return query
    
    def indicator_query(self, widget, platform: Optional[str], campaign_id: Optional[str], param: Optional[dict]):
        pg = self._get_conn()

        match widget:
            case "absence_recap":
                query = f"""
                    WITH pivoted AS (
                        SELECT 
                            CASE 
                                WHEN verification_status = 'valid'   THEN 'Menjalankan Tugas'
                                WHEN verification_status = 'invalid' THEN 'Upload Tidak Sesuai Ketentuan'
                                WHEN verification_status = 'not_uploaded' THEN 'Tidak Menjalankan Tugas'
                            END AS status_tugas,
                            COUNT(*) FILTER (WHERE platform = 'instagram') AS Instagram,
                            COUNT(*) FILTER (WHERE platform = 'facebook')  AS Facebook,
                            COUNT(*) FILTER (WHERE platform = 'twitter')  AS Twitter,
                            COUNT(*) FILTER (WHERE platform = 'youtube')   AS Youtube,
                            COUNT(*) FILTER (WHERE platform = 'tiktok')  AS Tiktok
                        FROM campaign_task_verification
                        WHERE campaign_id = '{campaign_id}'
                        GROUP BY verification_status
                    )
                    SELECT *
                    FROM pivoted
                    UNION ALL
                    SELECT 
                        'TOTAL' AS status_tugas,
                        SUM(Instagram),
                        SUM(Facebook),
                        SUM(Twitter),
                        SUM(Youtube),
                        SUM(Tiktok)
                    FROM pivoted
                    """
            case "regional_unit":
                query = f"""
                    select person_name,organization_name, updated_at, 'Menjalankan Tugas' AS status
                    from campaign_task_verification ctv 
                    where campaign_id ='{campaign_id}'and verification_status ='valid' and platform='{platform}'
                    order by updated_at asc 
                """
            case "regional_unit_tidak_sesuai":
                query = f"""
                    select person_name, organization_name, updated_at, 'Upload Tidak Sesuai Ketentuan' AS status
                    from campaign_task_verification ctv 
                    where campaign_id ='{campaign_id}'and verification_status ='invalid' and platform ='{platform}'
                """
            case "regional_unit_tidak_menjalankan":
                query = f"""
                    select person_name, organization_name, 'Tidak menjalankan Tugas' AS status
                    from campaign_task_verification ctv 
                    where campaign_id ='{campaign_id}'and verification_status ='not_uploaded' and email_status ='false' and platform ='{platform}'
                    order by updated_at asc
                """
            case "regional_unit_v2":
                query = f"""
                    SELECT 
                    ctv.person_name,
                    ctv.organization_name,
                    'Menjalankan Tugas' AS status,
                    ctve.average_score,
                    ctve.conclusion,
                    ctv.updated_at
                    FROM campaign_task_verification ctv
                    JOIN campaign_task_verification_evaluation ctve ON ctv.id = ctve.task_id
                    where 
                        ctv.campaign_id = '{campaign_id}' 
                        and verification_status ='valid' 
                        and platform ='{platform}'
                """
            case "regional_unit_tidak_sesuai_v2":
                query = f"""
                    select
                        person_name,
                        organization_name,
                        updated_at,
                        'Upload Tidak Sesuai Ketentuan' as status
                    from campaign_task_verification ctv
                    where campaign_id = '{campaign_id}' and verification_status = 'invalid' and platform = '{platform}'
                    order by ctv.updated_at asc
                """
            case "regional_unit_tidak_menjalankan_v2":
                query = f"""
                    select person_name, organization_name, updated_at, 'Tidak Menjalankan Tugas' AS status 
                    from campaign_task_verification ctv 
                    where campaign_id ='{campaign_id}'and verification_status ='not_uploaded' and email_status ='false' and platform ='{platform}'
                    order by person_name  asc
                """
            
            case "key_performance_indicator":
                query = f"""
                    SELECT 
                        filter AS filter,
                        ROUND(SUM(CASE WHEN kpi_type = 'dpi' AND type_statistic = 'dpi' THEN value ELSE 0 END)::numeric, 2) AS "DPI",
                        ROUND(SUM(CASE WHEN kpi_type = 'dii' AND type_statistic = 'dii' THEN value ELSE 0 END)::numeric, 2) AS "DII",
                        ROUND(SUM(CASE WHEN kpi_type = 'ppi' AND type_statistic = 'ppi' THEN value ELSE 0 END)::numeric, 2) AS "PPI",
                        ROUND(SUM(CASE WHEN kpi_type = 'kpi' AND type_statistic = 'kpi' THEN value ELSE 0 END)::numeric, 2) AS "KPI"
                    FROM kpi_polda_result_v2
                    WHERE 
                        start_time = '2024-12-29 00:00:00' AND end_time = '2025-01-24 00:00:00'
                        AND satuan_wilayah = filter
                    GROUP BY filter
                    ORDER BY "KPI" DESC
                """

                query = self._build_query_from_param(param, query)
            case "digital_platform_indicator_dpi" | "digital_interaction_indicator_dii" | "public_perception_indicator_ppi":
                query = f"""
                    SELECT 
                        filter AS filter,
                        ROUND(SUM(CASE WHEN kpi_type = '(field)' AND type_statistic = '(field)' THEN value ELSE 0 END)::numeric, 2) AS "(field_)"
                    FROM kpi_polda_result_v2
                    WHERE 
                        start_time = '2024-12-29 00:00:00' AND end_time = '2025-01-24 00:00:00'
                        AND satuan_wilayah = filter
                    GROUP BY filter
                    ORDER BY "(field_)" DESC
                """
                field = widget.split("_")[3]
                query = query.replace("(field)", f"{field}")
                query = query.replace("(field_)", f"{field.upper()}")
                
                query = self._build_query_from_param(param, query)
            case "polda" | "polres" | "polsek":
                query = f"""
                    select
                    (field_s),
                        SUM(CASE WHEN kpi_type = 'dpi' AND type_statistic = 'eksposure normalized' THEN value ELSE 0 END) AS "DPI Exposure Score",
                        SUM(CASE WHEN kpi_type = 'dpi' AND type_statistic = 'engagement normalized' THEN value ELSE 0 END) AS "DPI Engagement Score",
                        SUM(CASE WHEN kpi_type = 'dpi' AND type_statistic = 'sentiment normalized' THEN value ELSE 0 END) AS "DPI Sentiment Score",
                        ROUND(SUM(CASE WHEN kpi_type = 'dpi' AND type_statistic = 'dpi' THEN value ELSE 0 END)::numeric, 2) AS "DPI Score",
                        SUM(CASE WHEN kpi_type = 'dii' AND type_statistic = 'eksposure normalized' THEN value ELSE 0 END) AS "DII Exposure Score",
                        SUM(CASE WHEN kpi_type = 'dii' AND type_statistic = 'engagement normalized' THEN value ELSE 0 END) AS "DII Engagement Score",
                        SUM(CASE WHEN kpi_type = 'dii' AND type_statistic = 'engagement sentiment normalized' THEN value ELSE 0 END) AS "DII Engagement Sentiment Score",
                        SUM(CASE WHEN kpi_type = 'dii' AND type_statistic = 'mention normalized' THEN value ELSE 0 END) AS " DII Mention Score",
                        SUM(CASE WHEN kpi_type = 'dii' AND type_statistic = 'mention sentiment normalized' THEN value ELSE 0 END) AS "DII Mention Sentiment Score",
                        SUM(CASE WHEN kpi_type = 'dii' AND type_statistic = 'theme suitability' THEN value ELSE 0 END) AS "DII Interaction Theme Suitability Score",
                        ROUND(SUM(CASE WHEN kpi_type = 'dii' AND type_statistic = 'dii' THEN value ELSE 0 END)::numeric, 2) AS "DII Score",
                        SUM(CASE WHEN kpi_type = 'ppi' AND type_statistic = 'eksposure normalized' THEN value ELSE 0 END) AS "PPI Exposure Score",
                        SUM(CASE WHEN kpi_type = 'ppi' AND type_statistic = 'engagement normalized' THEN value ELSE 0 END) AS "PPI Engagement Score",
                        SUM(CASE WHEN kpi_type = 'ppi' AND type_statistic = 'engagement sentiment normalized' THEN value ELSE 0 END) AS "PPI Engagement Sentiment Score",
                        SUM(CASE WHEN kpi_type = 'ppi' AND type_statistic = 'mention normalized' THEN value ELSE 0 END) AS "PPI Mention Score",
                        SUM(CASE WHEN kpi_type = 'ppi' AND type_statistic = 'mention sentiment normalized' THEN value ELSE 0 END) AS "PPI Mention Sentiment Score",
                        SUM(CASE WHEN kpi_type = 'ppi' AND type_statistic = 'emotion eksposure normalized' THEN value ELSE 0 END) AS "PPI Emotion Score",
                        SUM(CASE WHEN kpi_type = 'ppi' AND type_statistic = 'emotion engagement normalized' THEN value ELSE 0 END) AS "PPI Emotion Engagement Score",
                        ROUND(SUM(CASE WHEN kpi_type = 'ppi' AND type_statistic = 'ppi' THEN value ELSE 0 END)::numeric, 2) AS "PPI Score",
                        ROUND(SUM(CASE WHEN kpi_type = 'kpi' AND type_statistic = 'kpi' THEN value ELSE 0 END)::numeric, 2) AS "KPI Score",
                        ROUND(SUM(CASE WHEN kpi_type = 'kpi' AND type_statistic = 'kpi normalized' THEN value ELSE 0 END)::numeric, 2) AS "KPI Score Normalized"
                    FROM kpi_polda_result_v2
                    WHERE 
                        start_time = '2024-12-29 00:00:00' AND end_time = '2025-01-24 00:00:00'
                        AND satuan_wilayah = '(field_f)'
                    GROUP BY (field_g) 
                    ORDER BY "KPI Score Normalized" DESC
                """
                field = widget
                
                if widget == "polda":
                    query = query.replace("(field_s)", field)
                    query = query.replace("(field_f)", field)
                    query = query.replace("(field_g)", field)
                if widget == "polres":
                    query = query.replace("(field_s)", f"polda, {field}")
                    query = query.replace("(field_f)", field)
                    query = query.replace("(field_g)", f"polda, {field}")
                if widget == "polsek":
                    query = query.replace("(field_s)", f"polda, polres, {field}")
                    query = query.replace("(field_f)", field)
                    query = query.replace("(field_g)", f"polda, polres, {field}")
                
                query = self._build_query_from_param(param, query)                
            
        if widget in ["digital_platform_indicator_dpi", "digital_interaction_indicator_dii", "public_perception_indicator_ppi", "key_performance_indicator"]:
            if param['satuanWilayah'] in ["polres", "polsek"]:
                query += "limit 34"

        logger.info(f"{widget}: {LogColor.GREEN} {query} {LogColor.END}")
        try:
            with pg.cursor() as cursor:
                cursor.execute(query=query)
                result = cursor.fetchall()

                colname = [desc[0] for desc in cursor.description]
                df = pd.DataFrame(result, columns=colname)
                df = df.fillna(0)
                # df.to_json()
                # print(df)

                if widget in ["regional_unit", "regional_unit_tidak_sesuai","regional_unit_v2","regional_unit_tidak_menjalankan_v2","regional_unit_tidak_sesuai_v2"]:
                    df["updated_at"] = pd.to_datetime(df["updated_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")

                if widget == "absence_recap":
                    df.columns = ["status", "instagram", "facebook", "twitter", "youtube", "tiktok"]
                elif widget in ["regional_unit","regional_unit_tidak_sesuai", "regional_unit_tidak_menjalankan_v2", "regional_unit_tidak_sesuai_v2"]:
                    df.columns = ["person", "organization", "updated", "status"]
                elif widget == "regional_unit_tidak_menjalankan":
                    df.columns = ["person", "organization", "status"]
                elif widget == "regional_unit_v2":
                    df.columns = ["person", "organization", "status", "skor", "conculsion", "updated"]
                elif widget == "key_performance_indicator":
                    df.columns = ["Polda", "DPI", "DII", "PPI", "KPI"]
                elif widget == "digital_platform_indicator_dpi":
                    df.columns  = ["Polda", "DPI"]
                elif widget == "digital_interaction_indicator_dii":
                    df.columns = ["Polda", "DII"]
                elif widget == "public_perception_indicator_ppi":
                    df.columns = ["Polda", "PPI"]
                elif widget == "polda":
                    # df.columns = ["polda","DPI Exsposure Score","DPI Engagement Score","DPI Sentiment Score","DPI Score","DII Exposure Score","DII Engagement Score","DII Engagement Sentiment Score","DII Mention Score","DII Mention Sentiment Score","DII Interaction Theme Suitability Score","DII Score","PPI Exposure Score","PPI Engagement Score","PPI Engagement Sentiment Score","PPI Mention Score","PPI Mention Sentiment Score","PPI Emotion Score","PPI Emotion Engagement Score","PPI Score","KPI Score","KPI Score Normalized"]
                    df.columns = ["POLDA","DPI EKSPOSURE SCORE","DPI ENGAGEMENT SCORE","DPI SENTIMENT SCRORE","DPI SCORE","DII EXPOSURE SCORE","DII ENGAGEMENT SCORE","DII ENGAGEMENT SENTIMENT SCORE","DII MENTION SCORE","DII MENTION SENTIMENT SCORE","DII INTERACTION THEME SUITABILITY SCORE","DII SCORE","PPI EXPOSURE SCORE","PPI ENGAGEMENT SCORE","PPI ENGAGEMENT SENTIMENT SCORE","PPI MENTION SCORE","PPI MENTION SENTIMENT SCORE","PPI EMOTION SCORE","PPI EMOTION ENGAGEMENT SCORE","PPI SCORE","KPI SCORE","KPI SCORE NORMALIZED"]
                elif widget == "polres":
                    df.columns = ["POLDA", "POLRES", "DPI EKSPOSURE SCORE","DPI ENGAGEMENT SCORE","DPI SENTIMENT SCRORE","DPI SCORE","DII EXPOSURE SCORE","DII ENGAGEMENT SCORE","DII ENGAGEMENT SENTIMENT SCORE","DII MENTION SCORE","DII MENTION SENTIMENT SCORE","DII INTERACTION THEME SUITABILITY SCORE","DII SCORE","PPI EXPOSURE SCORE","PPI ENGAGEMENT SCORE","PPI ENGAGEMENT SENTIMENT SCORE","PPI MENTION SCORE","PPI MENTION SENTIMENT SCORE","PPI EMOTION SCORE","PPI EMOTION ENGAGEMENT SCORE","PPI SCORE","KPI SCORE","KPI SCORE NORMALIZED"]
                elif widget == "polsek":
                    df.columns = ["POLDA", "POLRES", "POLSEK", "DPI EKSPOSURE SCORE","DPI ENGAGEMENT SCORE","DPI SENTIMENT SCRORE","DPI SCORE","DII EXPOSURE SCORE","DII ENGAGEMENT SCORE","DII ENGAGEMENT SENTIMENT SCORE","DII MENTION SCORE","DII MENTION SENTIMENT SCORE","DII INTERACTION THEME SUITABILITY SCORE","DII SCORE","PPI EXPOSURE SCORE","PPI ENGAGEMENT SCORE","PPI ENGAGEMENT SENTIMENT SCORE","PPI MENTION SCORE","PPI MENTION SENTIMENT SCORE","PPI EMOTION SCORE","PPI EMOTION ENGAGEMENT SCORE","PPI SCORE","KPI SCORE","KPI SCORE NORMALIZED"]
                
                table_data = df.to_dict(orient='records')
        finally:
            config.release_pg_conn(pg)
        # print(table_data)
        return table_data

    def vortex_query(self):
        pass