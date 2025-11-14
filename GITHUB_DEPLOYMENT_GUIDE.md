# GitHub Deployment Guide - Performance Metrics System

This guide explains how to deploy the performance metrics system through your existing GitHub CI/CD pipeline.

## 🚀 Deployment Options

### Option 1: Backend Metrics Only (Simplest - Recommended First)

Deploy just the backend metrics endpoints. No additional services needed.

**What gets deployed:**
- ✅ `/metrics` endpoint (Prometheus format)
- ✅ `/api/metrics` endpoint (client data ingestion)
- ✅ Automatic HTTP request tracking
- ✅ Token minting latency tracking
- ✅ Rate limit violation tracking
- ✅ Resource monitoring (CPU, memory)

**Steps:**

```bash
# 1. Commit your changes
cd /home/leo/full_duplex_assistant
git add .
git commit -m "feat: Add comprehensive performance metrics system

- Add Prometheus metrics collection in backend
- Add client-side performance tracker
- Add benchmarking test suite
- Add Grafana dashboard configuration
- Update dependencies (prometheus-client, psutil)"

# 2. Push to GitHub (triggers automatic deployment)
git push origin main

# 3. Monitor deployment
# Visit: https://github.com/YOUR_USERNAME/full_duplex_assistant/actions
# Watch the "Deploy to Production" workflow

# 4. After deployment completes (5-10 minutes), verify:
curl https://com-cloud.cloud/metrics

# Should output Prometheus metrics:
# service_up 1.0
# api_requests_total{method="GET",endpoint="/healthz",status="200"} 42
# ...
```

**Access metrics:**
- Metrics endpoint: https://com-cloud.cloud/metrics
- You can scrape this with any external Prometheus instance

---

### Option 2: Full Monitoring Stack (Production-Grade)

Deploy the complete monitoring infrastructure with Prometheus + Grafana + AlertManager.

**What gets deployed:**
- ✅ Everything from Option 1
- ✅ Prometheus (metrics storage, 30 days retention)
- ✅ Grafana (visualization dashboards)
- ✅ Node Exporter (system metrics)
- ✅ AlertManager (alert notifications)

**Accessible at:**
- Grafana: https://com-cloud.cloud/grafana
- Prometheus: https://com-cloud.cloud/prometheus
- AlertManager: https://com-cloud.cloud/alertmanager

#### Step-by-Step Deployment

**1. Update Environment Variables**

Add to your server's `.env` file (or GitHub Secrets):

```bash
# Grafana admin password
GRAFANA_PASSWORD=your_secure_password_here

# Prometheus basic auth (optional but recommended)
# Generate with: htpasswd -nb admin your_password
PROMETHEUS_AUTH=admin:$apr1$8eVXLq6I$5sSl0zEhVlVqLVl9vYxLW0
```

**2. Choose Deployment Method**

**Method A: Merge monitoring into main docker-compose.yml**

Edit your existing [docker-compose.yml](docker-compose.yml) and add the monitoring services from [docker-compose.production.yml](docker-compose.production.yml):

```bash
# Backup current docker-compose.yml
cp docker-compose.yml docker-compose.yml.backup

# Manually merge the monitoring services (prometheus, grafana, etc.)
# Or use the production compose file directly
```

**Method B: Use docker-compose.production.yml (Easier)**

Update your deployment script in [.github/workflows/deploy.yml](.github/workflows/deploy.yml):

```yaml
# In the deploy job, change the docker-compose command:
- name: Deploy
  run: |
    # ... existing setup ...

    # Use production compose (includes monitoring)
    docker-compose -f docker-compose.yml -f docker-compose.production.yml pull
    docker-compose -f docker-compose.yml -f docker-compose.production.yml up -d
```

**3. Update GitHub Secrets**

Add these secrets to your GitHub repository:

1. Go to: https://github.com/YOUR_USERNAME/full_duplex_assistant/settings/secrets/actions
2. Add New Repository Secret:
   - Name: `GRAFANA_PASSWORD`
   - Value: Your secure password
3. Update `deploy.yml` to include it:

```yaml
- name: Create .env file
  run: |
    cat <<EOF > .env
    IMAGE_TAG=${{ github.sha }}
    LE_EMAIL=${{ secrets.LE_EMAIL }}
    GRAFANA_PASSWORD=${{ secrets.GRAFANA_PASSWORD }}
    EOF
```

**4. Commit and Deploy**

