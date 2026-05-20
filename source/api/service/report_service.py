from fastapi.responses import JSONResponse, FileResponse
from api.model.campaign_model import CampaignModel
from docxtpl import DocxTemplate
from starlette.background import BackgroundTask
from util.http import *
from util.querybuilder.sql import FetchSQLQuery
import datetime
import os
from loguru import logger
from util.color import LogColor

class CampaignReportService:
    def __init__(self):
        self.fetchSqlQuery = FetchSQLQuery()
        # self.background_task = BackgroundTasks()
    
    def _cleanup_file(self, path):
        if os.path.exists(path):
            os.remove(path)
        else:
            logger.info("File doesn't exist")

    def _build_regional_data(self, campaign_id: str, reportType: str):
        PLATFORMS = ["Twitter", "Youtube", "Facebook", "Instagram", "Tiktok"]
        result = {}

        for platform in PLATFORMS:
            if reportType in ["like", "suka", "share", "repost", "bagikan", "unggahan ulang", "retweet"]:
                result[platform] = {
                    "menjalankan": self.fetchSqlQuery.indicator_query("regional_unit", platform.lower(), campaign_id, param=None),
                    "tidak_sesuai": self.fetchSqlQuery.indicator_query("regional_unit_tidak_sesuai", platform.lower(), campaign_id, param=None),
                    "tidak_menjalankan": self.fetchSqlQuery.indicator_query("regional_unit_tidak_menjalankan", platform.lower(), campaign_id, param=None),
                }
            elif reportType in ["post", "unggah", "comment", "komentar", "reply"]:
                result[platform] = {
                "menjalankan_v2": self.fetchSqlQuery.indicator_query("regional_unit_v2", platform.lower(), campaign_id, param=None),
                "tidak_menjalankan_v2": self.fetchSqlQuery.indicator_query("regional_unit_tidak_menjalankan_v2", platform.lower(), campaign_id, param=None)
                }
                if reportType in ["comment", "komentar", "reply"]:
                    result[platform]["tidak_sesuai_v2"] = self.fetchSqlQuery.indicator_query("regional_unit_tidak_sesuai_v2", platform.lower(), campaign_id, param=None)
        
        return result

    async def campaign_report_docx_service(self, param: CampaignModel):
        logger.info(f"{LogColor.YELLOW}[RUNNING] =============== Generating CampaignReport ==============={LogColor.END}")
        cid = param.campaign_id
        rType = param.reportType  

        # =============== TEMPLATE SELECTION ===============
        if rType in ["like", "suka"]:
            doc = DocxTemplate("template/interaction_template_like.docx")
        elif rType in ["share", "repost", "bagikan", "unggahan ulang", "retweet"]:
            doc = DocxTemplate("template/interaction_template_share.docx")
        elif rType in ["post", "unggah"]:
            doc = DocxTemplate("template/interaction_template_post.docx")
        elif rType in ["comment", "komentar", "reply"]:
            doc = DocxTemplate("template/interaction_template_comment.docx")
        else:
            return JSONResponse(status_code=500, content={"error": "invalid reportType, avaiable type ['like','share','post','comment','suka','bagikan','repost','unggahan ulang','unggah','komentar']"})


        # =============== SENDING REQUEST TO CAMPAIGN API ===============
        client = AsyncRequests(os.getenv('CAMPAIGN_SVC_MANAGAMENT'))
        resp = await client.new_request(
            with_path(f"/api/v1/campaign/by-id?id={cid}")
        )

        data = await resp.as_json()
        # print(data)

        # =============== REPLACER SECTION ===============

        startTime = datetime.datetime.strptime(data["data"]["start"], "%Y-%m-%d %H:%M:%S")
        data["data"]["start"] = startTime.strftime("%Y-%m-%d")
        endTime = datetime.datetime.strptime(data["data"]["end"], "%Y-%m-%d %H:%M:%S")
        data["data"]["end"] = endTime.strftime("%Y-%m-%d")

        data["platform_list"] = [p.strip().capitalize() for p in data["data"]["platform"].split(",")]
        absence_recap = self.fetchSqlQuery.indicator_query(widget="absence_recap", platform="", campaign_id=cid, param=None)
        data["recap_data"] = absence_recap
        data["regional_data"] = self._build_regional_data(cid, rType)
        task = data["data"]["task"].capitalize()
        data["data"]["task"] = task

        output_path = f'result/interaction_report_{rType}_{cid}.docx'
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # =============== RENDER TO JINJA ===============
        doc.render(data)
        doc.save(output_path)

        # ===============  HANDLE RESPONSE ===============
        return FileResponse(
            output_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"interaction_report_{rType}_{cid}.docx",
            background=BackgroundTask(self._cleanup_file, output_path),
        )

