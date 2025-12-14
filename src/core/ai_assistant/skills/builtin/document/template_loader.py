"""
Загрузчик MD шаблонов документов.
"""
import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class TemplateVariable:
    """Переменная шаблона."""
    name: str
    description: str = ""
    required: bool = False
    default: Optional[str] = None


@dataclass
class DocumentTemplate:
    """Шаблон документа."""
    id: str
    name: str
    description: str
    formats: List[str]
    variables: List[TemplateVariable]
    content: str
    
    def get_variables_schema(self) -> Dict[str, Any]:
        """Возвращает JSON Schema для переменных шаблона."""
        properties = {}
        required = []
        
        for var in self.variables:
            properties[var.name] = {
                "type": "string",
                "description": var.description or var.name,
            }
            if var.required:
                required.append(var.name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
    
    def render(self, variables: Dict[str, str]) -> str:
        """Рендерит шаблон с переменными."""
        result = self.content
        
        # Добавляем дату по умолчанию
        if 'date' not in variables:
            variables['date'] = datetime.now().strftime('%d.%m.%Y')
        
        # Заполняем значения по умолчанию
        for var in self.variables:
            if var.name not in variables and var.default:
                variables[var.name] = var.default
        
        # Заменяем переменные
        for name, value in variables.items():
            result = result.replace(f'{{{{{name}}}}}', str(value) if value else '')
        
        # Удаляем незаполненные переменные
        result = re.sub(r'\{\{[^}]+\}\}', '', result)
        
        return result.strip()


class TemplateLoader:
    """Загрузчик шаблонов из MD файлов."""
    
    def __init__(self, templates_dir: Optional[Path] = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent / 'templates'
        self.templates_dir = templates_dir
        self._templates: Dict[str, DocumentTemplate] = {}
        self._loaded = False
    
    def load_templates(self) -> None:
        """Загружает все шаблоны из директории."""
        if self._loaded:
            return
        
        if not self.templates_dir.exists():
            self.templates_dir.mkdir(parents=True, exist_ok=True)
            return
        
        for md_file in self.templates_dir.glob('*.md'):
            if md_file.name == 'README.md':
                continue
            
            try:
                template = self._parse_template(md_file)
                if template:
                    self._templates[template.id] = template
            except Exception as e:
                print(f"Ошибка загрузки шаблона {md_file}: {e}")
        
        self._loaded = True
    
    def _parse_template(self, file_path: Path) -> Optional[DocumentTemplate]:
        """Парсит MD файл шаблона."""
        content = file_path.read_text(encoding='utf-8')
        
        # Парсим YAML frontmatter
        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
        
        if not frontmatter_match:
            # Шаблон без метаданных - используем имя файла
            return DocumentTemplate(
                id=file_path.stem,
                name=file_path.stem.replace('_', ' ').title(),
                description="",
                formats=['docx', 'pdf'],
                variables=[],
                content=content,
            )
        
        yaml_content = frontmatter_match.group(1)
        template_content = frontmatter_match.group(2).strip()
        
        try:
            metadata = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError:
            metadata = {}
        
        # Парсим переменные
        variables = []
        for var_data in metadata.get('variables', []):
            if isinstance(var_data, dict):
                variables.append(TemplateVariable(
                    name=var_data.get('name', ''),
                    description=var_data.get('description', ''),
                    required=var_data.get('required', False),
                    default=var_data.get('default'),
                ))
            elif isinstance(var_data, str):
                variables.append(TemplateVariable(name=var_data))
        
        return DocumentTemplate(
            id=file_path.stem,
            name=metadata.get('name', file_path.stem.replace('_', ' ').title()),
            description=metadata.get('description', ''),
            formats=metadata.get('format', ['docx', 'pdf']),
            variables=variables,
            content=template_content,
        )
    
    def get_template(self, template_id: str) -> Optional[DocumentTemplate]:
        """Возвращает шаблон по ID."""
        self.load_templates()
        return self._templates.get(template_id)
    
    def get_all_templates(self) -> List[DocumentTemplate]:
        """Возвращает все шаблоны."""
        self.load_templates()
        return list(self._templates.values())
    
    def get_templates_description(self) -> str:
        """Возвращает описание шаблонов для LLM."""
        self.load_templates()
        
        if not self._templates:
            return "Нет доступных шаблонов."
        
        lines = ["Доступные шаблоны:"]
        for template in self._templates.values():
            vars_str = ", ".join(v.name for v in template.variables if v.required)
            lines.append(f"- {template.id}: {template.name} ({template.description})")
            if vars_str:
                lines.append(f"  Обязательные поля: {vars_str}")
        
        return "\n".join(lines)


# Глобальный экземпляр загрузчика
_template_loader: Optional[TemplateLoader] = None


def get_template_loader() -> TemplateLoader:
    """Возвращает глобальный экземпляр загрузчика шаблонов."""
    global _template_loader
    if _template_loader is None:
        _template_loader = TemplateLoader()
    return _template_loader