```bash
# Commit monitoring configuration
git add docker-compose.production.yml monitoring/
git commit -m "feat: Add production monitoring stack (Prometheus + Grafana)"

# Push to trigger deployment
git push origin main
```

**5. Verify Deployment**

After GitHub Actions completes:

```bash
# SSH to your server
ssh user@your-server-ip

# Check all services are running
docker ps

# Should see:
# - traefik
# - web
# - assistant
# - prometheus
# - grafana
# - node-exporter
# - alertmanager

# Check logs
docker-compose logs -f grafana
docker-compose logs -f prometheus
```

**6. Access Monitoring**

- **Grafana:** https://com-cloud.cloud/grafana
  - Login: `admin` / `<your GRAFANA_PASSWORD>`
  - Navigate to Dashboards → Full-Duplex Voice Assistant

- **Prometheus:** https://com-cloud.cloud/prometheus
  - Check Targets: https://com-cloud.cloud/prometheus/targets
  - All should show "UP" status

---

## 📊 What to Check After Deployment

### 1. Backend Metrics Endpoint

```bash
# Check metrics are exposed
curl https://com-cloud.cloud/metrics | head -20

# Expected output:
# HELP service_up Service health status (1=up, 0=down)
# TYPE service_up gauge
# service_up 1.0
# HELP api_requests_total Total API requests
# TYPE api_requests_total counter
# api_requests_total{method="GET",endpoint="/healthz",status="200"} 15.0
```

### 2. Client Metrics Ingestion

Test sending metrics from client:

```bash
curl -X POST https://com-cloud.cloud/api/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2025-11-14T12:00:00Z",
    "latency": {
      "endToEnd": {"p50": 850, "p95": 1120}
    },
    "streaming": {
      "packetLossRate": 0.02,
      "jitterMs": 12
    }
  }'

# Expected: {"status": "recorded"}
```

### 3. Prometheus Scraping (If deployed)

```bash
# Check Prometheus can reach backend
curl https://com-cloud.cloud/prometheus/api/v1/targets

# Or visit in browser:
# https://com-cloud.cloud/prometheus/targets
```

### 4. Grafana Dashboard (If deployed)

1. Open: https://com-cloud.cloud/grafana
2. Login with your credentials
3. Check dashboard shows data within 1-2 minutes

---

## 🔍 Troubleshooting

### Issue: Metrics endpoint returns 404

**Solution:**
```bash
# Check backend logs
docker-compose logs assistant | grep metrics

# Verify app.py was updated correctly
docker exec -it assistant cat /app/src/assistant/app.py | grep "def metrics"
```

### Issue: Prometheus shows "DOWN" for assistant-backend

**Solution:**
```bash
# Check Prometheus logs
docker-compose logs prometheus | grep assistant

# Verify network connectivity
docker exec prometheus wget -O- http://assistant:8000/metrics

# Check Prometheus config
docker exec prometheus cat /etc/prometheus/prometheus.yml
```

### Issue: Grafana shows "No Data"

**Solution:**
1. **Check datasource:**
   - Grafana → Configuration → Data Sources → Prometheus
   - Click "Test" - should show "Data source is working"

2. **Check Prometheus has data:**
   ```bash
   curl http://localhost:9090/api/v1/query?query=service_up
   ```

3. **Check time range:**
   - Dashboard shows "Last 1 hour" by default
   - Backend must have received requests in that timeframe

### Issue: Client metrics not appearing

**Solution:**
1. **Check browser console:**
   - Open DevTools → Console
   - Look for `[Metrics]` log messages
   - Check for XHR errors on `/api/metrics`

2. **Verify CORS:**
   - Backend must allow `https://com-cloud.cloud` origin
   - Check `ALLOWED_ORIGINS` env var

3. **Test endpoint manually:**
   ```javascript
   // In browser console
   fetch('/api/metrics', {
     method: 'POST',
     headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({timestamp: new Date().toISOString()})
   }).then(r => r.json()).then(console.log)
   ```

---

## 🔔 Setting Up Alerts (Optional)

### Slack Notifications

1. **Create Slack Webhook:**
   - Go to https://api.slack.com/apps
   - Create new app → Incoming Webhooks
   - Copy webhook URL

2. **Configure AlertManager:**

Edit [monitoring/alertmanager/alertmanager.yml](monitoring/alertmanager/alertmanager.yml):

```yaml
receivers:
  - name: 'critical-alerts'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#alerts'
        title: '🚨 {{ .GroupLabels.alertname }}'
        text: |
          {{ range .Alerts }}
          *{{ .Annotations.summary }}*
          {{ .Annotations.description }}
          {{ end }}
```

