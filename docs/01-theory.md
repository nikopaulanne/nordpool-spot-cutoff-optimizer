# Part 1: Theory - Understanding Load Cutoff Optimization

*Part 1 of 3: The Concept*

> **This document is a mirror of the [Home Assistant Community post](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-the-theory-part-1-of-3-understanding-the-concept/936741).**

---

## Introduction

Since October 2025, electric markets in Finland and Nordpool has moved to **15-minute electricity pricing data**. This granular data reveals significant price spikes lasting just 15-45 minutes - opportunities that hourly averaging completely misses.

**⚡ About This Series**

While this series uses **HVAC heating as the primary example**, the optimization principles apply to **any controllable electrical load**:
- Heat pumps and air conditioning
- Water heaters and boilers
- EV charging systems
- Pool pumps and spa heaters
- Industrial equipment with thermal/energy storage

The key requirement: Your load must tolerate short interruptions or have some form of energy storage capacity (thermal mass, battery, water tank, etc.).

---

Traditional HVAC energy-saving approaches:
- ❌ Turn off heating during the **most expensive hour**
- ❌ Ignore building thermal mass
- ❌ Result in temperature drops and comfort loss

**This series presents a smarter approach**: A Python-based optimization system that:
- ✅ Exploits 15-minute price peaks
- ✅ Respects building thermodynamics
- ✅ Maintains comfort while saving 10-20% on peak costs

**My heating system**: Two air-source heat pumps (ILPs) as the primary heat source, with hydronic radiator heating set very low as backup. This hybrid approach provides flexibility for intelligent optimization.

## The Core Problem

### Traditional Approach


17:00 - Expensive hour detected
17:00 - Turn off HVAC completely
18:00 - Turn on HVAC
18:00 - Building is cold, recovery takes hours


**Result**: Discomfort, slower recovery, suboptimal actual savings.

### My Approach: Intelligent Load Reduction


13:00 - PREHEAT: Warm building above target (store thermal energy)
17:00 - REDUCED HEATING: HVAC fan-only + radiators minimum
21:00 - RECOVERY: Gentle return to normal operation
01:00 - System back to baseline


**Result**: Minimal temperature drop, even heat distribution, optimal energy use, maximum savings.

## The Three Phases Explained

### Phase 1: Preheat (Pre-heating)

**Duration**: Same as cutoff period  
**HVAC Mode**: Active heating (+1°C above target)  
**Radiators**: Elevated temperature (target + offset)  
**Fan**: High speed  
**Purpose**: Store thermal energy in building mass

Your building is a **thermal battery**. By heating it 1-2°C above target before an expensive period, you store energy in walls, floors, and air that can sustain comfort during the reduced heating phase.

**Cost multiplier**: 1.5×  
*Why?* Heating above target requires more energy due to increased heat loss at higher ΔT.

### Phase 2: Reduced Heating (Cutoff)

**Duration**: 1-4 hours (optimized dynamically)  
**HVAC Mode**: Fan-only (circulates air without heating)  
**Radiators**: Minimum temperature setting  
**Fan**: High speed (maintains air circulation)  
**Purpose**: Minimize electricity consumption during peak prices

The heat pump switches to **fan-only mode** to maintain air circulation and even temperature distribution throughout the building, while radiators are set to minimum. This allows the building's thermal mass to sustain comfort with minimal active heating.

**Why not completely off?** Fan circulation prevents cold spots and maintains even temperature distribution using stored thermal energy. The fan draws minimal power (~50W) compared to active heating (2000-5000W).

**Weather-adaptive duration**:
- In extreme cold (<0°C) or heat (>24°C), the system automatically reduces max cutoff to **3 hours** to maintain comfort
- In mild conditions (0-24°C), full **4-hour cutoffs** are allowed

### Phase 3: Recovery

**Duration**: Same as cutoff period  
**HVAC Mode**: Active heating  
**Fan**: Medium to high speed  
**Radiators**: Return to normal offset  
**Purpose**: Return to baseline without shock-loading

Gentle ramp-up to normal operation. Slightly elevated consumption to restore baseline quickly without temperature overshoot.

**Cost multiplier**: 1.2×  
*Why?* You're catching up from a slightly lower temperature, requiring brief elevated output.

## The Optimization Algorithm

### Dynamic Price Difference Scaling

**The Problem**: How do you compare a 1-hour cutoff vs a 4-hour cutoff?

A 1-hour cutoff targets a **sharp price spike**:
- 17:30-18:30: Peak price 36.6 c/kWh
- Average of 1h: ~30 c/kWh
- Requires high price difference: **3.5 c/kWh**

A 4-hour cutoff spans **multiple price levels**:
- 16:00-20:00: Mix of 5-35 c/kWh
- Average of 4h: ~15 c/kWh
- If we required 3.5× 4 = 14 c/kWh difference, we'd **never find 4h cutoffs**

