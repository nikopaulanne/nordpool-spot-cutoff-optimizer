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

**Key principle:** The optimizer is **load-agnostic**. It finds optimal cutoff schedules and outputs them as sensors. YOU implement the actual load control in Part 3.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│ 1. Nordpool Integration (HACS)                          │
│    ├─ sensor.nordpool_kwh_fi_eur_3_10_0                │
│    ├─ raw_today (96 × 15min OR 24 × 1h)                │
│    └─ raw_tomorrow (96 × 15min OR 24 × 1h)             │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Python Script: nordpool_cutoff_optimizer.py         │
│    ├─ Read price data from Nordpool sensor             │
│    ├─ Dynamic Programming optimization                  │
│    ├─ Find globally optimal cutoff schedule(s)         │
│    └─ Output: sensor.nordpool_cutoff_periods_python    │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 3. Template Sensors (Home Assistant)                    │
│    ├─ sensor.cutoff_current_period                      │
│    ├─ sensor.cutoff_phase (preheat/cutoff/recovery)    │
│    └─ Extract data from periods list                    │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 4. YOUR Automations (YOU implement this in Part 3)     │
│    ├─ When cutoff_phase = "preheat" → YOUR action      │
│    ├─ When cutoff_phase = "shutdown" → YOUR action     │
│    └─ When cutoff_phase = "recovery" → YOUR action     │
└─────────────────────────────────────────────────────────┘
```

---

## Core Algorithm: Dynamic Programming

The optimizer uses **Dynamic Programming** to find the globally optimal cutoff schedule(s).

### Why Dynamic Programming?

**Alternative approach (Greedy):**
- Find the most expensive hour
- Apply cutoff there
- **Problem:** Might miss better opportunities or create overlaps

**Dynamic Programming approach:**
- Test all possible cutoff combinations
- Consider preheat and recovery costs
- Find globally optimal solution
- **Supports multiple cutoffs per day** (e.g., morning + evening peaks)

### Algorithm Steps

```python
1. Get price data (today + tomorrow) from Nordpool sensor
2. Resample to 15-min intervals if data is hourly
3. For each possible cutoff candidate:
   a. Calculate cutoff duration (0.5h, 0.75h, 1h, ... up to max)
   b. Calculate preheat start (same duration before cutoff)
   c. Calculate recovery end (same duration after cutoff)
   d. Compute costs:
      - baseline_cost = avg_price × duration
      - cutoff_cost = cutoff_price × residual_load (e.g. 0.1)
      - preheat_cost = preheat_price × preheat_multiplier (e.g. 1.5)
      - recovery_cost = recovery_price × recovery_multiplier (e.g. 1.2)
      - total_cost = cutoff + preheat + recovery
      - savings = baseline_cost - total_cost
   e. Check if savings > threshold
4. Use Dynamic Programming to select non-overlapping cutoffs
5. Output schedule(s) to sensor attributes
```

### Key Parameters

These are read from `input_number` entities you configure:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_price_diff` | 3.5 c/kWh | Min price diff for 1h cutoff |
| `max_cutoff_duration` | 4.0 hours | Max cutoff length |
| `min_cutoff_duration` | 0.5 hours | Min cutoff length |
| `preheat_multiplier` | 1.5 | Cost multiplier for preheat phase |
| `recovery_multiplier` | 1.2 | Cost multiplier for recovery |
| `residual_multiplier` | 0.1 | Residual load during cutoff (10%) |
| `min_savings_pct` | 10% | Min savings to activate |

**These are calibrated for YOUR system in Part 3.**

---

## Python Script Output

### Output Sensor: `sensor.nordpool_cutoff_periods_python`

The script creates a sensor with **a list of cutoff periods**:

