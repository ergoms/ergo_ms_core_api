"""Selected lock groups remain authoritative during fast paths and module pip."""
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commands.install import InstallCommand


class OptionalGroupInstallTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[3] / 'virtual_env/cache/tmp'
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix='optional_groups_', dir=base)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'pyproject.toml').write_text('[tool.poetry.dependencies]\npython=">=3.12,<3.13"\n')
        (self.root / 'poetry.lock').write_text('''[[package]]
name = "core-package"
version = "1.0"
groups = ["main"]
[[package]]
name = "statsmodels"
version = "0.14.6"
groups = ["analytics"]
''')
        self.command = InstallCommand()

    def run_with(self, installed):
        with patch('commands.install._auto_extra_groups', return_value=frozenset({'analytics'})), \
                patch.object(self.command, '_find_project_root', return_value=self.root), \
                patch.object(self.command, '_scan_module_configs', return_value=[]), \
                patch.object(self.command, '_get_installed_versions', return_value=installed), \
                patch.object(self.command, '_python_deps_stamp_matches', return_value=True), \
                patch.object(self.command, '_install_core', return_value=17) as install:
            result = self.command.run()
        return result, install

    def test_matching_stamp_does_not_hide_a_deleted_optional_package(self):
        code, install = self.run_with({'core-package': '1.0'})
        self.assertEqual(code, 17)
        install.assert_called_once_with(self.root, extra_groups=frozenset({'analytics'}))

    def test_matching_stamp_does_not_hide_optional_version_drift(self):
        code, install = self.run_with({'core-package': '1.0', 'statsmodels': '0.14.5'})
        self.assertEqual(code, 17)
        install.assert_called_once()

    def test_ready_optional_group_keeps_repeated_install_fast(self):
        for _ in range(2):
            code, install = self.run_with({'core-package': '1.0', 'statsmodels': '0.14.6'})
            self.assertEqual(code, 0)
            install.assert_not_called()

    def test_module_pip_constraints_cover_the_selected_optional_group(self):
        constraints = []
        def run(command, **kwargs):
            self.assertIn('-c', command)
            constraints.append(Path(command[command.index('-c') + 1]).read_text())
            return SimpleNamespace(returncode=0)
        with patch.object(self.command, '_collect_all_sources', return_value=[]), \
                patch('commands.install.subprocess.run', side_effect=run):
            self.assertEqual(self.command._install_module_packages(self.root, {}, {'extension': '>=1.0'},
                             extra_groups=frozenset({'analytics'})), 0)
        self.assertIn('statsmodels==0.14.6', constraints[0])
        self.assertIn('core-package==1.0', constraints[0])

    def test_sync_repairs_selected_optional_versions(self):
        with patch.object(self.command, '_get_installed_versions', return_value={'core-package': '1.0', 'statsmodels': '0.14.5'}), \
                patch('commands.install.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(self.command._sync_main_lock_versions(self.root, extra_groups=frozenset({'analytics'})), 0)
        self.assertEqual(run.call_args.args[0][-1], 'statsmodels==0.14.6')

    def test_main_only_sync_does_not_install_an_unselected_group(self):
        with patch.object(self.command, '_get_installed_versions', return_value={'core-package': '1.0'}), \
                patch('commands.install.subprocess.run') as run:
            self.assertEqual(self.command._sync_main_lock_versions(self.root), 0)
        run.assert_not_called()
