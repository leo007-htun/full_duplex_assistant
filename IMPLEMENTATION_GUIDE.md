# Performance Metrics & Benchmarking Implementation Guide

## Overview

This guide provides step-by-step instructions for integrating the comprehensive performance metrics and benchmarking system into your Full-Duplex Voice Assistant pipeline deployed on com-loud.cloud.

## What Has Been Added

### 📊 New Files Created

```
full_duplex_assistant/
├── docs/
│   └── performance_metrics_design.md          # Academic-level design document
├── web/
│   └── performance-tracker.js                 # Client-side metrics tracking
├── src/assistant/
│   └── core/
│       └── metrics.py                         # Backend Prometheus metrics
├── tests/
│   └── performance/
│       ├── test_latency.py                    # E2E latency benchmarks
│       └── test_throughput.py                 # Throughput & load tests
└── monitoring/
    ├── docker-compose.monitoring.yml          # Prometheus + Grafana stack
    ├── prometheus/
    │   ├── prometheus.yml                     # Prometheus config
    │   └── alerts.yml                         # Alert rules
    ├── grafana/
    │   ├── provisioning/
    │   │   ├── datasources/prometheus.yml
    │   │   └── dashboards/dashboard.yml
    │   └── dashboards/
    │       └── voice-assistant-performance.json  # Main dashboard
    └── README.md                              # Complete monitoring guide
```

### 🔧 Modified Files

- `src/assistant/app.py` - Added metrics middleware and endpoints
- `src/assistant/utils/requirements.txt` - Added prometheus-client and psutil

---

## Step-by-Step Implementation

### Phase 1: Backend Integration (30 minutes)

#### 1.1 Install Dependencies

```bash
cd /home/leo/full_duplex_assistant

# Install new Python dependencies
pip install prometheus-client>=0.19.0 psutil>=5.9.0

# Or reinstall from requirements.txt
pip install -r src/assistant/utils/requirements.txt
```

#### 1.2 Verify Backend Changes

The following has already been integrated into [app.py](src/assistant/app.py):

- ✅ Metrics middleware for automatic HTTP request tracking
- ✅ `/metrics` endpoint for Prometheus scraping
- ✅ `/api/metrics` endpoint for client metrics ingestion
- ✅ Token minting latency tracking
- ✅ Rate limit violation tracking

**Test the metrics endpoint:**

```bash
# Start your backend
cd src/assistant
python -m uvicorn app:app --reload

# In another terminal, check metrics
curl http://localhost:8000/metrics
```

You should see Prometheus-formatted metrics like:
```
# HELP service_up Service health status (1=up, 0=down)
# TYPE service_up gauge
service_up 1.0
# HELP token_mint_latency_seconds Token minting latency
# TYPE token_mint_latency_seconds histogram
...
```

#### 1.3 Update Docker Build

Since the Dockerfile installs from requirements.txt, the new dependencies will be included automatically on next build:

```bash
# Rebuild Docker image with new dependencies
docker build -t sithuyehtun/full_duplex_assistant:latest -f src/assistant/utils/Dockerfile .

# Or let CI/CD rebuild on next push to main
```

---

### Phase 2: Client-Side Integration (45 minutes)

#### 2.1 Add Performance Tracker to Frontend

**Option A: Direct inclusion (simplest)**

Add to [web/index.html](web/index.html) before the closing `</body>` tag:

```html
<!-- Performance Tracking -->
<script src="performance-tracker.js"></script>
<script>
  // Initialize performance tracker
  const perfTracker = new PerformanceTracker({
    enableLogging: true,           // Log to console
    sendToServer: true,            // Send to backend API
    serverEndpoint: '/api/metrics',
    aggregationInterval: 10000     // Report every 10 seconds
  });

  // Make globally accessible
  window.perfTracker = perfTracker;
</script>
```

#### 2.2 Integrate with Existing WebSocket Code

Update [web/script.js](web/script.js) to track metrics at key points:

**Example integration points:**

