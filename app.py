from flask import Flask, render_template, request, url_for
import requests
import datetime
import json
import sqlite3
import os
import math
from collections import Counter, defaultdict
from functools import lru_cache
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo
from analyzer import normalize_location, analyze_dates, analyze_unreported_floats, get_year_recovery_stats
from forecasting import (
    build_cluster_lookup,
    build_daily_forecast_briefing as compose_daily_forecast_briefing,
    build_recent_activity_snapshot,
    build_spot_forecast_lookup,
    convert_wind_speed_to_mph,
    empty_forecast_artifact,
    fetch_live_tide_context,
    fetch_live_weather_context,
    weather_emoji,
)
from locations import LOCATIONS
from utils import get_last_updated

app = Flask(__name__)
DB_NAME = 'floats.db'
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
FIELD_ETIQUETTE_PATH = os.path.join(APP_ROOT, 'data', 'field_etiquette.json')
FORECAST_ARTIFACT_PATH = os.path.join(APP_ROOT, 'generated', 'forecast_artifact.json')
METRICS_DB_PATH = os.path.join(APP_ROOT, 'output', 'metrics.db')
try:
    DISPLAY_TIMEZONE = ZoneInfo(os.getenv('APP_TIMEZONE', 'America/New_York'))
except Exception:
    DISPLAY_TIMEZONE = datetime.timezone.utc
FORECAST_ARTIFACT_STALE_HOURS = 48
FIELD_DIRECTORY_BATCH_SIZE = 12
ALLOWED_EVENT_NAMES = {'share_clicked', 'shared_location_view'}
ALLOWED_SHARE_METHODS = {'native', 'copy'}
OFFICIAL_LINKS = {
    'project': 'https://www.blockislandinfo.com/glass-float-project/',
    'register': 'https://www.blockislandinfo.com/glass-float-project/register-floats/',
    'found': 'https://www.blockislandinfo.com/glass-float-project/found-floats/',
    'tips': 'https://www.blockislandinfo.com/glass-float-project/tips-and-etiquette/',
    'greenway': 'https://www.blockislandinfo.com/glass-float-project/greenway-trail-guide/',
    'archives': 'https://www.blockislandinfo.com/glass-float-project/found-float-archives/',
}
REPORT_FIND_URL = OFFICIAL_LINKS['register']
DEFAULT_FIELD_ETIQUETTE = {
    'title': 'Hunt rules',
    'intro': 'Official rules and trail etiquette for the hunt.',
    'rules_heading': 'Hunt respectfully',
    'rules': [
        'Stay on established trails.',
        'Search near trails or between the bluffs and the high tide line.',
        'Do not dismantle stone walls.',
        'Do not whack vegetation.',
        'Stay off dunes.',
        'Keep pets on a leash.',
        'Look up. Floats may be hidden in trees.',
        'One float per person per year.',
    ],
    'notes_heading': 'Field reminders',
    'notes': [
        'Most official hides are on beaches or marked Greenway trails, with a smaller number in other public places.',
        'Trail hides sit close to the edge of established paths. Do not cut a new route into the brush for a promising spot.',
        'Leave no trace and carry out any trash you notice while hunting.',
        'Check for ticks and poison ivy after longer walks.',
        'If you find a second float, leave it in place or re-hide it in an approved area so someone else can discover it.',
        'Register your float so the official archive can attach your find, photo, and story to the season record.',
    ],
    'restricted_heading': 'Floats are NOT hidden on',
    'restricted_locations': [
        'Dunes or up bluffs',
        '"The Maze"',
        'School grounds',
        'Island cemeteries',
        'Private homes',
        'Flowerbeds',
        'The Statue of Rebecca',
    ],
    'resources_heading': 'Official resources',
    'resources': [
        {
            'label': 'Register floats',
            'href': OFFICIAL_LINKS['register'],
        },
        {
            'label': 'Greenway trail guide',
            'href': OFFICIAL_LINKS['greenway'],
        },
    ],
}


@app.context_processor
def inject_official_links():
    return {'official_links': OFFICIAL_LINKS}


def load_field_etiquette():
    try:
        with open(FIELD_ETIQUETTE_PATH, encoding='utf-8') as etiquette_file:
            return json.load(etiquette_file)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: using fallback field etiquette content: {exc}")
        return DEFAULT_FIELD_ETIQUETTE.copy()


FIELD_ETIQUETTE = load_field_etiquette()
@lru_cache(maxsize=4)
def _load_forecast_artifact_cached(path, mtime_ns):
    try:
        with open(path, encoding='utf-8') as forecast_file:
            return json.load(forecast_file)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: using empty forecast artifact: {exc}")
        return empty_forecast_artifact()


def clear_forecast_cache():
    _load_forecast_artifact_cached.cache_clear()


def load_forecast_artifact():
    try:
        mtime_ns = os.stat(FORECAST_ARTIFACT_PATH).st_mtime_ns
    except OSError:
        return empty_forecast_artifact()
    return _load_forecast_artifact_cached(FORECAST_ARTIFACT_PATH, mtime_ns)


def get_today():
    return datetime.date.today()


def get_current_time():
    return datetime.datetime.now(DISPLAY_TIMEZONE)


def parse_datetime_value(value):
    if value in (None, ''):
        return None

    timestamp = value
    if not isinstance(timestamp, datetime.datetime):
        raw_value = str(timestamp).strip()
        if not raw_value:
            return None
        if raw_value.endswith('Z'):
            raw_value = f'{raw_value[:-1]}+00:00'
        try:
            timestamp = datetime.datetime.fromisoformat(raw_value)
        except ValueError:
            return None

    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=DISPLAY_TIMEZONE)
    return timestamp.astimezone(DISPLAY_TIMEZONE)


def format_local_timestamp(value, missing='Unavailable'):
    localized = parse_datetime_value(value)
    if localized is None:
        return missing if value in (None, '') else str(value)

    time_label = localized.strftime('%I:%M %p').lstrip('0')
    return f"{localized.strftime('%b')} {localized.day}, {localized.year} at {time_label} {localized.tzname()}"


app.add_template_filter(format_local_timestamp, 'format_local_timestamp')


def format_public_date(value, missing='Unknown'):
    if value in (None, ''):
        return missing

    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return f"{value.strftime('%b')} {value.day}, {value.year}"

    localized = parse_datetime_value(value)
    if localized is not None:
        return f"{localized.strftime('%b')} {localized.day}, {localized.year}"

    raw_value = str(value).strip()
    if not raw_value:
        return missing
    try:
        parsed_date = datetime.date.fromisoformat(raw_value)
    except ValueError:
        return str(value)
    return f"{parsed_date.strftime('%b')} {parsed_date.day}, {parsed_date.year}"


