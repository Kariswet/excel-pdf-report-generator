
from config.db_connection import DatabaseManager
from botocore.config import Config
from datetime import datetime
from loguru import logger
from dotenv import load_dotenv
from util.querybuilder.sql import FetchSQLQuery
from util.querybuilder.es import FetchESQuery
from util.color import LogColor
import pandas as pd
import os
import boto3
import time

load_dotenv()
class ExcelReportGenerator:
    def __init__(self):
        config = DatabaseManager()
        self.bucket = os.getenv("S3_VORTEX_BUCKET_NETWORK")
        self.db = os.getenv("DB_NAME")
        self.collection = "report"
        self.mongo = config.get_mongo_collection(self.db, self.collection)

        self.s3_client = boto3.client(
            endpoint_url=os.getenv("S3_VORTEX_ADDRESS"),
            service_name='s3',
            aws_access_key_id=os.getenv("S3_VORTEX_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_VORTEX_SECRET_KEY"),
            config=Config(connect_timeout=90, retries={'max_attempts': 6})
        )
    
    def _get_report_time(self, param: dict):
        from_time = param['timeframe'].get('from')
        from_time = datetime.strptime(from_time, "%Y-%m-%d %H:%M:%S")
        return from_time.strftime("%Y-%m-%d")
    
    def _write_to_excel(self, output_path, data_map: dict):
        with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
            for sheet_name, df in data_map.items():
                df.to_excel(writer, sheet_name=sheet_name.capitalize(), index=False)

    def _cleanup_file(self, path):
        if os.path.exists(path):
            os.remove(path)
        else:
            logger.info("File doesn't exist")
    
    def _update_on_success(self, report_id, s3_path, execution_time):
        query_update = {
            "$set": {
                "status": "success",
                "s3Path": s3_path,
                "estimation": "1 minutes",
                "executionTime": f"{execution_time}"
            }
        }

        self.mongo.find_one_and_update({"_id": report_id}, query_update)
    
    def _update_on_fail(self, report_id):
        query_update = {
            "$set": {
                "status": "failed",
                "s3Path": ""
            }
        }
        self.mongo.find_one_and_update({"_id": report_id}, query_update)

    def generate_kpi_report_excel(self, param: dict):
        logger.info(f"{LogColor.CYAN}[RUNNING] =============== Generating ReportKPI ==============={LogColor.END}")
        fetchSqlQuery = FetchSQLQuery()
        start_time = time.time()

        try:
            report_id = self.mongo.find_one({"_id": param.get('id')})
            satuan_wilayah = ["polda", "polres", "polsek"]

            all_data = {}  # ✅ collect ALL sheets first

            for satwil in satuan_wilayah:
                data = fetchSqlQuery.indicator_query(widget=satwil, platform="", campaign_id="", param=param)

                df = pd.DataFrame(data)  # ✅ ensure DataFrame
                all_data[satwil] = df    # ✅ store by sheet name

            report_format_time = self._get_report_time(param)

            file_output_path = f"result/kpi_report_{report_format_time}_{report_id.get('_id')}.xlsx"
            file_to_store_path = f"kpi_report_{report_format_time}_{report_id.get('_id')}.xlsx"

            # ✅ WRITE ONCE
            self._write_to_excel(file_output_path, all_data)

            execution_time = time.time() - start_time

            s3_path = f"report/kpi/{file_to_store_path}"
            full_s3_path = f"s3://campaign-management/{s3_path}"

            # ✅ SAFE TO ENABLE AFTER TESTING
            self._update_on_success(report_id.get('_id'), full_s3_path, execution_time)
            self.s3_client.upload_file(file_output_path, self.bucket, s3_path)
            self._cleanup_file(file_output_path)

            return file_to_store_path  # ✅ return AFTER LOOP

            
        except Exception as e:
            logger.error(f"[CRASH] {e} ")
            self._update_on_fail(report_id.get('_id'))
            return e
    
    def generate_campaign_report_excel(self, param: dict):
        logger.info(f"{LogColor.CYAN}[RUNNING] =============== Generating ReportCAMPAIGN ==============={LogColor.END}")
        fetchEsQuery = FetchESQuery()
        start_time = time.time()

        try:
            report_id = self.mongo.find_one({"_id": param.get('id')})
            satuan_wilayah = ["polda", "polres", "polsek"]

            all_data = {}
            for satwil in satuan_wilayah:
                data = fetchEsQuery.campaign_query(widget=satwil, param=param)

                df = pd.DataFrame(data)  # ✅ ensure DataFrame
                all_data[satwil] = df 
            
            report_format_time = self._get_report_time(param)

            file_output_path = f"result/interaction_report_{report_format_time}_{report_id.get('_id')}.xlsx"
            file_to_store_path = f"interaction_report_{report_format_time}_{report_id.get('_id')}.xlsx"

            self._write_to_excel(file_output_path, all_data)

            execution_time = time.time() - start_time

            s3_path = f"report/interaction/{file_to_store_path}"
            full_s3_path = f"s3://campaign-management/{s3_path}"

            self._update_on_success(report_id.get('_id'), full_s3_path, execution_time)
            self.s3_client.upload_file(file_output_path, self.bucket, s3_path)
            self._cleanup_file(file_output_path)

            return file_to_store_path

        except Exception as e:
            logger.error(f"[CRASH]  {e} ")
            self._update_on_fail(report_id.get('_id'))
            return e

