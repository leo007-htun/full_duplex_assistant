# End-to-End Latency Measurement System

## Overview

This system allows you to measure **empirical end-to-end latency** from user speech to assistant audio playback, validating the theoretical 1.4-2.0s estimate in your paper.

## Quick Start

### 1. Integrate Latency Tracking

Follow the detailed guide in [LATENCY_INTEGRATION.md](LATENCY_INTEGRATION.md) to add tracking to your WebSocket handlers.

**Quick integration checklist:**
- [ ] Import `LatencyTracker` in `script.js`
- [ ] Call `onSpeechStart()` when user starts speaking
- [ ] Call `onSpeechStopEvent()` when VAD detects speech end
- [ ] Call `onTranscriptComplete()` when ASR finishes
- [ ] Call `onFirstToken()` when LLM response starts
- [ ] Call `onFirstAudioChunk()` when first TTS audio arrives
- [ ] Call `onAudioPlaybackStart()` when browser plays audio
- [ ] Call `onUserInterrupt()` and `onAudioStopped()` for barge-in

### 2. Collect Data

During user study sessions (N=20):

1. **Open browser developer console** (F12)
2. **Start conversation** with the system
3. **Watch latency measurements** print in console:
   ```
   [Latency] ⭐ E2E TOTAL: 1889.2ms
   [Latency] Breakdown:
     VAD:      823.4ms (43.6%)
     ASR:      287.3ms (15.2%)
     LLM:      412.8ms (21.9%)
     TTS:      298.5ms (15.8%)
     Playback: 67.2ms (3.6%)
   ```

4. **After each session**, click "Download Latency Data" button to export CSV

### 3. Analyze Results

Run the analysis script on collected data:

```bash
python3 analyze_latency.py latency_measurements_1234567890.csv
```

**Output includes:**
- Statistical summary (mean, median, p95, p99, stddev)
- E2E latency breakdown by component
- Comparison to theoretical targets
- LaTeX table ready for paper

### 4. Update Paper

Use the generated LaTeX table to replace theoretical estimates with empirical data!

## File Structure

```
/home/leo/full_duplex_assistant/
├── web/
│   ├── latency_tracker.js          # Client-side latency measurement module
│   └── script.js                    # (integrate tracker here)
├── analyze_latency.py               # Python analysis script
├── LATENCY_INTEGRATION.md           # Detailed integration guide
└── LATENCY_MEASUREMENT_README.md    # This file
```

## Measurement Breakdown

The system measures **7 latency components**:

### 1. E2E Latency (Total)
- **Start**: User begins speaking
- **End**: Audio starts playing from browser
- **Expected**: 1400-2000ms (p95)
- **Formula**: `E2E = VAD + ASR + LLM + TTS + Playback`

### 2. VAD Latency
- **Start**: User speech onset
- **End**: Server VAD emits `speech_stopped` event
- **Expected**: ~800ms (configured VAD window)

### 3. ASR Latency
- **Start**: `speech_stopped` event
- **End**: Transcript finalized
- **Expected**: 200-400ms

### 4. LLM Latency (TTFT)
- **Start**: Transcript complete
- **End**: First LLM token generated
- **Expected**: 300-600ms

### 5. TTS Latency
- **Start**: First LLM token
- **End**: First audio chunk generated
- **Expected**: 200-400ms

### 6. Playback Latency
- **Start**: First audio chunk received
- **End**: Browser AudioContext starts playing
- **Expected**: 50-100ms

### 7. Barge-In Latency
- **Start**: User interrupts during assistant speech
- **End**: Audio playback stops
- **Expected**: <500ms (p95 target)

## Example Output

### Console Logs
```
[Latency] Speech started at 12345.6
[Latency] VAD detection: 823.4ms
[Latency] Transcript: "What's the weather like?"
[Latency] ASR processing: 287.3ms
[Latency] LLM TTFT: 412.8ms
[Latency] TTS generation: 298.5ms
[Latency] Playback buffer: 67.2ms
[Latency] ⭐ E2E TOTAL: 1889.2ms
```

### Analysis Script Output
```
================================================================================
LATENCY STATISTICS (milliseconds)
================================================================================
Metric                      Count     Mean   Median      P95      P99      Min      Max   StdDev
------------------------------------------------------------------------------------------------
End-to-End (Total)            142   1645.3   1612.4   1887.5   2134.2   1234.5   2456.7    247.3
VAD Detection                 142    798.2    801.3    856.4    912.1    723.1    934.5     45.6
ASR Processing                142    312.4    298.7    421.3    487.2    187.3    512.8     78.4
LLM Time-to-First-Token       142    456.8    423.1    678.9    834.2    234.5    912.3    156.7
TTS Generation                142    287.3    276.4    367.8    412.5    198.7    456.2     62.1
Audio Playback Buffer         142     72.1     68.3     98.7    112.4     45.2    123.7     18.9
Barge-In Response              48    367.8    342.6    478.3    534.2    234.1    587.3     89.4
================================================================================

================================================================================
E2E LATENCY BREAKDOWN
================================================================================
Total E2E Latency (p95): 1887.5ms

Component                Mean (ms)   % of Total
--------------------------------------------
VAD Detection                798.2        48.5%
ASR Processing               312.4        19.0%
LLM Inference                456.8        27.8%
TTS Synthesis                287.3        17.5%
Playback Buffer               72.1         4.4%
================================================================================

================================================================================
COMPARISON TO THEORETICAL ESTIMATES
================================================================================

Paper estimate: 1.4-2.0s
  Target: 1400-2000ms
  Actual (p95): 1887.5ms
  Status: ✓ PASS

VAD window: 800ms
  Target: 800-800ms
  Actual (p95): 856.4ms
  Status: ✗ FAIL

Target: <500ms (p95)
  Target: 500-500ms
  Actual (p95): 478.3ms
  Status: ✓ PASS

================================================================================
```

