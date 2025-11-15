#!/usr/bin/env python3
"""
Analyze E2E Latency Measurements from CSV Export

Usage:
    python analyze_latency.py latency_measurements.csv
"""

import sys
import csv
import statistics
from collections import defaultdict
from typing import List, Dict

def load_csv(filename: str) -> Dict[str, List[float]]:
    """Load CSV and group by metric"""
    data = defaultdict(list)

    with open(filename, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            metric = row['metric']
            value_ms = float(row['value_ms'])
            data[metric].append(value_ms)

    return data

def calculate_stats(values: List[float]) -> Dict:
    """Calculate comprehensive statistics"""
    if not values:
        return None

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    # Basic stats
    mean_val = statistics.mean(sorted_vals)
    median_val = statistics.median(sorted_vals)
    stddev_val = statistics.stdev(sorted_vals) if n > 1 else 0

    # Percentiles
    p50 = sorted_vals[int(n * 0.50)] if n > 0 else 0
    p75 = sorted_vals[int(n * 0.75)] if n > 0 else 0
    p90 = sorted_vals[int(n * 0.90)] if n > 0 else 0
    p95 = sorted_vals[int(n * 0.95)] if n > 0 else 0
    p99 = sorted_vals[int(n * 0.99)] if n > 0 else 0

    return {
        'count': n,
        'min': sorted_vals[0],
        'max': sorted_vals[-1],
        'mean': mean_val,
        'median': median_val,
        'stddev': stddev_val,
        'p50': p50,
        'p75': p75,
        'p90': p90,
        'p95': p95,
        'p99': p99
    }

def print_stats_table(metrics: Dict[str, List[float]]):
    """Print statistics table"""
    print("\n" + "="*80)
    print("LATENCY STATISTICS (milliseconds)")
    print("="*80)

    metric_names = {
        'e2e_latency': 'End-to-End (Total)',
        'vad_latency': 'VAD Detection',
        'asr_latency': 'ASR Processing',
        'llm_latency': 'LLM Time-to-First-Token',
        'tts_latency': 'TTS Generation',
        'playback_latency': 'Audio Playback Buffer',
        'barge_in_latency': 'Barge-In Response'
    }

    header = f"{'Metric':<25} {'Count':>7} {'Mean':>8} {'Median':>8} {'P95':>8} {'P99':>8} {'Min':>8} {'Max':>8} {'StdDev':>8}"
    print(header)
    print("-" * len(header))

    for metric, values in sorted(metrics.items()):
        stats = calculate_stats(values)
        if not stats:
            continue

        name = metric_names.get(metric, metric)
        row = f"{name:<25} {stats['count']:>7} {stats['mean']:>8.1f} {stats['median']:>8.1f} " \
              f"{stats['p95']:>8.1f} {stats['p99']:>8.1f} {stats['min']:>8.1f} " \
              f"{stats['max']:>8.1f} {stats['stddev']:>8.1f}"
        print(row)

    print("="*80)

def analyze_e2e_breakdown(metrics: Dict[str, List[float]]):
    """Analyze E2E latency breakdown"""
    if 'e2e_latency' not in metrics:
        return

    e2e_stats = calculate_stats(metrics['e2e_latency'])

    print("\n" + "="*80)
    print("E2E LATENCY BREAKDOWN")
    print("="*80)

    print(f"Total E2E Latency (p95): {e2e_stats['p95']:.1f}ms\n")

    components = ['vad_latency', 'asr_latency', 'llm_latency', 'tts_latency', 'playback_latency']
    component_names = {
        'vad_latency': 'VAD Detection',
        'asr_latency': 'ASR Processing',
        'llm_latency': 'LLM Inference',
        'tts_latency': 'TTS Synthesis',
        'playback_latency': 'Playback Buffer'
    }

    print(f"{'Component':<20} {'Mean (ms)':>12} {'% of Total':>12}")
    print("-" * 44)

    total_mean = e2e_stats['mean']

    for component in components:
        if component not in metrics:
            continue

        stats = calculate_stats(metrics[component])
        percentage = (stats['mean'] / total_mean) * 100
        print(f"{component_names[component]:<20} {stats['mean']:>12.1f} {percentage:>11.1f}%")

    print("="*80)

def compare_to_target(metrics: Dict[str, List[float]]):
    """Compare against paper's theoretical estimates"""
    print("\n" + "="*80)
    print("COMPARISON TO THEORETICAL ESTIMATES")
    print("="*80)

    targets = {
        'e2e_latency': (1400, 2000, "Paper estimate: 1.4-2.0s"),
        'vad_latency': (800, 800, "VAD window: 800ms"),
        'barge_in_latency': (500, 500, "Target: <500ms (p95)")
    }

    for metric, (lower, upper, description) in targets.items():
        if metric not in metrics:
            continue

        stats = calculate_stats(metrics[metric])
        actual = stats['p95']

        status = "✓ PASS" if lower <= actual <= upper else "✗ FAIL"
        print(f"\n{description}")
        print(f"  Target: {lower}-{upper}ms")
        print(f"  Actual (p95): {actual:.1f}ms")
        print(f"  Status: {status}")

    print("\n" + "="*80)

def generate_latex_table(metrics: Dict[str, List[float]]):
    """Generate LaTeX table for paper"""
    print("\n" + "="*80)
    print("LATEX TABLE (Copy to paper)")
    print("="*80)

    print(r"""
\begin{table}[t]
\centering
\caption{Measured End-to-End Latency Components (empirical data, $N$ measurements)}
\label{tab:measured_latency}
\begin{tabular}{@{}lrrr@{}}
\toprule
\textbf{Component} & \textbf{Mean (ms)} & \textbf{P95 (ms)} & \textbf{Std Dev} \\
\midrule""")

    components = [
        ('VAD Detection', 'vad_latency'),
        ('ASR Processing', 'asr_latency'),
        ('LLM Time-to-First-Token', 'llm_latency'),
        ('TTS Synthesis', 'tts_latency'),
        ('Audio Playback', 'playback_latency'),
    ]

    for name, metric in components:
        if metric not in metrics:
            continue
        stats = calculate_stats(metrics[metric])
        print(f"{name} & {stats['mean']:.1f} & {stats['p95']:.1f} & {stats['stddev']:.1f} \\\\")

    print(r"""\midrule""")

    if 'e2e_latency' in metrics:
        e2e = calculate_stats(metrics['e2e_latency'])
        print(f"\\textbf{{Total E2E}} & \\textbf{{{e2e['mean']:.1f}}} & \\textbf{{{e2e['p95']:.1f}}} & {e2e['stddev']:.1f} \\\\")

    print(r"""\bottomrule
\end{tabular}
\end{table}
""")

    print("="*80)

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_latency.py <latency_csv_file>")
        sys.exit(1)

    filename = sys.argv[1]

    try:
        metrics = load_csv(filename)
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
        sys.exit(1)

    if not metrics:
        print("Error: No data found in CSV")
        sys.exit(1)

    # Print all analyses
    print_stats_table(metrics)
    analyze_e2e_breakdown(metrics)
    compare_to_target(metrics)
    generate_latex_table(metrics)

    # Summary
    if 'e2e_latency' in metrics:
        e2e = calculate_stats(metrics['e2e_latency'])
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Measured E2E Latency:")
        print(f"  Mean: {e2e['mean']:.1f}ms ({e2e['mean']/1000:.2f}s)")
        print(f"  P50:  {e2e['p50']:.1f}ms ({e2e['p50']/1000:.2f}s)")
        print(f"  P95:  {e2e['p95']:.1f}ms ({e2e['p95']/1000:.2f}s)")
        print(f"  P99:  {e2e['p99']:.1f}ms ({e2e['p99']/1000:.2f}s)")
        print(f"\nTotal Measurements: {e2e['count']}")
        print("="*80)

if __name__ == '__main__':
    main()