```yaml
sensor.nordpool_cutoff_periods_python:
  state: "2"  # Number of cutoffs today/tomorrow
  attributes:
    periods:
      - preheat_start: "2025-10-07T13:00:00+03:00"
        shutdown_start: "2025-10-07T17:00:00+03:00"
        shutdown_end: "2025-10-07T21:00:00+03:00"
        recovery_start: "2025-10-07T21:00:00+03:00"
        recovery_end: "2025-10-08T01:00:00+03:00"
        savings_pct: 35.9
        baseline_cost: 33.82
        optimized_cost: 21.67
        cutoff_duration_hours: 4.0

      - preheat_start: "2025-10-08T06:00:00+03:00"
        shutdown_start: "2025-10-08T08:00:00+03:00"
        shutdown_end: "2025-10-08T10:00:00+03:00"
        recovery_start: "2025-10-08T10:00:00+03:00"
        recovery_end: "2025-10-08T12:00:00+03:00"
        savings_pct: 18.2
        baseline_cost: 28.45
        optimized_cost: 23.27
        cutoff_duration_hours: 2.0

    data_resolution: "15min"
    optimization_method: "dynamic_programming"
```

**Key feature:** The `periods` list can contain **multiple cutoffs** (e.g., morning + evening peaks).

---

## Template Sensors: Extract Current Phase

You need template sensors to extract which phase is currently active:

### Minimal Example: Current Phase Sensor

```yaml
template:
  - sensor:
      - name: "Cutoff Current Phase"
        unique_id: cutoff_current_phase
        state: >
          {% set periods = state_attr('sensor.nordpool_cutoff_periods_python', 'periods') %}
          {% if not periods %}
            normal
          {% else %}
            {% set now_ts = now().timestamp() %}
            {% set ns = namespace(phase='normal') %}
            {% for period in periods %}
              {% set preheat_ts = as_timestamp(period.preheat_start) %}
              {% set shutdown_ts = as_timestamp(period.shutdown_start) %}
              {% set shutdown_end_ts = as_timestamp(period.shutdown_end) %}
              {% set recovery_end_ts = as_timestamp(period.recovery_end) %}

              {% if now_ts >= preheat_ts and now_ts < shutdown_ts %}
                {% set ns.phase = 'preheat' %}
              {% elif now_ts >= shutdown_ts and now_ts < shutdown_end_ts %}
                {% set ns.phase = 'shutdown' %}
              {% elif now_ts >= shutdown_end_ts and now_ts < recovery_end_ts %}
                {% set ns.phase = 'recovery' %}
              {% endif %}
            {% endfor %}
            {{ ns.phase }}
          {% endif %}
```

**This sensor will show:**
- `normal` - No active cutoff
- `preheat` - Currently preheating
- `shutdown` - Currently in cutoff phase
- `recovery` - Currently recovering

---

## Weather-Adaptive Optimization

The script automatically adjusts cutoff parameters based on outdoor temperature:

```python
# Inside the script (you don't need to configure this)
outdoor_temp = float(hass.states.get('sensor.outdoor_temperature').state)

if outdoor_temp < 0 or outdoor_temp > 24:
    # Extreme weather: shorter cutoffs
    max_cutoff_duration = 3.0  # hours
else:
    # Mild weather: longer cutoffs allowed
    max_cutoff_duration = 4.0  # hours (from input_number)
```

**Why?** Extreme temperatures increase heat loss → shorter cutoffs maintain comfort.

**You configure:** The outdoor temperature sensor entity ID in the script.

---

## Installation

### Step 1: Enable Python Scripts

Add to `configuration.yaml`:

```yaml
python_script:
```

Restart Home Assistant.

---

### Step 2: Copy Python Script

1. Download `nordpool_cutoff_optimizer.py` from this repository
2. Place it in `/config/python_scripts/`
3. File should be: `/config/python_scripts/nordpool_cutoff_optimizer.py`

---

### Step 3: Add Input Numbers

Add these to `configuration.yaml` (or use packages):

