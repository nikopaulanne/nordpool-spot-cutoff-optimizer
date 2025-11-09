"""
═══════════════════════════════════════════════════════════════════════════
NORDPOOL SPOT CUTOFF OPTIMIZER FOR HOME ASSISTANT
═══════════════════════════════════════════════════════════════════════════

PURPOSE:
    Analyze Nordpool spot prices and schedule optimal load cutoffs
    (preheat → shutdown → recovery) to minimize cost while preserving comfort.

VERSION: 2.0 (Production-Ready, Configurable Nordpool Sensor, Robust Timestamps)

WHAT’S INCLUDED IN v2.0:
    ✓ Configurable Nordpool sensor resolution (via service data / input_text / fallbacks)
    ✓ Mixed-resolution support (15 min + 60 min)
    ✓ Midnight crossover/date seam fixes for all cases
    ✓ Weather-adaptive preheat/recovery multipliers with failsafe
    ✓ DP-based optimal non-overlapping selection
    ✓ Telemetry: which Nordpool entity was used and how it was resolved

OUTPUT SENSOR:
    sensor.nordpool_cutoff_periods_python
    Attributes include:
      - periods: list of dicts with:
          preheat_start, shutdown_start, recovery_start, recovery_end
          cost_saving, cost_saving_percent
          shutdown_duration_hours, shutdown_duration_text
          details: total_cost_with_shutdown, total_cost_without_shutdown,
                   price_difference, adjusted_min_price_diff
      - data_resolution, today_slot_minutes, tomorrow_slot_minutes
      - optimization_method: "DP (full window), robust slots v2.0"
      - candidates_scanned, results_found, total_cost_saving
      - preheat_mult, recovery_mult, multiplier_source, outdoor_temp_c
      - nordpool_entity, nordpool_source

AUTHOR: Community contribution
LICENSE: MIT

NOTE:
  This script is designed for Home Assistant’s python_script sandbox.
  No external imports (datetime, etc.) are used; timestamps are handled
  with safe string parsing and guardrails.

═══════════════════════════════════════════════════════════════════════════
"""


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 — CONFIGURATION & HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def as_float(entity_id, fallback):
    """
    Safely read a numeric value from a Home Assistant entity.
    Returns fallback if entity missing, unavailable, or non-numeric.
    """
    try:
        return float(hass.states.get(entity_id).state)
    except Exception:
        return fallback


def as_str(entity_id, fallback):
    """
    Safely read a string value from a Home Assistant entity (e.g. input_text).
    Returns fallback if entity missing or unusable.
    """
    try:
        st = hass.states.get(entity_id)
        sv = st.state if st else None
        if sv and str(sv).lower() not in ('unknown', 'unavailable', 'none', 'null', 'nan', ''):
            return sv
        return fallback
    except Exception:
        return fallback


# User-configurable parameters (tune via HA UI)
max_hours = as_float('input_number.nordpool_price_savings_sequential_hours', 5.0)  # max length of a single shutdown
min_price_diff = as_float('input_number.nordpool_price_savings_minimum_price_difference', 3.0)  # base threshold (c/kWh) for 1h


# ───────────────────────────────────────────────────────────────────────────
# Nordpool entity resolution — fixes naming mismatch issues
# Priority: 1) service data np_entity → 2) input_text helper → 3) fallbacks
# ───────────────────────────────────────────────────────────────────────────

# 1) Service data parameter in automation:
# action:
#   - service: python_script.nordpool_cutoff_optimizer
#     data:
#       np_entity: sensor.your_nordpool_sensor
np_from_service = None
try:
    np_from_service = data.get('np_entity')
except Exception:
    np_from_service = None

# 2) Optional input_text helper (create in HA if you prefer UI config)
NP_INPUT_TEXT = 'input_text.nordpool_entity_id'
np_from_helper = as_str(NP_INPUT_TEXT, None)

# 3) Fallbacks for common Nordpool sensors (region-specific examples)
NP_FALLBACKS = [
    'sensor.nordpool_fi',
    'sensor.nordpool_kwh_fi_eur_3_10_0',
    'sensor.nordpool_kwh_se3_eur_3_10_0',
    'sensor.nordpool_kwh_dk1_eur_3_10_0',
    'sensor.nordpool_kwh_no2_eur_3_10_0'
]


