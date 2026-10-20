"""Optional loopback-only Ollama adapter. No tools, raw inputs or execution."""
import json
import os
import urllib.request
from urllib.parse import urlparse


def base_url():
    url = os.environ.get("PARKINGLAB_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise ValueError("Ollama地址必须为本机HTTP服务")
    return url


def request(path, payload=None, timeout=3):
    req = urllib.request.Request(base_url()+path, data=None if payload is None else json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as response:
        return json.load(response)


def models():
    try:
        data = request("/api/tags")
        return {"available":True, "models":[m["name"] for m in data.get("models", [])]}
    except (OSError, ValueError, KeyError):
        return {"available":False, "models":[], "message":"未检测到本地Ollama，仍可运行全部优化实验并导出报告"}


def explain(result, model):
    aggregates = {k:{a:b for a,b in v.items() if a != "schedule"} for k,v in result["policies"].items()}
    response = request("/api/chat", {"model":model, "stream":False, "options":{"temperature":0}, "messages":[
        {"role":"system", "content":"你是泊位规划实验的说明助手。只依据给出的计算结果，用中文解释接纳与风险的取舍。不得声称真实上线、论文复现、因果效果或联合概率保证。不能补造数字。说明抽样误差与正态偏差假设。控制在500字。"},
        {"role":"user", "content":json.dumps({"config":result["config"], "metrics":aggregates}, ensure_ascii=False)}]}, timeout=120)
    return response["message"]["content"]
