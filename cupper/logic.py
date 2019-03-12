import click
import os
import shutil
import subprocess
from cookiecutter.main import cookiecutter
from pathlib import Path
from typing import MutableMapping


class _TemporaryGitWorkingDirectory:
    """Context Manager for a temporary working directory of a branch in a git repo"""

    def __init__(self, path: str, repo: str, branch: str = 'master'):
        self.repo = repo
        self.path = path
        self.branch = branch

    def __enter__(self):
        if not os.path.exists(os.path.join(self.repo, ".git")):
            raise Exception("Not a git repository: %s" % self.repo)

        if os.path.exists(self.path):
            raise Exception("Temporary directory already exists: %s" % self.path)

        os.makedirs(self.path)
        subprocess.run(["git", "worktree", "add", "--no-checkout", self.path, self.branch],
                       cwd=self.repo, check=True)

    def __exit__(self, type, value, traceback):
        shutil.rmtree(self.path)
        subprocess.run(["git", "worktree", "prune"], cwd=self.repo, check=True)


def _git_repository_has_local_changes(git_repository: Path):
    result: subprocess.CompletedProcess = subprocess.run(["git", "diff-index", "--quiet", "HEAD", "--"],
                                                         cwd=str(git_repository), check=False)
    if result.returncode == 0:
        return False
    elif result.returncode == 1:
        return True
    else:
        raise Exception("could not determine whether git worktree is clean: " + repr(result))


def update_project_template_branch(context: MutableMapping[str, str], project_directory: str, branch: str):
    """Update template branch from a template url"""
    template_url = context['_template']
    tmpdir = os.path.join(project_directory, ".git", "cookiecutter")
    project_slug = os.path.basename(project_directory)
    tmp_workdir = os.path.join(tmpdir, project_slug)

    context['project_slug'] = project_slug
    if subprocess.run(["git", "rev-parse", "-q", "--verify", branch], cwd=project_directory).returncode != 0:
        # create a template branch if necessary
        click.echo(f"Creating git branch {branch}")
        firstref = subprocess.run(["git", "rev-list", "--max-parents=0", "--max-count=1", "HEAD"],
                                  cwd=project_directory,
                                  stdout=subprocess.PIPE,
                                  universal_newlines=True,
                                  check=True).stdout.strip()
        subprocess.run(["git", "branch", branch, firstref], cwd=project_directory)

    with _TemporaryGitWorkingDirectory(tmp_workdir, repo=project_directory, branch=branch):
        # update the template
        click.echo(f"Updating template in branch {branch} using extra_context={context}")
        cookiecutter(template_url,
                     no_input=True,
                     extra_context=context,
                     overwrite_if_exists=True,
                     output_dir=tmpdir)

        # commit to template branch
        subprocess.run(["git", "add", "-A", "."], cwd=tmp_workdir, check=True)
        if _git_repository_has_local_changes(Path(tmp_workdir)):
            click.echo("Committing changes...")
            subprocess.run(["git", "commit", "-m", "Update template"],
                           cwd=tmp_workdir, check=True)
            subprocess.run(["git", "push", "origin", branch],
                           cwd=tmp_workdir, check=False)

            click.echo(f"===========")
            click.echo(
                f"Changes have been commited into branch '{branch}'. Use the following command to update your branch:\n"
                f"git merge {branch}")
        else:
            click.echo("No changes found")