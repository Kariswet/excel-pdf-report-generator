from pydantic import BaseModel

class CampaignModel(BaseModel):
    campaign_id: str
    reportType: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "campaign_id": "c90c85716b5260e7f8b0ceb63da806d8",
                    "reportType": 'like/share/post/comment/suka/bagikan/repost/unggahan ulang/unggah/komentar'
                }
            ]
        }
    }