def has_nordpool_attributes(entity_id):
    """
    Validate that entity looks like a Nordpool price sensor
    (must have raw_today list, raw_tomorrow optional).
    """
    try:
        st = hass.states.get(entity_id)
        if not st:
            return False
        attrs = st.attributes
        return bool(attrs and 'raw_today' in attrs)
    except Exception:
        return False


# Collate candidates in priority order
candidates = []
if np_from_service:
    candidates.append(('service_data', np_from_service))
if np_from_helper:
    candidates.append(('input_text', np_from_helper))
for fb in NP_FALLBACKS:
    candidates.append(('fallback', fb))

# Resolve the Nordpool entity
nordpool = None
NP_ENTITY_USED = None
NP_SOURCE = None
for source, entity_id in candidates:
    if entity_id and has_nordpool_attributes(entity_id):
        nordpool = hass.states.get(entity_id)
        NP_ENTITY_USED = entity_id
        NP_SOURCE = source
        break

# Abort early (but gracefully) if Nordpool sensor isn’t found
if not nordpool:
    tried_entities = [eid for (src, eid) in candidates if eid]
    logger.error(
        "Nordpool sensor not found or missing raw_today. "
        "Tried: %s. Configure 'np_entity' in service data or create input_text.nordpool_entity_id.",
        tried_entities
    )
    hass.states.set('sensor.nordpool_cutoff_periods_python', 'error', {
        'friendly_name': 'Nordpool Cutoff Periods',
        'error': 'Nordpool sensor not found',
        'tried_entities': tried_entities,
        'solution': 'Set np_entity in automation or create input_text.nordpool_entity_id'
    })
    import sys
    sys.exit(0)  # do not crash HA, just exit script


# ───────────────────────────────────────────────────────────────────────────
# Weather-adaptive multipliers (with hard failsafe)
# ───────────────────────────────────────────────────────────────────────────

ENTITY_OUTDOOR_TEMP = 'sensor.weather_combined_temperature'
DEFAULT_PREHEAT = 1.5   # legacy fallback
DEFAULT_RECOVERY = 1.2  # legacy fallback


def get_state_str(entity_id):
    try:
        st = hass.states.get(entity_id)
        return st.state if st else None
    except Exception:
        return None


def get_safe_outdoor_temp(entity_id):
    """
    Returns (float_temp, None) on success.
    Returns (None, reason) if missing/invalid/unrealistic.
    """
    s = get_state_str(entity_id)
    if not s or str(s).lower() in ('unknown', 'unavailable', 'none', 'null', 'nan'):
        return None, 'missing_or_nonready'
    try:
        v = float(s)
    except Exception:
        return None, 'non_numeric'
    if v < -60.0 or v > 60.0:
        return None, 'out_of_range'
    return v, None


def dynamic_multipliers_by_temp(t_out_c):
    """
    Return (preheat_mult, recovery_mult) based on outdoor temp bands.
    Clamped to safe ranges: pre ∈ [1.02, 1.50], rec ∈ [1.01, 1.25].
    """
    if t_out_c >= 7.0:
        pre, rec = 1.08, 1.04
    elif t_out_c >= 2.0:
        pre, rec = 1.14, 1.08
    elif t_out_c >= -3.0:
        pre, rec = 1.24, 1.12
    elif t_out_c >= -10.0:
        pre, rec = 1.34, 1.15
    else:
        pre, rec = 1.45, 1.20
    pre = max(1.02, min(pre, 1.50))
    rec = max(1.01, min(rec, 1.25))
    return pre, rec


multiplier_source = 'fallback_legacy'
outdoor_temp_used = None
try:
    t_out, temp_err = get_safe_outdoor_temp(ENTITY_OUTDOOR_TEMP)
    if t_out is None:
        preheat_mult, recovery_mult = DEFAULT_PREHEAT, DEFAULT_RECOVERY
        try:
            logger.warning(
                "[HVAC multipliers] FAILSAFE (%s). Using defaults preheat=%.2f, recovery=%.2f",
                temp_err, DEFAULT_PREHEAT, DEFAULT_RECOVERY
            )
        except Exception:
            pass
        multiplier_source = "fallback_legacy:" + str(temp_err)
    else:
        preheat_mult, recovery_mult = dynamic_multipliers_by_temp(t_out)
        multiplier_source = 'dynamic_by_temp'
        outdoor_temp_used = t_out
