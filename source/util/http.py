import aiohttp
import json
import asyncio
from dataclasses import is_dataclass, asdict

class AsyncResponse:
    def __init__(self, resp: aiohttp.ClientResponse, body: bytes):
        self.status_code = resp.status
        self.header = resp.headers
        self.body = body
        self._resp = resp

    async def as_json(self):
        return json.loads(self.body)

    def text(self):
        return self.body.decode()
    
    async def save_file(self, file_path: str):
        with open(file_path, "wb") as f:
            f.write(self.body)
        return file_path

class AsyncRequestConfig:
    def __init__(self):
        self.method = "GET"
        self.path = ""
        self.query_params = {}
        self.body = None
        self.headers = {}
        self.bearer = None
        self.file = None
        self.form_fields = {}
        self.retries = 0

class AsyncRequests:
    def __init__(self, base_url: str, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout  

    async def new_request(self, *options):
        cfg = AsyncRequestConfig()
        for opt in options:
            opt(cfg)

        url = f"{self.base_url}/{cfg.path.lstrip('/')}"
        params = cfg.query_params or None

        headers = cfg.headers.copy()
        if cfg.bearer:
            headers['Authorization'] = f"Bearer {cfg.bearer}"

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:

            for attempt in range(cfg.retries + 1):
                try:
                    if cfg.file:
                        field_name, filename, filepath = cfg.file
                        form = aiohttp.FormData()
                        form.add_field(
                            field_name,
                            open(filepath, "rb"),
                            filename=filename
                        )
                        for k, v in cfg.form_fields.items():
                            form.add_field(k, v)
                        
                        async with session.request(cfg.method, url, data=form, headers=headers) as resp:
                            body = await resp.read()
                            return AsyncResponse(resp, body)
                    
                    else:
                        json_body = None
                        if is_dataclass(cfg.body):
                            json_body = cfg.body()
                        elif hasattr(cfg.body, "dict"):
                            json_body = cfg.body.dict()
                        else:
                            json_body = cfg.body

                        async with session.request(
                            cfg.method,
                            url,
                            params=params,
                            json=json_body,
                            headers=headers
                        ) as resp:
                            body = await resp.read()
                            # print("body", body)
                            return AsyncResponse(resp, body)

                except Exception as e:
                    if attempt >= cfg.retries:
                        raise
                
                    await asyncio.sleep(0.5)

                    
def with_method(method: str):
    def apply(cfg: AsyncRequestConfig):
        cfg.method = method.upper()
    return apply

def with_path(path: str):
    def apply(cfg: AsyncRequestConfig):
        cfg.path = path
    return apply

def with_query_param(key: str, value: str):
    def apply(cfg: AsyncRequestConfig):
        cfg.query_params[key] = value
    return apply

def with_query_params(params: dict):
    def apply(cfg: AsyncRequestConfig):
        cfg.query_params.update(params)
    return apply

def with_json(body):
    def apply(cfg: AsyncRequestConfig):
        cfg.body = body
    return apply

def with_header(key: str, value: str):
    def apply(cfg: AsyncRequestConfig):
        cfg.headers[key] = value
    return apply

def with_headers(hdrs: dict):
    def apply(cfg: AsyncRequestConfig):
        cfg.headers.update(hdrs)
    return apply

def with_bearer(token: str):
    def apply(cfg: AsyncRequestConfig):
        cfg.bearer = token
    return apply

def with_retry(n: int):
    def apply(cfg: AsyncRequestConfig):
        cfg.retries = n
    return apply

def with_file(field_name: str, filename: str, filepath: str):
    def apply(cfg: AsyncRequestConfig):
        cfg.file = (field_name, filename, filepath)
    return apply

def with_form(key: str, value: str):
    def apply(cfg: AsyncRequestConfig):
        cfg.form_fields[key] = value
    return apply