```javascript
// 1. Track speech start
function onLocalVADSpeechStart() {
  perfTracker.markSpeechStart();
  // ... existing code
}

// 2. Track speech end
function onLocalVADSpeechEnd() {
  perfTracker.markSpeechEnd();
  // ... existing code
}

// 3. Track audio send
function sendAudioChunk(audioData) {
  const timestamp = perfTracker.trackAudioSend(audioData.byteLength);
  // ... existing WebSocket send code
}

// 4. Track first transcript
ws.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === 'conversation.item.input_audio_transcription.delta') {
    perfTracker.trackFirstTranscript();
  }

  if (msg.type === 'conversation.item.input_audio_transcription.completed') {
    perfTracker.trackFinalTranscript();
  }

  // ... existing handlers
});

// 5. Track response created
if (msg.type === 'response.created') {
  perfTracker.trackResponseCreated();
}

// 6. Track first audio delta
if (msg.type === 'response.audio.delta') {
  perfTracker.trackFirstAudioDelta(msg.item_id);
  perfTracker.trackAudioReceived(msg.delta.length);
}

// 7. Track audio playback start
function onAudioPlaybackStart() {
  perfTracker.trackAudioPlaybackStart();
  // ... existing code
}

// 8. Track response complete
function onResponseComplete() {
  perfTracker.trackResponseComplete();
  // ... existing code
}

// 9. Track barge-in
function handleBargeIn() {
  const bargeInStart = performance.now();

  // Stop audio playback
  stopAudioPlayback();
  perfTracker.trackBargeIn('playback_stop', bargeInStart);

  // Cancel server response
  sendCancelMessage();
  perfTracker.trackBargeIn('server_cancel', bargeInStart);

  // Track total barge-in time
  perfTracker.trackBargeIn('total', bargeInStart);
}

// 10. Track errors
ws.addEventListener('error', (error) => {
  perfTracker.trackError('websocket', { message: error.message });
});

// 11. Track reconnections
function reconnectWebSocket() {
  perfTracker.trackReconnection();
  // ... existing reconnect logic
}
```

#### 2.3 Add Metrics Export Button (Optional)

Add a button to download metrics for debugging:

```html
<button id="export-metrics" style="position: fixed; bottom: 10px; right: 10px;">
  📊 Export Metrics
</button>

<script>
  document.getElementById('export-metrics').addEventListener('click', () => {
    perfTracker.exportMetrics();
  });
</script>
```

---

### Phase 3: Monitoring Stack Deployment (15 minutes)

#### 3.1 Start Monitoring Services Locally

```bash
cd monitoring

# Start Prometheus + Grafana + AlertManager
docker-compose -f docker-compose.monitoring.yml up -d

# Check services are running
docker ps | grep -E "prometheus|grafana|alertmanager"
```

Services will be available at:
- **Prometheus:** http://localhost:9090
- **Grafana:** http://localhost:3000 (admin/admin)
- **AlertManager:** http://localhost:9093

#### 3.2 Configure Prometheus Target

If running locally, Prometheus is configured to scrape `host.docker.internal:8000/metrics`.

For production deployment, edit [monitoring/prometheus/prometheus.yml](monitoring/prometheus/prometheus.yml):

```yaml
scrape_configs:
  - job_name: 'assistant-backend'
    metrics_path: '/metrics'
    static_configs:
      - targets:
          - 'com-cloud.cloud:443'  # Your production domain
    scheme: https
    scrape_interval: 10s
```

#### 3.3 Access Grafana Dashboard

1. Open http://localhost:3000
2. Login with `admin` / `admin` (change password)
3. Navigate to **Dashboards** → **Full-Duplex Voice Assistant - Performance Dashboard**
4. You should see real-time metrics updating

---

### Phase 4: Production Deployment on com-cloud.cloud (30 minutes)

#### 4.1 Update Docker Compose for Production

Add monitoring services to your existing [docker-compose.yml](docker-compose.yml):

```yaml
# Add to existing docker-compose.yml
services:
  # ... existing services (traefik, web, assistant)

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus:/etc/prometheus:ro
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
    networks:
      - web
    restart: unless-stopped
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.prometheus.rule=Host(`com-cloud.cloud`) && PathPrefix(`/prometheus`)"
      - "traefik.http.routers.prometheus.tls=true"
      - "traefik.http.routers.prometheus.tls.certresolver=letsencrypt"
      # Add basic auth for security
      - "traefik.http.routers.prometheus.middlewares=auth"
      - "traefik.http.middlewares.auth.basicauth.users=admin:$$apr1$$..."  # htpasswd hash

  grafana:
    image: grafana/grafana:latest
    volumes:
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro
      - grafana-data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
      - GF_SERVER_ROOT_URL=https://com-cloud.cloud/grafana
      - GF_SERVER_SERVE_FROM_SUB_PATH=true
    networks:
      - web
    restart: unless-stopped
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.grafana.rule=Host(`com-cloud.cloud`) && PathPrefix(`/grafana`)"
      - "traefik.http.routers.grafana.tls=true"
      - "traefik.http.routers.grafana.tls.certresolver=letsencrypt"

volumes:
  prometheus-data:
  grafana-data:
```

