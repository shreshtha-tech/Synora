"""Regressions for document storage, retries, authorization and grounded answers."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import test_large_documents  # Inert configuration before app imports.
from fastapi import BackgroundTasks, HTTPException
from app.services import vector_store, processing, llm
from app.api.endpoints import documents, qna


class SchemaTests(unittest.TestCase):
    def test_integrated_schema_uses_pinecone_model(self):
        schema = {'schema': {'fields': {'chunk_text': {'type': 'string', 'embed': {'model': 'llama-text-embed-v2', 'dimension': 1024}}, 'title': {'type': 'string'}}}}
        vector_store._layout.cache_clear()
        try:
            with patch.object(vector_store, '_client', return_value=Mock(indexes=Mock(describe=Mock(return_value=Mock(to_dict=Mock(return_value=schema)))))):
                self.assertEqual(vector_store._layout(), {'mode': 'integrated', 'text_field': 'chunk_text'})
        finally:
            vector_store._layout.cache_clear()

    def test_old_json_string_rows_are_normalized(self):
        data = SimpleNamespace(topics='["topic"]', explanations='{"topic":"notes"}', mindTree='{"name":"root","children":[]}', predictedQuestions='[{"question":"Q","answer":"A"}]')
        fields = documents.document_fields(data)
        self.assertEqual(fields['topics'], ['topic'])
        self.assertEqual(fields['mindTree']['name'], 'root')
        self.assertIsInstance(fields['predictedQuestions'], list)


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_integrated_operations_are_document_scoped_without_gemini(self):
        data = {'chunk_text': 'Actual passage', 'document_id': 'doc-a', 'chunk_index': 0}
        match = SimpleNamespace(id='doc-a_0', score=0.9, get=data.get)
        index = Mock(documents=Mock(upsert=Mock(return_value=SimpleNamespace(upserted_count=2)), search=Mock(return_value=SimpleNamespace(matches=[match])), delete=Mock()))
        with patch.object(vector_store, '_layout', return_value={'mode': 'integrated', 'text_field': 'chunk_text'}), patch.object(vector_store, '_index', return_value=index), patch.object(vector_store.genai, 'embed_content_async', AsyncMock()) as gemini:
            await vector_store.upsert_vectors('doc-a', iter(['First passage', 'Last passage']))
            result = await vector_store.query_vectors('Question', filter={'document_id': 'doc-a'})
            await vector_store.delete_vectors('doc-a')
            gemini.assert_not_called()
        self.assertEqual(index.documents.upsert.call_args.kwargs['namespace'], 'doc-a')
        self.assertEqual(index.documents.upsert.call_args.kwargs['documents'][1]['chunk_text'], 'Last passage')
        self.assertEqual(index.documents.search.call_args.kwargs['namespace'], 'doc-a')
        self.assertEqual(index.documents.search.call_args.kwargs['score_by'][0]['type'], 'embed')
        self.assertEqual(result.matches[0].metadata['text'], 'Actual passage')
        index.documents.delete.assert_called_once_with(namespace='doc-a', delete_all=True, timeout=60)
        index.upsert.assert_not_called()
        index.query.assert_not_called()

    async def test_json_writes_use_objects_and_upsert_existing_data(self):
        db = Mock(is_connected=Mock(return_value=True), documentdata=Mock(upsert=AsyncMock(), update=AsyncMock()))
        with patch.object(processing, 'db', db):
            await processing._save_document_data('doc', ['topic'], {'topic': 'notes'})
            await processing._update_document_data('doc', {'name': 'root', 'children': []}, [{'question': 'Q', 'answer': 'A'}])
        arguments = db.documentdata.upsert.call_args.kwargs
        self.assertEqual(arguments['where'], {'documentId': 'doc'})
        self.assertEqual(arguments['data']['update']['topics'].data, ['topic'])
        self.assertEqual(db.documentdata.update.call_args.kwargs['data']['mindTree'].data['name'], 'root')

    async def test_empty_or_invalid_topics_are_failures(self):
        for response in ('[]', '{"unexpected":true}', 'broken json'):
            with patch.object(llm, 'generate_content', AsyncMock(return_value=response)):
                with self.assertRaisesRegex(ValueError, 'Invalid AI'):
                    await llm.extract_topics('source text')

    async def test_foreign_owner_cannot_retry_or_delete(self):
        db = Mock(document=Mock(find_unique=AsyncMock(return_value=SimpleNamespace(userId='other-user'))))
        with patch.object(documents, 'db', db):
            for operation in (lambda: documents.retry_document('doc', BackgroundTasks(), {'sub': 'user'}), lambda: documents.delete_document('doc', {'sub': 'user'})):
                with self.assertRaises(HTTPException) as error:
                    await operation()
                self.assertEqual(error.exception.status_code, 403)
        db.document.update_many.assert_not_called()

    async def test_busy_document_cannot_be_retried_or_deleted(self):
        document = SimpleNamespace(userId='user', status='processing', documentData=None)
        db = Mock(document=Mock(find_unique=AsyncMock(return_value=document)))
        with patch.object(documents, 'db', db):
            for operation in (lambda: documents.retry_document('doc', BackgroundTasks(), {'sub': 'user'}), lambda: documents.delete_document('doc', {'sub': 'user'})):
                with self.assertRaises(HTTPException) as error:
                    await operation()
                self.assertEqual(error.exception.status_code, 409)
        db.document.update_many.assert_not_called()

    async def test_retry_reuses_original_and_enqueues_once(self):
        document = SimpleNamespace(id='doc', userId='user', status='failed', documentData=None, name='source.pdf', fileUrl='https://storage.invalid/f/key')
        db = Mock(document=Mock(find_unique=AsyncMock(return_value=document), update_many=AsyncMock(side_effect=[1, 0])))
        redis = Mock(delete=AsyncMock(), set=AsyncMock())
        tasks = BackgroundTasks()
        with patch.object(documents, 'db', db), patch.object(documents, 'redis_client', redis):
            result = await documents.retry_document('doc', tasks, {'sub': 'user'})
            self.assertEqual(result['status'], 'processing')
            self.assertEqual(len(tasks.tasks), 1)
            self.assertEqual(tasks.tasks[0].args[1], document.fileUrl)
            with self.assertRaises(HTTPException) as error:
                await documents.retry_document('doc', BackgroundTasks(), {'sub': 'user'})
            self.assertEqual(error.exception.status_code, 409)

    async def test_qa_does_not_generate_answer_without_context(self):
        db = Mock(document=Mock(find_unique=AsyncMock(return_value=SimpleNamespace(userId='user'))), documentdata=Mock(find_unique=AsyncMock(return_value=None)))
        with patch.object(qna, 'db', db), patch.object(vector_store, 'query_vectors', AsyncMock(return_value=SimpleNamespace(matches=[]))), patch.object(qna, 'generate_content', AsyncMock()) as generate:
            with self.assertRaises(HTTPException) as error:
                await qna.ask_question(qna.QuestionRequest(documentId='doc', question='Question'), {'sub': 'user'})
            self.assertEqual(error.exception.status_code, 409)
            generate.assert_not_called()

class CompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieval_failure_does_not_discard_successful_analysis(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import asyncio
        completed = []
        async def analyze(*args):
            await asyncio.sleep(0.01)
            completed.append(True)
        def extract(source, target, content_type):
            Path(target).write_text('source text')
            return 11
        db = Mock(document=Mock(update=AsyncMock()))
        redis = Mock(set=AsyncMock(), delete=AsyncMock())
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            source.write_text('source')
            with self.assertLogs(processing.logger, level='ERROR'), patch.object(processing, 'db', db), patch.object(processing, 'redis_client', redis), patch.object(processing, 'extract_to_file', extract), patch.object(processing, '_analyze_document', analyze), patch.object(processing, 'upsert_vectors', AsyncMock(side_effect=RuntimeError('index unavailable'))):
                await processing.process_document('doc', 'url', 'key', local_path=str(source))
        self.assertEqual(completed, [True])
        self.assertEqual(db.document.update.call_args.kwargs['data']['status'], 'failed')

    async def test_delete_cleans_related_data_in_transaction_and_only_its_namespace(self):
        from unittest.mock import MagicMock
        document = SimpleNamespace(userId='user', status='ready', fileUrl='https://storage.invalid/f/owned-key')
        transaction = SimpleNamespace(
            message=Mock(delete_many=AsyncMock()), documentdata=Mock(delete_many=AsyncMock()),
            vectormetadata=Mock(delete_many=AsyncMock()), document=Mock(delete=AsyncMock()),
        )
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=transaction)
        context.__aexit__ = AsyncMock(return_value=False)
        db = Mock(document=Mock(find_unique=AsyncMock(return_value=document), update_many=AsyncMock(return_value=1)), tx=Mock(return_value=context))
        redis = Mock(delete=AsyncMock())
        from app.services.uploadthing_storage import ut_service
        with patch.object(documents, 'db', db), patch.object(documents, 'redis_client', redis), patch.object(vector_store, 'delete_vectors', AsyncMock()) as remove_vectors, patch.object(ut_service, 'delete_file', AsyncMock()) as remove_file:
            result = await documents.delete_document('owned-doc', {'sub':'user'})
        self.assertEqual(result['message'], 'Document deleted successfully')
        remove_vectors.assert_awaited_once_with('owned-doc')
        remove_file.assert_awaited_once_with('owned-key')
        transaction.message.delete_many.assert_awaited_once_with(where={'documentId':'owned-doc'})
        transaction.document.delete.assert_awaited_once_with(where={'id':'owned-doc'})


class DeleteMissingNamespaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_namespace_still_deletes_file_and_database_rows(self):
        from unittest.mock import MagicMock
        from pinecone.errors import NotFoundError
        from app.services.uploadthing_storage import ut_service
        document = SimpleNamespace(userId='user', status='failed', fileUrl='https://storage.invalid/f/failed-key')
        transaction = SimpleNamespace(
            message=Mock(delete_many=AsyncMock()), documentdata=Mock(delete_many=AsyncMock()),
            vectormetadata=Mock(delete_many=AsyncMock()), document=Mock(delete=AsyncMock()),
        )
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=transaction)
        context.__aexit__ = AsyncMock(return_value=False)
        db = Mock(document=Mock(find_unique=AsyncMock(return_value=document), update_many=AsyncMock(return_value=1)), tx=Mock(return_value=context))
        redis = Mock(delete=AsyncMock())
        index = Mock(documents=Mock(delete=Mock(side_effect=NotFoundError('Namespace not found'))))
        with patch.object(documents, 'db', db), patch.object(documents, 'redis_client', redis), patch.object(vector_store, '_layout', return_value={'mode':'integrated'}), patch.object(vector_store, '_index', return_value=index), patch.object(ut_service, 'delete_file', AsyncMock()) as remove_file:
            result = await documents.delete_document('failed-doc', {'sub':'user'})
        self.assertEqual(result['message'], 'Document deleted successfully')
        index.documents.delete.assert_called_once_with(namespace='failed-doc', delete_all=True, timeout=60)
        remove_file.assert_awaited_once_with('failed-key')
        transaction.document.delete.assert_awaited_once_with(where={'id':'failed-doc'})

    async def test_other_provider_failures_are_not_ignored(self):
        from pinecone.errors import NotFoundError, ApiError
        for failure in (NotFoundError('Index not found'), ApiError('Service unavailable', status_code=503)):
            index = Mock(documents=Mock(delete=Mock(side_effect=failure)))
            with patch.object(vector_store, '_layout', return_value={'mode':'integrated'}), patch.object(vector_store, '_index', return_value=index):
                with self.assertRaises(type(failure)) as raised:
                    await vector_store.delete_vectors('doc')
                self.assertIs(raised.exception, failure)


if __name__ == '__main__':
    unittest.main()
