"""Tools for managing git from python."""
import logging
import subprocess


class VersionControl:
    """Tools for managing git from python."""

    def __init__(self, logger="version_control"):
        if isinstance(logger, str):
            logger = logging.getLogger(logger)
        self.log = logger
        self.log.info("initialized VersionControl")
        # self.summary = self.git_summary()

    @staticmethod
    def call(cmd, *args, **kwargs) -> str:
        """Call a shell command."""
        cmd += "".join([f" -{a}" for a in args])
        cmd += "".join([f" --{k} {v}" for k, v in kwargs.items()])
        return subprocess.check_output(cmd, shell=True).decode()

    # ____________________ INFO _______________________________
    @classmethod
    def git_status(cls) -> str:
        """Get the git status."""
        return cls.call("git status")

    @classmethod
    def git_remote(cls) -> str:
        """Git the remote branch."""
        return cls.call("git config --get remote.origin.url").split("\n")[0]

    @classmethod
    def git_branch(cls) -> str:
        """Git the active branch."""
        return cls.call("git rev-parse --abbrev-ref HEAD").split("\n")[0]

    @classmethod
    def git_commit(cls) -> str:
        """Git the active commit."""
        return cls.call("git rev-parse --abbrev-ref HEAD")

    @classmethod
    def git_commit_time(cls) -> str:
        """Git the time of the active commit."""
        return cls.call("git log -1 --format=%cd")

    @classmethod
    def git_diff_str(cls, *args) -> str:
        """Git the difference from the active commit."""
        return cls.call("git diff HEAD", *args)

    @classmethod
    def git_latest_tag(cls) -> str:
        """Git the latest tag."""
        try:
            if cls.call("git describe --tags --abbrev=0").strip() == "":
                return ""
            else:
                return cls.call("git describe --tags `git rev-list --tags --max-count=1`").strip()
        except subprocess.CalledProcessError:
            return ""

    @classmethod
    def git_changed_files(cls) -> dict:
        """Git a dictionary of the files which have changed and their status."""
        t = cls.git_diff_str("-name-status")
        files = {}
        for line in t.splitlines():
            status, fn, *_ = line.split("\t")
            files[fn] = status
        return files

    @classmethod
    def git_diff(cls) -> dict:
        """Git a dictionary of the files which have changed and their status and diff."""
        changed_files = cls.git_changed_files()
        files = {}
        for fn, status in changed_files.items():
            t = cls.call(f'git --no-pager diff HEAD --stat -- "{fn}"')
            if t:
                x = t.split("\n")[0].strip()
                if x.endswith("bytes"):
                    n = int(x.split(" ")[-2])
                    s = x
                else:
                    x = t.split("\n")[0].split(" | ")[1]
                    if " " in x:
                        n, s = x.split(" ")
                    else:
                        n = t
                        s = ""
            else:
                n = 0
                s = ""

            files[fn] = {"status": status, "stat": s, "diff_length": n}
            # e.g.      {'status': 'M', 'stat': '+--', 'diff_length': 3}
        return files

    @classmethod
    def git_config(cls) -> dict:
        """Git the current config."""
        config = cls.call("git config --list")
        config_dict = {}
        for line in config.splitlines():
            k, v = line.split("=")
            config_dict[k] = v
        return config_dict

    @classmethod
    def git_commit_info(cls) -> dict:
        """Git info about the active commit."""
        return cls.interpret_commit_log(cls.call("git log HEAD -1"))

    @classmethod
    def interpret_commit_log(cls, commit_log: str) -> dict:
        """Convert a commit log string into a dictionary of the data."""
        lines = commit_log.splitlines()
        merge = 1 * lines[1].startswith("Merge: ")
        commit_info = {
            "commit": lines[0].split("commit ")[1],
            "merge": lines[1].split("Merge: ")[1].strip() if merge else False,
            "author": lines[1 + merge].split("Author: ")[1].strip(),
            "date": lines[2 + merge].split("Date: ")[1].strip(),  # format = '%a %b %d %H:%M:%S %Y %z'
            "message": "\n".join(lines[(3 + merge) :]).strip(),
        }
        return commit_info

    @classmethod
    def git_summary(cls) -> dict:
        """Git a dictionary summarizing the git state."""
        remote = cls.git_remote()
        branch = cls.git_branch()
        info = cls.git_commit_info()
        diff = cls.git_diff()
        tag = cls.git_latest_tag()
        summary = {"remote": remote, "branch": branch, "tag": tag, **info, "diff": diff}
        return summary

    @classmethod
    def git_branches(cls):
        """Git a list of the branches."""
        return cls.call("git for-each-ref --sort=-committerdate refs/heads/ --format='%(refname:short)'").splitlines()

    @classmethod
    def git_tags(cls):
        """Git a list of the tags."""
        tag_lines = cls.call('git log --tags --simplify-by-decoration --pretty="format:%ai %d" | grep tag: ').splitlines()
        tags = [line.split("tag: ")[1].split(",")[0].replace(")", "") for line in tag_lines]
        return tags

    @classmethod
    def git_options(cls):
        """Git a dictionary of the branches and tags."""
        return {"branches": cls.git_branches(), "tags": cls.git_tags()}

    # ____________________ ACTIONS _______________________________
    @classmethod
    def git_stash(cls):
        """Stash local changes."""
        return cls.call("git stash")

    @classmethod
    def git_set_username(cls, name, set_global=False):
        """Set the git username."""
        return cls.call(f'git config {"--global "*set_global}user.name "{name}"')

    @classmethod
    def git_set_useremail(cls, email, set_global=False):
        """Set the git email."""
        return cls.call(f'git config {"--global "*set_global}user.email {email}')

    @classmethod
    def git_set_user(cls, name, email, set_global=False):
        """Set the git user."""
        r1 = cls.git_set_username(name, set_global=set_global)
        r2 = cls.git_set_useremail(email, set_global=set_global)
        return [r1, r2]