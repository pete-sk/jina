from docarray import DocumentArray
from jina import Document, Executor, Flow, requests

import pytest


class SimplExecutor(Executor):
    @requests
    def add_text(self, docs, **kwargs):
        docs[0].text = 'Hello World!'


def test_simple_docarray_return():
    f = Flow().add(uses=SimplExecutor)
    with f:
        docs = f.post(on='/index', inputs=[Document()], return_results=True)
    assert docs[0].text == 'Hello World!'


def test_flatten_docarrays():
    f = Flow().add(uses=SimplExecutor)
    with f:
        docs = f.post(
            on='/index',
            inputs=[Document() for _ in range(100)],
            request_size=10,
            return_results=True,
        )
    assert isinstance(docs, DocumentArray)
    assert len(docs) == 100
    assert docs[0].text == 'Hello World!'


def my_cb(resp):
    return resp


@pytest.mark.parametrize('return_results', [True, False])
@pytest.mark.parametrize('on_done', [None, my_cb])
@pytest.mark.parametrize('on_always', [None, my_cb])
@pytest.mark.parametrize('on_error', [None, my_cb])
def test_automatically_set_returnresults(return_results, on_done, on_always, on_error):
    f = Flow().add(uses=SimplExecutor)
    with f:
        docs = f.post(
            on='/index',
            inputs=[Document() for _ in range(100)],
            request_size=10,
            return_results=return_results,
            on_done=on_done,
            on_always=on_always,
            on_error=on_error,
        )
    if return_results or (on_done is None and on_always is None):
        assert isinstance(docs, DocumentArray)
        assert len(docs) == 100
        assert docs[0].text == 'Hello World!'
    else:
        assert docs is None
