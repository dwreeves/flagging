"""This file handles all database stuff, i.e. writing and retrieving data to
the Postgres database. Note that of the functionality in this file is available
directly in the command line.

While the app is running, the database connection is managed by SQLAlchemy. The
`db` object defined near the top of the file is that connector, and is used
throughout both this file and other files in the code base. The `db` object is
connected to the actual database in the `create_app` function: the app instance
is passed in via `db.init_app(app)`, and the `db` object looks for the config
variable `SQLALCHEMY_DATABASE_URI`.
"""
import os
from typing import Optional

import pandas as pd
import psycopg2
import psycopg2.errors
from psycopg2 import connect
import click
from flask import current_app

from flask_sqlalchemy import SQLAlchemy
from flask_postgres import init_db_callback
from sqlalchemy.exc import ResourceClosedError


db = SQLAlchemy()


def execute_sql(query: str) -> Optional[pd.DataFrame]:
    """Execute arbitrary SQL in the database. This works for both read and
    write operations. If it is a write operation, it will return None;
    otherwise it returns a Pandas dataframe.

    Args:
        query: (str) A string that contains the contents of a SQL query.

    Returns:
        Either a Pandas Dataframe the selected data for read queries, or None
        for write queries.
    """
    with db.engine.connect() as conn:
        res = conn.execute(query)
        try:
            df = pd.DataFrame(
                res.fetchall(),
                columns=res.keys()
            )
            return df
        except ResourceClosedError:
            return None


def execute_sql_from_file(file_name: str) -> Optional[pd.DataFrame]:
    """Execute SQL from a file in the `QUERIES_DIR` directory, which should be
    located at `app/data/queries`.

    Args:
        file_name: (str) A file name inside the `QUERIES_DIR` directory. It
                   should be only the file name alone and not the full path.

    Returns:
        Either a Pandas Dataframe the selected data for read queries, or None
        for write queries.
    """
    path = os.path.join(current_app.config['QUERIES_DIR'], file_name)
    with current_app.open_resource(path) as f:
        s = f.read().decode('utf8')
        print(s)
        return execute_sql(s)


def create_db(overwrite: bool = False) -> bool:
    """If the database defined by `POSTGRES_DB` doesn't exist, create it and
    return True, otherwise do nothing and return False. By default, the
    config variable `POSTGRES_DB` is set to "flagging".
    Returns:
        bool for whether the database needed to be created.
    """
    # connect to postgres database, get cursor
    conn = connect(
        user=current_app.config['POSTGRES_USER'],
        password=current_app.config['POSTGRES_PASSWORD'],
        host=current_app.config['POSTGRES_HOST'],
        port=current_app.config['POSTGRES_PORT'],
        dbname='postgres'
    )
    database = current_app.config['POSTGRES_DB']
    cursor = conn.cursor()
    cursor.execute('ROLLBACK')

    if overwrite:
        try:
            cursor.execute(f"DROP DATABASE {database};")
        except psycopg2.errors.lookup("3D000"):
            click.echo(f"Database {database!r} does not exist.")
            cursor.execute("ROLLBACK")
        else:
            click.echo(f"Database {database!r} was deleted.")

    try:
        cursor.execute(f'CREATE DATABASE {database};')
    except psycopg2.errors.lookup('42P04'):
        click.echo(f'Database {database!r} already exists.')
        cursor.execute('ROLLBACK')
        return False
    else:
        click.echo(f'Created database {database!r}.')
        return True


@init_db_callback
def init_db():
    """This data clears and then populates the database from scratch. You only
    need to run this function once per instance of the database.
    """

    # This file drops the tables if they already exist, and then defines
    # the tables. This is the only query that CREATES tables.
    execute_sql_from_file('schema.sql')

    # The models available in Base are given corresponding tables if they
    # do not already exist.
    db.create_all(app=current_app)

    # The boathouses table is populated. This table doesn't change, so it
    # only needs to be populated once.
    execute_sql_from_file('define_reach.sql')
    execute_sql_from_file('define_boathouse.sql')

    # The file for keeping track of if it's currently boating season
    execute_sql_from_file('define_default_options.sql')

    # Create a database trigger for manual overrides.
    execute_sql_from_file('override_event_triggers.sql')


def update_db():
    """This function basically controls all of our data refreshes. The
    following tables are updated in order:

    - usgs
    - hobolink
    - processed_data
    - model_outputs

    The functions run to calculate the data are imported from other files
    within the data folder.
    """
    options = {
        'con': db.engine,
        'index': False,
        'if_exists': 'replace'
    }

    hours = current_app.config['STORAGE_HOURS']

    from .globals import cache

    try:
        # Populate the `usgs` table.
        from app.data.processing.usgs import get_live_usgs_data
        df_usgs = get_live_usgs_data()
        df_usgs.tail(hours * 4).to_sql('usgs', **options)

        # Populate the `hobolink` table.
        from app.data.processing.hobolink import get_live_hobolink_data
        df_hobolink = get_live_hobolink_data()
        df_hobolink.tail(hours * 6).to_sql('hobolink', **options)

        # Populate the `processed_data` table.
        from app.data.processing.predictive_models import process_data
        df = process_data(df_hobolink=df_hobolink, df_usgs=df_usgs)
        df = df.tail(hours)
        df.to_sql('processed_data', **options)

        # Populate the `model_outputs` table.
        from app.data.processing.predictive_models import all_models
        model_outs = all_models(df)
        model_outs.to_sql('prediction', **options)

    finally:
        # Clear the cache every time this function runs.
        # the try -> finally makes sure this always runs, even if an error
        # occurs somewhere when updating.
        cache.clear()


def get_current_time() -> pd.Timestamp:
    return (
        pd.Timestamp('now', tz='UTC')
        .tz_convert('US/Eastern')
        .tz_localize(None)
    )


def delete_db(dbname: str = None):
    """Delete the database."""
    conn = connect(
        user=current_app.config['POSTGRES_USER'],
        password=current_app.config['POSTGRES_PASSWORD'],
        host=current_app.config['POSTGRES_HOST'],
        port=current_app.config['POSTGRES_PORT'],
        dbname='postgres'
    )

    database = dbname or current_app.config['POSTGRES_DB']
    cursor = conn.cursor()
    cursor.execute('ROLLBACK')

    # Don't validate name for `flagging_test`.
    if database != 'flagging_test':
        # Make sure we want to do this.
        click.echo(f'Are you sure you want to delete database {database!r}?')
        click.echo("Type in the database name '" +
                   click.style(database, fg='red') + "' to confirm")
        confirmation = click.prompt('Database name')
        if database != confirmation:
            click.echo('The input does not match. '
                       'The database will not be deleted.')
            return None

    cursor.execute(f'DROP DATABASE {database};')
    click.echo(f'Database {database!r} was deleted.')
