"""Корпус справки платформы: пакеты, меню, каталог модулей, строки интерфейса.

Модуль только вызывает ``collect_help_corpus`` / ``visible_help_owners``.
Индексация и поиск остаются в модуле.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from src.config.paths import SYSTEM_DIR
from src.core.utils.knowledge_pack import (
    CORE_OWNER,
    load_published_pack_documents,
    visible_knowledge_owners,
)

logger = logging.getLogger('utils.help_corpus')

MENU_SOURCE = 'user_ui/site_menu.md'
MODULES_SOURCE = 'user_ui/installed_modules.md'
PLATFORM_LOCALE_SKIP = frozenset({
    'module_template',
    'node_modules',
    '__pycache__',
})
_STRING_VALUE_RE = re.compile(
    r""":\s*(?:'((?:\\.|[^'\\])*)'|"((?:\\.|[^"\\])*)")""",
)
_SKIP_VALUE_PREFIXES = ('http://', 'https://', 'data:', '#')


@dataclass(frozen=True)
class HelpCorpusState:
    """Состояние последнего сбора пакетов: sync не чистит индекс при сбое моста."""

    complete: bool = True
    failed_owners: frozenset[str] = field(default_factory=frozenset)


_last_state = HelpCorpusState()


def help_corpus_sync_state() -> HelpCorpusState:
    return _last_state


def visible_help_owners(user) -> frozenset[str] | None:
    """None — все пакеты (админ). Иначе ядро и модули из снимка прав."""
    return visible_knowledge_owners(user)


def _document(
    *,
    owner: str,
    doc_id: str,
    title: str,
    text: str,
    source: str,
    permission_key: str = '',
    revision: str = '',
) -> dict[str, Any]:
    return {
        'owner': owner,
        'id': doc_id,
        'title': title,
        'text': text,
        'source': source,
        'permission_key': permission_key,
        'revision': revision,
    }


def _unescape_js_string(value: str) -> str:
    return (
        value.replace("\\'", "'")
        .replace('\\"', '"')
        .replace('\\n', '\n')
        .replace('\\\\', '\\')
    )


def _is_useful_ui_string(value: str) -> bool:
    text = value.strip()
    if len(text) < 4:
        return False
    if any(text.startswith(prefix) for prefix in _SKIP_VALUE_PREFIXES):
        return False
    if re.fullmatch(r'#[0-9a-fA-F]{3,8}', text):
        return False
    if not re.search(r'[A-Za-zА-Яа-яЁё]', text):
        return False
    if ' ' not in text and not re.search(r'[А-Яа-яЁё]', text) and len(text) < 40:
        if re.fullmatch(r'[A-Za-z0-9_.:-]+', text):
            return False
    return True


def _extract_strings_from_js(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding='utf-8')
    except OSError as exc:
        logger.warning('Не удалось прочитать %s: %s', path, exc)
        return []
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
    raw = re.sub(r'//.*?$', '', raw, flags=re.MULTILINE)
    values: list[str] = []
    seen: set[str] = set()
    for match in _STRING_VALUE_RE.finditer(raw):
        value = _unescape_js_string(
            match.group(1) if match.group(1) is not None else match.group(2)
        )
        if not _is_useful_ui_string(value) or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _iter_locale_files(root: Path, language: str) -> Iterator[Path]:
    seen: set[str] = set()
    lang = (language or 'ru').strip() or 'ru'

    def _yield(path: Path) -> Iterator[Path]:
        if not path.is_file():
            return
        rel = path.relative_to(root).as_posix().lower()
        if any(part in rel for part in PLATFORM_LOCALE_SKIP):
            return
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        yield path

    core_dir = root / 'core' / 'client' / 'src' / 'i18n' / 'locales' / lang
    if core_dir.is_dir():
        for path in sorted(core_dir.rglob('*.js')):
            yield from _yield(path)

    from src.core.utils.module_registry import get_installed_module_names

    for name in get_installed_module_names():
        client = root / 'modules' / name / 'client'
        if not client.is_dir():
            continue
        candidates = [
            client / 'js' / 'locales.js',
            client / 'js' / f'locales/{lang}.js',
        ]
        for path in candidates:
            yield from _yield(path)
        lang_dir = client / 'js' / 'locales' / lang
        if lang_dir.is_dir():
            for path in sorted(lang_dir.rglob('*.js')):
                yield from _yield(path)
        for path in sorted(client.glob('*/js/locales.js')):
            yield from _yield(path)
        for path in sorted(client.glob(f'*/js/locales/{lang}.js')):
            yield from _yield(path)
        for path in sorted(client.glob(f'*/js/locales/{lang}/*.js')):
            yield from _yield(path)


def collect_locale_documents(
    root: Path | None = None,
    *,
    language: str = 'ru',
) -> list[dict[str, Any]]:
    """Строки клиента: ядро и установленные модули, без имён в коде."""
    root = (root or Path(SYSTEM_DIR)).resolve()
    documents: list[dict[str, Any]] = []
    for path in _iter_locale_files(root, language):
        values = _extract_strings_from_js(path)
        if not values:
            continue
        rel = path.relative_to(root).as_posix()
        has_cyrillic = any(re.search(r'[А-Яа-яЁё]', value) for value in values)
        normalized = rel.replace('\\', '/')
        if not has_cyrillic and f'/locales/{language}' not in normalized:
            continue
        lines = [
            f'# Подписи интерфейса: {rel}',
            '',
            'Тексты экранов, кнопок и подсказок системы (для ответов пользователю).',
            '',
        ]
        lines.extend(f'- {value}' for value in values)
        source = f'user_ui/{rel}'
        documents.append(_document(
            owner=CORE_OWNER,
            doc_id=f'locale:{rel}',
            title=f'Интерфейс: {path.stem}',
            text='\n'.join(lines),
            source=source,
        ))
    return documents


