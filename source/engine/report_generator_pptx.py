from config.db_connection import DatabaseManager
from botocore.config import Config
from datetime import datetime
from loguru import logger
from dotenv import load_dotenv
from util.querybuilder.sql import FetchSQLQuery
from util.querybuilder.es import FetchESQuery
from util.color import LogColor
from util.chart import ChartAndOthers
from pptx import Presentation
from python_pptx_text_replacer import TextReplacer
import pandas as pd
import os
import boto3
import time

load_dotenv()
class BasePPTReport:
    def __init__(self):
        config = DatabaseManager()
        self.chart = ChartAndOthers()
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

        self.prs = None

    def load_template(self, template_path):
        self.prs = Presentation(template_path)  

    def _get_report_time(self, param: dict):
        from_time = param['timeframe'].get('from')
        from_time = datetime.strptime(from_time, "%Y-%m-%d %H:%M:%S")
        return from_time.strftime("%Y-%m-%d")

    def _replace_text(self, temp_file, pairs, output_file):
        replacer = TextReplacer(temp_file, slides='', tables=True, charts=False, textframes=True)
        replacer.replace_text(pairs)
        replacer.write_presentation_to_file(output_file)

    def _save_temp(self, path):
        self.prs.save(f"{path}")
    
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
    
    def _helper_grafik(self, g_data, source):
        grafik = []
        for item in g_data:
            if not isinstance(item, dict):
                continue

            if source == "key":
                dt = datetime.fromtimestamp(item[source] / 1000).strftime("%d %B %Y")
                grafik.append(dt)
            elif source == "doc_count":
                grafik.append(item[source])
        
        return grafik

