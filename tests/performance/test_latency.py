"""
End-to-End Latency Benchmarking Tests
Tests for measuring latency across the full voice assistant pipeline
"""

import pytest
import asyncio
import time
import json
from pathlib import Path
from typing import Dict, List
import statistics

# Test configuration
BASELINE_E2E_LATENCY_MS = 1200  # p95 target
BASELINE_TOKEN_MINT_MS = 500
BASELINE_ASR_LATENCY_MS = 300
BASELINE_TTS_LATENCY_MS = 400


class LatencyBenchmark:
    """Tracks latency measurements for benchmarking"""

    def __init__(self):
        self.measurements: Dict[str, List[float]] = {
            'e2e_latency': [],
            'token_mint': [],
            'asr_processing': [],
            'llm_ttft': [],
            'tts_processing': [],
            'network_rtt': []
        }

    def record(self, metric: str, value_ms: float):
        """Record a latency measurement"""
        if metric in self.measurements:
            self.measurements[metric].append(value_ms)

    def get_stats(self, metric: str) -> Dict:
        """Calculate statistics for a metric"""
        values = self.measurements.get(metric, [])
        if not values:
            return {}

        sorted_values = sorted(values)
        return {
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'mean': statistics.mean(values),
            'median': statistics.median(values),
            'p95': sorted_values[int(len(sorted_values) * 0.95)] if len(sorted_values) > 0 else 0,
            'p99': sorted_values[int(len(sorted_values) * 0.99)] if len(sorted_values) > 0 else 0,
            'stddev': statistics.stdev(values) if len(values) > 1 else 0
        }

    def generate_report(self) -> Dict:
        """Generate comprehensive latency report"""
        return {
            metric: self.get_stats(metric)
            for metric in self.measurements.keys()
        }


@pytest.fixture
def benchmark():
    """Fixture providing benchmark tracker"""
    return LatencyBenchmark()


@pytest.fixture
async def api_client():
    """Fixture providing HTTP client for API calls"""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        yield client


# ==================== Token Minting Latency Tests ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_token_mint_latency(api_client, benchmark):
    """
    Measure token minting latency (L5 component)
    Tests the /rt-token endpoint performance
    """
    iterations = 10

    for i in range(iterations):
        start = time.perf_counter()

        try:
            response = await api_client.get("/rt-token")
            assert response.status_code == 200

            elapsed_ms = (time.perf_counter() - start) * 1000
            benchmark.record('token_mint', elapsed_ms)

            # Avoid rate limiting
            if i < iterations - 1:
                await asyncio.sleep(1.1)

        except Exception as e:
            pytest.fail(f"Token mint failed: {e}")

    stats = benchmark.get_stats('token_mint')
    print(f"\nToken Mint Latency Stats:")
    print(f"  Mean: {stats['mean']:.2f}ms")
    print(f"  p95: {stats['p95']:.2f}ms")
    print(f"  p99: {stats['p99']:.2f}ms")

    # Assert against baseline
    assert stats['p95'] < BASELINE_TOKEN_MINT_MS, \
        f"Token mint p95 latency {stats['p95']:.2f}ms exceeds baseline {BASELINE_TOKEN_MINT_MS}ms"


# ==================== Health Check Latency ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_healthcheck_latency(api_client):
    """
    Measure health check endpoint latency
    Should be consistently fast (<10ms)
    """
    latencies = []

    for _ in range(100):
        start = time.perf_counter()
        response = await api_client.get("/healthz")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert response.status_code == 200
        assert response.json()['status'] == 'ok'

        latencies.append(elapsed_ms)

    mean = statistics.mean(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]

    print(f"\nHealth Check Latency:")
    print(f"  Mean: {mean:.2f}ms")
    print(f"  p95: {p95:.2f}ms")

    assert p95 < 50, f"Health check p95 {p95:.2f}ms too high"


# ==================== Network RTT Measurement ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_network_rtt(api_client, benchmark):
    """
    Measure round-trip time to backend
    """
    for _ in range(20):
        start = time.perf_counter()
        response = await api_client.get("/healthz")
        rtt_ms = (time.perf_counter() - start) * 1000

        assert response.status_code == 200
        benchmark.record('network_rtt', rtt_ms)

        await asyncio.sleep(0.1)

    stats = benchmark.get_stats('network_rtt')
    print(f"\nNetwork RTT Stats:")
    print(f"  Mean: {stats['mean']:.2f}ms")
    print(f"  p95: {stats['p95']:.2f}ms")


