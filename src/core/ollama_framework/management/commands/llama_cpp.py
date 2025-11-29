"""
Django команда для управления и тестирования llama.cpp
"""

import os
import time
from typing import Optional

import httpx

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Управление и тестирование llama.cpp сервера'
    
    # Цвета для консоли
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--info',
            action='store_true',
            help='Показать информацию о сервере llama.cpp'
        )
        parser.add_argument(
            '--health',
            action='store_true',
            help='Проверить статус сервера'
        )
        parser.add_argument(
            '--test',
            type=str,
            nargs='?',
            const='Привет! Расскажи о себе кратко.',
            help='Тестовый запрос к серверу (можно указать текст)'
        )
        parser.add_argument(
            '--prompt', '-p',
            type=str,
            help='Отправить промпт к серверу'
        )
        parser.add_argument(
            '--max-tokens', '-n',
            type=int,
            default=256,
            help='Максимальное количество токенов (по умолчанию: 256)'
        )
        parser.add_argument(
            '--temperature', '-t',
            type=float,
            default=0.7,
            help='Температура генерации (по умолчанию: 0.7)'
        )
        parser.add_argument(
            '--stream', '-s',
            action='store_true',
            help='Использовать streaming режим'
        )
        parser.add_argument(
            '--url',
            type=str,
            default=os.getenv('LLAMA_CPP_BASE_URL', 'http://localhost:8080'),
            help='URL llama.cpp сервера'
        )
    
    def handle(self, *args, **options):
        base_url = options['url'].rstrip('/')
        
        if options['info']:
            self._show_info(base_url)
        elif options['health']:
            self._check_health(base_url)
        elif options['test']:
            self._test_completion(
                base_url,
                options['test'],
                options['max_tokens'],
                options['temperature'],
                options['stream']
            )
        elif options['prompt']:
            self._test_completion(
                base_url,
                options['prompt'],
                options['max_tokens'],
                options['temperature'],
                options['stream']
            )
        else:
            # По умолчанию показываем info
            self._show_info(base_url)
    
    def _check_connection(self, base_url: str) -> bool:
        """Проверяет соединение с сервером"""
        try:
            response = httpx.get(f"{base_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False
    
    def _show_info(self, base_url: str):
        """Показывает информацию о сервере"""
        self.stdout.write(f'\n{self.BOLD}=== llama.cpp Server Info ==={self.RESET}')
        self.stdout.write(f'{self.DIM}URL: {base_url}{self.RESET}\n')
        
        if not self._check_connection(base_url):
            self.stdout.write(self.style.ERROR(
                f'{self.RED}Сервер недоступен!{self.RESET}\n'
                'Запустите сервер командой: ergoms start-llama-cpp --model <path>'
            ))
            return
        
        try:
            # Получаем props
            props_response = httpx.get(f"{base_url}/props", timeout=10.0)
            if props_response.status_code == 200:
                props = props_response.json()
                self._print_props(props)
            
            # Получаем health
            health_response = httpx.get(f"{base_url}/health", timeout=5.0)
            if health_response.status_code == 200:
                health = health_response.json()
                self._print_health(health)
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка: {e}'))
    
    def _print_props(self, props: dict):
        """Выводит свойства модели"""
        gen_settings = props.get('default_generation_settings', {})
        
        ctx_size = gen_settings.get('n_ctx', 'N/A')
        n_predict = gen_settings.get('n_predict', 'N/A')
        
        self.stdout.write(f'{self.CYAN}Model Configuration:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Context Size:{self.RESET}      {ctx_size} tokens')
        self.stdout.write(f'  {self.GREEN}Max Predict:{self.RESET}       {n_predict} tokens')
        
        # Параметры генерации
        temp = gen_settings.get('temperature', 'N/A')
        top_k = gen_settings.get('top_k', 'N/A')
        top_p = gen_settings.get('top_p', 'N/A')
        repeat_penalty = gen_settings.get('repeat_penalty', 'N/A')
        
        self.stdout.write(f'\n{self.CYAN}Generation Defaults:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Temperature:{self.RESET}       {temp}')
        self.stdout.write(f'  {self.GREEN}Top-K:{self.RESET}             {top_k}')
        self.stdout.write(f'  {self.GREEN}Top-P:{self.RESET}             {top_p}')
        self.stdout.write(f'  {self.GREEN}Repeat Penalty:{self.RESET}    {repeat_penalty}')
        
        # Слоты
        total_slots = props.get('total_slots', 1)
        self.stdout.write(f'\n{self.CYAN}Server Configuration:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Parallel Slots:{self.RESET}    {total_slots}')
    
    def _print_health(self, health: dict):
        """Выводит статус здоровья"""
        status = health.get('status', 'unknown')
        slots_idle = health.get('slots_idle', 0)
        slots_processing = health.get('slots_processing', 0)
        
        status_color = self.GREEN if status == 'ok' else self.YELLOW
        
        self.stdout.write(f'\n{self.CYAN}Server Status:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Status:{self.RESET}            {status_color}{status}{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Slots Idle:{self.RESET}        {slots_idle}')
        self.stdout.write(f'  {self.GREEN}Slots Processing:{self.RESET}  {slots_processing}')
    
    def _check_health(self, base_url: str):
        """Проверяет статус сервера"""
        self.stdout.write(f'Проверка {base_url}/health...')
        
        try:
            start = time.time()
            response = httpx.get(f"{base_url}/health", timeout=5.0)
            latency = (time.time() - start) * 1000
            
            if response.status_code == 200:
                health = response.json()
                status = health.get('status', 'unknown')
                
                self.stdout.write(self.style.SUCCESS(
                    f'{self.GREEN}OK{self.RESET} - Status: {status}, Latency: {latency:.1f}ms'
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f'{self.RED}FAIL{self.RESET} - HTTP {response.status_code}'
                ))
        except httpx.ConnectError:
            self.stdout.write(self.style.ERROR(
                f'{self.RED}FAIL{self.RESET} - Не удалось подключиться'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'{self.RED}FAIL{self.RESET} - {e}'))
    
    def _test_completion(self, base_url: str, prompt: str, max_tokens: int, temperature: float, stream: bool):
        """Тестовый запрос к серверу с выводом статистики"""
        if not self._check_connection(base_url):
            self.stdout.write(self.style.ERROR(
                'Сервер недоступен! Запустите: ergoms start-llama-cpp --model <path>'
            ))
            return
        
        self.stdout.write(f'\n{self.BOLD}=== llama.cpp Test Request ==={self.RESET}')
        self.stdout.write(f'{self.DIM}URL: {base_url}{self.RESET}')
        self.stdout.write(f'{self.DIM}Max Tokens: {max_tokens}, Temperature: {temperature}{self.RESET}')
        self.stdout.write(f'{self.DIM}Stream: {stream}{self.RESET}')
        
        self.stdout.write(f'\n{self.CYAN}Prompt:{self.RESET}')
        self.stdout.write(f'  {prompt}')
        
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "stream": stream,
            "stop": ["</s>", "<|end|>", "<|im_end|>"],
        }
        
        self.stdout.write(f'\n{self.CYAN}Response:{self.RESET}')
        
        start_time = time.time()
        
        try:
            if stream:
                self._stream_completion(base_url, payload, start_time)
            else:
                self._sync_completion(base_url, payload, start_time)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\nОшибка: {e}'))
    
    def _sync_completion(self, base_url: str, payload: dict, start_time: float):
        """Синхронный запрос"""
        response = httpx.post(
            f"{base_url}/completion",
            json=payload,
            timeout=300.0
        )
        response.raise_for_status()
        data = response.json()
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Выводим ответ
        content = data.get("content", "")
        self.stdout.write(f'  {content}')
        
        # Выводим статистику
        self._print_stats(data, duration_ms)
    
    def _stream_completion(self, base_url: str, payload: dict, start_time: float):
        """Streaming запрос"""
        final_data = {}
        
        with httpx.stream("POST", f"{base_url}/completion", json=payload, timeout=300.0) as response:
            response.raise_for_status()
            
            self.stdout.write('  ', ending='')
            
            for line in response.iter_lines():
                if not line:
                    continue
                
                if line.startswith("data: "):
                    line = line[6:]
                
                if line == "[DONE]":
                    break
                
                try:
                    import json
                    data = json.loads(line)
                    
                    text = data.get("content", "")
                    if text:
                        self.stdout.write(text, ending='')
                        self.stdout.flush()
                    
                    if data.get("stop") or data.get("timings"):
                        final_data = data
                    
                    if data.get("stop"):
                        break
                except:
                    continue
        
        self.stdout.write('')  # Новая строка после ответа
        
        duration_ms = (time.time() - start_time) * 1000
        self._print_stats(final_data, duration_ms)
    
    def _print_stats(self, data: dict, duration_ms: float):
        """Выводит статистику генерации"""
        timings = data.get("timings", {})
        
        # Токены
        prompt_tokens = timings.get("prompt_n", data.get("tokens_evaluated", 0))
        generated_tokens = timings.get("predicted_n", data.get("tokens_predicted", 0))
        total_tokens = prompt_tokens + generated_tokens
        
        # Скорость
        tokens_per_sec = timings.get("predicted_per_second", 0)
        if tokens_per_sec == 0 and generated_tokens > 0 and duration_ms > 0:
            tokens_per_sec = generated_tokens / (duration_ms / 1000)
        
        prompt_per_sec = timings.get("prompt_per_second", 0)
        
        # Время
        prompt_ms = timings.get("prompt_ms", 0)
        predicted_ms = timings.get("predicted_ms", 0)
        
        # Память (если доступно)
        truncated = data.get("truncated", False)
        stopped_eos = data.get("stopped_eos", False)
        stopped_limit = data.get("stopped_limit", False)
        
        self.stdout.write(f'\n{self.BOLD}=== Generation Statistics ==={self.RESET}')
        
        self.stdout.write(f'\n{self.CYAN}Tokens:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Prompt Tokens:{self.RESET}     {prompt_tokens}')
        self.stdout.write(f'  {self.GREEN}Generated:{self.RESET}         {generated_tokens}')
        self.stdout.write(f'  {self.GREEN}Total:{self.RESET}             {total_tokens}')
        
        self.stdout.write(f'\n{self.CYAN}Speed:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Prompt:{self.RESET}            {prompt_per_sec:.2f} tok/s')
        self.stdout.write(f'  {self.GREEN}Generation:{self.RESET}        {self.MAGENTA}{tokens_per_sec:.2f} tok/s{self.RESET}')
        
        self.stdout.write(f'\n{self.CYAN}Time:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Prompt Eval:{self.RESET}       {prompt_ms:.1f} ms')
        self.stdout.write(f'  {self.GREEN}Generation:{self.RESET}        {predicted_ms:.1f} ms')
        self.stdout.write(f'  {self.GREEN}Total:{self.RESET}             {duration_ms:.1f} ms ({duration_ms/1000:.2f}s)')
        
        self.stdout.write(f'\n{self.CYAN}Status:{self.RESET}')
        self.stdout.write(f'  {self.GREEN}Truncated:{self.RESET}         {truncated}')
        self.stdout.write(f'  {self.GREEN}Stopped EOS:{self.RESET}       {stopped_eos}')
        self.stdout.write(f'  {self.GREEN}Stopped Limit:{self.RESET}     {stopped_limit}')

