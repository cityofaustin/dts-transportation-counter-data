import argparse
import logging
import os

from datetime import timedelta, datetime, timezone
import requests
from sodapy import Socrata
from tqdm import tqdm
import uuid

from utils import get_logger

ECO_VISIO_API_KEY = os.getenv("ECO_VISIO_API_KEY")
ECO_VISIO_API_BASE_URL = os.getenv("ECO_VISIO_API_BASE_URL")

ECO_COUNTER_OBSERVATIONS_DATASET = os.getenv("ECO_COUNTER_OBSERVATIONS_DATASET")
ECO_COUNTER_FLOWS_DATASET = os.getenv("ECO_COUNTER_FLOWS_DATASET")
SOCRATA_SECRET_KEY = os.getenv("SOCRATA_SECRET_KEY")
SOCRATA_TOKEN = os.getenv("SOCRATA_TOKEN")
SOCRATA_API_KEY = os.getenv("SOCRATA_API_KEY")
SOCRATA_ENDPOINT = os.getenv("SOCRATA_ENDPOINT")

soda_client = Socrata(
    SOCRATA_ENDPOINT,
    SOCRATA_TOKEN,
    username=SOCRATA_API_KEY,
    password=SOCRATA_SECRET_KEY,
    timeout=60,
)

def date_range(start_date, end_date):
    """Returns a list of date strings from start_date to end_date, inclusive."""
    days = (end_date - start_date).days
    return [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days + 1)]


def to_floating_timestamp(ts: str) -> str:
    # Parse the ISO timestamp (handles offsets like -06:00)
    dt = datetime.fromisoformat(ts)

    # Strip the tzinfo WITHOUT converting — keeps wall-clock time as-is
    dt_naive = dt.replace(tzinfo=None)

    # Format with milliseconds (3 digits), like the JS Date toISOString format
    return dt_naive.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt_naive.microsecond // 1000:03d}"


def get_counter_metadata():
    url = f"{ECO_VISIO_API_BASE_URL}/api/v2/sites"

    page_size = 100

    params = {
        "page": 1,
        "pageSize": page_size,
        "sortBy": "id",
        "orderBy": "asc",
        "include": "flows,counters,tags,images,attributes,segments",
    }

    headers = {
        "accept": "application/json",
        "X-API-KEY": ECO_VISIO_API_KEY,
    }

    # Pagination for metadata requests
    page = 1
    sites = []
    while True:
        params["page"] = page
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        records = response.json()
        sites += records
        if not records or len(records) < page_size:
            break

    return sites

def process_flows_metadata(sites):
    # Fields from the site metadata that we want to include with the flow
    included_site_metadata = ["id", "name", "firstData", "lastData", 'granularity', "directional"]

    output = []
    for site in sites:
        # Adding site_ prefix to clarify these are describing the site
        site_metadata = {}
        for field in included_site_metadata:
            if field not in site:
                site_metadata[f"site_{field}"] = None
            else:
                site_metadata[f"site_{field}"] = site[field]
        # Creating a column with WKT format for location
        if "lat" in site["location"] and "lon" in site["location"]:
            site_metadata["location"] = f"POINT({site["location"]["lon"]} {site["location"]["lat"]})"
        else:
            site_metadata["location"] = None
        for flow in site["flows"]:
            entry = flow
            if "begin" in entry:
                entry["begin"] = to_floating_timestamp(entry["begin"])
            if "end" in entry:
                entry["end"] = to_floating_timestamp(entry["end"])
            if site_metadata["site_firstData"]:
                site_metadata["site_firstData"] = to_floating_timestamp(site_metadata["site_firstData"])
            if site_metadata["site_lastData"]:
                site_metadata["site_lastData"] = to_floating_timestamp(site_metadata["site_lastData"])
            entry.update(site_metadata)
            output.append(entry)
    return output

def process_raw_data(raw_data):
    output = []
    # Define a namespace (required for UUIDv5)
    # You can use standard pre-defined namespaces like NAMESPACE_DNS or NAMESPACE_URL


    for record in raw_data:
        # if nothing was recorded for the time period, just skip it
        if not record["data"]:
            continue
        # gathering metadata about where the data is from
        flow_metadata = {k: v for k, v in record.items() if k != 'data'}
        for count in record["data"]:
            # Create a unique ID for each record
            record_identifier = f"{flow_metadata["flowID"]};{str(count["timestamp"])}"
            generated_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, record_identifier)
            count["record_id"] = str(generated_uuid)
            count["timestamp"] = to_floating_timestamp(count["timestamp"])
            count.update(flow_metadata)
            output.append(count)
    return output


