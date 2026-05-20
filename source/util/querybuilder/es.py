from config.db_connection import DatabaseManager
from typing import Optional
from dotenv import load_dotenv
from util.color import LogColor
import pandas as pd
import os
import json
from loguru import logger

config = DatabaseManager()
load_dotenv

class FetchESQuery:
    def __init__(self):
        self.ES_CONNECTION = config.get_es()
        self.INDEX_VORTEX = os.getenv('ES_VORTEX_INDEX')
    
    def _get_conn(self):
        if self.ES_CONNECTION is None:
            self.ES_CONNECTION = config.get_es()
        return self.ES_CONNECTION

    def _build_query_from_param(self, param: dict, query, condition):
        from_time = param['timeframe'].get('from')
        to_time = param['timeframe'].get('to')

        timeframe_field = param['timeframe'].get('timeframe_field')
        if not timeframe_field:
            timeframe_field = param['timeframe']['timeframe_field'] = "created_at"
        
        query_filters = query['query']['bool'][f'{condition}']
        query_filter = [fil for fil in query_filters if not ('range' in fil and timeframe_field in fil['range'])]

        range_ = {
            "range": {
                "created_at": {
                    "format": "yyyy-MM-dd HH:mm:ss",
                    "gte": from_time,
                    "lte": to_time
                }
            }
        }
        query_filter.append(range_)
        query['query']['bool'][f'{condition}'] = query_filter

        filters = param.get('filters', [])

        if isinstance(filters, list):
            for f in filters:
                try:
                    field = f['field']
                    value = f['value']
                    build_filter = {
                        "match_phrase": {
                            field: value
                        }
                    }
                    query['query']['bool']['filter'].append(build_filter)
                    # print(query)
                except KeyError as e:
                    print("something wrong", e)
                    continue
        return query
    
    def _mapping_helper(self, widget, response):
        match widget:
            case "expose_jumlah_postingan" | "expose_jumlah_engagement" | "tren_engagement_trendline" | "tren_postingan_trendline" | "campaign_performance":
                buckets = response['aggregations']['2']['buckets']
                result =  [
                    {
                        "key": b['key'],
                        "doc_count": b['doc_count'],
                        "value": b['1']['value'] if "1" in b else None,
                        "key_as_string": b['key_as_string'] if "key_as_string" in b else "",
                        "inner_buckets": [
                            {
                                "key": ib['key'],
                                "doc_count": ib['doc_count'],
                                "value": ib['1']['value'] if "1" in ib else None
                            }
                            for ib in b['3']['buckets']
                        ] if "3" in b else []
                    }
                    for b in buckets
                ]
            case "polda" | "polres" | "polsek":
                rows = []
                agg = response['aggregations']['satwil']['buckets']

                for satwil in agg:
                    s_name = satwil['key']
                    for campaign in satwil['campaign']['buckets']:
                        c_name = campaign['key']
                        for platform in campaign['platform']['buckets']:
                            p_name = platform['key']
                            for task in platform['task']['buckets']:
                                t_name = task['key']
                                for date in task['created_at']['buckets']:
                                    rows.append({
                                        "Satker": s_name,
                                        "CampaignName": c_name,
                                        "CampaignPlatform": p_name,
                                        "CampaignTask": t_name,
                                        "WaktuCampaign": date['key_as_string'],
                                        "TotalCampaign": date['doc_count']
                                    })
                result = pd.DataFrame(rows)
            case "tren_postingan_matrick" | "tren_engagement_matrick":
                platforms = ["instagram", "tiktok", "facebook", "twitter", "youtube"]

                buckets = response['aggregations']['2']['buckets']
                buckets_map = {b["key"]: b for b in buckets}

                complete_buckets = []
                for platform in platforms:
                    bucket = buckets_map.get(platform)
                    if bucket:
                        complete_buckets.append(bucket)
                    else:
                        complete_buckets.append({
                            "key": platform,
                            "doc_count": 0,
                            "1": {"value": 0.0},
                            "3": {"buckets": []},
                            "key_as_string": platform
                        })
                
                result = [
                    {
                        "key": b['key'],
                        "doc_count": b['doc_count'],
                        "value": b['1']['value'] if "1" in b else None,
                        "key_as_string": b.get('key_as_string', ""),
                        "inner_buckets": [
                            {
                                "key": ib['key'],
                                "doc_count": ib['doc_count'],
                                "value": ib["1"]['value'] if "1" in ib else None,
                            }
                            for ib in b.get('3', {}).get('buckets', [])
                        ]
                    }
                    for b in complete_buckets
                ]

            case "tren_eksposure_matrick" | "tren_eksposure_trendline":
                buckets = response["aggregations"]["1"]["buckets"]
                result = [
                    {
                        "key": b['key'],
                        "doc_count": b['doc_count']
                    }
                    for b in buckets
                ]
            case "tren_eksposure_total":
                aggs = response['aggregations']
                result = {
                    "engagement": aggs.get('Engagement', {}).get('value', 0),
                    "eksposure": aggs.get('Eksposure', {}).get('value', 0)
                }
        return result
            
    
    def campaign_query(self, widget, param: Optional[dict]):
        es = self._get_conn()
        satwil = param['satuanWilayah']

        match widget:
            case "polda" | "polres" | "polsek":
                query = {"aggs":{"satwil":{"terms":{"field":"jurisdiction_area.polda.keyword","order":{"_key":"asc"},"size":100},"aggs":{"campaign":{"terms":{"field":"campaign.campaign_name","order":{"_key":"asc"},"size":5,"shard_size":25},"aggs":{"platform":{"terms":{"field":"campaign.campaign_platform","order":{"_key":"asc"},"size":5,"shard_size":25},"aggs":{"task":{"terms":{"field":"campaign.campaign_task","order":{"_key":"asc"},"size":5,"shard_size":25},"aggs":{"created_at":{"date_histogram":{"field":"created_at","calendar_interval":"1w","time_zone":"Asia/Bangkok","min_doc_count":1}}}}}}}}}}},"size":0,"fields":[{"field":"account_category.joind_date","format":"date_time"},{"field":"created_at","format":"date_time"},{"field":"group_created_at","format":"date_time"},{"field":"quoted_created_at","format":"date_time"},{"field":"quoted_user_created_at","format":"date_time"},{"field":"retweeted_status_created_at","format":"date_time"},{"field":"retweeted_user_created_at","format":"date_time"},{"field":"user_created_at","format":"date_time"}],"script_fields":{},"stored_fields":["*"],"runtime_mappings":{},"_source":{"excludes":[]},"query":{"bool":{"must":[],"filter":[{"exists":{"field":"campaign.campaign_id"}},{"exists":{"field":"jurisdiction_area.polda_code"}},{"bool":{"minimum_should_match":1,"should":[{"match_phrase":{"satuan_wilayah_polri":"polda"}}]}},{"range":{"created_at":{"format":"strict_date_optional_time","gte":"2023-10-02T03:55:10.562Z","lte":"2025-01-02T03:55:10.562Z"}}}],"should":[],"must_not":[]}}}

                satwil = widget
                query['query']['bool']['filter'][1]['exists']['field'] = f"jurisdiction_area.{satwil}_code"
                query['aggs']['satwil']['terms']['field'] = f"jurisdiction_area.{satwil}.keyword"
                query['query']['bool']['filter'][2]['bool']['should'][0]['match_phrase']['satuan_wilayah_polri'] = satwil

                query = self._build_query_from_param(param, query, "filter")
                # print(query)                    
            case "expose_jumlah_postingan" | "expose_jumlah_engagement" | "tren_postingan_matrick" | "tren_engagement_matrick":
                query = {"size":0,"aggs":{"2":{"terms":{"field":"platform","order":{"1":"desc"},"size":5,"shard_size":25},"aggs":{"1":{"sum":{"field":"engagement"}}}}},"query":{"bool":{"must":[],"filter":[{"exists":{"field":"campaign.campaign_id"}},{"bool":{"minimum_should_match":1,"should":[{"match_phrase":{"satuan_wilayah_polri":"polda"}}]}},{"range":{"created_at":{"format":"strict_date_optional_time","gte":"2024-09-01T00:00:00.000Z","lte":"2025-01-01T23:59:59.000Z"}}}]}}}
                
                if widget in ["expose_jumlah_postingan", "expose_jumlah_engagement"]:
                    query.update({"script_fields": {},"stored_fields": ["*"],"runtime_mappings": {},"_source": {"excludes": []},}) 
                
                query['query']['bool']['filter'][1]['bool']['should'][0]['match_phrase']['satuan_wilayah_polri'] = satwil

                query = self._build_query_from_param(param, query, "filter")
                # print(query)
            case "tren_engagement_trendline" | "tren_postingan_trendline":
                query = {"size":0,"aggs":{"2":{"date_histogram":{"field":"created_at","calendar_interval":"1d","time_zone":"Asia/Bangkok","min_doc_count":1},"aggs":{"3":{"terms":{"field":"platform","order":{"1":"desc"},"size":5,"shard_size":25},"aggs":{"1":{"sum":{"field":"engagement"}}}}}}},"query":{"bool":{"must":[],"filter":[{"exists":{"field":"campaign.campaign_id"}},{"bool":{"minimum_should_match":1,"should":[{"match_phrase":{"satuan_wilayah_polri":"polda"}}]}},{"range":{"created_at":{"format":"strict_date_optional_time","gte":"2024-09-01T00:00:00.000Z","lte":"2025-01-01T23:59:59.000Z"}}}]}}}

                query['query']['bool']['filter'][1]['bool']['should'][0]['match_phrase']['satuan_wilayah_polri'] = satwil
                
                query = self._build_query_from_param(param, query, "filter")
            case "campaign_performance":
                query = {"aggs":{"2":{"terms":{"field":"jurisdiction_area.polda.keyword","order":{"1":"desc"},"size":10,"shard_size":25},"aggs":{"1":{"sum":{"field":"engagement"}}}}},"size":0,"fields":[{"field":"account_category.joind_date","format":"date_time"},{"field":"created_at","format":"date_time"},{"field":"group_created_at","format":"date_time"},{"field":"quoted_created_at","format":"date_time"},{"field":"quoted_user_created_at","format":"date_time"},{"field":"retweeted_status_created_at","format":"date_time"},{"field":"retweeted_user_created_at","format":"date_time"},{"field":"user_created_at","format":"date_time"}],"script_fields":{},"stored_fields":["*"],"runtime_mappings":{},"_source":{"excludes":[]},"query":{"bool":{"must":[],"filter":[{"exists":{"field":"campaign.campaign_id"}},{"range":{"created_at":{"format":"strict_date_optional_time","gte":"2024-09-20T06:20:25.729Z","lte":"2025-01-03T06:20:25.729Z"}}}],"should":[],"must_not":[]}}}

                query['aggs']['2']['terms']['field'] = f"jurisdiction_area.{satwil}.keyword"
                query = self._build_query_from_param(param, query, "filter")
                # print(query)
            
            case "tren_eksposure_matrick" | "tren_eksposure_trendline" | "tren_eksposure_total":
                query = {"query":{"bool":{"must":[{"exists":{"field":"satuan_wilayah_polri"}},{"bool":{"minimum_should_match":1,"should":[{"match_phrase":{"satuan_wilayah_polri":"polda"}}]}},{"range":{"created_at":{"gte":"2024-12-30","lte":"2025-01-05","format":"yyyy-MM-dd"}}}]}},"size":0,"aggs":{"1":{"terms":{"field":"platform","size":10,"order":{"_count":"desc"}}}}}
                
                if widget == "tren_eksposure_trendline":
                    query['aggs'] = {"1":{"date_histogram":{"field":"created_at","fixed_interval":"1d","time_zone":"Asia/Jakarta","min_doc_count":1}}}
                if widget == "tren_eksposure_total":
                    query['aggs'] = {"Engagement":{"sum":{"field":"engagement"}},"Eksposure":{"value_count":{"field":"id"}}}

                query['query']['bool']['must'][1]['bool']['should'][0]['match_phrase']['satuan_wilayah_polri'] = satwil
                query = self._build_query_from_param(param, query, "must")
                # print(query)

        # print(f"query:{LogColor.YELLOW} {json.dumps(query, indent=4)} {LogColor.END}")
        logger.info(f"{widget}: {LogColor.YELLOW} {json.dumps(query)} {LogColor.END}")
        try:
            result = es.search(index=self.INDEX_VORTEX, body=query)
            response = self._mapping_helper(widget=widget, response=result)
            # print(response)
        
        except Exception as e:
            raise e
        
        return response