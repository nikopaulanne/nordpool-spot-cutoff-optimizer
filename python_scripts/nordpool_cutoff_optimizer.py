"""
Nordpool HVAC Cutoff Optimizer — ROBUST VERSION
================================================================

This script optimizes heating/cooling energy savings by identifying the best
times to reduce HVAC power during expensive electricity periods.

KEY FEATURES:
- Auto-detects 15-minute OR 1-hour Nordpool data slots
- Resamples 1-hour data into 15-minute slots (copies price values)
- Calculates costs using actual slot durations (handles DST changes)
- Uses Dynamic Programming to find globally optimal period combinations
- Supports minimum 30-minute cutoff periods (ideal for heat pump cycling)
- No external datetime imports (robust string parsing)

OPTIMIZATION LOGIC:
1. PREHEAT phase: Heat building above target to store thermal energy
2. CUTOFF phase: Reduce heating during expensive periods (fan-only mode)
3. RECOVERY phase: Gentle return to normal operation 

DYNAMIC PROGRAMMING:
Instead of greedily picking the highest-saving periods (which may overlap),
this script finds the best NON-OVERLAPPING combination that maximizes total
savings across the entire 48-hour window.

Author: Community contribution
Version: 2.0 (Robust, DP-based)
"""


# ============================================================================
# CONFIGURATION — Read settings from Home Assistant input helpers
# ============================================================================

def as_float(entity_id, fallback):
    """
    Safely read a float value from a Home Assistant entity.
    Returns fallback value if entity doesn't exist or can't be converted.
    
    Args:
        entity_id: Home Assistant entity ID (e.g., 'input_number.some_setting')
        fallback: Default value to return if reading fails
    
    Returns:
        Float value from entity state, or fallback
    """
    try:
        return float(hass.states.get(entity_id).state)
    except Exception:
        return fallback


# User-configurable parameters from Home Assistant UI
max_hours       = as_float('input_number.nordpool_price_savings_sequential_hours', 5.0)
min_price_diff  = as_float('input_number.nordpool_price_savings_minimum_price_difference', 3.0)

# Energy multipliers for each phase
preheat_mult    = 1.5   # Preheat uses 50% more energy (heating above target)
recovery_mult   = 1.2   # Recovery uses 20% more energy (catching up)

# Output limits
max_periods     = 6     # Maximum number of cutoff periods to return

# Dynamic scaling reference
reference_duration_h = 1.0  # Base duration (1 hour) for price difference threshold

# Slot processing constants
SLOTS_PER_HOUR  = 4     # Four 15-minute slots per hour
MIN_SLOTS       = 2     # Minimum cutoff duration: 2 slots = 30 minutes
MAX_SCAN        = 50000 # Safety limit: stop scanning after this many candidates


# ============================================================================
# UTILITY FUNCTIONS — No datetime imports, pure string manipulation
# ============================================================================

def clean_tz(s):
    """
    Remove timezone suffixes from ISO timestamp strings.
    Handles: +0300, +03:00, Z
    
    Example:
        '2025-10-03T16:00:00+0300' → '2025-10-03T16:00:00'
    
    Args:
        s: ISO timestamp string
    
    Returns:
        Timestamp string without timezone suffix
    """
    if not isinstance(s, str):
        return ""
    return s.replace("+0300", "").replace("+03:00", "").replace("Z", "")


def hh(s):
    """
    Extract hour component from ISO timestamp string.
    
    Example:
        '2025-10-03T16:30:00' → 16
    
    Args:
        s: ISO timestamp string
    
    Returns:
        Integer hour (0-23), or 0 if parsing fails
    """
    try:
        return int(clean_tz(s)[11:13])
    except Exception:
        return 0


def mm(s):
    """
    Extract minute component from ISO timestamp string.
    
    Example:
        '2025-10-03T16:30:00' → 30
    
    Args:
        s: ISO timestamp string
    
    Returns:
        Integer minute (0-59), or 0 if parsing fails
    """
    try:
        return int(clean_tz(s)[14:16])
    except Exception:
        return 0


def date_str(s):
    """
    Extract date component from ISO timestamp string.
    
    Example:
        '2025-10-03T16:30:00' → '2025-10-03'
    
    Args:
        s: ISO timestamp string
    
    Returns:
        Date string in YYYY-MM-DD format
    """
    try:
        return clean_tz(s)[:10]
    except Exception:
        return ""


