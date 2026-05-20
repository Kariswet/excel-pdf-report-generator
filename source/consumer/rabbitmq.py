from engine.report_generator_custom import CustomReport
from engine.report_generator_excel import ExcelReportGenerator
from engine.report_generator_pptx import CampaignReportGenerator
from config.db_connection import DatabaseManager


from loguru import logger
from util.color import LogColor
import json
import os
import aio_pika

class ReportConsumer:
    def __init__(self):
        config = DatabaseManager()
        self.db = os.getenv("DB_NAME")
        self.collection = "report"
        self.mongo = config.get_mongo_collection(self.db, self.collection)
    
    def _update_on_fail(self, report_id):
        query_update = {
            "$set": {
                "status": "failed",
                "s3Path": ""
            }
        }
        self.mongo.find_one_and_update({"_id": report_id}, query_update)

    async def _recieve_message(self, body: bytes):
        try:
            message = json.loads(body)
        except Exception as e:
            self._update_on_fail(message.get('id'))
            logger.info(f"invalid json: {LogColor.RED}[ERROR] {e} {LogColor.END}")
        
        pptGenerator = CampaignReportGenerator()
        excelGenerator = ExcelReportGenerator()
        customGenerator = CustomReport() 

        rType = message.get('reportType')
        if rType == "campaign-ppt":
            pptGenerator.generate_campaign_report_pptx(param=message)
        elif rType == "kpi-ppt":
            pptGenerator.generate_kpi_report_ppt(param=message)

        elif rType == "campaign":
            excelGenerator.generate_campaign_report_excel(param=message)
        elif rType == "kpi":
            excelGenerator.generate_kpi_report_excel(param=message)

        elif rType == "anev-campaign":
            await customGenerator.generate_custom_report_rar(param=message)
        elif rType == "amplification-robot":
            await customGenerator.generate_custom_report_isr(param=message)
        
        else:
            logger.info(f"{LogColor.RED}[ERROR] =============== invalid report type ==============={LogColor.END}")
            self._update_on_fail(message.get('id'))
        
        logger.info(f"{LogColor.CYAN}[INFO] =============== FINISHED GENERATING REPORT {rType} ==============={LogColor.END}")
    
    async def start_consumer(self):
        logger.info(f"{LogColor.CYAN}[RUNNING] =============== STARTING CONSUMER ==============={LogColor.END}")
        RABBITMQ_URL = f"amqp://{os.getenv('RABBITMQ_USERNAME')}:{os.getenv('RABBITMQ_PASSWORD')}@{os.getenv('RABBITMQ_HOST')}:{os.getenv('RABBITMQ_PORT')}/{os.getenv('RMQ_VHOST','')}"
        RABBITMQ_QUE = os.getenv('RABBITMQ_QUEUE')
        
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=5)

        queue = await channel.declare_queue(RABBITMQ_QUE, durable=True)
        logger.info(f"{LogColor.CYAN}[INFO] =============== LISTENING QUEU: {queue} ==============={LogColor.END}")

        async with queue.iterator() as queue_iter:
            async for msg in queue_iter:
                async with msg.process(ignore_processed=True):
                    try:
                        await self._recieve_message(msg.body)
                    except Exception as e:
                        logger.info(f"{LogColor.RED}[ERROR]  ERROR PROCESSING MESSAGE: {e} {LogColor.END}")
                        raise e