class CampaignReportGenerator(BasePPTReport):
    def __init__(self):
        super().__init__()
    
    def generate_campaign_report_pptx(self, param: dict):
        logger.info(f"{LogColor.CYAN}[RUNNING] =============== Generating ReportCAMPAIGN ==============={LogColor.END}")
        self.load_template("template/tmp-REPORT-CAMPAIGN.pptx")
        fetchEsQuery = FetchESQuery()
        start_time = time.time()

        try:
            report_id = self.mongo.find_one({"_id": param.get('id')})
            campaign = ["campaign_performance", "tren_postingan_matrick", "tren_postingan_trendline", "tren_engagement_matrick", "tren_engagement_trendline", "expose_jumlah_postingan", "expose_jumlah_engagement"]

            all_data = {}

            for cpn in campaign:
                data = fetchEsQuery.campaign_query(param=param, widget=cpn)
                all_data[cpn] = data
            
            # =============== CHART SECTION ===============
            self.chart.generate_line_chart(self.prs, all_data.get('tren_postingan_trendline', {}), 2, 0, "eksposure")
            self.chart.generate_line_chart(self.prs, all_data.get('tren_engagement_trendline', {}), 3, 0, "engagement")
            self.chart.generate_chart_string_key(self.prs, all_data.get('expose_jumlah_postingan', {}), 4, 0, "eksposure")
            self.chart.generate_chart_string_key(self.prs, all_data.get('expose_jumlah_engagement', {}), 4, 1, "engagement")
            
            # =============== TEXT SECTION ===============
            campaign_performance = self.chart.retrieve_data_object(all_data.get('campaign_performance', []), sub_key="key", length_min=10)
            cp_exposure = self.chart.retrieve_data_object(all_data.get('campaign_performance', []), sub_key="doc_count", length_min=10, default_fill=0)
            cp_engagement = self.chart.retrieve_data_object(all_data.get('campaign_performance', []), sub_key="value", length_min=10, default_fill=0)
            cp_engagement = [f"{value:,.2f}" for value in cp_engagement]

            tren_postingan_matrick = self.chart.retrieve_data_object(sorted(all_data.get('tren_postingan_matrick', []), key=lambda x: x['doc_count'], reverse=True), sub_key="key", length_min=5)
            stpm_count = self.chart.retrieve_data_object(sorted(all_data.get('tren_postingan_matrick', []), key=lambda x: x['doc_count'], reverse=True), sub_key="doc_count", length_min=5, default_fill=0)
            tpm_count = self.chart.retrieve_data_object(all_data.get('tren_postingan_matrick'), sub_key="doc_count", length_min=5, default_fill=0)

            tren_engagement_matrick = self.chart.retrieve_data_object(all_data.get('tren_engagement_matrick'), sub_key="key", length_min=5)
            tem_count = self.chart.retrieve_data_object(all_data.get('tren_engagement_matrick'), sub_key="value", length_min=5, default_fill=0)
            tem_count = [f"{value:,.2f}" for value in tem_count]

            expose_jumlah_engagement = self.chart.retrieve_data_object(all_data.get('expose_jumlah_engagement'), sub_key="key", length_min=5)


            report_time = self._get_report_time(param)
            output_name = f"interaction_{report_time}_{report_id.get('_id')}.pptx"
            temp_path = f"result/interaction_temp_{report_id.get('_id')}.pptx"
            final_path = f"result/{output_name}"
            
            # =============== REPLACER SECTION ===============
            month = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
            from_time = param["timeframe"].get("from")
            to_time = param["timeframe"].get("to")
            from_time = datetime.strptime(from_time, "%Y-%m-%d %H:%M:%S")
            to_time = datetime.strptime(to_time, "%Y-%m-%d %H:%M:%S")
            date = f"{from_time.day} {month[from_time.month - 1]} {from_time.year} - {to_time.day} {month[to_time.month - 1]} {to_time.year}"

            self._save_temp(temp_path)
            self._replace_text(temp_path, [
                ("{date}", date),

                ("{title_1}", str(campaign_performance[0])),
                ("{title_2}", str(campaign_performance[1])),
                ("{title_3}", str(campaign_performance[2])),
                ("{title_4}", str(campaign_performance[3])),
                ("{title_5}", str(campaign_performance[4])),
                ("{title_6}", str(campaign_performance[5])),

                ("{expo_1}", str(cp_exposure[0])),
                ("{expo_2}", str(cp_exposure[1])),
                ("{expo_3}", str(cp_exposure[2])),
                ("{expo_4}", str(cp_exposure[3])),
                ("{expo_5}", str(cp_exposure[4])),
                ("{expo_6}", str(cp_exposure[5])),

                ("{enga_1}", str(cp_engagement[0])),
                ("{enga_2}", str(cp_engagement[1])),
                ("{enga_3}", str(cp_engagement[2])),
                ("{enga_4}", str(cp_engagement[3])),
                ("{enga_5}", str(cp_engagement[4])),
                ("{enga_6}", str(cp_engagement[5])),

                ("{insta}", str(tpm_count[0])),
                ("{tiktok}", str(tpm_count[1])),
                ("{fb}", str(tpm_count[2])),
                ("{twit}", str(tpm_count[3])),
                ("{you}", str(tpm_count[4])),

                ("{rank_1}", str(tren_postingan_matrick[0])),
                ("{rank_2}", str(tren_postingan_matrick[1])),
                ("{rank_3}", str(tren_postingan_matrick[2])),
                ("{rank_4}", str(tren_postingan_matrick[3])),
                ("{rank_5}", str(tren_postingan_matrick[4])),

                ("{v_lead_1}", self.chart.rank_sum(tpm_count, 0)),
                ("{v_lead_2}", self.chart.rank_sum(tpm_count, 1)),

                ("{rnk_eng_1}", str(tren_engagement_matrick[0])),
                ("{rnk_eng_2}", str(tren_engagement_matrick[1])),
                ("{rnk_eng_3}", str(tren_engagement_matrick[2])),
                ("{rnk_eng_4}", str(tren_engagement_matrick[3])),
                ("{rnk_eng_5}", str(tren_engagement_matrick[4])),

                ("{sum_v12}", str(tem_count[0] + tem_count[1])),

                ("{result_1}", str(expose_jumlah_engagement[0])),
                ("{result_2}", str(expose_jumlah_engagement[1])),
                ("{result_3}", str(expose_jumlah_engagement[2])),
                ("{result_4}", str(expose_jumlah_engagement[3])),
                ("{result_5}", str(expose_jumlah_engagement[4])),

                ("{v_rank_1}", str(stpm_count[0])),
                ("{v_rank_2}", str(stpm_count[1])),
                ("{v_rank_3}", str(stpm_count[2])),
                ("{v_rank_4}", str(stpm_count[3])),
                ("{v_rank_5}", str(stpm_count[4])),

                ("{insta1}", str(tem_count[0])),
                ("{tiktok1}", str(tem_count[1])),
                ("{fb1}", str(tem_count[2])),
                ("{twit1}", str(tem_count[3])),
                ("{you1}", str(tem_count[4])),

                ("{influencer_expo_1}", str(cp_exposure[0])),
                ("{influencer_expo_2}", str(cp_exposure[1])),
                ("{influencer_expo_3}", str(cp_exposure[2])),
                ("{influencer_expo_4}", str(cp_exposure[3])),
                ("{influencer_expo_5}", str(cp_exposure[4])),
                ("{influencer_expo_6}", str(cp_exposure[5])),

                ("{i_enga_1}", str(cp_engagement[0])),
                ("{i_enga_2}", str(cp_engagement[1])),
                ("{i_enga_3}", str(cp_engagement[2])),
                ("{i_enga_4}", str(cp_engagement[3])),
                ("{i_enga_5}", str(cp_engagement[4])),
                ("{i_enga_6}", str(cp_engagement[5])),

                ("{judul_1}", str(campaign_performance[0])),
                ("{judul_2}", str(campaign_performance[1])),
                ("{judul_3}", str(campaign_performance[2])),
                ("{judul_4}", str(campaign_performance[3])),
                ("{judul_5}", str(campaign_performance[4])),
                ("{judul_6}", str(campaign_performance[5])),
            ], output_file=final_path)
            self._cleanup_file(temp_path)

            execution_time = time.time() - start_time

            s3_path = f"report/campaign-ppt/{output_name}"
            full_s3_path = f"s3://campaign-management/{s3_path}"

            self._update_on_success(report_id.get('_id'), full_s3_path, execution_time)
            self.s3_client.upload_file(final_path, self.bucket, s3_path)
            self._cleanup_file(final_path)
            
        except Exception as e:
            self._update_on_fail(report_id.get('_id'))
            raise e

    def generate_kpi_report_ppt(self, param: dict):
        logger.info(f"{LogColor.CYAN}[RUNNING] =============== Generating ReportKPI ==============={LogColor.END}")
        self.load_template("template/tmp-REPORT-KPI.pptx")
        fetchEsQuery = FetchESQuery()
        fetchSqlQuery = FetchSQLQuery()
        start_time = time.time()

        try:
            report_id = self.mongo.find_one({"_id": param.get('id')})
            table = ["digital_interaction_indicator_dii", "public_perception_indicator_ppi", "digital_platform_indicator_dpi", "key_performance_indicator"]
            statistic = ["tren_eksposure_trendline", "tren_eksposure_matrick", "tren_eksposure_total"]

            statistic_data = {}
            table_data = {}

            for stats in statistic:
                stats_data = fetchEsQuery.campaign_query(widget=stats, param=param)
                statistic_data[stats] = stats_data
                
            for tbl in table:
                tbl_data = fetchSqlQuery.indicator_query(widget=tbl, platform="", campaign_id="", param=param)
                df = pd.DataFrame(tbl_data)  # ✅ ensure DataFrame
                table_data[tbl] = df
    
            # =============== CHART SECTION ===============
            self.chart.generate_bar_chart(self.prs, statistic_data.get('tren_eksposure_trendline'), 1, 0)
            self.chart.generate_table(self.prs, s_idx=2, data=table_data.get('key_performance_indicator'), case="kpi")
            self.chart.generate_table(self.prs, s_idx=3, data=table_data.get('digital_platform_indicator_dpi'), case="dpi")
            self.chart.generate_table(self.prs, s_idx=4, data=table_data.get('digital_interaction_indicator_dii'), case="dii")
            self.chart.generate_table(self.prs, s_idx=5, data=table_data.get('public_perception_indicator_ppi'), case="ppi")

            # =============== TEXT SECTION ===============
            platform_name = self.chart.retrieve_data_object(statistic_data.get('tren_eksposure_matrick'), sub_key="key", length_min=5)
            platform_post = self.chart.retrieve_data_object(statistic_data.get('tren_eksposure_matrick'), sub_key="doc_count", length_min=5, default_fill=0)
            platform_post = [f"{num:,}".replace(",", ".") for num in platform_post]
    
            exposure = statistic_data.get('tren_eksposure_total').get('eksposure')
            exposure = f"{exposure:,.2f}"
            engagement= statistic_data.get('tren_eksposure_total').get('engagement')
            engagement = f"{engagement:,.2f}"

            grafik = self.chart.retrieve_data_object(sorted(statistic_data.get('tren_eksposure_trendline'), key=lambda x: x['doc_count'], reverse=False))
            grafik_date = self._helper_grafik(grafik, "key")
            grafik_value = self._helper_grafik(grafik, "doc_count")
            grafik_value = [f"{num:,}".replace(",", ".") for num in grafik_value]

            report_time = self._get_report_time(param)
            output_name = f"kpi_{report_time}_{report_id.get('_id')}.pptx"
            temp_path = f"result/kpi_temp_{report_id.get('_id')}.pptx"
            final_path = f"result/{output_name}"
            
            # =============== REPLACER SECTION ===============
            month = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
            from_time = param["timeframe"].get("from")
            to_time = param["timeframe"].get("to")
            from_time = datetime.strptime(from_time, "%Y-%m-%d %H:%M:%S")
            to_time = datetime.strptime(to_time, "%Y-%m-%d %H:%M:%S")
            date = f"{from_time.day} {month[from_time.month - 1]} {from_time.year} - {to_time.day} {month[to_time.month - 1]} {to_time.year}"

            self._save_temp(temp_path)
            self._replace_text(temp_path, [
                ("{date}", date),

                ("{insta}", str(platform_post[0])),
                ("{twitter}", str(platform_post[1])),
                ("{facebook}", str(platform_post[2])),
                ("{tiktok}", str(platform_post[3])),
                ("{youtube}", str(platform_post[4])),

                ("{v_exposure}", str(exposure)),
                ("{v_engagement}", str(engagement)),

                ("{rank_1}", str(platform_name[0])),
                ("{rank_2}", str(platform_name[1])),
                ("{rank_3}", str(platform_name[2])),
                ("{rank_4}", str(platform_name[3])),
                ("{rank_5}", str(platform_name[4])),

                ("{v_rank_1}", str(platform_post[0])),  
                ("{v_rank_2}", str(platform_post[1])),
                ("{v_rank_3}", str(platform_post[2])),
                ("{v_rank_4}", str(platform_post[3])),
                ("{v_rank_5}", str(platform_post[4])),

                ("{trendline_1}", str(grafik_date[0])),
                ("{trendline_2}", str(grafik_date[1])),
                ("{trendline_3}", str(grafik_date[2])),
                ("{trendline_4}", str(grafik_date[3])),
                ("{trendline_5}", str(grafik_date[4])),

                ("{v_trendline_1}", str(grafik_value[0])),
                ("{v_trendline_2}", str(grafik_value[1])),
                ("{v_trendline_3}", str(grafik_value[2])),
                ("{v_trendline_4}", str(grafik_value[3])),
                ("{v_trendline_5}", str(grafik_value[4])),

                ("{v_trendline_last}", str(grafik_value[-1])),
                ("{trendline_last}", str(grafik_date[-1])),

            ], output_file=final_path)
            self._cleanup_file(temp_path)

            execution_time = time.time() - start_time

            s3_path = f"report/campaign-ppt/{output_name}"
            full_s3_path = f"s3://campaign-management/{s3_path}"

            self._update_on_success(report_id.get('_id'), full_s3_path, execution_time)
            self.s3_client.upload_file(final_path, self.bucket, s3_path)
            self._cleanup_file(final_path)

        except Exception as e:
            self._update_on_fail(report_id.get('_id'))
            raise e