def slot_minutes(slot):
    """
    Calculate the duration of a price slot in minutes.
    Handles midnight crossover (e.g., 23:45 → 00:15).
    
    This is important because:
    - DST changes may create irregular slot durations
    - Some integrations may have varying slot lengths
    - Midnight crossover needs special handling
    
    Args:
        slot: Dictionary with 'start' and 'end' ISO timestamps
    
    Returns:
        Integer duration in minutes (defaults to 15 if calculation fails)
    """
    try:
        ss = slot.get('start')
        ee = slot.get('end')
        if not ss or not ee:
            return 15
        
        # Extract date and time components
        sd = date_str(ss); ed = date_str(ee)
        sh = hh(ss); sm = mm(ss)
        eh = hh(ee); em = mm(ee)
        
        # Convert to minutes since midnight
        smin = sh*60 + sm
        emin = eh*60 + em
        
        # Same day: simple subtraction
        if sd == ed:
            diff = emin - smin
        else:
            # Midnight crossover: add minutes to midnight + minutes after midnight
            diff = (24*60 - smin) + emin
        
        if diff <= 0:
            return 15
        return diff
    except Exception:
        return 15


def detect_typical_minutes(slots):
    """
    Detect the typical duration of slots in the dataset.
    
    This auto-detects whether Nordpool data is:
    - 15-minute resolution (already optimal)
    - 1-hour resolution (needs resampling)
    - Other 15-minute multiples (30min, 45min, etc.)
    
    Args:
        slots: List of slot dictionaries
    
    Returns:
        Typical slot duration in minutes (15, 60, etc.)
    """
    if not slots:
        return 15
    
    # Sample first 5 slots
    vals = []
    n = min(5, len(slots))
    for i in range(n):
        d = slot_minutes(slots[i])
        if d > 0:
            vals.append(d)
    
    if not vals:
        return 15
    
    # Calculate average duration
    avg = sum(vals) / len(vals)
    
    # Round to nearest 15-minute multiple
    k = int(round(avg / 15.0))
    if k < 1:
        k = 1
    return k * 15


