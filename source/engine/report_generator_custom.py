from config.db_connection import DatabaseManager
from botocore.config import Config
from util.http import *
from loguru import logger
from util.color import LogColor
import os
import boto3
import time

class BaseCustomReport:
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

    def _cleanup_file(self, path):
        if os.path.exists(path):
            os.remove(path)
        else:
            logger.info("File doesn't exist")

    def _update_on_success(self, report_id, s3_path, execution_time):
        query_update = {
            "$set": {
                "status": "success",
                "message": "test",
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

class CustomReport(BaseCustomReport):
    def __init__(self):
        super().__init__()
    
    async def generate_custom_report_rar(self, param: dict):
        logger.info(f"{LogColor.CYAN}[RUNNING] =============== Generating CustomReportRAR ==============={LogColor.END}")
        start_time = time.time()

        try:
            report_config = self.mongo.find_one({"_id": param.get('id')})
            param_request = report_config.get('config', {}).get('param', {})
            param_request['save_to_s3'] = False
            
            if not param_request:
                logger.info(f"{LogColor.RED}[ERROR] PARAM TO API EMPTY{LogColor.END}")
                self._update_on_fail(report_config.get('_id'))
                return

            output_name = param_request.get('output_filename')

            s3_path = f"report/custom-report/anev-campaign/{output_name}.pptx"
            full_s3_path = f"s3://campaign-management/{s3_path}"

            logger.info(f"param request:{LogColor.YELLOW} {json.dumps(param_request)} {LogColor.END}")

            client = AsyncRequests(os.getenv('RAR_SVC'))
            # print("hit api")
            resp = await client.new_request(
                with_method('POST'),
                with_path('/report/generator/generate_v3'),
                with_json(param_request)
            )

            resp_type = resp.header.get('Content-Type')

            if resp_type == "application/json":
                return await resp.as_json()
            
            await resp.save_file(f"result/{output_name}.pptx")
            final_path = f"result/{output_name}.pptx"

            execution_time = time.time() - start_time
        
            self._update_on_success(report_config.get('_id'), full_s3_path, execution_time)
            self.s3_client.upload_file(final_path, self.bucket, s3_path)
            self._cleanup_file(final_path)

            logger.info(f"{LogColor.YELLOW}[INFO] =============== Success Generating CustomReportRAR ==============={LogColor.END}")
        except Exception as e:
            self._update_on_fail(report_config.get('_id'))
            raise e

    async def generate_custom_report_isr(self, param: dict):
        logger.info(f"{LogColor.CYAN}[RUNNING] =============== Generating CustomReportISR ==============={LogColor.END}")
        start_time = time.time()
        
        report_config = self.mongo.find_one({"_id": param.get('id')})
        param_request = report_config.get('config', {}).get('param', {})

        if not param_request:
            logger.info(f"{LogColor.RED}[ERROR] PARAM TO API EMPTY{LogColor.END}")
            self._update_on_fail(report_config.get('_id'))
            return
        
        logger.info(f"param request:{LogColor.YELLOW} {json.dumps(param_request)} {LogColor.END}")
        client = AsyncRequests(os.getenv('ISR_GPT_SVC'))

        # =============== STEP 1, ADD REPORT ===============
        try:
            resp = await client.new_request(
                with_method('POST'),
                with_path('/api/v1/report/add'),
                with_json(param_request)
            )
            resp_json = await resp.as_json()
        except Exception as e:
            logger.error(f"FAILED TO SEND REQUEST: {e}")
            self._update_on_fail(report_config.get('_id'))
            return

        report_id = resp_json.get('data')
        if not report_id:
            logger.info(f"{LogColor.RED}[ERROR] PARAM DOWNLOAD EMPTY{LogColor.END}")
            self._update_on_fail(report_config.get('_id'))
            return
        logger.info(f"param download:{LogColor.YELLOW} {json.dumps(report_id)} {LogColor.END}")

        # =============== STEP 2 & 3, 2(HIT GET ONE TO CHECK STATUS, IF SUCCESS GO TO STEP 3). 3(HIT DOWNLOAD TO GET THE FILE)===============
        attemp = 0
        for _ in range(5):
            attemp += 1
            try:
                resp2 = await client.new_request(
                    with_path(f"/api/v1/report/get-one?report_id={report_id}")
                )
                status_json = await resp2.as_json()
                logger.info(f"{LogColor.CYAN}[RUNNING] =============== {report_id} attempt {attemp} ==============={LogColor.END}")
            except Exception as e:
                logger.info(f"{LogColor.YELLOW}[INFO] =============== {report_id} error GET response from API {e}==============={LogColor.END}")
                await asyncio.sleep(60)
                continue
            
            logger.info(f"response isr:{LogColor.YELLOW} {json.dumps(status_json)} {LogColor.END}")
            
            status = status_json.get('data', {}).get('status')

            if status in ["processing", "waiting", "running", None]:
                await asyncio.sleep(60)
                continue

            if status in ["failed", "error"]:
                logger.info(f"{LogColor.CYAN}[ERROR] =============== {report_id} FAILED ==============={LogColor.END}")
                self._update_on_fail(report_config.get('_id'))
                return

            if status in ["success", "done", "completed"]:
                logger.info(f"{LogColor.CYAN}[INFO] =============== {report_id} SUCCESS -> START TO DOWNLOADING ==============={LogColor.END}")
                break
        else:
            logger.info(f"{LogColor.CYAN}[TIMEOUT] =============== {report_id} FAILED AFTER {attemp} attempts ==============={LogColor.END}")
            self._update_on_fail(report_config.get("_id"))
            return

        # =============== STEP 3. HIT DOWNLOAD TO GET THE FILE ===============
        try:
            resp3 = await client.new_request(
                with_path(f"/api/v1/report/download?report_id={report_id}")
            )
        except Exception as e:
            logger.error(f"{report_id} DOWNLOAD FAILED: {e}")
            self._update_on_fail(report_config.get('_id'))
            return

        if resp3.header.get('Content-Type') == "application/json":
            logger.info(f"download returns json:{LogColor.YELLOW} {json.dumps(await resp3.as_json())} {LogColor.END}")
            return

        output_name = status_json.get('data', {}).get('report_file_name')
        file_output_path = f"result/{output_name}"
        s3_path = f"report/custom-report/amplification-robot/{output_name}_[DEV].pptx"
        full_s3_path = f"s3://campaign-management/{s3_path}"

        await resp3.save_file(file_output_path)
        
        execution_time = time.time() - start_time

        self._update_on_success(report_config.get('_id'), full_s3_path, execution_time)
        self.s3_client.upload_file(file_output_path, self.bucket, s3_path)
        self._cleanup_file(file_output_path)

        return   