except Exception as exc:
    preheat_mult, recovery_mult = DEFAULT_PREHEAT, DEFAULT_RECOVERY
    multiplier_source = "failsafe_exception:" + str(exc)
    try:
        logger.warning(
            "[HVAC multipliers] FAILSAFE exception: %s; using defaults preheat=%.2f, recovery=%.2f",
            exc, DEFAULT_PREHEAT, DEFAULT_RECOVERY
        )
    except Exception:
        pass


# ───────────────────────────────────────────────────────────────────────────
# Core constants
# ───────────────────────────────────────────────────────────────────────────
max_periods = 6             # maximum number of selected cutoff periods
reference_duration_h = 1.0  # used for duration scaling of min_price_diff
SLOTS_PER_HOUR = 4          # 4 × 15 min slots / hour
MIN_SLOTS = 2               # minimum cutoff (30 min)
MAX_SCAN = 50000            # safety upper bound for candidate scanning


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 — TIME/TIMESTAMP UTILITIES (no datetime imports)
# ═══════════════════════════════════════════════════════════════════════════

def clean_tz(s):
    """
    Strip timezone suffixes (+0300, +03:00, +0200, +02:00, Z).
    HA’s as_timestamp works consistently with tz-less ISO strings.
    """
    if not isinstance(s, str):
        return ""
    s = s.replace("+0300", "").replace("+03:00", "")
    s = s.replace("+0200", "").replace("+02:00", "")
    s = s.replace("Z", "")
    return s


def hh(s):
    """Extract hour from 'YYYY-MM-DDTHH:MM:SS'."""
    try:
        return int(clean_tz(s)[11:13])
    except Exception:
        return 0


def mm(s):
    """Extract minute from 'YYYY-MM-DDTHH:MM:SS'."""
    try:
        return int(clean_tz(s)[14:16])
    except Exception:
        return 0


def date_str(s):
    """Extract 'YYYY-MM-DD' from ISO timestamp."""
    try:
        return clean_tz(s)[:10]
    except Exception:
        return ""


def add_day(date_string):
    """
    Add one day to YYYY-MM-DD string (handles month/year/leap-year).
    Implemented without datetime to comply with python_script sandbox.
    """
    try:
        y = int(date_string[0:4])
        m = int(date_string[5:7])
        d = int(date_string[8:10])
        days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        is_leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
        if is_leap:
            days_in_month[1] = 29
        d += 1
        if d > days_in_month[m - 1]:
            d = 1
            m += 1
            if m > 12:
                m = 1
                y += 1
        return f"{y:04d}-{m:02d}-{d:02d}"
    except Exception:
        return date_string


def fix_midnight_crossover(start_ts, end_ts):
    """
    Fix end timestamp if it appears to be before start due to midnight rollover.
    Cases:
      - Same date but end hour < start hour → move end to next day
      - Late evening (20–23) → early morning (00–02) on same date → move end to next day
    """
    start_cleaned = clean_tz(start_ts)
    end_cleaned = clean_tz(end_ts)
    start_date = date_str(start_cleaned)
    end_date = date_str(end_cleaned)
    start_hour = hh(start_cleaned)
    end_hour = hh(end_cleaned)

    if end_date == start_date and end_hour < start_hour:
        next_day = add_day(end_date)
        end_time = end_cleaned[11:]
        return f"{next_day}T{end_time}"

    if end_hour <= 2 and start_hour >= 20 and end_date == start_date:
        next_day = add_day(end_date)
        end_time = end_cleaned[11:]
        return f"{next_day}T{end_time}"

    return end_cleaned


def ensure_tomorrow_dates(slots, reference_date):
    """
    Ensure that tomorrow slots are on/after today’s last date (fix seam issues).
    If start date < reference, bump start to reference+1 day (preserve time).
    Ensure end date >= start date similarly.
    """
    if not slots or not reference_date:
        return slots
    fixed = []
    for slot in slots:
        start_ts = slot.get('start', '')
        end_ts = slot.get('end', '')
        start_date = date_str(start_ts)
        end_date = date_str(end_ts)

        if start_date < reference_date:
            next_date = add_day(reference_date)
            start_ts = f"{next_date}T{start_ts[11:]}"

        start_date_fixed = date_str(start_ts)
        if end_date < start_date_fixed:
            next_date = add_day(start_date_fixed)
            end_ts = f"{next_date}T{end_ts[11:]}"

        fixed.append({
            'start': start_ts,
            'end': end_ts,
            'value': slot.get('value', 0.0),
            'dur_min': slot.get('dur_min', 15)
        })
    return fixed


