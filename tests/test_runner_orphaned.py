"""Exercise orphan cleanup functions only in disposable targets, never live HOME."""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import test_runner_review_regressions as fixtures


@unittest.skipUnless(shutil.which("zsh"), "requires zsh")
class OrphanedLibraryTests(unittest.TestCase):
    def test_library_links_are_found_without_removing_unowned_content(self):
        helper = fixtures.ExistingReviewFixTests()
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repo, target = root / "repo", root / "target"
                repo.mkdir()
                library = target / ".local/lib/fixture"
                library.mkdir(parents=True)
                owned = [library / "probe.py", library / "relative.py",
                         library.parent / "folded"]
                owned[0].symlink_to(repo / "packages/fixture/install/.local/lib/fixture/probe.py")
                owned[1].symlink_to(os.path.relpath(repo / "stow/fixture/.local/lib/fixture/relative.py", library))
                owned[2].symlink_to(repo / "stow/fixture/.local/lib/folded")
                foreign = library / "foreign.py"
                foreign.symlink_to(root / "other-repo/stow/fixture/.local/lib/fixture/foreign.py")
                other_package = library / "other-package.py"
                other_package.symlink_to(repo / "stow/fixture-other/.local/lib/other.py")
                regular = library / "regular.py"
                regular.write_text("keep this fixture\n")
                external = root / "outside"
                external.mkdir()
                protected = external / "probe.py"
                protected.symlink_to(repo / "stow/fixture/.local/lib/fixture/probe.py")
                (library / "external-directory").symlink_to(external, target_is_directory=True)
                script = "set -eu\n" + helper.function("run.sh", "reap_orphaned_package") + '''
repo_root="$1"
target="$2"
validate_package_name() { [[ "$1" == fixture ]]; }
package_has_user_install() { return 1; }
stow_target_is_home() { return 1; }
die() { print -u2 -- "$*"; exit 65; }
systemctl() { print -u2 -- "unexpected systemctl"; exit 99; }
reap_orphaned_package fixture "$3" 1
'''
                result = helper.zsh(script, str(repo), str(target), str(int(dry_run)))
                self.assertEqual(result.returncode, 0, result.stderr)
                for link in owned:
                    self.assertIn(str(link), result.stdout)
                    self.assertEqual(link.is_symlink(), dry_run)
                self.assertTrue(foreign.is_symlink())
                self.assertTrue(other_package.is_symlink())
                self.assertTrue(protected.is_symlink())
                self.assertEqual(regular.read_text(), "keep this fixture\n")
                self.assertTrue(library.is_dir())
