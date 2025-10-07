# Part 2: The Cutoff Optimizer - Python Implementation

*Part 2 of 3: Technical Deep-Dive*

> **This document covers the core optimization algorithm and Home Assistant integration.**  
> **→ [Discuss on Home Assistant Community](LINK-WHEN-PUBLISHED)**

---

## Introduction

In [Part 1](./01-theory.md), we explored the theory behind load cutoff optimization using 15-minute Nordpool pricing. Now it's time to **build the actual system**.

This part covers:
- ✅ Core optimization algorithm (Dynamic Programming)
- ✅ Python script for Home Assistant
- ✅ Template sensors and integration
- ✅ How to adapt it for YOUR load

**Key principle:** The optimizer is **load-agnostic**. It only finds optimal cutoff schedules and outputs them as sensors. YOU implement the actual load control in Part 3.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│ 1. Nordpool Integration (HACS)                          │
│    ├─ sensor.nordpool_kwh                               │
│    ├─ raw_today (96 × 15min OR 24 × 1h)                │
│    └─ raw_tomorrow (96 × 15min OR 24 × 1h)             │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Python Script: nordpool_cutoff_optimizer.py         │
│    ├─ Read price data                                   │
│    ├─ Dynamic Programming optimization                  │
│    ├─ Find globally optimal cutoff schedule             │
│    └─ Output: Sensor attributes                         │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 3. Template Sensors (Home Assistant)                    │
│    ├─ sensor.cutoff_start_time                          │
│    ├─ sensor.cutoff_end_time                            │
│    ├─ sensor.preheat_start_time                         │
│    ├─ sensor.recovery_end_time                          │
│    ├─ sensor.cutoff_phase (current phase)               │
│    └─ sensor.estimated_savings                          │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 4. YOUR Automations (YOU implement this)                │
│    ├─ When cutoff_phase = "preheat" → YOUR action      │
│    ├─ When cutoff_phase = "cutoff" → YOUR action       │
│    └─ When cutoff_phase = "recovery" → YOUR action     │
└─────────────────────────────────────────────────────────┘
```

## Core Algorithm: Dynamic Programming

The optimizer uses **Dynamic Programming** to find the globally optimal cutoff schedule.

### Why Dynamic Programming?

**Alternative approach (Greedy):**
- Find the most expensive hour
- Apply cutoff there
- **Problem:** Might miss better opportunities

**Dynamic Programming approach:**
- Test all possible cutoff combinations
- Consider preheat and recovery costs
- Find globally optimal solution

### Algorithm Steps

```python
1. Get price data (today + tomorrow)
2. Resample to 15-min intervals if needed
3. For each possible cutoff candidate:
   a. Calculate cutoff duration (1h, 1.25h, 1.5h, ... up to max)
   b. Calculate preheat start (same duration before cutoff)
   c. Calculate recovery end (same duration after cutoff)
   d. Compute costs:
      - baseline_cost = avg_price × duration
      - cutoff_cost = cutoff_price × 0.1 (10% residual load)
      - preheat_cost = preheat_price × 1.5 (higher temp)
      - recovery_cost = recovery_price × 1.2 (catch-up)
      - total_cost = cutoff + preheat + recovery
      - savings = baseline_cost - total_cost
   e. Check if savings > threshold
4. Select cutoff with maximum savings
5. Output schedule to sensor attributes
```

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_price_diff` | 3.5 c/kWh | Min price diff for 1h cutoff |
| `max_cutoff_duration` | 4.0 hours | Max cutoff length |
| `min_cutoff_duration` | 1.0 hours | Min cutoff length |
| `cutoff_step` | 0.25 hours | Step size (15 min) |
| `preheat_multiplier` | 1.5 | Cost multiplier for preheat |
| `recovery_multiplier` | 1.2 | Cost multiplier for recovery |
| `cutoff_multiplier` | 0.1 | Residual load during cutoff |
| `min_savings_pct` | 10% | Min savings to activate |

**These are calibrated for YOUR system in Part 3.**

## Python Script Structure

### Input Configuration

The script reads these `input_number` entities:

```yaml
input_number:
  cutoff_base_price_diff:
    name: "Base Price Difference (c/kWh)"
    min: 0.5
    max: 10.0
    step: 0.1
    initial: 3.5

  cutoff_max_duration:
    name: "Max Cutoff Duration (hours)"
    min: 1.0
    max: 6.0
    step: 0.25
    initial: 4.0

  cutoff_preheat_multiplier:
    name: "Preheat Cost Multiplier"
    min: 1.0
    max: 2.0
    step: 0.1
    initial: 1.5

  cutoff_recovery_multiplier:
    name: "Recovery Cost Multiplier"
    min: 1.0
    max: 2.0
    step: 0.1
    initial: 1.2

  cutoff_residual_multiplier:
    name: "Cutoff Residual Load"
    min: 0.0
    max: 0.5
    step: 0.05
    initial: 0.1

  cutoff_min_savings_pct:
    name: "Min Savings Threshold (%)"
    min: 0
    max: 30
    step: 1
    initial: 10
```

### Output: Sensor Attributes

The script outputs a `sensor.cutoff_optimizer_state` with attributes:

```yaml
sensor.cutoff_optimizer_state:
  state: "active"  # or "no_cutoff"
  attributes:
    preheat_start: "2025-10-07 13:00:00"
    cutoff_start: "2025-10-07 17:00:00"
    cutoff_end: "2025-10-07 21:00:00"
    recovery_end: "2025-10-07 01:00:00"
    cutoff_duration: 4.0  # hours
    estimated_savings_pct: 35.9
    baseline_cost: 33.82
    optimized_cost: 21.67
    cutoff_avg_price: 15.3  # c/kWh
    preheat_avg_price: 5.2
    recovery_avg_price: 3.8
```

### Template Sensors Extract Data

```yaml
template:
  - sensor:
      - name: "Cutoff Phase"
        unique_id: cutoff_current_phase
        state: >
          {% set now_ts = now().timestamp() %}
          {% set preheat = state_attr('sensor.cutoff_optimizer_state', 'preheat_start') | as_datetime | as_local %}
          {% set cutoff_start = state_attr('sensor.cutoff_optimizer_state', 'cutoff_start') | as_datetime | as_local %}
          {% set cutoff_end = state_attr('sensor.cutoff_optimizer_state', 'cutoff_end') | as_datetime | as_local %}
          {% set recovery = state_attr('sensor.cutoff_optimizer_state', 'recovery_end') | as_datetime | as_local %}

          {% if states('sensor.cutoff_optimizer_state') == 'no_cutoff' %}
            normal
          {% elif now_ts < preheat.timestamp() %}
            normal
          {% elif now_ts >= preheat.timestamp() and now_ts < cutoff_start.timestamp() %}
            preheat
          {% elif now_ts >= cutoff_start.timestamp() and now_ts < cutoff_end.timestamp() %}
            cutoff
          {% elif now_ts >= cutoff_end.timestamp() and now_ts < recovery.timestamp() %}
            recovery
          {% else %}
            normal
          {% endif %}
```

## Weather-Adaptive Optimization

The system automatically adjusts cutoff parameters based on outdoor temperature:

```python
# Get outdoor temperature
outdoor_temp = hass.states.get('sensor.outdoor_temperature').state

# Adjust parameters based on weather
if outdoor_temp < 0 or outdoor_temp > 24:
    # Extreme weather: shorter cutoffs
    max_cutoff_duration = 3.0  # hours
    base_price_diff = 2.5  # c/kWh (lower threshold)
else:
    # Mild weather: longer cutoffs allowed
    max_cutoff_duration = 4.0  # hours
    base_price_diff = 3.5  # c/kWh
```

**Why?** Extreme temperatures increase heat loss → shorter cutoffs maintain comfort.

## Installation

### 1. Enable Python Scripts

Add to `configuration.yaml`:

```yaml
python_script:
```

### 2. Copy Script File

Place `nordpool_cutoff_optimizer.py` in `/config/python_scripts/`

### 3. Add Input Numbers

Add the `input_number` configuration above to your `configuration.yaml` or use packages.

### 4. Add Template Sensors

Add template sensors to extract cutoff phase and times.

### 5. Automation to Run Script

```yaml
automation:
  - alias: "Run Cutoff Optimizer"
    trigger:
      - platform: time_pattern
        minutes: "/15"  # Every 15 minutes
      - platform: state
        entity_id: sensor.nordpool_kwh
        attribute: raw_tomorrow
    action:
      - service: python_script.nordpool_cutoff_optimizer
```

## Testing Without Load Control

You can test the optimizer **without connecting it to any loads**:

1. Install script and sensors
2. Watch `sensor.cutoff_phase` change throughout the day
3. Verify schedule matches price peaks
4. Check `estimated_savings_pct` is reasonable

**Only after verification, implement actual load control (Part 3).**

## Debugging

### Enable Debug Logging

```yaml
logger:
  default: info
  logs:
    homeassistant.components.python_script: debug
```

### Check Sensor Attributes

Developer Tools → States → `sensor.cutoff_optimizer_state`

Look for:
- All timestamps present
- Reasonable savings percentage
- Cutoff during expensive hours

### Common Issues

**Issue:** No cutoff detected  
**Fix:** Lower `base_price_diff` or `min_savings_pct`

**Issue:** Cutoff during cheap hours  
**Fix:** Increase `base_price_diff`

**Issue:** Too long cutoff duration  
**Fix:** Lower `max_cutoff_duration`

## Performance

- **Execution time:** ~0.5-2 seconds (depends on candidate count)
- **Memory usage:** Minimal (~5-10 MB)
- **CPU usage:** Negligible (runs every 15 min)

**Safe for Raspberry Pi and low-power systems.**

## Next Steps

→ **[Part 3: Integration Examples](./03-integration-examples.md)** - How to connect the optimizer to YOUR specific loads

---

## Key Takeaways

- The optimizer is **load-agnostic** - it only finds schedules
- YOU implement actual load control based on `sensor.cutoff_phase`
- Dynamic Programming finds globally optimal solution
- Weather-adaptive adjustments maintain comfort
- Test thoroughly before connecting to real loads

---

*Questions? Discuss in the [Home Assistant Community thread](LINK-WHEN-PUBLISHED)*