def resample_to_15min(slots):
    """
    Convert any slot duration to 15-minute resolution.
    
    WHY THIS IS NEEDED:
    - Some Nordpool integrations provide only 1-hour data
    - To optimize 30-minute cutoffs, we need 15-minute resolution
    - This function "splits" 1-hour slots into 4× 15-minute slots
    
    EXAMPLE:
        Input:  [{'start': '16:00', 'end': '17:00', 'value': 5.2}]
        Output: [
            {'start': '16:00', 'end': '16:15', 'value': 5.2},
            {'start': '16:15', 'end': '16:30', 'value': 5.2},
            {'start': '16:30', 'end': '16:45', 'value': 5.2},
            {'start': '16:45', 'end': '17:00', 'value': 5.2}
        ]
    
    Args:
        slots: Original list of price slots
    
    Returns:
        Tuple: (normalized_slots, original_duration_minutes)
    """
    out = []
    if not slots:
        return out, None

    typ_min = detect_typical_minutes(slots)

    # CASE 1: Already 15-minute resolution
    if typ_min == 15:
        for s in slots:
            out.append({
                'start': s['start'],
                'end':   s['end'],
                'value': float(s['value']),
                'dur_min': slot_minutes(s)
            })
        return out, 15

    # CASE 2: 15-minute multiple (e.g., 60 min) → split into quarters
    if typ_min % 15 == 0:
        factor = typ_min // 15  # How many 15-min slots fit in original
        
        for s in slots:
            ss = clean_tz(s.get('start', ''))
            sh, sm = hh(ss), mm(ss)
            sd = date_str(ss)

            # Create 'factor' 15-minute slots from this one slot
            for k in range(factor):
                # Calculate start time of this 15-min slot
                total_min = sh*60 + sm + 15*k
                nh = (total_min // 60) % 24
                nm = total_min % 60
                st = f"{sd}T{str(nh).zfill(2)}:{str(nm).zfill(2)}:00"
                
                # Calculate end time (15 minutes later)
                et_total = total_min + 15
                eh = (et_total // 60) % 24
                em = et_total % 60
                et = f"{sd}T{str(eh).zfill(2)}:{str(em).zfill(2)}:00"

                out.append({
                    'start': st,
                    'end': et,
                    'value': float(s['value']),  # Copy same price to all sub-slots
                    'dur_min': 15
                })
        return out, typ_min

    # CASE 3: Irregular duration → use as-is
    for s in slots:
        out.append({
            'start': s.get('start'),
            'end':   s.get('end'),
            'value': float(s['value']),
            'dur_min': slot_minutes(s)
        })
    return out, typ_min


# ============================================================================
# MAIN OPTIMIZATION LOGIC
# ============================================================================

# Retrieve Nordpool sensor data
nordpool = hass.states.get('sensor.nordpool_fi')

if not nordpool:
    logger.error("Nordpool sensor not found")
    hass.states.set('sensor.nordpool_cutoff_periods_python', 'error', {
        'friendly_name': 'Nordpool Cutoff Periods',
        'error': 'Nordpool sensor not found'
    })
else:
    # Get raw price data (today and tomorrow)
    raw_today    = list(nordpool.attributes.get('raw_today', []))
    raw_tomorrow = list(nordpool.attributes.get('raw_tomorrow', []))

    if not raw_today or len(raw_today) < 4:
        logger.warning("Insufficient Nordpool data (today)")
        hass.states.set('sensor.nordpool_cutoff_periods_python', '0', {
            'periods': [],
            'friendly_name': 'Nordpool Cutoff Periods',
            'warning': 'Insufficient today data'
        })
    else:
        # Normalize both datasets to 15-minute resolution
        today15,  dur_today_min  = resample_to_15min(raw_today)
        tomo15,   dur_tomo_min   = resample_to_15min(raw_tomorrow) if raw_tomorrow else ([], None)

        # Combine into single 48-hour dataset
        all_slots = today15 + tomo15
        
        if not all_slots:
            hass.states.set('sensor.nordpool_cutoff_periods_python', '0', {
                'periods': [],
                'friendly_name': 'Nordpool Cutoff Periods',
                'warning': 'No normalized slots available'
            })
        else:
            # ================================================================
            # STEP 1: GENERATE CANDIDATE CUTOFF PERIODS
            # ================================================================
            
            results = []          # Will store all valid candidate periods
            start_offset = 0      # Start scanning from beginning (could be 64 for "after 16:00")
            max_slots = int(max_hours * SLOTS_PER_HOUR)  # Max slots in a cutoff
            N = len(all_slots)    # Total number of 15-min slots available
            scanned = 0           # Counter for safety limit

            # Minimum cutoff duration in hours (e.g., 0.5h for 30 minutes)
            min_shutdown_h = MIN_SLOTS * 15.0 / 60.0

            # Loop through every possible cutoff start position
            for start in range(start_offset, N):
                # Calculate maximum possible cutoff length at this position
                # Must have room for: preheat (before) + cutoff + recovery (after)
                max_len_here = min(
                    max_slots,              # User-defined max
                    start,                  # Can't go before start of data (need preheat space)
                    N - (start + MIN_SLOTS*2)  # Need space for cutoff + recovery
                )
                
                if max_len_here < MIN_SLOTS:
                    continue  # Not enough room, skip this start position

                # Try all possible cutoff lengths from this start position
                for length in range(MIN_SLOTS, max_len_here + 1):
                    scanned += 1
                    if scanned > MAX_SCAN:
                        break  # Safety: prevent infinite loops

                    # Define the three phases:
                    # PREHEAT: [pre_start ... sh_start)
                    # CUTOFF:  [sh_start ... rec_start)
                    # RECOVERY: [rec_start ... rec_end_i]
                    
                    pre_start = start - length
                    sh_start  = start
                    rec_start = start + length
                    rec_end_i = start + length*2 - 1
                    
                    # Validate indices
                    if pre_start < 0 or rec_end_i >= N:
                        continue

                    try:
                        # ====================================================
                        # PHASE 1: PREHEAT COST CALCULATION
                        # ====================================================
                        # Heat building above target before expensive period
                        # Store thermal energy in building mass
                        
                        pre_cost = 0.0  # Total cost in this phase
                        pre_min = 0     # Total duration in minutes
                        
                        for i in range(pre_start, sh_start):
                            dm = int(all_slots[i].get('dur_min', 15))
                            # Cost = price (c/kWh) × duration (hours)
                            pre_cost += float(all_slots[i]['value']) * (dm/60.0)
                            pre_min  += dm

                        # ====================================================
                        # PHASE 2: CUTOFF COST CALCULATION
                        # ====================================================
                        # This is the expensive period we want to avoid
                        # Calculate how much we WOULD spend if heating normally
                        
                        high_cost = 0.0
                        high_min = 0
                        
                        for i in range(sh_start, rec_start):
                            dm = int(all_slots[i].get('dur_min', 15))
                            high_cost += float(all_slots[i]['value']) * (dm/60.0)
                            high_min  += dm

                        # ====================================================
                        # PHASE 3: RECOVERY COST CALCULATION
                        # ====================================================
                        # Gentle ramp-up back to normal operation
                        
                        rec_cost = 0.0
                        rec_min = 0
                        
                        for i in range(rec_start, rec_start + length):
                            dm = int(all_slots[i].get('dur_min', 15))
                            rec_cost += float(all_slots[i]['value']) * (dm/60.0)
                            rec_min  += dm

                        # Convert minutes to hours for calculations
                        pre_h = pre_min/60.0
                        high_h = high_min/60.0
                        rec_h = rec_min/60.0

                        # ====================================================
                        # COST COMPARISON
                        # ====================================================
                        
                        # WITH cutoff: elevated preheat + skip cutoff + elevated recovery
                        total_with = (pre_cost * preheat_mult) + (rec_cost * recovery_mult)
                        
                        # WITHOUT cutoff: normal consumption throughout all phases
                        total_without = pre_cost + high_cost + rec_cost

                        # ====================================================
                        # PRICE DIFFERENCE ANALYSIS
                        # ====================================================
                        # Calculate average prices to verify cutoff period is
                        # genuinely more expensive than preheat/recovery periods
                        
                        # Average price during cutoff period
                        avg_high = (high_cost / high_h) if high_h > 0 else 0.0
                        
                        # Weighted average price during preheat + recovery
                        # (weighted by multipliers)
                        denom = pre_h * preheat_mult + rec_h * recovery_mult
                        avg_rest = ((pre_cost * preheat_mult + rec_cost * recovery_mult) / denom) if denom > 0 else 0.0
                        
                        # Price difference: how much more expensive is cutoff period?
                        price_diff = avg_high - avg_rest

                        # ====================================================
                        # DYNAMIC SCALING
                        # ====================================================
                        # Longer cutoffs naturally have lower average price differences
                        # (they include both peaks and valleys)
                        # Scale the minimum threshold accordingly:
                        # - 1h cutoff: requires 3.5 c/kWh difference
                        # - 2h cutoff: requires 1.75 c/kWh difference
                        # - 4h cutoff: requires 0.88 c/kWh difference
                        
                        duration_factor = reference_duration_h / high_h if high_h > 0 else 1.0
                        adjusted_min = min_price_diff * duration_factor

                        # ====================================================
                        # VALIDATION CHECKS
                        # ====================================================
                        # A period is valid if:
                        # 1. Cutoff duration >= minimum (e.g., 30 minutes)
                        # 2. We actually save money (total_with < total_without)
                        # 3. Price difference meets scaled threshold
                        
                        if high_h >= min_shutdown_h and total_with < total_without and price_diff >= adjusted_min:
                            # Format duration for display (e.g., "2h 30min")
                            htxt_h = int(high_h)
                            htxt_m = int(round((high_h - htxt_h) * 60))
                            
                            # Create period dictionary with all relevant data
                            period = {
                                'preheat_start': all_slots[pre_start]['start'],
                                'shutdown_start': all_slots[sh_start]['start'],
                                'recovery_start': all_slots[rec_start]['start'],
                                'recovery_end':   all_slots[rec_end_i]['end'],
                                'cost_saving': round(total_without - total_with, 3),
                                'cost_saving_percent': round(((total_without - total_with)/total_without)*100, 1) if total_without > 0 else 0,
                                'shutdown_duration_hours': round(high_h, 2),
                                'shutdown_duration_text': f"{htxt_h}h {htxt_m}min" if htxt_m > 0 else f"{htxt_h}h",
                                'details': {
                                    'total_cost_with_shutdown': round(total_with, 3),
                                    'total_cost_without_shutdown': round(total_without, 3),
                                    'price_difference': round(price_diff, 3),
                                    'adjusted_min_price_diff': round(adjusted_min, 3)
                                },
                                'idx': sh_start,  # For overlap detection
                                'len': length     # For overlap detection
                            }
                            results.append(period)

                    except Exception as e:
                        logger.warning(f"Calculation error: {e}")
                        continue

                if scanned > MAX_SCAN:
                    logger.warning(f"Candidate scan limit reached: {MAX_SCAN}")
                    break

            # ================================================================
            # STEP 2: DYNAMIC PROGRAMMING — OPTIMAL PERIOD SELECTION
            # ================================================================
            # Problem: We have many overlapping candidate periods
            # Goal: Select the best NON-OVERLAPPING combination
            # Method: Weighted Interval Scheduling (DP algorithm)
            
            intervals = []
            for p in results:
                # Each period reserves a "window" spanning:
                # preheat + cutoff + recovery
                win_start = p['idx'] - p['len']       # Start of preheat
                win_end   = p['idx'] + 2*p['len']     # End of recovery (exclusive)
                
                intervals.append({
                    'start': win_start,
                    'end': win_end,
                    'save': p['cost_saving'],
                    'p': p
                })

            final = []         # Selected periods
            total_saving = 0.0 # Total savings across all periods

            if intervals:
                # Sort intervals by end time (required for DP)
                intervals.sort(key=lambda it: it['end'])
                ends = [it['end'] for it in intervals]

                def prev_compat(i):
                    """
                    Find the latest interval that ends before interval i starts.
                    Uses binary search for efficiency.
                    
                    This is the key to DP: for each interval, we need to know
                    which previous interval we can combine it with without overlap.
                    """
                    lo = 0
                    hi = i - 1
                    ans = -1
                    s = intervals[i]['start']
                    
                    while lo <= hi:
                        mid = (lo + hi)//2
                        if ends[mid] <= s:
                            ans = mid
                            lo = mid + 1
                        else:
                            hi = mid - 1
                    return ans

                # Precompute compatibility for all intervals
                prev_idx = [prev_compat(i) for i in range(len(intervals))]

                # DP arrays
                n = len(intervals)
                dp = [0.0]*(n+1)      # dp[i] = max savings using intervals 0..i-1
                take = [False]*n      # take[i] = whether to include interval i

                # Fill DP table
                for i in range(1, n+1):
                    # Option 1: Don't take interval i-1
                    notake = dp[i-1]
                    
                    # Option 2: Take interval i-1
                    j = prev_idx[i-1]
                    take_val = intervals[i-1]['save'] + (dp[j+1] if j >= 0 else 0.0)
                    
                    # Choose better option
                    if take_val > notake:
                        dp[i] = take_val
                        take[i-1] = True
                    else:
                        dp[i] = notake

                # Backtrack to find which intervals were selected
                chosen = []
                i = n - 1
                while i >= 0 and len(chosen) < max_periods:
                    if take[i]:
                        chosen.append(intervals[i]['p'])
                        # Jump to last compatible interval
                        i = prev_idx[i] if prev_idx[i] is not None else -1
                    else:
                        i -= 1

                # Sort selected periods chronologically
                final = sorted(chosen, key=lambda x: x['preheat_start'])
                total_saving = round(sum(p['cost_saving'] for p in final), 3)

            # ================================================================
            # STEP 3: CREATE SENSOR WITH RESULTS
            # ================================================================
            
            # Determine data resolution description
            data_res = '15min (normalized)'
            if (dur_today_min and dur_today_min != 15) or (dur_tomo_min and dur_tomo_min != 15):
                data_res = 'mixed→15min'

            # Create sensor with all results and metadata
            hass.states.set('sensor.nordpool_cutoff_periods_python', str(len(final)), {
                'periods': final,
                'friendly_name': 'Nordpool Cutoff Periods',
                'icon': 'mdi:lightning-bolt',
                'data_resolution': data_res,
                'today_slot_minutes': dur_today_min,
                'tomorrow_slot_minutes': dur_tomo_min,
                'optimization_method': 'DP (full window), robust slots',
                'unit_of_measurement': 'periods',
                'candidates_scanned': scanned,
                'results_found': len(results),
                'total_cost_saving': total_saving,
                'min_slots': MIN_SLOTS,
                'max_slots': max_slots
            })
            
            logger.info(f"Nordpool optimizer complete: "
                       f"final={len(final)} periods, "
                       f"candidates={len(results)}, "
                       f"scanned={scanned}, "
                       f"total_saving={total_saving}, "
                       f"today_resolution={dur_today_min}min, "
                       f"tomorrow_resolution={dur_tomo_min}min")