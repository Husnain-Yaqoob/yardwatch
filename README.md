# YardWatch

Bay allocation, queue measurement and shift handover for a capacity-constrained
vehicle yard.

## The problem

A logistics site admits third-party HGVs through a single controlled barrier.
Inside the perimeter there are **two bays**. When both are occupied, arriving
vehicles have to wait **on the public road outside** until one frees up.

One operator manages this by eye, overnight, alongside patrols, CCTV and radio.
Two things follow from that:

1. **Nobody knows how bad the queue actually gets.** Vehicles idling on a public
   road are a traffic and safety problem, but there is no record of how often it
   happens or for how long — so there is no evidence base for asking whether two
   bays is the right number.
2. **Knowledge dies at handover.** Faults found during a shift (a lock panel not
   engaging, a barrier arm sticking, a camera dropping out) are written down in
   prose, and the incoming operator has to read it all to find the two things
   that still need action.

YardWatch addresses both: it enforces the capacity constraint, measures what the
queue costs, and generates a handover report ordered by what the next shift has
to act on.

## What it does

- **Allocates bays** first-come-first-served, and never exceeds capacity.
- **Measures the overflow** — how long vehicles waited outside, how long the
  queue got, and what proportion were admitted inside the target wait.
- **Logs shift events** — faults with severity, unauthorised access attempts,
  completed patrols.
- **Generates a handover report** that leads with unresolved faults and current
  yard state, rather than a chronological wall of text.

## Try it

```bash
python -m yardwatch.cli                    # simulated night shift, 2 bays
python -m yardwatch.cli --capacity 3       # what if there were three?
python -m yardwatch.cli --seed 7           # a different night
python -m yardwatch.cli --out handover.md  # write the report to a file
pytest                                     # 17 tests
```

Runs are deterministic for a given seed, so any figure quoted below can be
reproduced by anyone with the same command.

## The finding

Running the same simulated night against different capacities is the point of
the whole exercise. Every figure below uses the default seed (`42`) and the
default 8-hour shift, so they reproduce exactly:

```bash
python -m yardwatch.cli --capacity 2
python -m yardwatch.cli --capacity 3
python -m yardwatch.cli --capacity 4
```

Identical 23 arrivals in each run — only the bay count changes:

| Bays | Admitted within 15 min | Road overflow | Max wait | Peak queue | Still waiting at shift end |
|------|------------------------|---------------|----------|------------|----------------------------|
| 2    | 31.6%                  | 293.3 min     | 99.4 min | 6          | 4                          |
| 3    | 69.6%                  | 146.4 min     | 50.2 min | 4          | 0                          |
| 4    | 91.3%                  | 75.6 min      | 41.9 min | 3          | 0                          |

Two bays is not marginally tight, it is under-provisioned. Two thirds of
arrivals wait longer than the target, the queue reaches six vehicles on the
public road, and four vehicles never get in before the shift ends. A third bay
clears the backlog but still misses the target on three arrivals in ten.
Holding a 90% target takes four.

The shape of that curve is the useful part: each added bay roughly halves the
overflow, so there is no threshold to discover — only a cost decision about how
much road queueing is acceptable. Framing it this way replaces an argument
about whether the yard "feels busy" with a choice between numbers.

One caveat, stated plainly: the arrival rate and dwell distribution in
`simulate.py` are modelled, not measured. The conclusion holds for the modelled
rate. Before this is used to argue for anything operationally, those parameters
need re-tuning against observed vehicle counts.

## Design decisions

**Why FIFO.** Admission is strictly by arrival time. A priority scheme (say,
shortest-expected-dwell first) would lower the mean wait, but a single operator
at a barrier cannot verify expected dwell, and any departure from visible
first-come-first-served invites disputes with drivers. Fairness that can be
enforced beats optimality that cannot.

**Why arrival and admission are separate events.** A vehicle joins the queue
even when a bay is free, and is admitted as a distinct step. This costs an extra
state transition but means wait time is *always* measured — including the near-zero
waits. Only recording waits when the yard is full would bias every statistic.

**Why an SLO rather than an average.** The headline indicator is the proportion
of vehicles admitted within a target wait, not the mean wait. A mean of 6
minutes hides the vehicle that waited 34. The proportion-within-target framing
comes from service reliability practice and answers the question that actually
matters: how often is this bad?

**Why replay rather than sampling.** Queue length over time is reconstructed by
replaying arrival and admission timestamps as +1/-1 changes, not by sampling at
intervals. Sampling would miss short spikes, which are precisely the events
worth catching.

**Why log-normal dwell times.** In the simulation, most vehicles turn around
quickly and a few take far longer. It is that long tail — not the median — that
causes the queue to spill onto the road, so a symmetric distribution would have
made the two-bay constraint look far safer than it is.

## A note on data

Everything in this repository is synthetic. It contains no real site data,
vehicle registration, carrier name or personnel name, and describes no specific
site's security arrangements. The domain model is deliberately generic: any
facility with a controlled barrier and limited bays has this problem.

## Structure

```
yardwatch/
  models.py     domain types — vehicles, events, shifts
  yard.py       bay allocation and queue management
  metrics.py    service-level indicators
  handover.py   shift handover report generation
  simulate.py   synthetic night-shift generator
  cli.py        command-line entry point
  pyproject.toml  packaging and pytest configuration
tests/          17 unit tests
```

## Next

- [ ] Re-tune arrival rate and dwell distribution against observed vehicle counts
- [ ] Export metrics to Prometheus and build a Grafana dashboard of bay
      occupancy, queue length and wait-time percentiles
- [ ] Persist to SQLite so shifts accumulate over weeks rather than one night
- [ ] Alert when queue length or wait time crosses threshold
- [ ] Deploy to AWS with Terraform
