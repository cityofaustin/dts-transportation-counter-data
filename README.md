# Transportation Data Counters

This repository's purpose is to store code for publishing data from transportation count devices deployed around Austin. 
Note that none of these sensors are able to identify individual people or vehicles, the counts are for planning and operational 
purposes only.

## Active Transportation Counters

**Location:** `active-transportation-counters/get_eco_counter_data.py`

These scripts are used to publish raw data from the active transportation counters deployed around Austin. These are used
to understand the usage of the city's infrastructure primarily by active modes such as pedestrians and cyclists. 
The vendor is [Eco Counter](https://eco-counter.com/).

A public dashboard can be found [here](https://cityofaustin.eco-counter.us/).

The data is published to the [Austin Open Data Portal](https://data.austintexas.gov/d/u4i6-pw3h).

![An example photo of an active transportation counter installed by the City of Austin Transporation Public Works Dept.](docs/example_trail_counter_location.jpg)
*<sub>An example photo of an active transportation counter installed by the City of Austin Transporation Public Works Dept.</sub>*

### `get_eco_counter_data.py`

Downloads traffic count data from the Eco-Counter API and uploads it, along with site/flow metadata, to Socrata.
 
#### Usage
 
```bash
python get_eco_counter_data.py [-s START] [-e END] [-n] [-p]
```
 
#### Arguments
 
| Flag | Long form        | Type                  | Default             | Description                                                                                                                                 |
|------|------------------|-----------------------|---------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `-s` | `--start`        | string (`YYYY-MM-DD`) | 3 days before today | First date to pull counts for, inclusive.                                                                                                   |
| `-e` | `--end`          | string (`YYYY-MM-DD`) | today               | Last date to pull counts for, inclusive.                                                                                                    |
| `-n` | `--dry-run`      | flag                  | off                 | Tests site metadata download and Socrata login without downloading or uploading any count data. Nothing is written to Socrata in this mode. |
| `-p` | `--progress-bar` | flag                  | off                 | Shows a live `tqdm` progress bar (site/date/rows-so-far) instead of logging each site/date upload individually.                             |
 
Dates passed to `-s`/`-e` must be in `YYYY-MM-DD` format; anything else raises an argument error and exits before any API calls are made.
 
#### Examples
 
Run with default 3-day lookback window, plain logging:
```bash
python get_eco_counter_data.py
```
 
Backfill a specific date range with a progress bar:
```bash
python get_eco_counter_data.py -s 2026-06-01 -e 2026-06-30 -p
```
 
Sanity-check credentials and connectivity without uploading anything to Socrata:
```bash
python get_eco_counter_data.py -n
```
 
## Required environment variables
 
See also: `env_template`

| Variable                           | Purpose                                                             |
|------------------------------------|---------------------------------------------------------------------|
| `ECO_VISIO_API_KEY`                | API key for Eco-Counter's `api.eco-counter.us` endpoints.           |
| `ECO_VISIO_API_BASE_URL`           | Base url for Eco-Counter API.                                       |
| `ECO_COUNTER_OBSERVATIONS_DATASET` | Socrata dataset ID that raw per-timestamp counts are upserted into. |
| `ECO_COUNTER_FLOWS_DATASET`        | Socrata dataset ID that flow/site metadata is replaced into.        |
| `SOCRATA_ENDPOINT`                 | Socrata domain (e.g. `data.austintexas.gov`).                       |
| `SOCRATA_TOKEN`                    | Socrata app token.                                                  |
| `SOCRATA_API_KEY`                  | Socrata API key ID (or username).                                   |
| `SOCRATA_SECRET_KEY`               | Socrata API key secret (or password).                               |
 
## Dependencies
 
- `requests`
- `sodapy`
- `tqdm` 


# Docker

## Building the image

From the repo root:

```bash
docker build -t atddocker/dts-transportation-counter-data:local .
```

## Running the image

### Default script (Eco-Counter)

```bash
docker run --rm --env-file .env atddocker/dts-transportation-counter-data:local
```

`CMD` defaults to `active-transportation-counters/get_eco_counter_data.py`, so no arguments are needed to run it as-is.

### Passing arguments to the default script

Anything appended after the image name replaces `CMD` and is passed straight to `python`, so you have to include the script path yourself:

```bash
docker run --rm --env-file .env atddocker/dts-transportation-counter-data:local \
  active-transportation-counters/get_eco_counter_data.py -s 2026-06-01 -e 2026-06-30 -p
```

| Flag                   | Description                                                                    |
|------------------------|--------------------------------------------------------------------------------|
| `-s`, `--start`        | Start date (`YYYY-MM-DD`), default 3 days before today                         |
| `-e`, `--end`          | End date (`YYYY-MM-DD`), default today                                         |
| `-n`, `--dry-run`      | Test metadata download and Socrata login without fetching/uploading count data |
| `-p`, `--progress-bar` | Show a `tqdm` progress bar instead of per-item log lines                       |

## Debugging inside the container

Get an interactive shell instead of running any ETL script, by overriding `--entrypoint`:

```bash
docker run -it --rm --entrypoint /bin/bash --env-file .env atddocker/dts-transportation-counter-data:local
```

From there you're in `/app` and can inspect files, check `env`, or run a script manually (e.g. `python active-transportation-counters/get_eco_counter_data.py -n`).