3. **Commit and redeploy:**
```bash
git add monitoring/alertmanager/alertmanager.yml
git commit -m "Configure Slack alerts"
git push origin main
```

### PagerDuty Integration

```yaml
receivers:
  - name: 'critical-alerts'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
        description: '{{ .Annotations.summary }}'
```

---

## 📈 Monitoring Production Performance

After deployment, you can:

### 1. View Real-Time Metrics

**Grafana Dashboard:**
- E2E latency: p50, p95, p99
- Barge-in response time
- Packet loss and jitter
- Active connections
- Error rates
- CPU and memory usage

### 2. Query Metrics via API

```bash
# Get current E2E latency p95
curl 'https://com-cloud.cloud/prometheus/api/v1/query?query=histogram_quantile(0.95,rate(e2e_latency_client_milliseconds_bucket[5m]))'

# Get error rate
curl 'https://com-cloud.cloud/prometheus/api/v1/query?query=rate(http_errors_total[5m])'
```

### 3. Run Benchmarks Against Production

```bash
# Run latency tests against production
pytest tests/performance/test_latency.py -v \
  --base-url https://com-cloud.cloud

# Load test
ab -n 1000 -c 50 https://com-cloud.cloud/api/healthz
```

---

## 🔄 Rollback Plan

If something goes wrong:

### Option 1: Rollback via GitHub

```bash
# Revert the commit
git revert HEAD
git push origin main

# GitHub Actions will automatically redeploy previous version
```

### Option 2: Manual Rollback on Server

```bash
# SSH to server
ssh user@your-server-ip

# Stop monitoring services only (keep backend running)
docker-compose stop prometheus grafana alertmanager node-exporter

# Or rollback entire deployment
docker-compose down
git checkout <previous-commit-sha>
docker-compose up -d
```

---

## 📝 Deployment Checklist

Before pushing to GitHub:

- [ ] All new files are committed
- [ ] `requirements.txt` includes new dependencies
- [ ] `GRAFANA_PASSWORD` secret added to GitHub
- [ ] Prometheus config updated for production
- [ ] Client-side tracker integrated into web app
- [ ] AlertManager configured (optional)
- [ ] Tested locally with `docker-compose up`

After GitHub deployment:

- [ ] GitHub Actions workflow succeeded
- [ ] `/metrics` endpoint is accessible
- [ ] `/api/metrics` endpoint accepts POST
- [ ] Prometheus scraping backend successfully
- [ ] Grafana dashboard shows data
- [ ] Alerts are being evaluated
- [ ] No errors in container logs

---

## 🎯 Success Criteria

Your deployment is successful when:

1. ✅ **Metrics Endpoint Working:**
   ```bash
   curl https://com-cloud.cloud/metrics | grep service_up
   # Returns: service_up 1.0
   ```

2. ✅ **Client Metrics Ingestion:**
   - Browser console shows `[Metrics] Periodic Report`
   - POST to `/api/metrics` returns `{"status": "recorded"}`

3. ✅ **Prometheus Collecting Data:**
   - Targets page shows assistant-backend as "UP"
   - Query `api_requests_total` returns data

4. ✅ **Grafana Dashboard Populated:**
   - All panels show graphs (not "No Data")
   - Latency metrics are realistic (500-2000ms)

5. ✅ **No Degradation:**
   - Application still works normally
   - No increased latency
   - No new errors in logs

---

## 📞 Support

If you encounter issues:

1. **Check GitHub Actions logs:**
   - https://github.com/YOUR_USERNAME/full_duplex_assistant/actions
   - Look for failed steps

2. **Check server logs:**
   ```bash
   ssh user@server
   docker-compose logs -f --tail=100
   ```

3. **Test metrics locally first:**
   ```bash
   cd /home/leo/full_duplex_assistant
   docker-compose up
   curl http://localhost:8000/metrics
   ```

4. **Review implementation guide:**
   - [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md)
   - [monitoring/README.md](monitoring/README.md)

---

## Next Steps After Deployment

1. **Monitor for 24 hours** - Check dashboard regularly
2. **Set baseline metrics** - Run benchmarks to establish normal performance
3. **Configure alerts** - Add Slack/PagerDuty notifications
4. **Create custom dashboards** - Add business-specific metrics
5. **Run load tests** - Find system capacity limits

🎉 You're now ready to deploy with full observability!