# ==================== Concurrent Request Latency ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_concurrent_request_latency(api_client):
    """
    Test latency under concurrent load
    Ensures latency doesn't degrade significantly with concurrency
    """

    async def make_request():
        start = time.perf_counter()
        response = await api_client.get("/healthz")
        return (time.perf_counter() - start) * 1000, response.status_code

    # Test different concurrency levels
    concurrency_levels = [1, 5, 10, 20]
    results = {}

    for concurrency in concurrency_levels:
        tasks = [make_request() for _ in range(concurrency)]
        responses = await asyncio.gather(*tasks)

        latencies = [lat for lat, status in responses if status == 200]
        p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

        results[concurrency] = {
            'mean': statistics.mean(latencies),
            'p95': p95
        }

        print(f"\nConcurrency {concurrency}:")
        print(f"  Mean: {results[concurrency]['mean']:.2f}ms")
        print(f"  p95: {results[concurrency]['p95']:.2f}ms")

        await asyncio.sleep(0.5)

    # Check latency degradation
    baseline_p95 = results[1]['p95']
    max_p95 = results[max(concurrency_levels)]['p95']

    degradation = (max_p95 - baseline_p95) / baseline_p95 if baseline_p95 > 0 else 0
    print(f"\nLatency degradation at max concurrency: {degradation * 100:.1f}%")

    assert degradation < 2.0, f"Latency degraded {degradation * 100:.1f}% under load"


# ==================== Benchmarking Report Generator ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_generate_latency_report(api_client, benchmark, tmp_path):
    """
    Run full latency benchmark suite and generate report
    """

    # Token minting
    for _ in range(5):
        start = time.perf_counter()
        try:
            response = await api_client.get("/rt-token")
            if response.status_code == 200:
                benchmark.record('token_mint', (time.perf_counter() - start) * 1000)
        except:
            pass
        await asyncio.sleep(1.5)

    # Generate report
    report = benchmark.generate_report()
    report['timestamp'] = time.time()
    report['test_environment'] = 'localhost'

    # Save to file
    report_file = tmp_path / "latency_benchmark.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\nBenchmark report saved to: {report_file}")
    print(json.dumps(report, indent=2))

    assert report_file.exists()


# ==================== Baseline Comparison ====================

def load_baseline_metrics(baseline_path: Path) -> Dict:
    """Load baseline metrics from previous run"""
    if not baseline_path.exists():
        return {}
    with open(baseline_path) as f:
        return json.load(f)


@pytest.mark.asyncio
@pytest.mark.regression
async def test_latency_regression(api_client, tmp_path):
    """
    Compare current performance against baseline
    Fails if performance has regressed significantly
    """
    baseline_file = Path("tests/benchmarks/baseline_results.json")
    baseline = load_baseline_metrics(baseline_file)

    if not baseline:
        pytest.skip("No baseline metrics found")

    # Run current benchmark
    current_benchmark = LatencyBenchmark()

    for _ in range(10):
        start = time.perf_counter()
        response = await api_client.get("/healthz")
        if response.status_code == 200:
            current_benchmark.record('health_check', (time.perf_counter() - start) * 1000)

    current_stats = current_benchmark.get_stats('health_check')

    # Compare against baseline
    if 'health_check' in baseline:
        baseline_p95 = baseline['health_check'].get('p95', 0)
        current_p95 = current_stats['p95']

        regression = (current_p95 - baseline_p95) / baseline_p95 if baseline_p95 > 0 else 0

        print(f"\nRegression Test:")
        print(f"  Baseline p95: {baseline_p95:.2f}ms")
        print(f"  Current p95: {current_p95:.2f}ms")
        print(f"  Regression: {regression * 100:.1f}%")

        assert regression < 0.2, f"Performance regressed by {regression * 100:.1f}%"


# ==================== pytest Configuration ====================

def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "benchmark: mark test as benchmark test")
    config.addinivalue_line("markers", "regression: mark test as regression test")


if __name__ == "__main__":
    # Run benchmarks directly
    pytest.main([__file__, "-v", "-m", "benchmark", "--tb=short"])
