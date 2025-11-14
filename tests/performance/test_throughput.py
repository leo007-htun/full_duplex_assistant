"""
Throughput and Concurrency Benchmarking Tests
Tests for measuring system capacity and concurrent session handling
"""

import pytest
import asyncio
import time
import statistics
from typing import List, Dict


class ThroughputBenchmark:
    """Track throughput metrics"""

    def __init__(self):
        self.metrics = {
            'requests_per_second': [],
            'concurrent_sessions': [],
            'total_requests': 0,
            'failed_requests': 0,
            'start_time': time.time()
        }

    def record_request(self, success: bool):
        self.metrics['total_requests'] += 1
        if not success:
            self.metrics['failed_requests'] += 1

    def calculate_rps(self) -> float:
        elapsed = time.time() - self.metrics['start_time']
        return self.metrics['total_requests'] / elapsed if elapsed > 0 else 0

    def get_error_rate(self) -> float:
        total = self.metrics['total_requests']
        return self.metrics['failed_requests'] / total if total > 0 else 0


@pytest.fixture
def throughput_benchmark():
    return ThroughputBenchmark()


@pytest.fixture
async def api_client():
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        yield client


# ==================== Request Rate Tests ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_sustained_request_rate(api_client, throughput_benchmark):
    """
    Test sustained request rate over time
    Target: 10 req/s for 30 seconds
    """
    duration_seconds = 30
    target_rps = 10

    start_time = time.time()
    end_time = start_time + duration_seconds

    requests_sent = 0

    while time.time() < end_time:
        try:
            response = await api_client.get("/healthz")
            success = response.status_code == 200
            throughput_benchmark.record_request(success)
            requests_sent += 1

            # Rate limiting: maintain target RPS
            await asyncio.sleep(1.0 / target_rps)

        except Exception as e:
            throughput_benchmark.record_request(False)
            print(f"Request failed: {e}")

    actual_rps = throughput_benchmark.calculate_rps()
    error_rate = throughput_benchmark.get_error_rate()

    print(f"\nSustained Load Test ({duration_seconds}s):")
    print(f"  Target RPS: {target_rps}")
    print(f"  Actual RPS: {actual_rps:.2f}")
    print(f"  Total Requests: {requests_sent}")
    print(f"  Error Rate: {error_rate * 100:.2f}%")

    assert actual_rps >= target_rps * 0.9, f"RPS {actual_rps:.2f} below target"
    assert error_rate < 0.05, f"Error rate {error_rate * 100:.1f}% too high"


# ==================== Concurrent Sessions Test ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_concurrent_sessions(api_client):
    """
    Test handling of concurrent connections
    Target: Support 50+ concurrent sessions
    """

    async def simulate_session(session_id: int, duration: float) -> Dict:
        """Simulate a single session with multiple requests"""
        start = time.time()
        requests = 0
        errors = 0

        while time.time() - start < duration:
            try:
                response = await api_client.get("/healthz")
                if response.status_code == 200:
                    requests += 1
                else:
                    errors += 1
            except:
                errors += 1

            await asyncio.sleep(0.1)  # 10 req/s per session

        return {
            'session_id': session_id,
            'requests': requests,
            'errors': errors,
            'duration': time.time() - start
        }

    # Test different concurrency levels
    concurrency_levels = [10, 25, 50]

    for concurrency in concurrency_levels:
        print(f"\nTesting {concurrency} concurrent sessions...")

        # Run concurrent sessions
        session_duration = 10  # seconds
        tasks = [simulate_session(i, session_duration) for i in range(concurrency)]

        start = time.time()
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        # Analyze results
        total_requests = sum(r['requests'] for r in results)
        total_errors = sum(r['errors'] for r in results)
        error_rate = total_errors / (total_requests + total_errors) if total_requests + total_errors > 0 else 0

        print(f"  Concurrency: {concurrency}")
        print(f"  Duration: {elapsed:.2f}s")
        print(f"  Total Requests: {total_requests}")
        print(f"  Total Errors: {total_errors}")
        print(f"  Error Rate: {error_rate * 100:.2f}%")
        print(f"  Throughput: {total_requests / elapsed:.2f} req/s")

        # Assertions
        assert error_rate < 0.10, f"Error rate {error_rate * 100:.1f}% too high at {concurrency} concurrent sessions"

        await asyncio.sleep(2)  # Cool down between tests