```yaml
input_number:
  cutoff_base_price_diff:
    name: "Base Price Difference"
    min: 0.5
    max: 10.0
    step: 0.1
    initial: 3.5
    unit_of_measurement: "c/kWh"

  cutoff_max_duration:
    name: "Max Cutoff Duration"
    min: 0.5
    max: 6.0
    step: 0.25
    initial: 4.0
    unit_of_measurement: "hours"

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

  cutoff_residual_load:
    name: "Cutoff Residual Load"
    min: 0.0
    max: 0.5
    step: 0.05
    initial: 0.1

  cutoff_min_savings_pct:
    name: "Min Savings Threshold"
    min: 0
    max: 30
    step: 1
    initial: 10
    unit_of_measurement: "%"
```

Restart Home Assistant.

---

### Step 4: Add Template Sensor

Add the "Cutoff Current Phase" sensor from above to your `configuration.yaml`:

```yaml
template:
  - sensor:
      - name: "Cutoff Current Phase"
        unique_id: cutoff_current_phase
        state: >
          # ... (copy from above)
```

Restart Home Assistant.

---

### Step 5: Automation to Run Script

Create an automation that runs the optimizer:

```yaml
automation:
  - alias: "Run Nordpool Cutoff Optimizer"
    trigger:
      # Run every 15 minutes
      - platform: time_pattern
        minutes: "/15"

      # Run when tomorrow's prices arrive
      - platform: state
        entity_id: sensor.nordpool_kwh_fi_eur_3_10_0
        attribute: raw_tomorrow

    action:
      - service: python_script.nordpool_cutoff_optimizer
        data: {}
```

**The script will now run automatically!**

---

## Testing Without Load Control

You can test the optimizer **without connecting it to any loads**:

### 1. Check the Output Sensor

Go to: **Developer Tools** → **States** → Search for `sensor.nordpool_cutoff_periods_python`

You should see:
- State: Number of cutoffs (e.g., "2")
- Attributes: `periods` list with all cutoff details

### 2. Monitor Current Phase

Watch `sensor.cutoff_current_phase` throughout the day:
- Should be `normal` most of the time
- Changes to `preheat` before expensive periods
- Changes to `shutdown` during expensive periods
- Changes to `recovery` after cutoffs

### 3. Verify Schedule Matches Prices

Compare cutoff times with Nordpool prices:
- Cutoffs should be during **expensive** hours
- Preheat should be during **cheaper** hours before peaks

**Only after verification, implement actual load control (Part 3).**

---

## Debugging

### Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    homeassistant.components.python_script: debug
```

### Check Sensor Attributes

**Developer Tools** → **States** → `sensor.nordpool_cutoff_periods_python`

Look for:
- All timestamps present in `periods`
- Reasonable `savings_pct` values
- Cutoffs during expensive hours

### Common Issues

| Issue | Fix |
|-------|-----|
| No cutoff detected | Lower `base_price_diff` or `min_savings_pct` |
| Cutoff during cheap hours | Increase `base_price_diff` |
| Cutoff too long | Lower `max_cutoff_duration` |
| Script error | Check logs, verify Nordpool sensor exists |

---

## Performance

- **Execution time:** ~0.5-2 seconds
- **Memory usage:** ~5-10 MB
- **CPU usage:** Negligible (runs every 15 min)

**Safe for Raspberry Pi and low-power systems.**

---

## Next Steps

→ **[Part 3: Integration Examples](./03-integration-examples.md)** - How to connect the optimizer to YOUR specific loads (HVAC, water heater, etc.)

---

## Key Takeaways

- The optimizer is **load-agnostic** - it only finds schedules
- Output: `sensor.nordpool_cutoff_periods_python` with `periods` list
- **Multiple cutoffs per day** are supported (morning + evening peaks)
- YOU implement actual load control based on `sensor.cutoff_current_phase`
- Dynamic Programming finds globally optimal solution
- Weather-adaptive adjustments maintain comfort
- Test thoroughly before connecting to real loads

---

*Questions? Discuss in the [Home Assistant Community thread](LINK-WHEN-PUBLISHED)*
