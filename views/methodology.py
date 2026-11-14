"""Methodology: how every number and animation in the app is produced."""

import streamlit as st

from f1insights import analysis, data
from ui import components

components.inject_css()
st.html('<p class="gp-title">Methodology</p>'
        '<p class="gp-meta">How every number and animation in this app is produced, and where it can mislead.</p>')

SECTIONS = [
    ("source", "white", "Data source and its quirks", f"""
All data comes from [OpenF1](https://openf1.org), a free, unofficial API that republishes Formula 1 live
timing from 2023 on. No account is needed. The 2024 Hungarian Grand Prix is bundled with the app as parquet
files, so the default view also works when OpenF1 is down.

Things in the data that shaped the code:

- **Rate limit of 3 requests per second**, and a whole session of car positions cannot be requested at once.
  Telemetry is fetched per driver, with pauses between requests.
- **Missing values are real.** A pit-lane starter has no time for lap 1, a retiring car has no time for its
  last lap, and a lap can have a valid time with one sector missing. Missing stays missing; nothing is filled in.
- **Outside races, a pit-out "lap time" includes the time in the garage** and can exceed 1 000 seconds.
- **Safety cars are not a field.** They are read from race control messages ("SAFETY CAR DEPLOYED",
  "VIRTUAL SAFETY CAR DEPLOYED", a red flag) and end at the next "TRACK CLEAR".
- **Two sources for the finishing order.** The official result includes post-race penalties and is preferred;
  the on-track position feed is the fallback.
"""),
    ("clean", "gray", "The clean-lap filter", f"""
Pace statistics should describe how fast a driver could go, not when they pitted. A lap counts as **clean**
unless one of these applies (the first match is recorded as the reason):

1. it has no lap time,
2. it is lap 1 (standing start, cold tyres, traffic),
3. it is a pit in-lap or
4. a pit out-lap,
5. any part of it ran under a safety car, virtual safety car or red flag,
6. it is slower than **{analysis.SLOW_LAP_FACTOR:.0%} of the driver's median** over the laps left after steps 1 to 5.

Step 6 catches laps ruined by traffic, mistakes or blue flags. In qualifying most laps are deliberately slow,
so there the reference is the driver's fastest lap instead of the median. Excluded laps are never deleted:
the Pace page can show them in grey with their reason.

*Limit:* 107% is a convention borrowed from the qualifying rule, not a law of nature. On a drying track a
genuinely representative lap can be excluded.
"""),
    ("median", "white", "Why median and IQR", """
Lap times are not symmetric: a driver cannot be much faster than their best, but can easily be seconds slower.
The **mean** is pulled towards those slow laps and the **standard deviation** grows with them.

The **median** is the middle lap: half were faster, half slower. The **IQR** (interquartile range) is the
width of the middle 50% of laps. One bad lap changes neither, which is why they describe typical pace and
consistency better here. Standard deviation is still shown for comparison.
"""),
    ("regression", "gray", "Tyre degradation: linear regression", f"""
For each stint a straight line is fitted through lap time against tyre age (ordinary least squares,
`scipy.stats.linregress`):

> lap time = intercept + slope × tyre age

- **Slope** is the degradation in seconds per lap.
- The **95% confidence interval** is slope ± t × standard error, with n − 2 degrees of freedom. If it includes
  zero, the stint does not show measurable wear.
- **R²** is the share of lap-time variation the line explains.
- Only clean laps count, the first lap of each stint is left out (tyres are still coming up to temperature),
  and stints with fewer than {analysis.MIN_STINT_LAPS} usable laps are skipped.

*Assumptions and limits:* wear is assumed to be linear, although real tyres often hold steady and then drop
off. Laps are treated as independent, yet a driver managing pace makes neighbouring laps similar, so the
intervals are somewhat too narrow. Track evolution and traffic are not modelled.
"""),
    ("fuel", "sand", "The fuel correction", f"""
A car burns roughly 1.5 kg of fuel per lap and gets faster as it gets lighter. That gain works against tyre
wear, so the raw slope understates degradation and can even be negative.

With the toggle on, **{analysis.FUEL_SECONDS_PER_LAP} s is added to a lap time for every lap already driven**.
This is one constant for every car and track; the true value depends on fuel load, track length and engine
mode. It is off by default so that the first number you see is assumption-free.
"""),
    ("bootstrap", "white", "Head-to-head: bootstrap confidence interval", f"""
Two drivers are compared only on laps that are clean **for both**, as lap-by-lap differences. The headline is
the median difference.

To show how sure that median is, the differences are **resampled with replacement
{analysis.BOOTSTRAP_RESAMPLES} times** (each resample has as many laps as the original) and the median is taken
each time. The middle 95% of those medians is the confidence interval. The random seed is fixed, so the page
shows the same numbers on every run.

The bootstrap is used because it needs no assumption that the differences are normally distributed.

*Limit:* it says the gap is unlikely to be noise, not why it exists. Tyre age, fuel, traffic and team orders
all remain in the data.
"""),
    ("replay", "gray", "Race replay: downsampling and interpolation", f"""
OpenF1 reports each car's position about 3.7 times per second: around 35 000 points per driver per race. For
the replay every driver is linearly interpolated onto one shared time grid at **{data.REPLAY_HZ:g} samples per
second**, which cuts the data by almost half and lets all cars share one clock. The browser then interpolates
between samples again for smooth motion at any playback speed.

At {data.REPLAY_HZ:g} Hz a car covers up to about 45 metres between samples, so on the screen it cuts a corner
by less than its own width. Positions in the tower come from the timing feed, not from the map.
"""),
    ("ghost", "sky", "Ghost lap: aligning two laps and mini-sectors", """
Two laps are compared **by distance, not by time**. For each lap the distance travelled is summed from the
position samples and divided by the total, giving a lap fraction from 0 to 1. Speed, throttle and brake come
from a second feed with its own timestamps and are attached to the nearest earlier position sample
(`pandas.merge_asof`).

**Elapsed time is rebuilt from speed.** The position timestamps jitter by about a tenth of a second, more
than the gaps being measured. So the time for each small step of the lap is its length divided by the measured
speed (time = distance / speed); the steps are summed and scaled so the lap ends exactly at the official lap
time.

The lap is cut into **25 mini-sectors of equal distance**. In each, the driver who needed less time is
faster, and the track is coloured accordingly. The running delta at any point is the difference in elapsed
time at the same lap fraction.

*Limit:* speed is sampled about four times per second and matched to a position that can be 10 to 15 metres
off, which matters most in braking zones. Gaps inside the lap are therefore good to roughly five hundredths
to a tenth of a second, and mini-sector gaps under 0.03 s are shown as too close to call. The final gap
always equals the official lap-time gap.
"""),
]

for name, tone, title, body in SECTIONS:
    with components.tile(name, tone):
        st.markdown(f"### {title}\n{body}")

components.footer()
