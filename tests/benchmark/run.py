#!/usr/bin/env python3
"""
AI Cognitive Gateway — 性能基线基准测试

测量关键端点延迟，输出 p50/p95/p99 及成功率。
用于 CI 和每次改动后的防回归验证。

使用方法：
  # 先启动服务:  python main.py serve
  # 新终端运行:
  python tests/benchmark/run.py
  python tests/benchmark/run.py --url http://localhost:8000 --samples 50
"""

import argparse
import json
import statistics
import sys
import time
import urllib.request
import urllib.error


BASE_URL = "http://localhost:8000"
SAMPLES = 30
TIMEOUT = 30


def request(method: str, url: str, body: dict | None = None) -> tuple[int, float]:
    """发起 HTTP 请求，返回 (status_code, latency_ms)。"""
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    start = time.perf_counter()
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        latency = (time.perf_counter() - start) * 1000
        return resp.status, latency
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - start) * 1000
        return e.code, latency
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return 0, latency


def bench_endpoint(name: str, method: str, path: str, body: dict | None = None,
                   samples: int = SAMPLES) -> dict:
    """对单个端点执行多次请求，返回统计数据。"""
    latencies = []
    statuses = {}
    successes = 0

    for i in range(samples):
        status, latency = request(method, f"{BASE_URL}{path}", body)
        latencies.append(latency)
        statuses[status] = statuses.get(status, 0) + 1
        if status == 200:
            successes += 1

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    avg = statistics.mean(latencies)
    success_rate = (successes / samples) * 100

    result = {
        "endpoint": name,
        "samples": samples,
        "success_rate_pct": round(success_rate, 1),
        "latency_ms": {
            "min": round(min(latencies), 2),
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "p99": round(p99, 2),
            "max": round(max(latencies), 2),
            "avg": round(avg, 2),
        },
        "status_codes": statuses,
    }
    return result


def print_result(result: dict):
    """格式化输出基准结果。"""
    name = result["endpoint"]
    lat = result["latency_ms"]
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    print(f"  样本数:     {result['samples']}")
    print(f"  成功率:     {result['success_rate_pct']}%")
    print(f"  延迟 (ms):")
    print(f"    min:  {lat['min']:>8.2f}")
    print(f"    p50:  {lat['p50']:>8.2f}")
    print(f"    p95:  {lat['p95']:>8.2f}")
    print(f"    p99:  {lat['p99']:>8.2f}")
    print(f"    max:  {lat['max']:>8.2f}")
    print(f"    avg:  {lat['avg']:>8.2f}")
    print(f"  状态码分布: {result['status_codes']}")


def main():
    parser = argparse.ArgumentParser(description="AI Cognitive Gateway 性能基线测试")
    parser.add_argument("--url", default="http://localhost:8000", help="网关地址")
    parser.add_argument("--samples", type=int, default=30, help="每个端点的采样次数")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--ci", action="store_true", help="CI 模式（非 200 时退出码 1）")
    args = parser.parse_args()

    global BASE_URL, SAMPLES
    BASE_URL = args.url.rstrip("/")
    SAMPLES = args.samples

    print(f"\n🚀 AI Cognitive Gateway 性能基线测试")
    print(f"   目标: {BASE_URL}")
    print(f"   每个端点采样: {SAMPLES} 次")
    print(f"   开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    endpoints = [
        ("健康检查 GET /health", "GET", "/health"),
        ("模型列表 GET /v1/models", "GET", "/v1/models"),
        ("Prometheus GET /metrics", "GET", "/metrics"),
        ("基本对话 POST /chat", "POST", "/chat", {"user_input": "Hello"}),
        ("空输入 POST /chat", "POST", "/chat", {"user_input": "test"}),
    ]

    results = []
    all_ok = True
    for endpoint in endpoints:
        result = bench_endpoint(*endpoint, samples=SAMPLES)
        results.append(result)
        if not args.json:
            print_result(result)
        if result["success_rate_pct"] < 100:
            all_ok = False

    if args.json:
        print(json.dumps({
            "summary": {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "target": BASE_URL,
                "samples_per_endpoint": SAMPLES,
                "all_endpoints_ok": all_ok,
            },
            "results": results,
        }, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*50}")
        overall = "✅ 所有端点正常" if all_ok else "⚠️  部分端点未达到 100% 成功率"
        print(f"  总体结论: {overall}")

    if args.ci and not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
