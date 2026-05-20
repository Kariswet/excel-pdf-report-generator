from consumer.rabbitmq import ReportConsumer
from api.controller.report_controller import CampaignReportController
from engine.report_generator_custom import CustomReport
from fastapi import FastAPI
from util.http import *
from loguru import logger
import argparse
import uvicorn
import os
import sys

logger.remove()
logger.add(sys.stdout, colorize=True,
           format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level}</level> | <cyan>{module}:{function}:</cyan><level>{line}</level> - {message}")


def run_service():
    app = FastAPI()
    app_port = os.getenv('VORTEX_SVC_REPORT_GENERATOR_PORT')
    
    campaign_controller = CampaignReportController()
    app.include_router(campaign_controller.router)
    
    uvicorn.run(app=app, host="0.0.0.0", port=int(app_port))

def run_engine():
    consumer = ReportConsumer()
    asyncio.run(consumer.start_consumer())

def test():
    param = {
        "id": "c867c63edfc0455f96ff13e9cd620f19",
        "reportType": "amplification-robot",
        "satuanWilayah": "",
        "timeframe": {
            "from": "2025-09-28 00:00:00",
            "to": "2025-10-03 23:59:59"
        }
    }

    cus_report = CustomReport()
    test = asyncio.run(cus_report.generate_custom_report_isr(param=param))
    return test
    # pptx = CampaignReportGenerator()
    # pptx.generate_campaign_report_pptx(param)

def main():
    parser = argparse.ArgumentParser(description="Run engine or service")
    parser.add_argument("-m", "--mode", choices=["engine", "service", "test"], required=True, help="Select mode to run: engine or service")
    args = parser.parse_args()

    if args.mode == "service":
        run_service()
    elif args.mode == "engine":
        run_engine()

    # development mode
    elif args.mode == "test":
        test()
    else:
        print("Argument needed, or not ready yet")

if __name__ == "__main__":
    main()
    # test()