# Performance Monitoring & Benchmarking Guide

This guide explains how to set up, deploy, and use the comprehensive performance monitoring and benchmarking system for the Full-Duplex Voice Assistant.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Installation](#installation)
4. [Running Benchmarks](#running-benchmarks)
5. [Monitoring Dashboard](#monitoring-dashboard)
6. [Metrics Reference](#metrics-reference)
7. [Alert Configuration](#alert-configuration)
8. [Best Practices](#best-practices)

---

## Quick Start

### 1. Start Monitoring Stack

```bash
cd monitoring
docker-compose -f docker-compose.monitoring.yml up -d
```

This starts:
- **Prometheus** (metrics storage) - http://localhost:9090
- **Grafana** (visualization) - http://localhost:3000
- **Node Exporter** (system metrics) - http://localhost:9100
- **AlertManager** (alerting) - http://localhost:9093

### 2. Access Grafana Dashboard

1. Open http://localhost:3000
2. Login with `admin` / `admin`
3. Navigate to Dashboards → "Full-Duplex Voice Assistant - Performance Dashboard"

### 3. Run Benchmarks

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx psutil

# Run all performance tests
pytest tests/performance/ -v -m benchmark

# Run specific test suite
pytest tests/performance/test_latency.py -v
pytest tests/performance/test_throughput.py -v
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser Client                       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  performance-tracker.js                              │  │
│  │  • Tracks E2E latency                                │  │
│  │  • Measures barge-in speed                           │  │
│  │  • Monitors streaming stability                      │  │
│  │  • Records quality metrics                           │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓ POST /api/metrics                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                         │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  core/metrics.py                                     │  │
│  │  • Prometheus metrics registry                       │  │
│  │  • MetricsMiddleware (HTTP tracking)                 │  │
│  │  • Resource monitoring                               │  │
│  │  • Client metrics ingestion                          │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓ /metrics endpoint                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                       Prometheus                            │
│  • Scrapes /metrics every 15s                              │
│  • Stores time-series data (30 days retention)             │
│  • Evaluates alert rules                                   │
│  • Triggers AlertManager                                   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                         Grafana                             │
│  • Queries Prometheus datasource                           │
│  • Visualizes metrics on dashboards                        │
│  • Displays alerts and annotations                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Installation

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js (for client-side integration)

### Backend Setup

1. **Install Python dependencies:**

```bash
cd src/assistant
pip install -r utils/requirements.txt
```

2. **Update your application to include metrics:**

The metrics system is already integrated into `app.py`. Ensure you have:

```python
from .core.metrics import (
    MetricsMiddleware,
    initialize_metrics,
    get_metrics_response
)

# Initialize metrics
initialize_metrics(version="1.0.0", environment="production")

# Add middleware
app.add_middleware(MetricsMiddleware)
```

3. **Expose metrics endpoint:**

The `/metrics` endpoint is already configured in `app.py`.

### Client-Side Setup

1. **Include performance tracker in your HTML:**

```html
<script src="performance-tracker.js"></script>
<script>
  // Initialize tracker
  const perfTracker = new PerformanceTracker({
    enableLogging: true,
    sendToServer: true,
    serverEndpoint: '/api/metrics',
    aggregationInterval: 10000  // Send metrics every 10s
  });

  // Track events in your application
  perfTracker.markSpeechStart();
  perfTracker.trackFirstTranscript();
  // ... etc
</script>
```

2. **Integration with existing code:**

See `web/script.js` for integration examples with the WebSocket client.

---

## Running Benchmarks

### Latency Tests

```bash
# Run all latency benchmarks
pytest tests/performance/test_latency.py -v -m benchmark

# Run with detailed output
pytest tests/performance/test_latency.py -v -s

# Generate benchmark report
pytest tests/performance/test_latency.py::test_generate_latency_report -v
```

**Metrics tested:**
- Token minting latency (p50, p95, p99)
- Health check latency
- Network round-trip time
- Concurrent request latency
- Latency degradation under load

### Throughput Tests

```bash
# Run throughput benchmarks
pytest tests/performance/test_throughput.py -v -m benchmark

# Test specific scenarios
pytest tests/performance/test_throughput.py::test_concurrent_sessions -v
pytest tests/performance/test_throughput.py::test_spike_load -v
```

**Metrics tested:**
- Sustained request rate (req/s)
- Concurrent session handling (10, 25, 50 sessions)
- Spike load tolerance (20-80 concurrent requests)
- Rate limiting enforcement
- Memory stability (leak detection)

### Regression Testing

```bash
# Compare against baseline
pytest tests/performance/ -v -m regression

# Update baseline after improvements
cp /tmp/pytest-*/latency_benchmark.json tests/benchmarks/baseline_results.json
```

### Load Testing with Artillery

```bash
# Install Artillery
npm install -g artillery

# Run WebSocket load test
artillery run tests/load/websocket-load.yml

# Run HTTP endpoint test
artillery run tests/load/http-load.yml
```

---

## Monitoring Dashboard

### Accessing Grafana

1. **URL:** http://localhost:3000
2. **Default credentials:** admin / admin (change on first login)

### Dashboard Panels

The main dashboard includes:

#### 1. **Service Health Overview**
- Service status (up/down)
- Active WebSocket connections
- Request rate

#### 2. **Latency Metrics**
- **End-to-End Latency:** p50, p95, p99 over time
- **Barge-In Latency:** Interruption response time
- **Component Latencies:** ASR, LLM (TTFT), TTS breakdown

#### 3. **Streaming Stability**
- Packet loss rate (%)
- Network jitter (ms)
- Network Quality Index (0-1 scale)
- Audio underrun events

#### 4. **Throughput**
- API request rate (req/s)
- WebSocket messages/sec
- Concurrent sessions

#### 5. **Resource Utilization**
- CPU usage (%)
- Memory usage (%)
- Process memory (RSS)

#### 6. **Errors & Alerts**
- HTTP errors by status code
- Rate limit violations
- WebSocket disconnections
- Recent alerts

### Creating Custom Dashboards

1. Navigate to Dashboards → New Dashboard
2. Add panel with query:
   ```promql
   # Example: 95th percentile E2E latency
   histogram_quantile(0.95, rate(e2e_latency_client_milliseconds_bucket[5m]))
   ```
3. Configure visualization (Time series, Gauge, Stat, etc.)
4. Save dashboard

---

## Metrics Reference

### Client-Side Metrics

Tracked by `performance-tracker.js`:

| Metric | Description | Unit |
|--------|-------------|------|
| `e2e_latency` | Speech → audio response | ms |
| `barge_in_latency` | Interruption detection → playback stop | ms |
| `asr_processing` | Speech → first transcript | ms |
| `llm_ttft` | Request → first token | ms |
| `tts_processing` | Text → first audio chunk | ms |
| `packet_loss_rate` | Dropped packets / total | % |
| `jitter` | Variance in packet arrival | ms |
| `network_quality_index` | Composite network score | 0-1 |

### Server-Side Metrics

Exposed at `/metrics` endpoint:

#### Latency Metrics
- `token_mint_latency_seconds` - Token minting duration
- `openai_api_latency_seconds` - OpenAI API call duration
- `http_request_latency_seconds` - HTTP request duration

#### Throughput Metrics
- `api_requests_total` - Total API requests
- `websocket_connections_active` - Current WebSocket connections
- `websocket_messages_sent_total` - Messages sent to clients
- `websocket_messages_received_total` - Messages from clients

#### Quality Metrics
- `conversation_turns_total` - User/assistant turns
- `conversation_interruptions_total` - Barge-in events
- `asr_transcription_delay_milliseconds` - ASR finalization time

#### Error Metrics
- `rate_limit_exceeded_total` - Rate limit violations
- `http_errors_total` - HTTP errors by code
- `application_errors_total` - Application-level errors

#### Resource Metrics
- `system_cpu_percent` - System CPU usage
- `system_memory_bytes` - System memory (used/available/total)
- `process_memory_bytes` - Process memory (RSS/VMS)
- `process_cpu_percent` - Process CPU usage

### Query Examples

```promql
# Average E2E latency over 5 minutes
rate(e2e_latency_client_milliseconds_sum[5m]) / rate(e2e_latency_client_milliseconds_count[5m])

# Error rate percentage
rate(http_errors_total[5m]) / rate(api_requests_total[5m]) * 100

# WebSocket reconnection rate per hour
rate(streaming_reconnections_total[1h]) * 3600

# Memory growth rate (MB/10min)
rate(process_memory_bytes{type="rss"}[10m]) / 1024 / 1024 * 600
```

---

## Alert Configuration

### Alert Rules

Defined in `prometheus/alerts.yml`:

#### Critical Alerts (PagerDuty/Slack)
- `HighEndToEndLatency` - p95 > 2000ms for 5min
- `HighErrorRate` - >5 errors/sec for 2min
- `ServiceDown` - Service unreachable for 1min
- `HighCPUUsage` - CPU >90% for 3min

#### Warning Alerts (Slack)
- `SlowTokenMinting` - p95 > 1s for 5min
- `SlowBargeInResponse` - p95 > 500ms for 3min
- `HighPacketLoss` - >1% loss for 2min
- `HighMemoryUsage` - >85% memory for 5min

### AlertManager Configuration

Edit `alertmanager/alertmanager.yml`:

```yaml
route:
  receiver: 'slack-notifications'
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 3h

receivers:
  - name: 'slack-notifications'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts'
        title: 'Voice Assistant Alert'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_KEY'
```

### Testing Alerts

```bash
# Trigger high latency alert (simulate load)
ab -n 10000 -c 50 http://localhost:8000/rt-token

# Check firing alerts
curl http://localhost:9090/api/v1/alerts
```

---

## Best Practices

### 1. Baseline Establishment

Before optimizing, establish baseline metrics:

```bash
# Run baseline benchmark
pytest tests/performance/ -v -m benchmark

# Save baseline
cp /tmp/pytest-*/latency_benchmark.json tests/benchmarks/baseline_results.json

# Commit to git
git add tests/benchmarks/baseline_results.json
git commit -m "Add performance baseline"
```

### 2. Continuous Monitoring

Set up daily automated benchmarks:

```yaml
# .github/workflows/performance.yml
name: Daily Performance Benchmarks

on:
  schedule:
    - cron: '0 3 * * *'  # 3 AM daily

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run benchmarks
        run: |
          pytest tests/performance/ -v -m benchmark
      - name: Compare against baseline
        run: |
          pytest tests/performance/ -v -m regression
```

### 3. Alert Fatigue Prevention

- Set appropriate thresholds (allow some variance)
- Use `for` duration to avoid transient spikes
- Group related alerts
- Set up on-call rotation for critical alerts only

### 4. Dashboard Organization

Create role-specific dashboards:

- **Developer Dashboard:** Latency breakdown, error details
- **Operations Dashboard:** Resource usage, uptime, errors
- **Executive Dashboard:** High-level metrics, SLA compliance

### 5. Capacity Planning

Monitor trends over time:

```promql
# Predict when you'll hit capacity
predict_linear(websocket_connections_active[1w], 86400 * 7)
```

### 6. A/B Testing

Use metrics to validate changes:

```python
# Tag metrics with experiment variant
from .core.metrics import api_requests_total

api_requests_total.labels(
    method="GET",
    endpoint="/rt-token",
    variant="experiment_b"  # Add variant label
).inc()
```

---

## Troubleshooting

### Metrics Not Appearing

1. **Check backend is exposing metrics:**
   ```bash
   curl http://localhost:8000/metrics
   ```

2. **Verify Prometheus is scraping:**
   - Open http://localhost:9090/targets
   - Check "assistant-backend" target status

3. **Check Prometheus logs:**
   ```bash
   docker logs prometheus
   ```

### Dashboard Not Loading

1. **Verify Grafana datasource:**
   - Configuration → Data Sources → Prometheus
   - Click "Test" button

2. **Check dashboard JSON syntax:**
   ```bash
   cat monitoring/grafana/dashboards/voice-assistant-performance.json | jq .
   ```

### High Cardinality Issues

If Prometheus is slow/consuming too much memory:

1. **Reduce label cardinality:**
   - Don't use user IDs or timestamps as labels
   - Limit label values (e.g., aggregate rare status codes)

2. **Adjust retention:**
   ```yaml
   # prometheus.yml
   --storage.tsdb.retention.time=15d  # Reduce from 30d
   ```

---

## Academic Evaluation

For research paper publication, use the comprehensive evaluation suite:

```bash
# Run full evaluation suite
pytest tests/performance/ -v --tb=short

# Generate academic report
python tests/performance/generate_academic_report.py \
  --output paper_results/ \
  --format latex
```

This generates:
- LaTeX tables with statistical significance tests
- Plots comparing against baseline systems
- Ablation study results
- Multi-condition robustness tests (network quality, accents, noise)

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/your-repo/issues
- Monitoring Stack: https://prometheus.io/docs/
- Grafana Docs: https://grafana.com/docs/

---

**Last Updated:** 2025-11-14
**Version:** 1.0.0