def is_date_in_range(date_str, first_data, last_data):
    # Parse the bare date, make it timezone-aware (UTC) so it can compare
    date = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)

    first = datetime.fromisoformat(first_data)
    last = datetime.fromisoformat(last_data)

    return first <= date <= last


def build_work_items(dates, sites):
    """
    Precompute every (date, site) pair that will actually be fetched, so we
    know the total up front instead of discovering validity inside the loop.
    """
    items = []
    for start_date in dates:
        for site in sites:
            # some sites are missing these fields, and they all appear to be decommissioned.
            if "firstData" in site and "lastData" in site:
                if is_date_in_range(start_date, site["firstData"], site["lastData"]):
                    site_id = site["id"]
                    items.append({
                        "start_date": start_date,
                        "site_id": site_id,
                    })
    return items


def main():
    # Fallback dates if no args are supplied
    today = datetime.today().date()
    three_days_ago = today - timedelta(days=3)

    # Argument parsing
    parser = argparse.ArgumentParser(
        description="Download and upload Eco-Counter data to Socrata."
    )
    parser.add_argument(
        "-s",
        "--start",
        default=three_days_ago.strftime("%Y-%m-%d"),
        help="Start date in YYYY-MM-DD format (default: 3 days ago)",
    )
    parser.add_argument(
        "-e",
        "--end",
        default=today.strftime("%Y-%m-%d"),
        help="End date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Allows for a test dry run where nothing actually gets downloaded or uploaded, but API logins are tested.",
    )
    parser.add_argument(
        "-p",
        "--progress-bar",
        action="store_true",
        help="Show a tqdm progress bar instead of logging each site/date upload individually.",
    )
    args = parser.parse_args()

    # Validate date formats
    try:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end = datetime.strptime(args.end, "%Y-%m-%d").date()
    except ValueError as e:
        parser.error(f"Invalid date format: {e}")

    # Generate a list of dates to download
    logger.info(f"Start date: {args.start}, End date: {args.end}")
    dates = date_range(start, end)

    # Getting metadata from Eco Counters
    sites = get_counter_metadata()
    flows = process_flows_metadata(sites)

    if args.dry_run:
        logger.info("Dry run mode was enabled. Only tested downloading count site metadata and logging into to Socrata.")
        dates_info = "Would normally download traffic counts for the following dates: "
        for date in dates:
            dates_info += date + ", "
        logger.info(dates_info)
        return

    soda_res = soda_client.replace(ECO_COUNTER_FLOWS_DATASET, flows)
    logger.info(soda_res)

    todos = build_work_items(dates, sites)

    total_rows_uploaded = 0

    # Logic for what iterator to use for a given logging type
    iterator = tqdm(todos, unit="site-days") if args.progress_bar else todos

    for item in iterator:
        start_date = item["start_date"]
        site_id = item["site_id"]
        end_date = start_date  # We are just getting one day worth of count data at a time

        url = f"{ECO_VISIO_API_BASE_URL}/api/v2/history/traffic/raw"

        params = {
            "siteId": site_id,
            "startDate": start_date,
            "endDate": end_date,
            "startTime": "00:00",
            "endTime": "23:59",
            "gapFilling": "false",
            "validatedDataOnly": "false",
            "rawDataOnly": "true"
        }

        headers = {
            "accept": "application/json",
            "X-API-KEY": ECO_VISIO_API_KEY,
        }

        response = requests.get(url, params=params, headers=headers)
        raw = response.json()

        processed = process_raw_data(raw)
        soda_res = soda_client.upsert(ECO_COUNTER_OBSERVATIONS_DATASET, processed)

        total_rows_uploaded += len(processed)

        if args.progress_bar:
            iterator.set_postfix(site=site_id, date=start_date, rows=total_rows_uploaded)
        else:
            logger.info(f"successfully uploaded: {start_date} for site {site_id}")
            logger.info(soda_res)

    logger.info(f"Done. Total rows uploaded across run: {total_rows_uploaded}")

if __name__ == "__main__":
    logger = get_logger(
        __name__,
        level=logging.INFO,
    )

    main()
