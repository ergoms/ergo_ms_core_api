"""
Реализации OSAbstraction для Windows и Linux.
"""


class WindowsImpl:
    """Реализация для Windows."""

    def is_windows(self) -> bool:
        return True

    def process_executable_names(self, base_name: str) -> tuple[str, ...]:
        return (base_name, f"{base_name}.exe")

    def server_process_name(self, base_name: str) -> str:
        return f"{base_name}.exe"

    def basename_from_path(self, path_str: str) -> str:
        return path_str.replace('/', '\\').split('\\')[-1]

    def path_ends_with(self, path_str: str, component: str) -> bool:
        return (
            path_str.endswith(component)
            or path_str.endswith('/' + component)
            or path_str.endswith('\\' + component)
        )


class LinuxImpl:
    """Реализация для Linux."""

    def is_windows(self) -> bool:
        return False

    def process_executable_names(self, base_name: str) -> tuple[str, ...]:
        return (base_name,)

    def server_process_name(self, base_name: str) -> str:
        return base_name

    def basename_from_path(self, path_str: str) -> str:
        return path_str.replace('\\', '/').split('/')[-1]

    def path_ends_with(self, path_str: str, component: str) -> bool:
        return (
            path_str.endswith(component)
            or path_str.endswith('/' + component)
            or path_str.endswith('\\' + component)
        )
