# Mooring session + weather architecture

## Operational intent
A port-call schedule drives the expected session window. The operator can
confirm start when lines are being made fast and stop when the vessel is
secured/released. The system records a time series rather than one final
weather value.

## Weather provider
Windy Point Forecast API is the primary integrated provider. It supplies
machine-readable forecast data for a coordinate and selected model. The API
requires a Point Forecast key and uses POST `/api/point-forecast/v2`.

Important limitation: Windy Point Forecast provides the latest forecast and
cannot retrieve historical forecasts. Therefore stored records are labelled
`FORECAST`, not `OBSERVED`. A future observed-data provider or manual bridge
observation can be stored with `source_kind=OBSERVED`.

## Session record
Each session stores:
- session ID and port/berth;
- start/end UTC;
- periodic environmental snapshots;
- per-line tension/utilization exposure and duration;
- source/provider for every environmental observation.

## Line history
The complete session history is the input to line-life analytics. The current
implementation reports exposure hours, maximum utilization, time above a
review threshold, and a traceable status. It deliberately does NOT infer a
replacement/end-to-end date until manufacturer/inspection criteria and the
validated MEG4 service-life methodology are available.

## Security
`WINDY_POINT_FORECAST_API_KEY` must be supplied through deployment secrets or
environment variables. It must never be committed to GitHub or written into
session records.

## Schedule automation
The existing port-call schedule remains the source of planned ETA/ETD. The
session engine should use it to propose `START_PENDING` and `STOP_PENDING`
states, but an automatic start must require an explicit operational trigger
or a configured vessel event. This avoids silently creating false mooring
sessions while the ship is alongside but not actually moored.
