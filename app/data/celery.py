import logging
from abc import ABCMeta
from typing import Any
from typing import Dict
from typing import List
from typing import TypeVar

from celery import Celery as _Celery
from celery import Task
from celery.signals import task_postrun
from celery.signals import task_prerun
from celery.utils.log import get_task_logger
from flask import Flask


RecordsType = TypeVar("RecordsType", bound=List[Dict[str, Any]])


class WithAppContextTask(Task, metaclass=ABCMeta):
    def __call__(self, *args, **kwargs):
        with self.app.flask_app.app_context():
            return super().__call__(*args, **kwargs)


class Celery(_Celery):
    task_cls = WithAppContextTask
    flask_app: Flask = None

    def health(self) -> None:
        if self.control.inspect().ping() is not None:
            raise RuntimeError(
                "It looks like Celery is not ready."
                " Open up a second terminal and run the command:"
                " `flask celery worker`"
            )


celery_app = Celery(__name__)
celery_app.conf.broker_connection_retry_on_startup = True

logger: logging.Logger = get_task_logger(__name__)
logger.setLevel(logging.INFO)


def init_celery(app: Flask):
    celery_app.flask_app = app
    celery_app.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
    )


@task_prerun.connect
def task_starting_handler(*args, **kwargs):
    logger.info("Starting task.")


@task_postrun.connect
def task_finished_handler(*args, **kwargs):
    logger.info("Finished task.")


@celery_app.task
def live_hobolink_data_task(*args, **kwargs) -> RecordsType:
    from app.data.processing.hobolink import get_live_hobolink_data

    df = get_live_hobolink_data(*args, **kwargs)
    return df.to_dict(orient="records")


@celery_app.task
def live_usgs_data_task(*args, **kwargs) -> RecordsType:
    from app.data.processing.usgs import get_live_usgs_data

    df = get_live_usgs_data(*args, **kwargs)
    return df.to_dict(orient="records")


@celery_app.task
def combine_data_v1_task(*args, **kwargs) -> RecordsType:
    from app.data.processing.core import combine_v1_job

    df = combine_v1_job(*args, **kwargs)
    return df.to_dict(orient="records")


@celery_app.task
def combine_data_v2_task(*args, **kwargs) -> RecordsType:
    from app.data.processing.core import combine_v2_job

    df = combine_v2_job(*args, **kwargs)
    return df.to_dict(orient="records")


@celery_app.task
def combine_data_v3_task(*args, **kwargs) -> RecordsType:
    from app.data.processing.core import combine_v3_job

    df = combine_v3_job(*args, **kwargs)
    return df.to_dict(orient="records")


@celery_app.task
def combine_data_v4_task(*args, **kwargs) -> RecordsType:
    from app.data.processing.core import combine_v4_job

    df = combine_v4_job(*args, **kwargs)
    return df.to_dict(orient="records")


@celery_app.task
def predict_v1_task(*args, **kwargs) -> RecordsType:
    from app.data.processing.core import predict_v1_job

    df = predict_v1_job(*args, **kwargs)
    return df.to_dict(orient="records")


@celery_app.task
def predict_v2_task(*args, **kwargs) -> RecordsType:
    from app.data.processing.core import predict_v2_job

    df = predict_v2_job(*args, **kwargs)
    return df.to_dict(orient="records")


@celery_app.task
def predict_v3_task(*args, **kwargs) -> RecordsType:
    from app.data.processing.core import predict_v3_job

    df = predict_v3_job(*args, **kwargs)
    return df.to_dict(orient="records")


@celery_app.task
def predict_v4_task(*args, **kwargs) -> RecordsType:
    from app.data.processing.core import predict_v4_job

    df = predict_v4_job(*args, **kwargs)
    return df.to_dict(orient="records")


@celery_app.task
def update_db_task(tweet_status: bool = False) -> None:
    from app.data.globals import website_options
    from app.data.processing.core import update_db

    update_db()
    if tweet_status and website_options.boating_season:
        from app.twitter import tweet_current_status

        tweet_current_status()


@celery_app.task
def send_database_exports_task() -> None:
    from app.data.processing.core import send_database_exports

    send_database_exports()


# Some IDEs have a hard time getting type annotations for decorated objects.
# Down here, we define the types for the tasks to help the IDE.
live_hobolink_data_task: WithAppContextTask
live_usgs_data_task: WithAppContextTask
combine_data_v1_task: WithAppContextTask
combine_data_v2_task: WithAppContextTask
combine_data_v3_task: WithAppContextTask
combine_data_v4_task: WithAppContextTask
clear_cache_task: WithAppContextTask
predict_v1_task: WithAppContextTask
predict_v2_task: WithAppContextTask
predict_v3_task: WithAppContextTask
predict_v4_task: WithAppContextTask
update_db_task: WithAppContextTask
send_database_exports_task: WithAppContextTask