app.add_template_filter(format_public_date, 'format_public_date')

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def parse_selected_year(raw_year):
    """Return a sanitized year filter tuple of (selected_year, year_param)."""
    if raw_year in (None, "", "all"):
        return "all", None

    try:
        year = int(raw_year)
    except (TypeError, ValueError):
        return "all", None

    return str(year), year

def build_finds_where_clause(year_param=None):
    clauses = []
    params = []
    if year_param is not None:
        clauses.append('year = ?')
        params.append(year_param)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    return where, params


def build_cta(label, href, external=False):
    cta = {
        'label': label,
        'href': href,
    }
    if external:
        cta['external'] = True
    return cta


def build_page_meta(
    active_nav,
    mode,
    kicker,
    title,
    subtitle,
    primary_cta=None,
    description=None,
    url=None,
    image=None,
    meta_title=None,
    image_alt=None,
    meta_type='website',
):
    page_meta = {
        'active_nav': active_nav,
        'mode': mode,
        'kicker': kicker,
        'title': title,
        'subtitle': subtitle,
        'description': description or subtitle,
        'meta_type': meta_type,
    }
    if primary_cta:
        page_meta['primary_cta'] = primary_cta
    if url:
        page_meta['url'] = url
    if image:
        page_meta['image'] = image
    if meta_title:
        page_meta['meta_title'] = meta_title
    if image_alt:
        page_meta['image_alt'] = image_alt
    return page_meta


def join_label_list(labels):
    cleaned = [str(label).strip() for label in labels if str(label).strip()]
    if not cleaned:
        return ''
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f'{cleaned[0]} and {cleaned[1]}'
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def calculate_distance_miles(lat1, lon1, lat2, lon2):
    earth_radius_miles = 3959
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_miles * c