**Solution**: Dynamic scaling


required_price_diff = base_requirement × (1h / cutoff_duration)

1h cutoff: 3.5 × (1/1) = 3.5 c/kWh
2h cutoff: 3.5 × (1/2) = 1.75 c/kWh
4h cutoff: 3.5 × (1/4) = 0.88 c/kWh


**Calibrating the base requirement (3.5 c/kWh):**

This value isn't arbitrary - I calculated it from my **real heating data and Nordpool price history**. By analyzing which cutoff periods actually delivered 10%+ savings over several months, I found that 3.5 c/kWh price difference for 1-hour cutoffs consistently met this threshold for my specific building.

**Your building will likely need different values** depending on:
- Thermal mass (concrete, wood, insulation)
- Heat pump efficiency (SCOP values)
- Backup heating system (radiators, resistive)
- Building size and layout

**Part 3 of this series will show you how to calibrate this value for your own home** using historical data analysis.

This allows the algorithm to find **both sharp peaks and broader elevated periods** while ensuring each cutoff delivers meaningful savings for your specific building characteristics.

### 15-Minute Precision

The system tests:
- **Start time**: Every 15 minutes (16:00, 16:15, 16:30…)
- **Duration**: Every 15 minutes (1.0h, 1.25h, 1.5h, 1.75h, 2.0h…)
- **Total candidates**: ~100-200 per day

**Why not test every possible combination?**

Testing every start × every duration would create 1000+ candidates → memory overflow in Home Assistant templates.

**Python script solution**: Handles this easily, selecting the top ~100 candidates that meet criteria.

## Real-World Example

### October 1, 2025 - Extreme Price Day

**Peak price**: 36.6 c/kWh at 17:45  
**Minimum price**: 0.3 c/kWh at 03:00  
**Average**: 6.2 c/kWh

**Optimized schedule**:
- 13:00-17:00: Preheat
- 17:00-21:00: Reduced heating (4h)
- 21:00-01:00: Recovery

**Costs**:
- Without optimization: 33.82 kWh-value
- With optimization: 21.67 kWh-value

**Savings: 12.15 kWh-value (35.9%)**

**Price difference**: 2.70 c/kWh (average cutoff vs average preheat+recovery)  
**Scaled requirement**: 0.88 c/kWh (for 4h cutoff)

### October 3, 2025 - Moderate Price Day

**Peak price**: 7.66 c/kWh at 17:45  
**Minimum price**: 0.25 c/kWh at 00:45  
**Average**: 2.0 c/kWh

**Optimized schedule**:
- 12:15-16:15: Preheat
- 16:15-20:15: Reduced heating (4h) ← *15-min optimization!*
- 20:15-00:15: Recovery

**Why 16:15 instead of 16:00?**

The 16:00-16:15 slot is relatively cheap (2.45 c/kWh). By starting at 16:15, the system:
- Avoids cutoff during that cheaper period
- Includes the 20:00-20:15 slot in cutoff (2.90 c/kWh)

**Result**: +4.1% additional savings vs hourly optimization

## Key Insights

- **Building thermal mass is a battery**: Store energy when cheap, use when expensive
- **Symmetry is critical**: Preheat and recovery durations must match cutoff
- **Dynamic scaling is necessary**: Different cutoff lengths need different thresholds
- **15-minute precision matters**: 4% additional savings over hourly precision
- **Fan-only maintains comfort**: Air circulation uses minimal energy while distributing stored heat
- **Weather-adaptive optimization**: Cutoff duration adjusted automatically based on outdoor temperature
  - **Summer** (>24°C) or **Winter** (<0°C): 3h max cutoff, 2.5 c/kWh threshold
  - **Mild seasons** (0-24°C): 4h max cutoff, 3.5 c/kWh threshold
  - *Why?* Extreme temperatures increase heat loss → shorter cutoffs maintain comfort

## Generic Application

While this example focuses on HVAC, the same principles apply to:

- **Water heaters**: Preheat water to higher temp, allow tank to cool during cutoff
- **EV charging**: Charge battery above needed level before expensive period
- **Pool heating**: Raise temperature before cutoff period
- **Any load with energy storage capability**

The key is identifying your system's "thermal mass" equivalent and calibrating parameters accordingly.

## Next Steps

→ **[Part 2: Cutoff Optimizer Implementation](./02-cutoff-optimizer.md)** - Python code and technical details  
→ **[Part 3: Integration Examples](./03-integration-examples.md)** - How to integrate with YOUR system

---

*Questions? Discuss in the [Home Assistant Community thread](https://community.home-assistant.io/t/optimizing-hvac-energy-savings-with-nordpool-15-min-pricing-the-theory-part-1-of-3-understanding-the-concept/936741)*

