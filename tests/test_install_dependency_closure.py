"""Dependency pruning keeps only runtime dependencies and requested extras."""
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commands.install import InstallCommand  # noqa: E402


class DependencyClosureTests(unittest.TestCase):
    def setUp(self):
        self.command = InstallCommand()
        self.requirements = {
            'torch': ['cuda-toolkit[cudart,nvrtc]>=13', 'base'],
            'cuda-toolkit': [
                'nvidia-cuda-runtime; extra == "cudart"',
                'nvidia-cuda-nvrtc; extra == "nvrtc" and python_version >= "3.0"',
                'debugger; extra == "debug"',
                'ancient; extra == "cudart" and python_version < "1.0"',
            ],
            'nvidia-cuda-runtime': [], 'nvidia-cuda-nvrtc': [], 'base': [],
        }

    def distribution(self, name):
        if name not in self.requirements:
            raise PackageNotFoundError(name)
        return SimpleNamespace(requires=self.requirements[name])

    def test_transitive_extras_are_kept_but_unrequested_and_inactive_extras_are_not(self):
        with patch('importlib.metadata.distribution', side_effect=self.distribution):
            actual = self.command._dependency_closure({'torch'})
        self.assertEqual(actual, set(self.requirements))

    def test_extras_are_revisited_after_the_base_distribution_was_processed(self):
        self.requirements.update({'entry': ['requester', 'shared'],
                                  'requester': ['shared[feature]'],
                                  'shared': ['feature; extra == "feature"'], 'feature': []})
        with patch('importlib.metadata.distribution', side_effect=self.distribution):
            actual = self.command._dependency_closure({'entry'})
        self.assertEqual(actual, {'entry', 'requester', 'shared', 'feature'})

    def test_dependency_cycles_terminate_and_missing_metadata_is_retained(self):
        self.requirements.update({'entry': ['shared[feature]', 'missing'],
                                  'shared': ['entry', 'feature; extra == "feature"'], 'feature': []})
        with patch('importlib.metadata.distribution', side_effect=self.distribution):
            actual = self.command._dependency_closure({'entry'})
        self.assertEqual(actual, {'entry', 'shared', 'feature', 'missing'})

    def test_pruning_removes_only_the_unrelated_distribution(self):
        installed = {name: '1.0' for name in (*self.requirements, 'unused')}
        with (
            patch('importlib.metadata.distribution', side_effect=self.distribution),
            patch.object(self.command, '_parse_poetry_lock', return_value={'torch': '2.11'}),
            patch.object(self.command, '_get_installed_versions', return_value=installed),
            patch('commands.install.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run,
        ):
            self.assertEqual(self.command._remove_orphaned_packages(Path('.'), {}), 0)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], [sys.executable, '-m', 'pip', 'uninstall', '-y', 'unused'])

    def test_missing_extra_dependencies_make_an_installed_module_unsatisfied(self):
        with (
            patch('importlib.metadata.distribution', side_effect=self.distribution),
            patch.object(self.command, '_get_installed_versions', return_value={'torch': '2.11', 'cuda-toolkit': '13', 'base': '1'}),
        ):
            self.assertEqual(self.command._filter_unsatisfied_module_deps({'torch': '==2.11'}, Path('.')),
                             {'torch': '==2.11'})

    def test_ready_extra_dependencies_keep_the_fast_path(self):
        installed = {name: '1.0' for name in self.requirements}
        installed['torch'] = '2.11'
        installed['cuda-toolkit'] = '13'
        with (
            patch('importlib.metadata.distribution', side_effect=self.distribution),
            patch.object(self.command, '_get_installed_versions', return_value=installed),
        ):
            self.assertEqual(self.command._filter_unsatisfied_module_deps({'torch': '==2.11'}, Path('.')), {})


if __name__ == '__main__':
    unittest.main()
