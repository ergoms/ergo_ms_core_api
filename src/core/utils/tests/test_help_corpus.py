from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from src.core.utils.help_corpus import (
    MENU_SOURCE,
    MODULES_SOURCE,
    collect_help_corpus,
    collect_locale_documents,
    collect_menu_document,
    collect_modules_document,
    visible_help_owners,
)
from src.core.utils.knowledge_pack import CORE_OWNER


class HelpCorpusTests(SimpleTestCase):
    def test_visible_owners_delegates(self):
        with patch(
            'src.core.utils.help_corpus.visible_knowledge_owners',
            return_value=frozenset({CORE_OWNER, 'sample_mod'}),
        ) as mocked:
            result = visible_help_owners(SimpleNamespace(pk=1))
        self.assertEqual(result, frozenset({CORE_OWNER, 'sample_mod'}))
        mocked.assert_called_once()

    def test_menu_document_walks_tree(self):
        root = SimpleNamespace(
            id=1,
            parent_id=None,
            name='Кабинет',
            route_name='Home',
            is_admin_only=False,
        )
        child = SimpleNamespace(
            id=2,
            parent_id=1,
            name='Права',
            route_name='Roles',
            is_admin_only=True,
        )

        class _Query:
            def filter(self, **_):
                return self

            def order_by(self, *_):
                return self

            def only(self, *_):
                return [root, child]

        fake_model = SimpleNamespace(objects=_Query())
        with patch('src.core.cms.adp.menu.models.MenuItem', fake_model):
            document = collect_menu_document()

        self.assertIsNotNone(document)
        self.assertEqual(document['source'], MENU_SOURCE)
        self.assertIn('**Кабинет**', document['text'])
        self.assertIn('только администратор', document['text'])
        self.assertIn('раздел «Roles»', document['text'])

    def test_modules_document_uses_catalog(self):
        catalog = [
            {
                'module_name': 'sample_mod',
                'module_label': 'Пример',
                'user_description': 'Делает пример.',
                'permissions': {'sample_view': 'Смотреть пример'},
                'disabled': False,
            },
        ]
        with patch(
            'src.core.cms.adp.services.permission_catalog.get_modules_catalog',
            return_value=catalog,
        ):
            document = collect_modules_document()

        self.assertIsNotNone(document)
        self.assertEqual(document['source'], MODULES_SOURCE)
        self.assertIn('## Пример', document['text'])
        self.assertIn('Смотреть пример', document['text'])

    def test_locale_documents_scan_core_and_modules(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            core_locale = (
                root / 'core' / 'client' / 'src' / 'i18n' / 'locales' / 'ru' / 'common.js'
            )
            core_locale.parent.mkdir(parents=True)
            core_locale.write_text(
                "export default { save: 'Сохранить черновик' }\n",
                encoding='utf-8',
            )
            module_locale = (
                root / 'modules' / 'sample_mod' / 'client' / 'js' / 'locales.js'
            )
            module_locale.parent.mkdir(parents=True)
            module_locale.write_text(
                "export default { ru: { open: 'Открыть карточку' } }\n",
                encoding='utf-8',
            )
            with patch(
                'src.core.utils.module_registry.get_installed_module_names',
                return_value=['sample_mod'],
            ):
                documents = collect_locale_documents(root, language='ru')

        sources = {item['source'] for item in documents}
        self.assertTrue(any(item['text'].find('Сохранить черновик') >= 0 for item in documents))
        self.assertTrue(any(item['text'].find('Открыть карточку') >= 0 for item in documents))
        self.assertTrue(any(source.startswith('user_ui/') for source in sources))

    def test_collect_help_corpus_merges_sources(self):
        pack_doc = {
            'owner': 'sample_mod',
            'id': 'overview',
            'title': 'Обзор',
            'text': 'Текст пакета',
            'source': 'knowledge/sample_mod/overview',
            'permission_key': '',
            'revision': 'abc',
        }
        with patch(
            'src.core.utils.help_corpus.load_published_pack_documents',
            return_value={
                'documents': [pack_doc],
                'failed_owners': [],
                'descriptors': {'sample_mod': {'owner': 'sample_mod'}},
            },
        ), patch(
            'src.core.utils.help_corpus.collect_menu_document',
            return_value={
                'owner': CORE_OWNER,
                'id': 'site_menu',
                'title': 'Меню',
                'text': 'Пункты',
                'source': MENU_SOURCE,
            },
        ), patch(
            'src.core.utils.help_corpus.collect_modules_document',
            return_value=None,
        ), patch(
            'src.core.utils.help_corpus.collect_locale_documents',
            return_value=[],
        ):
            result = collect_help_corpus()

        sources = [item['source'] for item in result['documents']]
        self.assertEqual(sources, ['knowledge/sample_mod/overview', MENU_SOURCE])
        self.assertEqual(result['failed_owners'], [])
        self.assertEqual(result['descriptors']['sample_mod']['owner'], 'sample_mod')