## Validation Checklist

After integration, verify:

- [ ] Timestamps are sequential (each > previous)
- [ ] VAD latency ≈ 800ms (configured window)
- [ ] E2E latency ≈ 1.4-2.0s (paper estimate)
- [ ] Sum of components equals total E2E
- [ ] Barge-in latency < 500ms (p95 target)
- [ ] No `null` timestamps in console
- [ ] CSV export works correctly
- [ ] Analysis script runs without errors

## Troubleshooting

### Problem: All timestamps are `null`
**Solution**: Check that `latencyTracker` is properly imported and initialized before any event handlers

### Problem: E2E latency too low (<1000ms)
**Solution**: Verify `onSpeechStart()` is called when user *begins* speaking, not when VAD confirms

### Problem: Component sum doesn't equal total
**Solution**: Ensure all intermediate timestamps are recorded; check for missing event handlers

### Problem: VAD latency much higher than 800ms
**Solution**: Check network latency; VAD event may be delayed by poor connection

### Problem: Measurements missing for some turns
**Solution**: Check browser console for errors; ensure `resetTurn()` is called after each complete cycle

## Backend API (Optional)

To aggregate measurements server-side:

1. **Add endpoint** in `src/assistant/main.py` (see [LATENCY_INTEGRATION.md](LATENCY_INTEGRATION.md#step-11-backend-api-endpoint-optional))
2. **Enable reporting** in latency tracker:
   ```javascript
   latencyTracker.sendToBackend = true;
   latencyTracker.backendUrl = '/api/metrics/latency';
   ```
3. **Query aggregate stats**:
   ```bash
   curl http://localhost:8000/api/metrics/latency/stats
   ```

## Prometheus Integration

For long-term monitoring, integrate with existing Prometheus metrics:

```python
from prometheus_client import Histogram

E2E_LATENCY = Histogram(
    'e2e_latency_seconds',
    'End-to-end speech latency',
    buckets=[0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0, 10.0]
)
```

See integration guide for complete example.

## For User Study (N=20)

### Pre-Study Setup
1. Integrate latency tracking into production system
2. Test with 2-3 pilot users to verify measurements
3. Prepare CSV export button for easy data collection

### During Study
1. Instruct participants to complete tasks normally
2. Latency tracking runs silently in background
3. No extra action required from participants

### Post-Study
1. Export CSV after each participant session
2. Run analysis script on each CSV
3. Aggregate results across all N=20 participants
4. Calculate grand mean/median/p95 across all sessions

### Analysis Commands
```bash
# Analyze individual session
python3 analyze_latency.py participant_01.csv > results_p01.txt

# Combine all CSVs (for aggregate analysis)
cat participant_*.csv | grep -v "^metric,value" > combined_latency.csv
echo "metric,value_ms,timestamp" | cat - combined_latency.csv > temp && mv temp combined_latency.csv

# Analyze combined data
python3 analyze_latency.py combined_latency.csv > final_results.txt
```

## Paper Updates

After collecting empirical data, update your paper:

### Section IV (Latency Analysis)
Replace theoretical estimates with measured values:

**Before:**
```latex
The p95 latency estimate:
\begin{equation}
L_{\text{total, p95}} \approx 1.4\text{--}2.0\,\text{s}
\end{equation}
```

**After:**
```latex
Empirical measurements from N=20 user study participants (142 total conversational turns) yielded p95 latency:
\begin{equation}
L_{\text{total, p95}} = 1887.5\,\text{ms} \approx 1.9\,\text{s}
\end{equation}
validating the theoretical 1.4-2.0s estimate.
```

### User Study Section
Add subsection on latency validation:

```latex
\subsubsection{Latency Validation}

Client-side instrumentation measured actual end-to-end latency across all user study sessions (Table~\ref{tab:measured_latency}). Measurements confirm that the system achieves p95 latency of 1887.5ms, well within the theoretical 1.4-2.0s range estimated in Section IV.

[Insert generated LaTeX table here]
```

## Next Steps

1. **Integrate** tracking into `web/script.js` (15-30 minutes)
2. **Test** with a few conversations (5 minutes)
3. **Validate** measurements match expectations (5 minutes)
4. **Deploy** to production for user study
5. **Collect** data from N=20 participants
6. **Analyze** with provided script
7. **Update** paper with empirical results!

## Support

If you encounter issues:
1. Check browser console for error messages
2. Verify all event handlers are called in correct order
3. Test with simple conversation first
4. Compare timestamps to ensure they're sequential
5. Review [LATENCY_INTEGRATION.md](LATENCY_INTEGRATION.md) for detailed examples

## License

MIT License - feel free to adapt for your research needs!