# ==================== Spike Load Test ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_spike_load(api_client):
    """
    Test response to sudden traffic spike
    Simulate 0 → 80 concurrent requests in 10 seconds
    """

    async def burst_request():
        start = time.perf_counter()
        try:
            response = await api_client.get("/healthz")
            latency = (time.perf_counter() - start) * 1000
            return {'success': response.status_code == 200, 'latency': latency}
        except:
            return {'success': False, 'latency': None}

    spike_sizes = [20, 40, 60, 80]
    results = {}

    for spike_size in spike_sizes:
        print(f"\nSpike test: {spike_size} concurrent requests...")

        tasks = [burst_request() for _ in range(spike_size)]
        responses = await asyncio.gather(*tasks)

        success_count = sum(1 for r in responses if r['success'])
        latencies = [r['latency'] for r in responses if r['latency'] is not None]

        results[spike_size] = {
            'success_rate': success_count / len(responses),
            'error_rate': 1 - (success_count / len(responses)),
            'mean_latency': statistics.mean(latencies) if latencies else 0,
            'p95_latency': sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
        }

        print(f"  Success Rate: {results[spike_size]['success_rate'] * 100:.1f}%")
        print(f"  Error Rate: {results[spike_size]['error_rate'] * 100:.1f}%")
        print(f"  Mean Latency: {results[spike_size]['mean_latency']:.2f}ms")
        print(f"  p95 Latency: {results[spike_size]['p95_latency']:.2f}ms")

        # Assert acceptable error rate
        assert results[spike_size]['error_rate'] < 0.05, \
            f"Error rate {results[spike_size]['error_rate'] * 100:.1f}% too high during spike"

        await asyncio.sleep(1)


# ==================== Rate Limiting Test ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_rate_limit_enforcement(api_client):
    """
    Test that rate limiting works correctly
    /rt-token should enforce 10 req/10s limit
    """

    # Send requests rapidly
    responses = []
    for i in range(15):
        try:
            response = await api_client.get("/rt-token")
            responses.append(response.status_code)
        except Exception as e:
            print(f"Request {i} error: {e}")
            responses.append(0)

        await asyncio.sleep(0.5)  # 2 req/s = 20 in 10s (exceeds limit)

    # Count rate limit responses
    rate_limited_count = sum(1 for status in responses if status == 429)
    success_count = sum(1 for status in responses if status == 200)

    print(f"\nRate Limit Test:")
    print(f"  Total Requests: {len(responses)}")
    print(f"  Success (200): {success_count}")
    print(f"  Rate Limited (429): {rate_limited_count}")

    # Should have some rate limited responses
    assert rate_limited_count > 0, "Rate limiting not enforced"


# ==================== Memory Leak Detection ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_memory_stability(api_client):
    """
    Test for memory leaks under sustained load
    Memory usage should stabilize, not grow continuously
    """
    import psutil
    import os

    # Get process for backend (approximate - this tests the client)
    process = psutil.Process(os.getpid())

    memory_samples = []
    iterations = 100
    requests_per_iteration = 10

    for i in range(iterations):
        # Make batch of requests
        tasks = [api_client.get("/healthz") for _ in range(requests_per_iteration)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Sample memory every 10 iterations
        if i % 10 == 0:
            mem_info = process.memory_info()
            memory_samples.append(mem_info.rss / 1024 / 1024)  # MB

    print(f"\nMemory Stability Test:")
    print(f"  Total Requests: {iterations * requests_per_iteration}")
    print(f"  Initial Memory: {memory_samples[0]:.2f} MB")
    print(f"  Final Memory: {memory_samples[-1]:.2f} MB")
    print(f"  Memory Growth: {memory_samples[-1] - memory_samples[0]:.2f} MB")

    # Check for continuous growth (potential leak)
    # Calculate linear regression slope
    if len(memory_samples) > 1:
        x = list(range(len(memory_samples)))
        mean_x = statistics.mean(x)
        mean_y = statistics.mean(memory_samples)

        slope = sum((x[i] - mean_x) * (memory_samples[i] - mean_y) for i in range(len(x))) / \
                sum((x[i] - mean_x) ** 2 for i in range(len(x)))

        print(f"  Growth Rate: {slope:.4f} MB/sample")

        # Assert memory growth is not excessive
        assert slope < 1.0, f"Potential memory leak detected: {slope:.2f} MB/sample growth"


# ==================== Throughput Report ====================

@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_generate_throughput_report(api_client, tmp_path):
    """
    Generate comprehensive throughput report
    """
    import json

    report = {
        'timestamp': time.time(),
        'tests': {}
    }

    # Quick throughput test
    duration = 10
    start = time.time()
    success = 0
    failed = 0

    while time.time() - start < duration:
        try:
            response = await api_client.get("/healthz")
            if response.status_code == 200:
                success += 1
            else:
                failed += 1
        except:
            failed += 1

        await asyncio.sleep(0.05)  # 20 req/s

    elapsed = time.time() - start
    report['tests']['throughput'] = {
        'duration_seconds': elapsed,
        'total_requests': success + failed,
        'successful_requests': success,
        'failed_requests': failed,
        'requests_per_second': (success + failed) / elapsed,
        'error_rate': failed / (success + failed) if success + failed > 0 else 0
    }

    # Save report
    report_file = tmp_path / "throughput_benchmark.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\nThroughput Report:")
    print(json.dumps(report, indent=2))

    assert report_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "benchmark"])
