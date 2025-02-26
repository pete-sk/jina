from docarray import DocumentArray
from jina import Document, Executor, Flow, requests

import pytest


class SimplExecutor(Executor):
    @requests
    def add_text(self, docs, **kwargs):
        docs[0].text = 'Hello World!'


def test_simple_routing():
    f = Flow().add(uses=SimplExecutor)
    with f:
        results = f.post(on='/index', inputs=[Document()], return_results=True)
        assert results[0].docs[0].text == 'Hello World!'


class MergeExecutor(Executor):
    @requests
    def add_text(self, docs, docs_matrix, **kwargs):
        if len(docs) == 2:
            docs[0].text = 'merged'


def test_expected_messages_routing():
    f = (
        Flow()
        .add(name='foo', uses=SimplExecutor)
        .add(name='bar', uses=MergeExecutor, needs=['foo', 'gateway'])
    )

    with f:
        results = f.post(on='/index', inputs=[Document(text='1')], return_results=True)
        # there merge executor actually does not merge despite its name
        assert len(results[0].docs) == 2
        assert results[0].docs[0].text == 'merged'


class SimpleAddExecutor(Executor):
    @requests
    def add_doc(self, docs, **kwargs):
        docs.append(Document(text=self.runtime_args.name))


def test_shards():
    f = Flow().add(uses=SimpleAddExecutor, shards=2)

    with f:
        results = f.post(on='/index', inputs=[Document(text='1')], return_results=True)
        assert len(results[0].docs) == 2


class MergeDocsExecutor(Executor):
    @requests
    def add_doc(self, docs, **kwargs):
        return docs


def test_complex_flow():
    f = (
        Flow()
        .add(name='first', uses=SimpleAddExecutor, needs=['gateway'])
        .add(name='forth', uses=SimpleAddExecutor, needs=['first'], shards=2)
        .add(
            name='second_shards_needs',
            uses=SimpleAddExecutor,
            needs=['gateway'],
            shards=2,
        )
        .add(
            name='third',
            uses=SimpleAddExecutor,
            shards=3,
            needs=['second_shards_needs'],
        )
        .add(name='merger', uses=MergeDocsExecutor, needs=['forth', 'third'])
    )

    with f:
        results = f.post(on='/index', inputs=[Document(text='1')], return_results=True)
    assert len(results[0].docs) == 6


class DynamicPollingExecutorDefaultNames(Executor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @requests(on='/index')
    def index(self, docs: DocumentArray, **kwargs):
        docs.append(Document(text='added'))
        return docs

    @requests(on='/search')
    def search(self, docs: DocumentArray, **kwargs):
        docs.append(Document(text='added'))
        return docs

    @requests(on='/custom')
    def custom(self, docs: DocumentArray, **kwargs):
        docs.append(Document(text='added'))
        return docs


@pytest.mark.parametrize('polling', ['any', 'all'])
def test_flow_default_polling_endpoints(polling):
    f = Flow().add(uses=DynamicPollingExecutorDefaultNames, shards=2, polling=polling)

    with f:
        results_index = f.post(
            on='/index', inputs=[Document(text='1')], return_results=True
        )
        results_search = f.post(
            on='/search', inputs=[Document(text='1')], return_results=True
        )
        results_custom = f.post(
            on='/custom', inputs=[Document(text='1')], return_results=True
        )
    assert len(results_index[0].docs) == 2
    assert len(results_search[0].docs) == 3
    assert len(results_custom[0].docs) == 3 if polling == 'all' else 2


@pytest.mark.parametrize('polling', ['any', 'all'])
def test_flow_default_polling_endpoints(polling):
    custom_polling_config = {'/custom': 'ALL', '/search': 'ANY', '*': polling}
    f = Flow().add(
        uses=DynamicPollingExecutorDefaultNames,
        shards=2,
        polling=custom_polling_config,
    )

    with f:
        results_index = f.post(
            on='/index', inputs=[Document(text='1')], return_results=True
        )
        results_search = f.post(
            on='/search', inputs=[Document(text='1')], return_results=True
        )
        results_custom = f.post(
            on='/custom', inputs=[Document(text='1')], return_results=True
        )
    assert len(results_index[0].docs) == 2
    assert len(results_search[0].docs) == 2
    assert len(results_custom[0].docs) == 3
