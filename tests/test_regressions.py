import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import analyzer
import app as app_module
import ml_predictor
import pytest
from flask import template_rendered


def create_finds_db(path: Path, *, include_image_url: bool) -> None:
    columns = [
        'id TEXT PRIMARY KEY',
        'year TEXT',
        'float_number TEXT',
        'finder TEXT',
        'location_raw TEXT',
        'location_normalized TEXT',
        'date_found TEXT',
        'url TEXT',
    ]
    if include_image_url:
        columns.append('image_url TEXT')

    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE finds ({', '.join(columns)})")
    conn.commit()
    conn.close()


def insert_find(path: Path, **values) -> None:
    conn = sqlite3.connect(path)
    columns = ', '.join(values.keys())
    placeholders = ', '.join('?' for _ in values)
    conn.execute(
        f'INSERT INTO finds ({columns}) VALUES ({placeholders})',
        tuple(values.values()),
    )
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def clear_ml_predictor_cache():
    ml_predictor.clear_model_cache()
    yield
    ml_predictor.clear_model_cache()


@pytest.fixture
def capture_templates():
    recorded = []

    def record(sender, template, context, **extra):
        recorded.append((template, context))

    template_rendered.connect(record, app_module.app)
    try:
        yield recorded
    finally:
        template_rendered.disconnect(record, app_module.app)


def test_location_detail_handles_legacy_schema_without_image_url(tmp_path, monkeypatch, capture_templates):
    db_path = tmp_path / 'legacy.db'
    create_finds_db(db_path, include_image_url=False)
    insert_find(
        db_path,
        id='1',
        year='2025',
        float_number='12',
        finder='Tester',
        location_raw='rodman',
        location_normalized='rodman',
        date_found='2025-07-10',
        url='https://example.com/find/1',
    )

    monkeypatch.setattr(app_module, 'DB_NAME', str(db_path))

    with app_module.app.test_client() as client:
        response = client.get("/location/Rodman's Hollow")

    assert response.status_code == 200
    _, context = capture_templates[-1]
    assert context['location_name'] == "Rodman's Hollow"
    assert context['images'] == []


def test_build_forecast_artifact_ignores_blank_dates_for_seasonality(tmp_path):
    db_path = tmp_path / 'seasonality.db'
    create_finds_db(db_path, include_image_url=True)

    for month in range(1, 13):
        insert_find(
            db_path,
            id=f'dated-{month}',
            year='2025',
            float_number=str(month),
            finder='Tester',
            location_raw='rodman',
            location_normalized='rodman',
            date_found=f'2025-{month:02d}-15',
            url='',
            image_url='',
        )

    for idx in range(50):
        insert_find(
            db_path,
            id=f'blank-{idx}',
            year='2025',
            float_number=f'B{idx}',
            finder='Tester',
            location_raw='rodman',
            location_normalized='rodman',
            date_found='',
            url='',
            image_url='',
        )
    artifact = ml_predictor.build_forecast_artifact(
        db_name=str(db_path),
        total_records=62,
        latest_source_date='2025-12-15',
        generated_at='2026-03-21T00:00:00Z',
    )

    assert artifact['source']['training_rows'] == 12
    assert artifact['version'] == 2
    assert artifact['seasonality_by_month']['7'] == 5.0


def test_build_forecast_artifact_preserves_normalized_prediction_locations(tmp_path):
    db_path = tmp_path / 'forecast.db'
    create_finds_db(db_path, include_image_url=True)

    for idx in range(12):
        insert_find(
            db_path,
            id=f'forecast-{idx}',
            year='2025',
            float_number=str(idx + 1),
            finder='Tester',
            location_raw='rodman' if idx % 2 == 0 else 'clayhead',
            location_normalized='unused',
            date_found=f'2025-07-{(idx % 12) + 1:02d}',
            url='',
            image_url='',
        )
    artifact = ml_predictor.build_forecast_artifact(
        db_name=str(db_path),
        total_records=12,
        latest_source_date='2025-07-12',
        generated_at='2026-03-21T00:00:00Z',
    )
    day_priors = artifact['seasonal_priors_by_day']['182']
    profile_names = {
        spot['name']
        for profile in artifact['cluster_profiles'].values()
        if profile['dated_support_count'] > 0
        for spot in profile['supporting_spots']
    }

    assert day_priors
    assert profile_names <= {"Rodman's Hollow", "Clay Head Trail"}
    assert artifact['evaluation']['selection']['primary_model'] != 'current_random_forest'


def test_build_forecast_artifact_returns_empty_predictions_when_training_data_is_insufficient(tmp_path):
    db_path = tmp_path / 'small.db'
    create_finds_db(db_path, include_image_url=True)

    for idx in range(3):
        insert_find(
            db_path,
            id=f'small-{idx}',
            year='2025',
            float_number=str(idx + 1),
            finder='Tester',
            location_raw='rodman',
            location_normalized='unused',
            date_found=f'2025-07-{idx + 1:02d}',
            url='',
            image_url='',
        )
    artifact = ml_predictor.build_forecast_artifact(
        db_name=str(db_path),
        total_records=3,
        latest_source_date='2025-07-03',
        generated_at='2026-03-21T00:00:00Z',
    )

    assert all(predictions == {} for predictions in artifact['seasonal_priors_by_day'].values())
    assert artifact['evaluation']['selection']['primary_model'] == 'kernel_seasonal'


def test_build_forecast_artifact_includes_day_366(tmp_path):
    db_path = tmp_path / 'leap.db'
    create_finds_db(db_path, include_image_url=True)

    for idx in range(12):
        insert_find(
            db_path,
            id=f'leap-{idx}',
            year='2025',
            float_number=str(idx + 1),
            finder='Tester',
            location_raw='rodman' if idx % 2 == 0 else 'clayhead',
            location_normalized='unused',
            date_found=f'2025-12-{(idx % 12) + 1:02d}',
            url='',
            image_url='',
        )

    artifact = ml_predictor.build_forecast_artifact(
        db_name=str(db_path),
        total_records=12,
        latest_source_date='2025-12-12',
        generated_at='2026-03-21T00:00:00Z',
    )

    assert '366' in artifact['seasonal_priors_by_day']
    assert isinstance(artifact['seasonal_priors_by_day']['366'], dict)
    assert '366' in artifact['activity_index_by_day']


def test_index_uses_unique_float_counts_for_all_years_unreported(tmp_path, monkeypatch, capture_templates):
    db_path = tmp_path / 'dashboard.db'
    create_finds_db(db_path, include_image_url=True)

    rows = [
        ('2025-1', '2025', '1'),
        ('2025-2a', '2025', '2'),
        ('2025-2b', '2025', '2'),
        ('2024-1', '2024', '1'),
        ('2024-3a', '2024', '3'),
        ('2024-3b', '2024', '3'),
    ]
    for row_id, year, float_number in rows:
        insert_find(
            db_path,
            id=row_id,
            year=year,
            float_number=float_number,
            finder='Tester',
            location_raw='rodman',
            location_normalized='rodman',
            date_found='',
            url='',
            image_url='',
        )

    monkeypatch.setattr(app_module, 'DB_NAME', str(db_path))
    monkeypatch.setattr(analyzer, 'DB_NAME', str(db_path))
    monkeypatch.setattr(app_module, 'get_last_updated', lambda: 'Test fixture')

    with app_module.app.test_client() as client:
        response = client.get('/')

    assert response.status_code == 200
    _, context = capture_templates[-1]
    assert context['still_out_there'] == 1
