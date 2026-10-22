"""Local regressions: no cloud credentials or provider calls are used."""
import asyncio
import io
import os
import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch
from zipfile import ZipFile

import pymupdf
from starlette.datastructures import UploadFile

# Supply inert configuration so the suite also runs on a clean checkout.
for key, value in {
    'DATABASE_URL': 'postgresql://test:test@localhost:5432/test',
    'GEMINI_API_KEY': 'test-only', 'PINECONE_API_KEY': 'test-only',
    'PINECONE_ENV': 'test', 'REDIS_URL': 'redis://localhost:6379',
    'GOOGLE_CLIENT_ID': 'test-only',
    'UPLOADTHING_TOKEN': base64.b64encode(json.dumps({'apiKey': 'test-only', 'appId': 'test', 'regions': ['sea1']}).encode()).decode(),
}.items():
    os.environ[key] = value

from app.services.document_text import DOCX_TYPE, extract_to_file, text_chunks
from app.services.parallel import together
from app.services import llm, vector_store, processing
from app.api.endpoints.upload import _spool_upload


class ExtractionTests(unittest.TestCase):
    def test_all_pdf_pages_survive_extraction_and_chunking(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'large.pdf', Path(directory) / 'text.txt'
            with pymupdf.open() as document:
                for number in range(25):
                    page = document.new_page()
                    page.insert_text((40, 40), f'PAGE_{number:03d} ' + 'study material ' * 25)
                document.save(source)
            extract_to_file(str(source), str(target), 'application/pdf')
            text = target.read_text()
            self.assertIn('PAGE_024', text)
            for number in range(25):
                self.assertIn(f'PAGE_{number:03d}', text)
            chunks = list(text_chunks(target, size=400, overlap=50))
            self.assertEqual(text, chunks[0] + ''.join(chunk[50:] for chunk in chunks[1:]))

    def test_docx_body_and_table_text(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'test.docx', Path(directory) / 'text.txt'
            with ZipFile(source, 'w') as archive:
                archive.writestr('word/document.xml', '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>First concept</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Final table concept</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>''')
            extract_to_file(str(source), str(target), DOCX_TYPE)
            self.assertIn('Final table concept', target.read_text())

    def test_image_only_pdf_is_explicit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'blank.pdf', Path(directory) / 'text.txt'
            with pymupdf.open() as document:
                document.new_page()
                document.save(source)
            with self.assertRaisesRegex(ValueError, 'OCR'):
                extract_to_file(str(source), str(target), 'application/pdf')


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        layout = patch.object(vector_store, '_layout', return_value={'mode': 'vectors', 'dimension': 768})
        layout.start()
        self.addCleanup(layout.stop)
    async def test_upload_endpoint_preserves_original_pdf_and_hands_off_local_file(self):
        import httpx
        from main import app
        from app.core.security import get_current_user
        from app.api.endpoints import upload

        with pymupdf.open() as document:
            for i in range(15):
                document.new_page().insert_text((40, 40), f'PAGE_{i}')
            original = document.tobytes()
        uploaded, processed = [], []

        async def store(source, filename, content_type, file_size):
            uploaded.append(source.read())
            self.assertEqual(file_size, len(original))
            return {'url': 'https://storage.invalid/file', 'key': 'test-key'}

        async def process(document_id, url, key, content_type, path):
            processed.append(Path(path).read_bytes())
            Path(path).unlink()

        app.dependency_overrides[get_current_user] = lambda: {'sub': 'test-user'}
        try:
            with patch.object(upload.ut_service, 'upload_file', store), patch.object(upload, 'process_document', process), patch.object(upload, 'db', Mock(document=Mock(create=AsyncMock(return_value=Mock(id='doc-id'))))):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                    response = await client.post('/api/v1/upload/', files={'file': ('all-pages.pdf', original, 'application/pdf')})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(uploaded, [original])
            self.assertEqual(processed, [original])
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    async def test_large_context_reads_final_section_and_reduces_recursively(self):
        seen = []
        active = peak = 0

        async def summarize(text):
            nonlocal active, peak
            seen.append(text)
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.001)
            active -= 1
            return ('LAST_SECTION ' if 'LAST_SECTION' in text else '') + 'summary ' * 30

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'text.txt'
            path.write_text('first section ' * 5000 + 'LAST_SECTION')
            with patch.object(llm.settings, 'ANALYSIS_CONTEXT_CHARS', 4000), patch.object(llm, '_summarize_section', summarize):
                result = await llm.analysis_context(str(path))
            self.assertLessEqual(len(result), 4000)
            self.assertIn('LAST_SECTION', result)
            self.assertTrue(any('LAST_SECTION' in text for text in seen))
            self.assertGreater(peak, 1)
            self.assertLessEqual(peak, llm.settings.LLM_CONCURRENCY)

    async def test_small_context_avoids_summary_api(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'text.txt'
            path.write_text('small document')
            with patch.object(llm, '_summarize_section', AsyncMock()) as summarize:
                self.assertEqual(await llm.analysis_context(str(path)), 'small document')
                summarize.assert_not_called()

    async def test_embedding_batches_are_bounded_complete_and_nonblocking(self):
        active = peak = produced = 0
        batches, vectors, thread_ids = [], [], []
        main_thread = threading.get_ident()

        async def embed(**kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            batches.append(kwargs['content'])
            self.assertLessEqual(produced - len(vectors), 32)
            await asyncio.sleep(0.001)
            active -= 1
            return {'embedding': [[1.0] * 768 for _ in kwargs['content']]}

        def upsert(*, vectors):
            thread_ids.append(threading.get_ident())
            captured.extend(vectors)

        def chunks():
            nonlocal produced
            for i in range(101):
                produced += 1
                yield f'chunk {i}'

        captured = vectors
        with patch.object(vector_store.genai, 'embed_content_async', embed), patch.object(vector_store, '_index', return_value=Mock(upsert=upsert)):
            await vector_store.upsert_vectors('doc', chunks())
        self.assertEqual(len(batches), 7)  # Previously 101 sequential requests.
        self.assertTrue(all(len(batch) <= 16 for batch in batches))
        self.assertEqual({v['id'] for v in vectors}, {f'doc_{i}' for i in range(101)})
        self.assertEqual({v['metadata']['text'] for v in vectors}, {f'chunk {i}' for i in range(101)})
        self.assertGreater(peak, 1)
        self.assertLessEqual(peak, 2)
        self.assertTrue(all(i != main_thread for i in thread_ids))

    async def test_failure_cancels_sibling_work(self):
        cancelled = asyncio.Event()

        async def fail():
            await asyncio.sleep(0.001)
            raise RuntimeError('provider unavailable')

        async def sibling():
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()

        with self.assertRaisesRegex(RuntimeError, 'provider unavailable'):
            await together(fail(), sibling())
        self.assertTrue(cancelled.is_set())

    async def test_upload_size_limit_and_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = str(Path(directory) / 'upload')
            with self.assertRaisesRegex(Exception, '413'):
                await _spool_upload(UploadFile(io.BytesIO(b'abcde')), destination, 4)
            with self.assertRaisesRegex(Exception, '400'):
                await _spool_upload(UploadFile(io.BytesIO(b'')), destination, 4)

    async def test_processing_reuses_local_source_and_cleans_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.pdf'
            source.write_bytes(b'local source')
            fake_db = Mock(document=Mock(update=AsyncMock()))
            fake_redis = Mock(set=AsyncMock(), delete=AsyncMock())
            with self.assertLogs(processing.logger, level='ERROR'), patch.object(processing, 'db', fake_db), patch.object(processing, 'redis_client', fake_redis), patch.object(processing, 'extract_to_file', side_effect=ValueError('bad file')), patch.object(processing.ut_service, 'download_to_file', AsyncMock()) as download:
                await processing.process_document('doc', 'url', 'key', local_path=str(source))
                download.assert_not_called()
            self.assertFalse(source.exists())
            self.assertEqual(fake_db.document.update.call_args.kwargs['data']['status'], 'failed')

    async def test_full_processing_publishes_topics_before_indexing_completes(self):
        embedding_started, topics_published = asyncio.Event(), asyncio.Event()
        states, indexed = [], []

        async def update(**kwargs):
            state = kwargs['data']['status']
            states.append(state)
            if state == 'topics_ready':
                topics_published.set()

        async def context(path):
            await asyncio.wait_for(embedding_started.wait(), timeout=2)
            return Path(path).read_text()

        async def embed(document_id, chunks):
            indexed.extend(chunks)
            embedding_started.set()
            await asyncio.wait_for(topics_published.wait(), timeout=2)

        fake_db = Mock(document=Mock(update=AsyncMock(side_effect=update)), documentdata=Mock(upsert=AsyncMock(), update=AsyncMock()))
        fake_redis = Mock(set=AsyncMock(), delete=AsyncMock())
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.pdf'
            with pymupdf.open() as document:
                for i in range(12):
                    document.new_page().insert_text((40, 40), f'CONCEPT_{i}')
                document.save(source)
            with patch.object(processing, 'db', fake_db), patch.object(processing, 'redis_client', fake_redis), patch.object(processing, 'analysis_context', context), patch.object(processing, 'upsert_vectors', embed), patch.object(processing, 'extract_topics', AsyncMock(return_value=['concept'])), patch.object(processing, 'generate_explanations', AsyncMock(return_value={'concept': 'explanation'})), patch.object(processing, 'generate_mind_tree', AsyncMock(return_value={'name': 'root', 'children': []})), patch.object(processing, 'generate_predicted_questions', AsyncMock(return_value=[])):
                await processing.process_document('doc', 'url', 'key', local_path=str(source))
            self.assertEqual(states, ['processing', 'topics_ready', 'ready'])
            self.assertIn('CONCEPT_11', ''.join(indexed))
            self.assertFalse(source.exists())


if __name__ == '__main__':
    unittest.main()
