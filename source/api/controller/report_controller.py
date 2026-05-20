from api.model.campaign_model import CampaignModel
from api.service.report_service import CampaignReportService
from fastapi import APIRouter

class CampaignReportController:
    def __init__(self):
        self.router = APIRouter(
            tags=["interaction"]
        )
        
        self.router.post("/api/v1/generate-report")(self.campaign_report_docx_controller)
    
    async def campaign_report_docx_controller(self, param: CampaignModel):
        report_service = CampaignReportService()
        generate = await report_service.campaign_report_docx_service(param)

        return generate