#### 4.2 Add Environment Variables

Add to your `.env` file:

```bash
GRAFANA_PASSWORD=your_secure_password_here
```

#### 4.3 Update Prometheus Configuration for Production

Edit [monitoring/prometheus/prometheus.yml](monitoring/prometheus/prometheus.yml):

```yaml
scrape_configs:
  - job_name: 'assistant-backend'
    metrics_path: '/metrics'
    static_configs:
      - targets:
          - 'assistant:8000'  # Internal Docker network
    scrape_interval: 10s
```

#### 4.4 Deploy to Production

```bash
# SSH to your server
ssh user@your-server-ip

# Pull latest code
cd /path/to/full_duplex_assistant
git pull

# Rebuild and restart services
docker-compose build assistant
docker-compose up -d

# Check all services are healthy
docker-compose ps
docker-compose logs -f prometheus grafana
```

#### 4.5 Verify Production Deployment

1. **Check metrics endpoint:**
   ```bash
   curl https://com-cloud.cloud/metrics
   ```

2. **Access Grafana:**
   - URL: https://com-cloud.cloud/grafana
   - Login with your configured password

3. **Verify Prometheus targets:**
   - URL: https://com-cloud.cloud/prometheus/targets
   - All targets should show "UP" status

---

### Phase 5: Benchmarking & Testing (20 minutes)

#### 5.1 Install Test Dependencies

```bash
pip install pytest pytest-asyncio httpx psutil
```

#### 5.2 Run Baseline Benchmarks

```bash
# Run all performance tests
pytest tests/performance/ -v -m benchmark

# Run specific test suites
pytest tests/performance/test_latency.py -v
pytest tests/performance/test_throughput.py -v

# Generate detailed report with timing
pytest tests/performance/ -v -s --tb=short
```

#### 5.3 Save Baseline Results

```bash
# Find the generated report
ls -la /tmp/pytest-*/*.json

# Copy to benchmarks directory
cp /tmp/pytest-*/latency_benchmark.json tests/benchmarks/baseline_results.json

# Commit baseline
git add tests/benchmarks/baseline_results.json
git commit -m "Add performance baseline results"
```

#### 5.4 Setup Continuous Benchmarking (Optional)

Add to [.github/workflows/performance.yml](.github/workflows/performance.yml):

```yaml
name: Performance Benchmarks

on:
  schedule:
    - cron: '0 3 * * *'  # Daily at 3 AM
  workflow_dispatch:

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r src/assistant/utils/requirements.txt
          pip install pytest pytest-asyncio httpx psutil

      - name: Start backend
        run: |
          cd src/assistant
          uvicorn app:app &
          sleep 5

      - name: Run benchmarks
        run: |
          pytest tests/performance/ -v -m benchmark

      - name: Compare against baseline
        run: |
          pytest tests/performance/ -v -m regression
```

---

## Validation Checklist

Use this checklist to verify your implementation:

### Backend ✅

- [ ] `/metrics` endpoint returns Prometheus metrics
- [ ] `/api/metrics` endpoint accepts POST requests
- [ ] Token minting latency is tracked
- [ ] Rate limit violations are counted
- [ ] HTTP requests are tracked by MetricsMiddleware
- [ ] Resource metrics (CPU, memory) are updated

**Test command:**
```bash
curl http://localhost:8000/metrics | grep -E "service_up|token_mint_latency|api_requests_total"
```

### Client-Side ✅

- [ ] `performance-tracker.js` is loaded
- [ ] PerformanceTracker instance is created
- [ ] Speech start/end events are tracked
- [ ] Transcription events trigger metrics
- [ ] Audio send/receive is tracked
- [ ] Barge-in events are captured
- [ ] Metrics are sent to `/api/metrics` every 10s