def describe_relative_age(delta):
    total_hours = max(int(delta.total_seconds() // 3600), 0)
    if total_hours < 24:
        display_hours = max(total_hours, 1)
        return f'{display_hours} hour{"s" if display_hours != 1 else ""}'

    total_days = max(int(delta.total_seconds() // 86400), 1)
    if total_days < 7:
        return f'{total_days} day{"s" if total_days != 1 else ""}'

    total_weeks = max(total_days // 7, 1)
    return f'{total_weeks} week{"s" if total_weeks != 1 else ""}'


def build_forecast_freshness(briefing):
    freshness_data = dict(briefing.get('feature_freshness') or {})
    artifact_generated_at = parse_datetime_value(freshness_data.get('artifact_generated_at'))
    artifact_age = None
    artifact_age_label = ''
    is_stale = False

    if artifact_generated_at is not None:
        artifact_age = max(get_current_time() - artifact_generated_at, datetime.timedelta())
        artifact_age_label = describe_relative_age(artifact_age)
        is_stale = artifact_age >= datetime.timedelta(hours=FORECAST_ARTIFACT_STALE_HOURS)

    if is_stale and artifact_generated_at is not None:
        summary = (
            'Live weather and tide are current, but the ranking model was generated on '
            f'{format_local_timestamp(artifact_generated_at)} and is about {artifact_age_label} old.'
        )
        return {
            'is_stale': True,
            'summary': summary,
            'headline': 'Latest model guidance for today',
            'subtitle': (
                'Use live weather and tide as current context, and treat the ranked area as a planning suggestion '
                'from the latest forecast artifact.'
            ),
            'lead_prefix': 'Latest model points to',
            'lead_suffix': 'Starting suggestion from the latest forecast artifact',
            'priority_badge': 'Model-based suggestion',
            'rail_badge': 'Model advisory',
            'rail_context': 'Live conditions + older model artifact',
            'zone_lead_summary': 'This area still leads the latest model, but the ranking artifact is no longer same-day fresh.',
            'zone_backup_summary': 'Keep this reserve area from the latest model if the first stop is crowded, blocked, or quiet on the ground.',
            'warning_label': f'Model artifact age: {artifact_age_label}',
        }

    return {
        'is_stale': False,
        'summary': 'Live weather, tide, and the latest ranked area are close enough in time to use as a same-day starting guide.',
        'headline': 'Where to start today',
        'subtitle': 'Get a simple starting recommendation based on find history, seasonality, tide, and weather.',
        'lead_prefix': 'Start with',
        'lead_suffix': 'Best first stop today',
        'priority_badge': '#1 today',
        'rail_badge': 'Today',
        'rail_context': 'History + live conditions',
        'zone_lead_summary': "This area has the clearest mix of archive history and today's conditions.",
        'zone_backup_summary': 'Keep this one in reserve if your first stop feels crowded or quiet on the ground.',
        'warning_label': '',
    }


def build_field_directory_state(hunting_spots, batch_size=FIELD_DIRECTORY_BATCH_SIZE):
    total = len(hunting_spots)
    initial_visible_count = min(total, batch_size)
    remaining_count = max(total - initial_visible_count, 0)
    return {
        'batch_size': batch_size,
        'initial_visible_count': initial_visible_count,
        'remaining_count': remaining_count,
        'has_more': remaining_count > 0,
    }


def format_distance_label(distance_miles):
    if distance_miles < 0.1:
        return 'Under 0.1 mi away'
    return f'{distance_miles:.1f} mi away'


def build_archive_signal(total_finds, years_tracked):
    if total_finds >= 12 or years_tracked >= 5:
        return {
            'badge_label': 'Strong archive signal',
            'share_label': 'strong archive signal',
            'summary': 'Repeated finds across the archive make this a friend-ready stop to start from.',
        }
    if total_finds >= 4 or years_tracked >= 2:
        return {
            'badge_label': 'Steady archive signal',
            'share_label': 'steady archive signal',
            'summary': 'More than one season has produced finds here, so the history is solid enough to plan around.',
        }
    return {
        'badge_label': 'Light archive signal',
        'share_label': 'light archive signal',
        'summary': 'Archive support is thinner here, so it works better as part of a short backup route.',
    }


def format_archive_report_label(count):
    return '1 archived report' if count == 1 else f'{count} archived reports'


def build_google_maps_href(lat, lon):
    return f'https://maps.google.com/?q={lat},{lon}'


def build_apple_maps_href(lat, lon, label=''):
    query = str(label).strip() or f'{lat},{lon}'
    return f'maps://?ll={lat},{lon}&q={quote_plus(query)}'


def build_field_reason_text(spot_name, count, zone_meta=None):
    archive_label = format_archive_report_label(count)
    archive_verb = 'keeps' if count == 1 else 'keep'
    reason_tag = ''

    if zone_meta:
        reason_tag = next((tag for tag in zone_meta.get('reason_tags', []) if tag), '')
        if zone_meta.get('support_rank', 0) == 0:
            if zone_meta.get('reason_text'):
                return zone_meta['reason_text']
            if reason_tag:
                return f"{reason_tag} keeps {spot_name} at the front of the shortlist."
            return f"{archive_label.capitalize()} {archive_verb} {spot_name} near the top of the shortlist."

        if reason_tag:
            return f"{reason_tag} also points toward {spot_name} as the next move off {zone_meta['zone_label']}."
        return f"{archive_label.capitalize()} {archive_verb} {spot_name} attached to the {zone_meta['zone_label']} lane."

    if count == 1:
        return f"Only {archive_label}, so treat {spot_name} as a thinner archive backup."
    return f"{archive_label.capitalize()} keep {spot_name} on the shortlist even without forecast support."


def build_support_summary(support_names, empty_message):
    names = [str(name).strip() for name in support_names if str(name).strip()]
    if not names:
        return empty_message
    label = join_label_list(names[:3])
    noun = 'stop' if len(names[:3]) == 1 else 'stops'
    return f"Keep {label} ready as the next {noun} if the first pass comes up quiet."


def build_forecast_zone_cards(zones, freshness):
    cards = []

    for index, zone in enumerate(zones, start=1):
        card = dict(zone)
        primary_name = zone.get('primary_spot') or zone.get('label')
        support_names = [
            spot.get('name')
            for spot in zone.get('supporting_spots', [])
            if spot.get('name')
        ]
        backup_names = [name for name in support_names if name and name != primary_name]
        season_count = len(zone.get('actual_years', []) or [])
        dated_support_count = int(zone.get('dated_support_count') or 0)
        dated_label = '1 dated report' if dated_support_count == 1 else f'{dated_support_count} dated reports'
        reason_text = next((text for text in zone.get('reason_texts', []) if text), '')
        reason_tag = next((tag for tag in zone.get('reason_tags', []) if tag), '')

        if reason_text:
            summary = reason_text
        elif reason_tag:
            if index == 1:
                summary = f"{reason_tag} keeps {zone.get('label') or primary_name} in front."
            else:
                summary = f"{reason_tag} keeps {zone.get('label') or primary_name} ready behind the lead area."
        else:
            summary = freshness['zone_lead_summary'] if index == 1 else freshness['zone_backup_summary']

        if backup_names:
            detail = (
                f"{dated_label.capitalize()} across {season_count} season{'s' if season_count != 1 else ''}, "
                f"with {join_label_list(backup_names[:3])} on the same run."
            )
        else:
            detail = (
                f"{dated_label.capitalize()} across {season_count} season{'s' if season_count != 1 else ''} "
                f"keep this area on the board."
            )

        card['summary_copy'] = summary
        card['detail_copy'] = detail
        cards.append(card)

    return cards


def build_search_result_groups(rows):
    grouped_results = {}
    ungrouped_results = []

    for row in rows:
        location_name = normalize_location(row['location_raw'])
        if location_name == 'Other/Unknown':
            location_name = str(row['location_normalized'] or '').strip() or location_name
        display_row = {
            'year': row['year'],
            'float_number': row['float_number'],
            'finder': row['finder'] or 'Unknown finder',
            'location_name': location_name,
            'location_raw': row['location_raw'],
            'date_found': row['date_found'],
            'report_url': row['url'],
        }

        if location_name and location_name != 'Other/Unknown':
            group = grouped_results.setdefault(
                location_name,
                {
                    'location_name': location_name,
                    'latest_report': display_row,
                    'recent_finders': [],
                    'reports': [],
                },
            )
            group['reports'].append(display_row)
            if display_row['finder'] not in group['recent_finders']:
                group['recent_finders'].append(display_row['finder'])
        else:
            ungrouped_results.append(display_row)

    display_groups = []
    for group in grouped_results.values():
        display_groups.append({
            'location_name': group['location_name'],
            'latest_report': group['latest_report'],
            'recent_finders': group['recent_finders'][:3],
            'report_count': len(group['reports']),
            'reports': group['reports'],
        })

    return display_groups, ungrouped_results


def row_matches_search_query(row, query):
    query_text = str(query or '').strip()
    if not query_text:
        return False

    query_lower = query_text.lower()
    location_name = normalize_location(row['location_raw'])
    normalized_query = normalize_location(query_text)
    searchable_fields = (
        row['finder'],
        row['location_raw'],
        row['float_number'],
        row['location_normalized'],
        location_name,
    )

    if any(query_lower in str(field or '').lower() for field in searchable_fields):
        return True

    if '#' in query_text:
        return False

    return normalized_query != 'Other/Unknown' and location_name == normalized_query


def get_metrics_db_connection():
    metrics_dir = os.path.dirname(METRICS_DB_PATH)
    if metrics_dir:
        os.makedirs(metrics_dir, exist_ok=True)
    return sqlite3.connect(METRICS_DB_PATH)


def ensure_metrics_schema(conn):
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS growth_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            location_name TEXT NOT NULL,
            share_method TEXT,
            created_at TEXT NOT NULL
        )
        '''
    )
    conn.commit()


def parse_event_payload():
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload

    raw_payload = request.get_data(as_text=True)
    if not raw_payload:
        return None

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def normalize_event_payload(payload):
    if not isinstance(payload, dict):
        return None

    event_name = str(payload.get('event_name') or '').strip()
    location_name = str(payload.get('location_name') or '').strip()
    share_method = payload.get('share_method')
    if isinstance(share_method, str):
        share_method = share_method.strip()

    if event_name not in ALLOWED_EVENT_NAMES or not location_name:
        return None

    if event_name == 'share_clicked':
        if share_method not in ALLOWED_SHARE_METHODS:
            return None
    else:
        share_method = None

    return {
        'event_name': event_name,
        'location_name': location_name,
        'share_method': share_method,
    }


def record_growth_event(event_name, location_name, share_method=None):
    conn = get_metrics_db_connection()
    try:
        ensure_metrics_schema(conn)
        conn.execute(
            '''
            INSERT INTO growth_events (event_name, location_name, share_method, created_at)
            VALUES (?, ?, ?, ?)
            ''',
            (
                event_name,
                location_name,
                share_method,
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_db_mtime():
    try:
        return os.path.getmtime(DB_NAME)
    except OSError:
        return 0


@lru_cache(maxsize=16)
def _get_location_counts_cached(selected_year, db_mtime):
    year_param = None if selected_year == 'all' else int(selected_year)
    where_clause, where_params = build_finds_where_clause(year_param=year_param)

    conn = get_db_connection()
    try:
        all_locs = conn.execute(
            f'SELECT location_raw FROM finds {where_clause}',
            where_params,
        ).fetchall()
    except sqlite3.Error:
        conn.close()
        return tuple()
    conn.close()

    loc_counts = Counter(normalize_location(row['location_raw']) for row in all_locs)
    return tuple(loc_counts.items())


def get_location_counts(year_param=None):
    year_key = 'all' if year_param is None else str(year_param)
    return Counter(dict(_get_location_counts_cached(year_key, get_db_mtime())))


def build_mapped_spots(loc_counts):
    spots = []
    for loc, count in loc_counts.most_common():
        coords = LOCATIONS.get(loc)
        if not coords:
            continue

        spots.append({
            'name': loc,
            'count': count,
            'lat': coords['lat'],
            'lon': coords['lon'],
        })

    return spots


def build_field_priority_tiers(hunting_spots, briefing, focused_route=None):
    if not hunting_spots:
        return {
            'best_bet': None,
            'closest_worthwhile': [],
            'more_options': [],
            'directory_count': 0,
        }

    spot_lookup = {spot['name']: spot for spot in hunting_spots}
    zones = briefing.get('zones', []) if briefing else []
    zone_details_by_spot = {}

    for rank, zone in enumerate(zones, start=1):
        ordered_names = []
        primary_name = zone.get('primary_spot') or zone.get('label')
        if primary_name:
            ordered_names.append(primary_name)
        ordered_names.extend(
            support.get('name')
            for support in zone.get('supporting_spots', [])
            if support.get('name')
        )

        seen_names = set()
        for support_rank, name in enumerate(ordered_names):
            if name in seen_names or name not in spot_lookup:
                continue
            seen_names.add(name)

            existing = zone_details_by_spot.get(name)
            if existing and existing['rank'] <= rank:
                continue

            zone_details_by_spot[name] = {
                'rank': rank,
                'support_rank': support_rank,
                'zone_label': zone.get('label') or name,
                'signal_label': zone.get('signal_label') or '',
                'reason_text': next(
                    (text for text in zone.get('reason_texts', []) if text),
                    '',
                ),
                'reason_tags': [tag for tag in zone.get('reason_tags', []) if tag][:3],
            }

    def clone_spot(
        name,
        *,
        priority_label='',
        priority_reason='',
        priority_tags=None,
        support_summary='',
        supporting_spots=None,
    ):
        base_spot = spot_lookup.get(name)
        if not base_spot:
            return None

        cloned = dict(base_spot)
        cloned['priority_label'] = priority_label
        cloned['priority_reason'] = priority_reason
        cloned['priority_tags'] = list(priority_tags or [])
        cloned['location_href'] = (
            base_spot.get('location_href')
            or url_for('location_detail', location_name=name)
        )
        cloned['support_summary'] = support_summary
        cloned['supporting_spots'] = list(supporting_spots or [])
        return cloned

    featured_names = set()
    worthwhile_names = []

    def add_worthwhile(name):
        if (
            not name
            or name in featured_names
            or name in worthwhile_names
            or name not in spot_lookup
        ):
            return
        worthwhile_names.append(name)

    best_bet = None

    if focused_route and focused_route.get('name') in spot_lookup:
        support_names = [
            stop['name']
            for stop in focused_route.get('backup_stops', [])
            if stop.get('name') in spot_lookup and stop.get('name') != focused_route.get('name')
        ]
        best_bet = clone_spot(
            focused_route['name'],
            priority_label='Shared route start',
            priority_reason=focused_route.get('summary')
            or 'Shared from a location page so you can start with a known stop.',
            support_summary=build_support_summary(
                support_names,
                'Sort the shortlist below by distance once you are moving.',
            ),
            supporting_spots=support_names[:3],
        )
        featured_names.add(focused_route['name'])
        for name in support_names:
            add_worthwhile(name)

    if not best_bet:
        lead_zone = zones[0] if zones else None
        if lead_zone:
            lead_name = lead_zone.get('primary_spot') or lead_zone.get('label')
            lead_meta = zone_details_by_spot.get(lead_name, {})
            support_names = []
            for support in lead_zone.get('supporting_spots', []):
                support_name = support.get('name')
                if (
                    support_name
                    and support_name != lead_name
                    and support_name in spot_lookup
                    and support_name not in support_names
                ):
                    support_names.append(support_name)

            best_bet = clone_spot(
                lead_name,
                priority_label='Best bet right now',
                priority_reason=build_field_reason_text(
                    lead_name,
                    int(spot_lookup.get(lead_name, {}).get('count') or 0),
                    lead_meta,
                ),
                priority_tags=[],
                support_summary=build_support_summary(
                    support_names,
                    'Use the shortlist below if access, crowds, or conditions change the plan.',
                ),
                supporting_spots=support_names[:3],
            )
            if best_bet:
                featured_names.add(lead_name)

        if not best_bet:
            fallback_name = hunting_spots[0]['name']
            best_bet = clone_spot(
                fallback_name,
                priority_label='Archive leader',
                priority_reason=build_field_reason_text(
                    fallback_name,
                    int(spot_lookup.get(fallback_name, {}).get('count') or 0),
                ),
                support_summary='Use the shortlist below to keep one or two backups ready.',
            )
            featured_names.add(fallback_name)

    for zone in zones[:3]:
        add_worthwhile(zone.get('primary_spot') or zone.get('label'))
        for support in zone.get('supporting_spots', []):
            add_worthwhile(support.get('name'))

    for spot in hunting_spots:
        if len(worthwhile_names) >= 4:
            break
        add_worthwhile(spot['name'])

    closest_worthwhile = []
    for name in worthwhile_names[:4]:
        zone_meta = zone_details_by_spot.get(name)
        if zone_meta:
            if zone_meta['support_rank'] == 0:
                priority_label = zone_meta['signal_label'] or 'Forecast-backed stop'
            else:
                priority_label = 'Forecast-backed backup'
            priority_tags = zone_meta['reason_tags'][:1]
        else:
            priority_label = 'Archive standout'
            priority_tags = []

        worthwhile_spot = clone_spot(
            name,
            priority_label=priority_label,
            priority_reason=build_field_reason_text(
                name,
                int(spot_lookup.get(name, {}).get('count') or 0),
                zone_meta,
            ),
            priority_tags=priority_tags,
        )
        if worthwhile_spot:
            closest_worthwhile.append(worthwhile_spot)

    excluded_names = featured_names.union(worthwhile_names)
    more_options = []
    for spot in hunting_spots:
        if spot['name'] in excluded_names:
            continue

        zone_meta = zone_details_by_spot.get(spot['name'])
        if zone_meta:
            priority_label = f"Forecast zone #{zone_meta['rank']}"
            priority_tags = zone_meta['reason_tags'][:1]
        else:
            priority_label = 'Archive signal'
            priority_tags = []

        more_option = clone_spot(
            spot['name'],
            priority_label=priority_label,
            priority_reason=build_field_reason_text(
                spot['name'],
                int(spot.get('count') or 0),
                zone_meta,
            ),
            priority_tags=priority_tags,
        )
        if more_option:
            more_options.append(more_option)
        if len(more_options) >= 6:
            break

    return {
        'best_bet': best_bet,
        'closest_worthwhile': closest_worthwhile,
        'more_options': more_options,
        'directory_count': len(hunting_spots),
    }


def build_nearby_route_stops(location_name, coords, loc_counts, limit=2):
    if not coords:
        return []

    nearby = []
    for spot in build_mapped_spots(loc_counts):
        if spot['name'] == location_name:
            continue

        distance_miles = calculate_distance_miles(
            coords['lat'],
            coords['lon'],
            spot['lat'],
            spot['lon'],
        )
        count = int(spot['count'])
        count_label = '1 report in the archive' if count == 1 else f'{count} reports in the archive'
        nearby.append({
            'name': spot['name'],
            'count': count,
            'count_label': count_label,
            'distance_miles': round(distance_miles, 1),
            'distance_label': format_distance_label(distance_miles),
            'location_href': url_for('location_detail', location_name=spot['name']),
            'google_maps_href': build_google_maps_href(spot['lat'], spot['lon']),
            'apple_maps_href': build_apple_maps_href(spot['lat'], spot['lon'], spot['name']),
        })

    nearby.sort(key=lambda spot: (spot['distance_miles'], -spot['count'], spot['name']))
    return nearby[:limit]


def build_map_clusters(spots):
    grouped = defaultdict(list)
    for spot in spots:
        grouped[(spot['lat'], spot['lon'])].append(spot)

    clusters = []
    for (lat, lon), group in grouped.items():
        ranked_group = sorted(group, key=lambda spot: (-spot['count'], spot['name']))
        total_count = sum(spot['count'] for spot in ranked_group)
        primary_spot = ranked_group[0]

        clusters.append({
            'lat': lat,
            'lon': lon,
            'count': total_count,
            'label': primary_spot['name'] if len(ranked_group) == 1 else f"{primary_spot['name']} area",
            'spot_count': len(ranked_group),
            'spots': [
                {
                    'name': spot['name'],
                    'count': spot['count'],
                }
                for spot in ranked_group[:5]
            ],
            'remaining_spot_count': max(len(ranked_group) - 5, 0),
        })

    return sorted(clusters, key=lambda cluster: (-cluster['count'], cluster['label']))


def build_dashboard_map_payload(spots):
    clusters = build_map_clusters(spots)
    max_count = max((cluster['count'] for cluster in clusters), default=1)

    return {
        'center': [41.17, -71.58],
        'clusters': clusters,
        'cluster_count': len(clusters),
        'spot_count': len(spots),
        'max_count': max_count,
        'top_cluster': clusters[0] if clusters else None,
    }

# Simple in-memory cache for weather data
weather_cache = {
    'data': None,
    'timestamp': None
}


def normalize_weather_payload(weather):
    if not isinstance(weather, dict):
        return None

    normalized = dict(weather)
    condition = str(normalized.get('condition') or '').strip()
    summary = str(normalized.get('summary') or '').strip()
    if not condition or condition.lower() == 'unknown':
        condition = summary

    if condition:
        normalized['condition'] = condition
    else:
        normalized.pop('condition', None)

    timestamp = str(normalized.get('timestamp') or '').strip()
    if timestamp:
        normalized['timestamp'] = timestamp
    else:
        normalized.pop('timestamp', None)

    if not normalized.get('emoji') and condition:
        normalized['emoji'] = weather_emoji(condition)

    if (
        normalized.get('temp') is None
        and normalized.get('wind') is None
        and not normalized.get('condition')
    ):
        return None

    return normalized


def get_weather_data():
    """
    Fetch current weather for Block Island (Station KBID) from NOAA API.
    Caches data for 15 minutes to avoid rate limiting.
    """
    global weather_cache
    
    # Check cache (15 minute expiration)
    now = datetime.datetime.now(DISPLAY_TIMEZONE)
    cached_weather = normalize_weather_payload(weather_cache['data'])
    if (cached_weather and weather_cache['timestamp'] and 
        (now - weather_cache['timestamp']).total_seconds() < 900):
        return cached_weather
        
    try:
        # NOAA API requires a User-Agent
        headers = {
            'User-Agent': '(glassfloattracker.com, contact@glassfloattracker.com)',
            'Accept': 'application/geo+json'
        }
        
        # Station KBID is Block Island State Airport
        url = "https://api.weather.gov/stations/KBID/observations/latest"
        
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            props = data.get('properties', {})
            
            # Extract relevant data
            temp_c = props.get('temperature', {}).get('value')
            wind_payload = props.get('windSpeed', {})
            text_desc = props.get('textDescription') or ''
            temp_f = round((temp_c * 9/5) + 32) if temp_c is not None else None
            wind_mph = convert_wind_speed_to_mph(
                wind_payload.get('value'),
                wind_payload.get('unitCode'),
            )
            
            # Map text description to emoji
            desc_lower = text_desc.lower()
            if 'sunny' in desc_lower or 'clear' in desc_lower:
                emoji = '☀️'
            elif 'partly cloudy' in desc_lower:
                emoji = '⛅'
            elif 'cloudy' in desc_lower or 'overcast' in desc_lower:
                emoji = '☁️'
            elif 'rain' in desc_lower or 'drizzle' in desc_lower or 'shower' in desc_lower:
                emoji = '☔'
            elif 'thunder' in desc_lower:
                emoji = '⛈️'
            elif 'snow' in desc_lower:
                emoji = '❄️'
            elif 'fog' in desc_lower or 'mist' in desc_lower:
                emoji = '🌫️'
            elif 'wind' in desc_lower:
                emoji = '💨'
            else:
                emoji = '🌡️' # Thermometer as default
                
            weather_data = normalize_weather_payload({
                'temp': temp_f,
                'condition': text_desc,
                'wind': wind_mph,
                'emoji': weather_emoji(text_desc or 'Live weather'),
                'timestamp': now.strftime("%I:%M %p")
            })

            if weather_data:
                weather_cache['data'] = weather_data
                weather_cache['timestamp'] = now
                return weather_data
            
    except Exception as e:
        print(f"Error fetching weather: {e}")
        
    return None


tide_cache = {
    'data': None,
    'timestamp': None,
}


def get_weather_context():
    """Fetch richer NWS weather context for the forecast briefing."""
    global weather_cache

    now = datetime.datetime.now(DISPLAY_TIMEZONE)
    cached_weather = normalize_weather_payload(weather_cache['data'])
    if (
        cached_weather
        and weather_cache['timestamp']
        and (now - weather_cache['timestamp']).total_seconds() < 900
        and cached_weather.get('summary')
    ):
        return cached_weather

    weather = normalize_weather_payload(
        fetch_live_weather_context(now=now, request_get=requests.get)
    )
    if weather:
        weather_cache['data'] = weather
        weather_cache['timestamp'] = now
        return weather
    return get_weather_data()


def get_tide_context():
    global tide_cache

    now = datetime.datetime.now()
    if (
        tide_cache['data']
        and tide_cache['timestamp']
        and (now - tide_cache['timestamp']).total_seconds() < 1800
    ):
        return tide_cache['data']

    tide = fetch_live_tide_context(target_time=now, request_get=requests.get)
    if tide:
        tide_cache['data'] = tide
        tide_cache['timestamp'] = now
    return tide


def build_daily_forecast_briefing(target_date=None):
    target = target_date or get_today()
    artifact = load_forecast_artifact()
    location_counts = get_location_counts()
    location_to_cluster = build_cluster_lookup(location_counts)
    recent_activity = build_recent_activity_snapshot(
        DB_NAME,
        target_date=target,
        location_to_cluster=location_to_cluster,
    )
    briefing = compose_daily_forecast_briefing(
        artifact,
        target_date=target,
        weather_context=get_weather_context(),
        tide_context=get_tide_context(),
        recent_activity=recent_activity,
    )

    conditions = briefing.get('conditions', {}) if isinstance(briefing.get('conditions'), dict) else {}
    normalized_weather = normalize_weather_payload(conditions.get('weather'))
    conditions['weather'] = normalized_weather
    briefing['conditions'] = conditions
    if not normalized_weather:
        briefing.setdefault('feature_freshness', {})['weather_updated_at'] = ''
        briefing['feature_freshness']['live_weather_available'] = False

    for zone in briefing.get('zones', []):
        primary_spot = zone.get('primary_spot') or zone.get('label')
        zone['location_href'] = url_for('location_detail', location_name=primary_spot)
        zone['field_href'] = url_for('field_mode')

    return briefing

@app.route('/')
def index():
    conn = get_db_connection()

    # Get year filter from query parameter
    selected_year, year_param = parse_selected_year(request.args.get('year', 'all'))
    where_clause, where_params = build_finds_where_clause(year_param=year_param)
    # Get total finds (filtered)
    total_finds = conn.execute(
        f'SELECT count(*) FROM finds {where_clause}',
        where_params,
    ).fetchone()[0]
    
    # Get year recovery statistics (hidden, found, recovery rate for each year)
    year_recovery_stats = get_year_recovery_stats()
    
    # Calculate total floats hidden across all years
    total_hidden_all_years = sum(year['hidden'] for year in year_recovery_stats)
    total_found_all_years = sum(year['found'] for year in year_recovery_stats)
    
    # Get date analysis stats (filtered)
    date_stats = analyze_dates(year_param)
    best_months = date_stats['best_months']
    total_dates_analyzed = date_stats['total_dates_analyzed']
    
    # Get unreported float stats (only for specific years, not "all")
    # Float numbers are reused each year, so aggregation across years doesn't make sense
    if year_param is not None:
        unreported_stats = analyze_unreported_floats(year_param)
        still_out_there = unreported_stats['unreported']
    else:
        unreported_stats = None
        still_out_there = max(total_hidden_all_years - total_found_all_years, 0)
    
    loc_counts = get_location_counts(year_param=year_param)
    mapped_spots = build_mapped_spots(loc_counts)
    top_locs = mapped_spots[:20]
    dashboard_map = build_dashboard_map_payload(mapped_spots)
    
    conn.close()
    
    # Get last updated timestamp
    last_updated = get_last_updated()
    forecast_briefing = build_daily_forecast_briefing()
    lead_zone = forecast_briefing['zones'][0] if forecast_briefing.get('zones') else None
    primary_location = top_locs[0] if top_locs else None
    best_month = best_months[0] if best_months else None
    best_recovery_year = max(
        year_recovery_stats,
        key=lambda row: row['recovery_rate'],
    ) if year_recovery_stats else None
    
    return render_template('index.html', 
                           total_finds=total_finds,
                           years=year_recovery_stats,
                           top_locs=top_locs,
                           dashboard_map=dashboard_map,
                           best_months=best_months,
                           total_dates_analyzed=total_dates_analyzed,
                           unreported_stats=unreported_stats,
                           still_out_there=still_out_there,
                           last_updated=last_updated,
                           selected_year=selected_year,
                           forecast_briefing=forecast_briefing,
                           lead_zone=lead_zone,
                           primary_location=primary_location,
                           best_month=best_month,
                           best_recovery_year=best_recovery_year,
                           page_meta=build_page_meta(
                               active_nav='dashboard',
                               mode='dashboard',
                               kicker='Explore',
                               title='Plan your Block Island glass float hunt with real find history',
                               subtitle='See which beaches and trails keep producing finds, when finds peak, and where to start today.',
                               primary_cta=build_cta(
                                   label='Explore hotspots',
                                   href='#explore-map',
                               ),
                               description='Use public find history to compare hotspots, seasonality, and the best places to start a Block Island glass float hunt.',
                           ))

@app.route('/search')
def search():
    query = request.args.get('q', '')
    conn = get_db_connection()
    if query:
        rows = conn.execute(
            "SELECT * FROM finds ORDER BY year DESC, date_found DESC"
        ).fetchall()
        results = [row for row in rows if row_matches_search_query(row, query)][:50]
    else:
        results = []
    grouped_results, ungrouped_results = build_search_result_groups(results)
    conn.close()
    return render_template(
        'search.html',
        grouped_results=grouped_results,
        ungrouped_results=ungrouped_results,
        query=query,
        result_count=len(results),
        grouped_result_count=len(grouped_results),
        page_meta=build_page_meta(
            active_nav='search',
            mode='utility',
            kicker='Archive',
            title='Search the float archive by place, finder, or number',
            subtitle='Use the public archive to confirm a report, trace a location, or jump into the full place history.',
            description='Search public Block Island glass float reports by place name, finder, or float number.',
        ),
    )

@app.route('/about')
def about():
    return render_template(
        'about.html',
        page_meta=build_page_meta(
            active_nav='about',
            mode='story',
            kicker='Guide',
            title='Plan smarter, then use the official site to claim the find',
            subtitle='This tracker turns public float reports into a clearer starting plan. Use the official site for rules, registration, and finder stories.',
            primary_cta=build_cta(
                label='Explore hotspots',
                href=url_for('index'),
            ),
            description='Learn how the tracker helps plan a Block Island glass float hunt, and when to use the official project site.',
        ),
    )

@app.route('/field')
def field_mode():
    """Mobile-optimized field mode for on-island hunting"""
    location_counts = get_location_counts()
    hunting_spots = build_mapped_spots(location_counts)
    briefing = build_daily_forecast_briefing()
    forecast_lookup = build_spot_forecast_lookup(briefing)
    for spot in hunting_spots:
        spot['location_href'] = url_for('location_detail', location_name=spot['name'])
        badge = forecast_lookup.get(spot['name'])
        if badge:
            spot['forecast_rank'] = badge['rank']
            spot['forecast_zone'] = badge['zone_label']

    requested_focus = str(request.args.get('focus') or '').strip()
    focused_spot_name = normalize_location(requested_focus) if requested_focus else None
    focused_route = None
    if focused_spot_name:
        focused_spot = next((spot for spot in hunting_spots if spot['name'] == focused_spot_name), None)
        if focused_spot:
            hunting_spots = [
                focused_spot,
                *[spot for spot in hunting_spots if spot['name'] != focused_spot_name],
            ]
            focused_backups = build_nearby_route_stops(
                focused_spot_name,
                {'lat': focused_spot['lat'], 'lon': focused_spot['lon']},
                location_counts,
            )
            backup_names = join_label_list(stop['name'] for stop in focused_backups)
            focused_route = {
                'name': focused_spot_name,
                'summary': (
                    f"Shared from a location page. Start at {focused_spot_name}, then keep {backup_names} nearby if the first pass is quiet."
                    if backup_names
                    else f'Shared from a location page. Start at {focused_spot_name}, then sort the rest by distance once you are moving.'
                ),
                'backup_stops': focused_backups,
            }
        else:
            focused_spot_name = None

    priority_tiers = build_field_priority_tiers(
        hunting_spots,
        briefing,
        focused_route=focused_route,
    )
    directory_state = build_field_directory_state(hunting_spots)
    last_updated = get_last_updated()
    weather = normalize_weather_payload(
        briefing.get('conditions', {}).get('weather')
    ) or get_weather_data()

    return render_template('field.html',
                           hunting_spots=hunting_spots,
                           priority_tiers=priority_tiers,
                           directory_state=directory_state,
                           last_updated=last_updated,
                           weather=weather,
                           forecast_briefing=briefing,
                          focused_spot_name=focused_spot_name,
                          focused_route=focused_route,
                          etiquette=FIELD_ETIQUETTE,
                          page_meta=build_page_meta(
                              active_nav='field',
                              mode='utility',
                              kicker='Field',
                              title='Find the best spots near you',
                              subtitle='Sort mapped locations by distance, open directions fast, and keep hunt rules close at hand.',
                              description='Use the field view to sort nearby Block Island float locations, open directions, and keep official hunt rules close.',
                          ))

@app.route('/location/<path:location_name>')
def location_detail(location_name):
    """Detail page for a specific location showing all finds and photos"""
    conn = get_db_connection()

    # Get all finds and filter by normalizing location_raw
    # (location_normalized column is not populated in DB, normalization happens on the fly)
    finds_query = 'SELECT * FROM finds'
    finds_query += ' ORDER BY year DESC, date_found DESC'
    all_finds = conn.execute(
        finds_query
    ).fetchall()
    
    # Filter finds by normalizing the location_raw
    finds = [f for f in all_finds if normalize_location(f['location_raw']) == location_name]
    
    if not finds:
        conn.close()
        return "Location not found", 404

    has_image_url = 'image_url' in finds[0].keys()
    location_counts = get_location_counts()
    
    # Calculate stats
    total_finds = len(finds)
    years = {}
    finders = {}
    images = []
    
    for find in finds:
        # Year distribution
        year = find['year']
        years[year] = years.get(year, 0) + 1
        
        # Top finders
        finder = find['finder']
        if finder:
            finders[finder] = finders.get(finder, 0) + 1
        
        # Collect images
        image_url = find['image_url'] if has_image_url else None
        if image_url:
            # Filter out generic Block Island logo/placeholder images
            is_placeholder = 'default_image' in image_url
            
            if not is_placeholder:
                images.append({
                    'url': image_url,
                    'finder': finder,
                    'year': year,
                    'float_number': find['float_number'],
                    'date': find['date_found']
                })
    
    # Get coordinates
    coords = LOCATIONS.get(location_name, None)
    
    # Top stats
    peak_year = max(years.items(), key=lambda x: x[1]) if years else (None, 0)
    top_finder = max(finders.items(), key=lambda x: x[1]) if finders else (None, 0)
    years_tracked = len(years)
    latest_find = next((find for find in finds if find['date_found']), None)
    featured_images = images[:12]
    extra_images = images[12:]
    recent_finds = finds[:18]
    older_finds = finds[18:]
    shared_ref = request.args.get('ref') == 'share'
    share_url = url_for('location_detail', location_name=location_name, ref='share', _external=True)
    location_url = url_for('location_detail', location_name=location_name, _external=True)
    field_share_url = url_for('field_mode', focus=location_name, _external=True) if coords else ''
    field_href = url_for('field_mode', focus=location_name) if coords else url_for('field_mode')
    season_label = 'season' if years_tracked == 1 else 'seasons'
    find_label = 'find' if total_finds == 1 else 'finds'
    latest_date = latest_find['date_found'] if latest_find and latest_find['date_found'] else None
    latest_date_label = format_public_date(latest_date, missing='Undated in the archive') if latest_date else None
    archive_signal = build_archive_signal(total_finds, years_tracked)
    nearby_route_stops = build_nearby_route_stops(location_name, coords, location_counts)
    backup_names = join_label_list(stop['name'] for stop in nearby_route_stops)
    share_parts = [
        f'{location_name} outing card: {archive_signal["share_label"]} with {total_finds} reported {find_label} across {years_tracked} {season_label}.',
    ]
    if latest_date_label:
        share_parts.append(f'Latest dated report: {latest_date_label}.')
    if backup_names:
        backup_label = 'Backup stop' if len(nearby_route_stops) == 1 else 'Backup stops'
        share_parts.append(f'{backup_label}: {backup_names}.')
    share_text = ' '.join(share_parts)
    share_copy_lines = [share_text, share_url]
    if field_share_url:
        share_copy_lines.append(f'Focused field view: {field_share_url}')
    share_copy_text = '\n'.join(share_copy_lines)
    route_summary = (
        f'If the first pass feels quiet, keep {backup_names} nearby as the next move.'
        if backup_names
        else 'If the first pass feels quiet, jump into field mode and sort the rest by distance.'
    )
    page_description = share_text
    page_image = images[0]['url'] if images else url_for('static', filename='icon-512.png', _external=True)
    google_maps_href = build_google_maps_href(coords['lat'], coords['lon']) if coords else None
    apple_maps_href = build_apple_maps_href(coords['lat'], coords['lon'], location_name) if coords else None
    
    conn.close()
    
    return render_template('location_detail.html',
                          location_name=location_name,
                          total_finds=total_finds,
                          finds=finds,
                          images=images,
                          featured_images=featured_images,
                          extra_images=extra_images,
                          coords=coords,
                          peak_year=peak_year,
                          top_finder=top_finder,
                          years=sorted(years.items(), reverse=True),
                          years_tracked=years_tracked,
                          latest_find=latest_find,
                          latest_date_label=latest_date_label,
                          recent_finds=recent_finds,
                          older_finds=older_finds,
                          outing_card={
                              'badge_label': archive_signal['badge_label'],
                              'summary': archive_signal['summary'],
                              'route_summary': route_summary,
                              'backup_stops': nearby_route_stops,
                              'field_href': field_href,
                              'google_maps_href': google_maps_href,
                              'apple_maps_href': apple_maps_href,
                              'share_preview': share_text,
                          },
                          share_payload={
                              'title': f'{location_name} outing card',
                              'share_url': share_url,
                              'share_text': share_text,
                              'copy_text': share_copy_text,
                              'location_name': location_name,
                          },
                          shared_ref=shared_ref,
                          page_meta=build_page_meta(
                              active_nav='dashboard',
                              mode='utility',
                              kicker='Location guide',
                              title=location_name,
                              subtitle=(
                                  f'{location_name} keeps surfacing in public find reports, with {total_finds} reports across {years_tracked} seasons.'
                                  if years_tracked
                                  else f'{location_name} has {total_finds} recorded reports in the archive.'
                              ),
                              primary_cta=build_cta(
                                  label='Open in Google Maps',
                                  href=google_maps_href,
                                  external=True,
                              ) if coords else None,
                              description=page_description,
                              url=location_url,
                              image=page_image,
                              meta_title=f'{location_name} outing card',
                              image_alt=f'Archive photo from {location_name}' if images else 'Block Island Glass Floats map marker',
                          ))


@app.route('/api/events', methods=['POST'])
def record_event():
    payload = normalize_event_payload(parse_event_payload())
    if payload is None:
        return {'error': 'invalid event payload'}, 400

    record_growth_event(
        payload['event_name'],
        payload['location_name'],
        share_method=payload.get('share_method'),
    )
    return '', 204

def predict_today():
    artifact = load_forecast_artifact()
    day_key = str(get_today().timetuple().tm_yday)
    priors = artifact.get('seasonal_priors_by_day', {}).get(day_key, {})
    return [
        {'zone': label, 'score': score}
        for label, score in sorted(priors.items(), key=lambda item: (-float(item[1]), item[0]))[:3]
    ]


def get_seasonality_score():
    artifact = load_forecast_artifact()
    day_key = str(get_today().timetuple().tm_yday)
    activity = artifact.get('activity_index_by_day', {}).get(day_key, 0)
    try:
        return float(activity)
    except (TypeError, ValueError):
        return 0.0

@app.route('/forecast')
def forecast():
    """Show the daily zone briefing."""
    briefing = build_daily_forecast_briefing()
    freshness = build_forecast_freshness(briefing)
    briefing['zones'] = build_forecast_zone_cards(briefing.get('zones', []), freshness)

    return render_template('forecast.html', 
                          briefing=briefing,
                          freshness=freshness,
                          lead_zone=briefing['zones'][0] if briefing.get('zones') else None,
                          page_meta=build_page_meta(
                              active_nav='forecast',
                              mode='utility',
                              kicker='Today' if not freshness['is_stale'] else 'Advisory',
                              title=freshness['headline'],
                              subtitle=freshness['subtitle'],
                              primary_cta=build_cta(
                                  label='Open field view',
                                  href=url_for('field_mode'),
                              ),
                              description='See the latest recommended starting area for a Block Island glass float hunt, plus the live conditions and forecast freshness behind it.',
                            ))

@app.route('/sw.js')
def service_worker():
    from flask import send_from_directory
    response = send_from_directory('static', 'sw.js')
    response.headers['Cache-Control'] = 'no-cache'
    return response


@app.route('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory('static', 'icon-192.png', mimetype='image/png')


@app.route('/healthz')
def healthcheck():
    return {'status': 'ok'}, 200

if __name__ == '__main__':
    app.run(
        debug=os.getenv('FLASK_DEBUG', '').lower() in {'1', 'true', 'yes', 'on'},
        host='0.0.0.0',
        port=int(os.getenv('PORT', '5000')),
    )
