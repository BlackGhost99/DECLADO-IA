from celery import shared_task

from .outbox import dispatch_pending


@shared_task(name="core.dispatch_outbox", ignore_result=True)
def dispatch_outbox():
    return dispatch_pending()