**Test:** Open browser console and check for:
```
[Metrics] Speech started
[Metrics] ASR latency: 245.32ms
[Metrics] Time to First Token: 312.45ms
[Metrics] End-to-End Latency: 1056.78ms
[Metrics] Periodic Report: {...}
```

### Monitoring Stack ✅

- [ ] Prometheus is scraping metrics successfully
- [ ] Grafana dashboard shows live data
- [ ] All panels are populated (no "No data" errors)
- [ ] Alerts are configured and visible
- [ ] AlertManager is receiving alerts

**Test:**
1. Open http://localhost:9090/targets - all targets should be "UP"
2. Query: `service_up` - should return 1
3. Open http://localhost:3000 - dashboard shows graphs

### Production Deployment ✅

- [ ] Monitoring services are running on com-cloud.cloud
- [ ] HTTPS access to Grafana works
- [ ] Prometheus is scraping production backend
- [ ] Client metrics are flowing to backend
- [ ] Alerts are configured for Slack/PagerDuty

---

## Next Steps

### 1. Customize Alerts

Edit [monitoring/prometheus/alerts.yml](monitoring/prometheus/alerts.yml) to match your SLAs:

```yaml
- alert: HighEndToEndLatency
  expr: histogram_quantile(0.95, rate(e2e_latency_client_milliseconds_bucket[5m])) > 1500  # Adjust threshold
  for: 5m
```

### 2. Add Custom Metrics

Track domain-specific metrics in your code:

```python
# Backend
from .core.metrics import Counter

user_intents_total = Counter(
    'user_intents_total',
    'Total user intents by type',
    ['intent_type']
)

user_intents_total.labels(intent_type='weather').inc()
```

```javascript
// Client
perfTracker.quality.userIntents = {
  weather: 5,
  calendar: 3,
  general: 12
};
```

### 3. Create Additional Dashboards

- **User Experience Dashboard:** Focus on latency and quality
- **Operations Dashboard:** Resource usage, errors, alerts
- **Business Metrics:** Usage patterns, conversation analytics

### 4. Setup Alerting

Configure AlertManager with your notification channels:

```yaml
# monitoring/alertmanager/alertmanager.yml
receivers:
  - name: 'slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#voice-assistant-alerts'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
```

### 5. Run Load Tests

Stress test your system to find capacity limits:

```bash
# Install Apache Bench
sudo apt-get install apache2-utils

# Test concurrent requests
ab -n 1000 -c 50 https://com-cloud.cloud/rt-token

# Monitor dashboard during load test
```

---

## Troubleshooting

### Issue: "No data" in Grafana

**Solution:**
1. Check Prometheus targets: http://localhost:9090/targets
2. If "DOWN", verify backend is exposing `/metrics`
3. Check firewall/network connectivity
4. Verify Grafana datasource configuration

### Issue: Client metrics not appearing

**Solution:**
1. Open browser console, check for errors
2. Verify `/api/metrics` endpoint is accessible
3. Check CORS configuration in backend
4. Inspect Network tab for failed POST requests

### Issue: High memory usage in Prometheus

**Solution:**
1. Reduce retention period: `--storage.tsdb.retention.time=15d`
2. Check for high cardinality labels
3. Reduce scrape interval for less critical metrics

---

## Resources

- **Design Document:** [docs/performance_metrics_design.md](docs/performance_metrics_design.md)
- **Monitoring Guide:** [monitoring/README.md](monitoring/README.md)
- **Prometheus Docs:** https://prometheus.io/docs/
- **Grafana Docs:** https://grafana.com/docs/
- **OpenTelemetry (future upgrade):** https://opentelemetry.io/

---

## Summary

You now have:

✅ **Client-side performance tracking** - Tracks E2E latency, barge-in speed, streaming stability
✅ **Backend metrics collection** - Prometheus-compatible metrics for all key operations
✅ **Comprehensive benchmarking suite** - Automated latency and throughput tests
✅ **Real-time monitoring dashboard** - Grafana visualization with 12+ panels
✅ **Alerting system** - Configurable alerts for critical issues
✅ **Production-ready deployment** - Docker Compose stack for com-cloud.cloud

Your pipeline now has **academic-grade evaluation capabilities** suitable for research papers, performance optimization, and production monitoring.

---

**Questions or Issues?**
File an issue on GitHub or consult the monitoring README for detailed troubleshooting.
