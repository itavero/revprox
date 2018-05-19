#!/usr/bin/env python3
from pathlib import Path
import os
from subprocess import call
import sys
from urllib.parse import urlparse, urlunparse, quote
import re
from blessings import Terminal
from git import Repo
from shutil import rmtree
import yaml
from questionhelper import interview, Question, QuestionType


KEY_STORAGE_PATH = 'storage_path'
KEY_GIT_REPO = 'repository'
KEY_GIT_USER = 'username'
KEY_GIT_PASS = 'key'


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def validate_storage_path(answers, current):
    if not current:
        return False
    path = Path(current)
    if path.exists():
        return path.is_dir() and os.access(str(path), os.W_OK)
    return True


def validate_not_empty(answers, current):
    if not current or current.isspace():
        return False
    return True


def default_repo_user(answers):
    if not KEY_GIT_REPO in answers:
        return ''
    url = urlparse(answers[KEY_GIT_REPO])
    if url.path:
        p = Path(url.path).parts
        if len(p) > 2:
            return p[1]
    return ''


def git_repo_already_exists(answers):
    if not KEY_STORAGE_PATH in answers:
        return False
    repo = Path(answers[KEY_STORAGE_PATH]) / 'config' / '.git'
    return repo.exists()


def must_create_storage_path(answers):
    if not KEY_STORAGE_PATH in answers:
        return False
    path = Path(answers[KEY_STORAGE_PATH])
    return path.exists()


def create_storage_path(answers, current):
    if not KEY_STORAGE_PATH in answers:
        return False
    path = Path(answers[KEY_STORAGE_PATH])
    if not path.exists() and not current:
        return False
    if path.exists() and path.is_dir():
        if os.access(str(path), os.W_OK):
            return True
        sys.exit("Directory '{}' is not writable. Please restart the setup script and try with a different directory or change the permissions.".format(str(path)))
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except:
        eprint('Failed to create storage path. Error:', sys.exc_info()[0])
        return False


def validate_git_repository(answers, current):
    url = urlparse(current)
    if not url.scheme or not url.scheme.startswith('http'):
        eprint('{t.normal}\n{t.bold}{t.red}[!] You MUST use an HTTP(S) url.{t.normal}'.format(
            t=Terminal()))
        return False
    if '@' in url.netloc:
        eprint('{t.normal}\n{t.bold}{t.red}[!] You MUST NOT include credentials in the url.{t.normal}'.format(
            t=Terminal()))
        return False
    return True


def url_add_auth(url, username, password):
    parsed_url = urlparse(url)
    netloc = parsed_url.netloc
    if '@' in netloc:
        netloc = netloc.split('@', 1)[1]
    return parsed_url._replace(netloc='{u}:{p}@{l}'.format(u=quote(username, safe=''), p=quote(password, safe=''), l=netloc)).geturl()


if __name__ == '__main__':
    questions = [
        Question(type=QuestionType.TEXT,
                 name=KEY_STORAGE_PATH,
                 message="Storage directory for RevProx", default=str(Path.home() / '.revprox'),
                 validate=validate_storage_path),
        Question(type=QuestionType.CONFIRM,
                 name='do_create_storage_path',
                 message="Path does NOT exist yet. Create it?",
                 ignore=must_create_storage_path,
                 default=True,
                 validate=create_storage_path),
        Question(type=QuestionType.TEXT,
                 name=KEY_GIT_REPO,
                 message="Git config repository URL",
                 validate=validate_git_repository,
                 ignore=git_repo_already_exists),
        Question(type=QuestionType.TEXT,
                 name=KEY_GIT_USER,
                 message="HTTP username for Git repo",
                 validate=validate_not_empty,
                 default=default_repo_user,
                 ignore=git_repo_already_exists),
        Question(type=QuestionType.SECRET,
                 name=KEY_GIT_PASS,
                 message="HTTP password/key for Git repo",
                 validate=validate_not_empty,
                 ignore=git_repo_already_exists)
    ]

    answers = interview(questions)
    if not answers:
        sys.exit('{t.bold}{t.red}Setup aborted.{t.normal}'.format(t=Terminal()))

    storage = Path(answers[KEY_STORAGE_PATH])
    repo_path = storage / 'config'
    cert_path = storage / 'certs'
    nginx_path = storage / 'nginx'

    # Clone repository
    if not git_repo_already_exists(answers):
        if repo_path.exists():
            # Delete first
            print('{t.normal}[{t.cyan}+{t.normal}] Deleting {t.bold}{t.magenta}{path}{t.normal} and its contents...'.format(
                t=Terminal(), path=repo_path))
            rmtree(repo_path)
        print('{t.normal}[{t.cyan}+{t.normal}] Cloning {t.bold}{t.cyan}{repo}{t.normal} into {t.bold}{t.magenta}{path}{t.normal}'.format(
            t=Terminal(), repo=answers[KEY_GIT_REPO], path=repo_path))
        full_repo_url = url_add_auth(
            answers[KEY_GIT_REPO], answers[KEY_GIT_USER], answers[KEY_GIT_PASS])
        config_repo = None
        try:
            config_repo = Repo.clone_from(full_repo_url, repo_path)
        except:
            eprint('Failed to clone the repository. Error:', sys.exc_info()[0])
            sys.exit('Terminated.')

    # Check if configuration file found
    config_file = repo_path / 'config.yml'
    if not config_file.exists():
        eprint('config.yml not found in repository.')
        sys.exit('Please try again.')

    # Run update-config
    print('{t.normal}[{t.cyan}+{t.normal}] Run update script (forced)...'.format(t=Terminal()))
    current_dir = Path(__file__).parent
    call([current_dir / 'update-config.py', '--force', storage])

    # Install crontab
    print('{t.normal}[{t.cyan}+{t.normal}] Configure cron tab...'.format(t=Terminal()))
    # TODO configure crontab
    print('TO DO')