def slot_minutes(slot):
    """
    Compute slot duration in minutes. Handles midnight crossover.
    Return 15 on any parsing error (safe default).
    """
    try:
        ss = slot.get('start'); ee = slot.get('end')
        if not ss or not ee:
            return 15
        sd = date_str(ss); ed = date_str(ee)
        sh = hh(ss); sm = mm(ss)
        eh = hh(ee); em = mm(ee)
        smin = sh * 60 + sm
        emin = eh * 60 + em
        if sd == ed:
            diff = emin - smin
        else:
            diff = (24 * 60 - smin) + emin
        if diff <= 0:
            return 15
        return diff
    except Exception:
        return 15


def detect_typical_minutes(slots):
    """
    Detect typical slot duration (15/30/45/60...). Uses first up to 5 slots.
    Rounds to nearest 15-minute multiple; defaults to 15 if uncertain.
    """
    if not slots:
        return 15
    vals = []
    n = min(5, len(slots))
    for i in range(n):
        d = slot_minutes(slots[i])
        if d > 0:
            vals.append(d)
    if not vals:
        return 15
    avg = sum(vals) / len(vals)
    k = int(round(avg / 15.0))
    if k < 1:
        k = 1
    return k * 15


def resample_to_15min(slots):
    """
    Normalize input slots to 15-minute resolution.
    CASE 1: Already 15 min → strip tz + fix midnight crossover
    CASE 2: Multiple of 15 (e.g. 60 min) → split into 15 min sub-slots
    CASE 3: Irregular → keep as-is, but normalize tz and fix end time
    Returns (normalized_slots, original_typical_minutes or None).
    """
    out = []
    if not slots:
        return out, None

    typ_min = detect_typical_minutes(slots)

    # CASE 1 — already 15-minute resolution
    if typ_min == 15:
        for s in slots:
            start_clean = clean_tz(s['start'])
            end_clean = clean_tz(s['end'])
            end_fixed = fix_midnight_crossover(start_clean, end_clean)
            out.append({
                'start': start_clean,
                'end': end_fixed,
                'value': float(s['value']),
                'dur_min': slot_minutes(s)
            })
        return out, 15

    # CASE 2 — 15-minute multiple (e.g. 60 → split to 4×15)
    if typ_min % 15 == 0:
        factor = typ_min // 15
        for s in slots:
            ss = clean_tz(s.get('start', ''))
            ee = clean_tz(s.get('end', ''))
            sh, sm = hh(ss), mm(ss)
            sd = date_str(ss)
            ed = date_str(ee)
            for k in range(factor):
                total_min = sh * 60 + sm + 15 * k
                nh = (total_min // 60) % 24
                nm = total_min % 60
                # midnight crossover for start
                if nh < sh and k > 0:
                    st_date = ed if ed != sd else add_day(sd)
                else:
                    st_date = sd
                st = f"{st_date}T{str(nh).zfill(2)}:{str(nm).zfill(2)}:00"
                # end 15 minutes later
                et_total = total_min + 15
                eh = (et_total // 60) % 24
                em = et_total % 60
                # midnight crossover for end
                if eh < nh or (eh == 0 and nh == 23):
                    et_date = ed if ed != sd else add_day(st_date)
                else:
                    et_date = st_date
                et = f"{et_date}T{str(eh).zfill(2)}:{str(em).zfill(2)}:00"
                out.append({
                    'start': st,
                    'end': et,
                    'value': float(s['value']),
                    'dur_min': 15
                })
        return out, typ_min

    # CASE 3 — irregular durations; normalize tz and fix end
    for s in slots:
        start_clean = clean_tz(s.get('start', ''))
        end_clean = clean_tz(s.get('end', ''))
        end_fixed = fix_midnight_crossover(start_clean, end_clean)
        out.append({
            'start': start_clean,
            'end': end_fixed,
            'value': float(s['value']),
            'dur_min': slot_minutes(s)
        })
    return out, typ_min


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 — MAIN OPTIMIZATION
# ═══════════════════════════════════════════════════════════════════════════

# Read raw data
raw_today = list(nordpool.attributes.get('raw_today', []))
raw_tomorrow = list(nordpool.attributes.get('raw_tomorrow', []))

if not raw_today or len(raw_today) < 4:
    logger.warning("Insufficient Nordpool data (today)")
    hass.states.set('sensor.nordpool_cutoff_periods_python', '0', {
        'periods': [],
        'friendly_name': 'Nordpool Cutoff Periods',
        'warning': 'Insufficient today data',
        'nordpool_entity': NP_ENTITY_USED,
        'nordpool_source': NP_SOURCE
    })
else:
    # Normalize to 15-minute resolution
    today15, dur_today_min = resample_to_15min(raw_today)
    tomo15,  dur_tomo_min  = resample_to_15min(raw_tomorrow) if raw_tomorrow else ([], None)

    # Seam fix: ensure tomorrow slots start from at least today’s last date
    if today15 and tomo15:
        last_today_date = date_str(today15[-1]['end'])
        tomo15 = ensure_tomorrow_dates(tomo15, last_today_date)

    all_slots = today15 + tomo15

    if not all_slots:
        hass.states.set('sensor.nordpool_cutoff_periods_python', '0', {
            'periods': [],
            'friendly_name': 'Nordpool Cutoff Periods',
            'warning': 'No normalized slots available',
            'nordpool_entity': NP_ENTITY_USED,
            'nordpool_source': NP_SOURCE
        })
    else:
        # STEP 1 — generate candidate shutdown windows
        results = []
        start_offset = 0
        max_slots = int(max_hours * SLOTS_PER_HOUR)
        N = len(all_slots)
        scanned = 0
        min_shutdown_h = MIN_SLOTS * 15.0 / 60.0

        for start in range(start_offset, N):
            # Enough space before (preheat) and after (shutdown+recovery)?
            max_len_here = min(max_slots, start, N - (start + MIN_SLOTS * 2))
            if max_len_here < MIN_SLOTS:
                continue

            for length in range(MIN_SLOTS, max_len_here + 1):
                scanned += 1
                if scanned > MAX_SCAN:
                    break

                pre_start = start - length
                sh_start  = start
                rec_start = start + length
                rec_end_i = start + length * 2 - 1

                if pre_start < 0 or rec_end_i >= N:
                    continue

                try:
                    # Cost over preheat window
                    pre_cost = 0.0; pre_min = 0
                    for i in range(pre_start, sh_start):
                        dm = int(all_slots[i].get('dur_min', 15))
                        pre_cost += float(all_slots[i]['value']) * (dm / 60.0)
                        pre_min  += dm

                    # Hypothetical cost over expensive shutdown window (baseline)
                    high_cost = 0.0; high_min = 0
                    for i in range(sh_start, rec_start):
                        dm = int(all_slots[i].get('dur_min', 15))
                        high_cost += float(all_slots[i]['value']) * (dm / 60.0)
                        high_min  += dm

                    # Cost over recovery window
                    rec_cost = 0.0; rec_min = 0
                    for i in range(rec_start, rec_start + length):
                        dm = int(all_slots[i].get('dur_min', 15))
                        rec_cost += float(all_slots[i]['value']) * (dm / 60.0)
                        rec_min  += dm

                    pre_h  = pre_min  / 60.0
                    high_h = high_min / 60.0
                    rec_h  = rec_min  / 60.0

                    # Cost with vs without shutdown
                    total_with    = (pre_cost * preheat_mult) + (rec_cost * recovery_mult)
                    total_without = pre_cost + high_cost + rec_cost

                    # Ensure cutoff is truly expensive vs rest (weighted by multipliers)
                    avg_high = (high_cost / high_h) if high_h > 0 else 0.0
                    denom    = pre_h * preheat_mult + rec_h * recovery_mult
                    avg_rest = ((pre_cost * preheat_mult + rec_cost * recovery_mult) / denom) if denom > 0 else 0.0
                    price_diff = avg_high - avg_rest

                    # Duration scaling: longer shutdown → lower threshold required
                    duration_factor = reference_duration_h / high_h if high_h > 0 else 1.0
                    adjusted_min = min_price_diff * duration_factor

                    if high_h >= min_shutdown_h and total_with < total_without and price_diff >= adjusted_min:
                        htxt_h = int(high_h)
                        htxt_m = int(round((high_h - htxt_h) * 60))
                        period = {
                            'preheat_start':  all_slots[pre_start]['start'],
                            'shutdown_start': all_slots[sh_start]['start'],
                            'recovery_start': all_slots[rec_start]['start'],
                            'recovery_end':   all_slots[rec_end_i]['end'],
                            'cost_saving': round(total_without - total_with, 3),
                            'cost_saving_percent': round(((total_without - total_with) / total_without) * 100, 1) if total_without > 0 else 0,
                            'shutdown_duration_hours': round(high_h, 2),
                            'shutdown_duration_text': f"{htxt_h}h {htxt_m}min" if htxt_m > 0 else f"{htxt_h}h",
                            'details': {
                                'total_cost_with_shutdown': round(total_with, 3),
                                'total_cost_without_shutdown': round(total_without, 3),
                                'price_difference': round(price_diff, 3),
                                'adjusted_min_price_diff': round(adjusted_min, 3)
                            },
                            'idx': sh_start,  # for DP overlap constraints
                            'len': length
                        }
                        results.append(period)

                except Exception as calc_exc:
                    logger.warning("Calculation error: %s", calc_exc)
                    continue

            if scanned > MAX_SCAN:
                logger.warning("Candidate scan limit reached: %d", MAX_SCAN)
                break

        # STEP 2 — select optimal non-overlapping set via Weighted Interval Scheduling (DP)
        intervals = []
        for p in results:
            win_start = p['idx'] - p['len']
            win_end   = p['idx'] + 2 * p['len']
            intervals.append({'start': win_start, 'end': win_end, 'save': p['cost_saving'], 'p': p})

        final = []
        total_saving = 0.0

        if intervals:
            intervals.sort(key=lambda it: it['end'])
            ends = [it['end'] for it in intervals]

            def prev_compat(i):
                lo, hi, ans = 0, i - 1, -1
                s = intervals[i]['start']
                while lo <= hi:
                    mid = (lo + hi) // 2
                    if ends[mid] <= s:
                        ans = mid; lo = mid + 1
                    else:
                        hi = mid - 1
                return ans

            prev_idx = [prev_compat(i) for i in range(len(intervals))]
            n = len(intervals)
            dp = [0.0] * (n + 1)
            take = [False] * n

            for i in range(1, n + 1):
                notake = dp[i - 1]
                j = prev_idx[i - 1]
                take_val = intervals[i - 1]['save'] + (dp[j + 1] if j >= 0 else 0.0)
                if take_val > notake:
                    dp[i] = take_val
                    take[i - 1] = True
                else:
                    dp[i] = notake

            chosen = []
            i = n - 1
            while i >= 0 and len(chosen) < max_periods:
                if take[i]:
                    chosen.append(intervals[i]['p'])
                    i = prev_idx[i] if prev_idx[i] is not None else -1
                else:
                    i -= 1

            final = sorted(chosen, key=lambda x: x['preheat_start'])
            total_saving = round(sum(p['cost_saving'] for p in final), 3)

        # STEP 3 — expose results as a sensor (with telemetry)
        data_res = '15min (normalized)'
        if (dur_today_min and dur_today_min != 15) or (dur_tomo_min and dur_tomo_min != 15):
            data_res = 'mixed→15min'

        hass.states.set('sensor.nordpool_cutoff_periods_python', str(len(final)), {
            'periods': final,
            'friendly_name': 'Nordpool Cutoff Periods',
            'icon': 'mdi:lightning-bolt',
            'data_resolution': data_res,
            'today_slot_minutes': dur_today_min,
            'tomorrow_slot_minutes': dur_tomo_min,
            'optimization_method': 'DP (full window), robust slots v2.0',
            'unit_of_measurement': 'periods',
            'candidates_scanned': scanned,
            'results_found': len(results),
            'total_cost_saving': total_saving,
            'min_slots': MIN_SLOTS,
            'max_slots': max_slots,
            'preheat_mult': preheat_mult,
            'recovery_mult': recovery_mult,
            'multiplier_source': multiplier_source,
            'outdoor_temp_c': outdoor_temp_used,
            'nordpool_entity': NP_ENTITY_USED,
            'nordpool_source': NP_SOURCE
        })

        logger.info(
            "Nordpool optimizer v2.0: final=%d, candidates=%d, scanned=%d, "
            "total_saving=%.3f, np_entity=%s (src=%s), today=%smin, tomorrow=%smin, "
            "preheat=%.2f, recovery=%.2f, mult_src=%s, T_out=%s",
            len(final), len(results), scanned, total_saving,
            NP_ENTITY_USED, NP_SOURCE, str(dur_today_min), str(dur_tomo_min),
            preheat_mult, recovery_mult, multiplier_source, str(outdoor_temp_used)
        )
