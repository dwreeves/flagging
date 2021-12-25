"""
Synchronous processing functions. Designed to be simple-stupid, and not shy
about adding a little repetition and not worrying about async processing-- both
in service of simplifying the code for ease of maintenance.
"""
import typing as t

from flask import current_app
import pandas as pd

from app.data.processing.hobolink import get_live_hobolink_data
from app.data.processing.hobolink import HOBOLINK_DEFAULT_EXPORT_NAME
from app.data.processing.hobolink import HOBOLINK_ROWS_PER_HOUR
from app.data.processing.usgs import get_live_usgs_data
from app.data.processing.usgs import USGS_DEFAULT_DAYS_AGO
from app.data.processing.usgs import USGS_ROWS_PER_HOUR
from app.data.processing.predictive_models import process_data
from app.data.processing.predictive_models import all_models
from app.data.globals import cache
from app.data.models.prediction import Prediction
from app.data.database import db
from app.data.database import get_current_time
from app.mail import mail_on_fail
from app.mail import ExportEmail
from app.mail import mail


def _write_to_db(
        df: pd.DataFrame,
        table_name: str,
        rows: t.Optional[int] = None
) -> None:
    """Takes a Pandas DataFrame, and writes it to the database."""
    if rows is not None:
        df = df.tail(rows)
    df.to_sql(
        table_name,
        con=db.engine,
        index=False,
        if_exists='replace'
    )


@mail_on_fail
def combine_job(
        days_ago: int = USGS_DEFAULT_DAYS_AGO,
        export_name: str = HOBOLINK_DEFAULT_EXPORT_NAME
) -> pd.DataFrame:
    df_usgs = get_live_usgs_data(days_ago=days_ago)
    df_hobolink = get_live_hobolink_data(export_name=export_name)
    df_combined = process_data(df_hobolink=df_hobolink, df_usgs=df_usgs)
    return df_combined


@mail_on_fail
def predict_job(
        days_ago: int = USGS_DEFAULT_DAYS_AGO,
        export_name: str = HOBOLINK_DEFAULT_EXPORT_NAME
) -> pd.DataFrame:
    df_usgs = get_live_usgs_data(days_ago=days_ago)
    df_hobolink = get_live_hobolink_data(export_name=export_name)
    df_combined = process_data(df_hobolink=df_hobolink, df_usgs=df_usgs)
    df_predictions = all_models(df_combined)
    return df_predictions


@mail_on_fail
def update_db() -> None:
    df_usgs = get_live_usgs_data()
    df_hobolink = get_live_hobolink_data()
    df_combined = process_data(df_hobolink=df_hobolink, df_usgs=df_usgs)
    df_predictions = all_models(df_combined)

    hours = current_app.config['STORAGE_HOURS']
    try:
        _write_to_db(df_usgs, 'usgs', rows=hours * USGS_ROWS_PER_HOUR)
        _write_to_db(df_hobolink, 'hobolink', rows=hours * HOBOLINK_ROWS_PER_HOUR)
        _write_to_db(df_combined, 'processed_data')
        _write_to_db(df_predictions, Prediction.__tablename__)
    finally:
        # Clear the cache every time we are dumping to the database.
        # the try -> finally makes sure this always runs, even if an error
        # occurs somewhere when updating.
        cache.clear()


@mail_on_fail
def send_database_exports() -> None:
    df_usgs = get_live_usgs_data(days_ago=90)
    df_hobolink = get_live_hobolink_data(export_name='code_for_boston_export_90d')
    df_combined = process_data(df_hobolink=df_hobolink, df_usgs=df_usgs)
    df_predictions = all_models(df_combined)

    todays_date = get_current_time().strftime('%Y_%m_%d')

    msg = ExportEmail()

    msg.attach_dataframe(df_usgs, f'{todays_date}-usgs.csv')
    msg.attach_dataframe(df_hobolink, f'{todays_date}-hobolink.csv')
    msg.attach_dataframe(df_combined, f'{todays_date}-combined.csv')
    msg.attach_dataframe(df_predictions, f'{todays_date}-prediction.csv')

    mail.send(msg)