def collect_menu_document() -> dict[str, Any] | None:
    """Снимок бокового меню. Без фильтра по пользователю."""
    try:
        from src.core.cms.adp.menu.models import MenuItem
    except Exception as exc:
        logger.warning('Меню недоступно для корпуса: %s', exc)
        return None

    items = list(
        MenuItem.objects.filter(is_active=True)
        .order_by('order', 'name')
        .only('name', 'route_name', 'item_type', 'is_admin_only', 'parent_id', 'module_source')
    )
    if not items:
        return None

    by_parent: dict[int | None, list] = {}
    for item in items:
        by_parent.setdefault(item.parent_id, []).append(item)

    lines = [
        '# Разделы системы (боковое меню)',
        '',
        'Карта разделов, доступных пользователям в интерфейсе ERGO MS.',
        'Помоги найти, куда нажать, чтобы открыть нужную функцию.',
        '',
    ]

    def walk(parent_id, depth: int) -> None:
        for item in by_parent.get(parent_id, []):
            indent = '  ' * depth
            admin = ' (только администратор)' if item.is_admin_only else ''
            route = f', раздел «{item.route_name}»' if item.route_name else ''
            lines.append(f'{indent}- **{item.name}**{admin}{route}')
            walk(item.id, depth + 1)

    walk(None, 0)
    return _document(
        owner=CORE_OWNER,
        doc_id='site_menu',
        title='Разделы системы (меню)',
        text='\n'.join(lines),
        source=MENU_SOURCE,
    )


def collect_modules_document() -> dict[str, Any] | None:
    """Каталог установленных модулей и подписи прав."""
    try:
        from src.core.cms.adp.services.permission_catalog import get_modules_catalog
    except Exception as exc:
        logger.warning('Каталог модулей недоступен: %s', exc)
        return None

    modules = get_modules_catalog(include_disabled=False)
    if not modules:
        return None

    lines = [
        '# Возможности и модули системы',
        '',
        'Установленные модули ERGO MS и связанные с ними действия (с точки зрения пользователя).',
        'Объясняй, что можно сделать в системе, без технических деталей разработки.',
        '',
    ]
    for mod in modules:
        if mod.get('disabled'):
            continue
        label = mod.get('module_label') or mod.get('module_name')
        lines.append(f'## {label}')
        lines.append('')
        description = (mod.get('user_description') or '').strip()
        if description:
            lines.append(description)
            lines.append('')
        perms = mod.get('permissions') or {}
        if perms:
            lines.append('Доступные действия (права):')
            for key, perm_label in sorted(perms.items(), key=lambda item: str(item[1] or item[0])):
                human = (perm_label or key).strip()
                lines.append(f'- {human}')
        elif not description:
            lines.append('Модуль установлен; подробные права в каталоге не описаны.')
        lines.append('')

    return _document(
        owner=CORE_OWNER,
        doc_id='installed_modules',
        title='Модули и возможности системы',
        text='\n'.join(lines),
        source=MODULES_SOURCE,
    )


def collect_help_corpus(
    root: Path | None = None,
    *,
    language: str = 'ru',
) -> dict[str, Any]:
    """Полный корпус для индексации: пакеты + меню + каталог + локали."""
    global _last_state
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(item: dict[str, Any] | None) -> None:
        if not item:
            return
        text = str(item.get('text') or '').strip()
        source = str(item.get('source') or '').strip()
        if not text or not source or source in seen:
            return
        seen.add(source)
        documents.append(item)

    try:
        packs = load_published_pack_documents()
    except Exception:
        logger.warning('Пакеты справки недоступны', exc_info=True)
        _last_state = HelpCorpusState(complete=False)
        packs = {'documents': [], 'failed_owners': None, 'descriptors': {}}

    for item in packs.get('documents') or []:
        if not isinstance(item, dict):
            continue
        _add(item)

    failed = packs.get('failed_owners')
    if failed is None and not documents:
        _last_state = HelpCorpusState(complete=False)
    elif failed is None:
        _last_state = HelpCorpusState(complete=False)
        logger.warning('Дескрипторы пакетов справки недоступны, старый индекс сохранён')
    else:
        failed_names = frozenset(str(name) for name in failed)
        _last_state = HelpCorpusState(complete=True, failed_owners=failed_names)
        if failed_names:
            logger.warning(
                'Часть пакетов справки недоступна, старый индекс сохранён: %s',
                ', '.join(sorted(failed_names)),
            )

    _add(collect_menu_document())
    _add(collect_modules_document())
    for item in collect_locale_documents(root, language=language):
        _add(item)

    return {
        'documents': documents,
        'failed_owners': (
            None if not _last_state.complete else sorted(_last_state.failed_owners)
        ),
        'descriptors': packs.get('descriptors') or {},
    }
