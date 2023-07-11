"""A command line interface for the repository.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path

from memic.utility.better_enum import BetterEnum

# use outermost directory as root
os.chdir(Path(__file__).parent.parent.parent)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler(sys.stdout))


class Cmds(BetterEnum):
    """A collection of commands to be run in the terminal."""

    # jupyter tools
    jup = [
        "jupyter",
        "notebook",
        "--ip=0.0.0.0",
        "--allow-root",
        "--notebook-dir='src/jupyter'",
        "--NotebookApp.token=''",
        "--NotebookApp.password=''",
    ]

    console = ["ipython", "-i", "-c"]
    repl = ["python", "-i", "-c"]

    @classmethod
    def get_help(cls):
        s = "Direct Command Aliases:\n"
        end = "\033[0m"
        bold = "\033[1m"
        blue = "\033[34m"
        for name, cmd in cls.items():
            c = " ".join(cmd)
            s += f"\t`memic {bold}{blue}{name}{end}` => `{c}`\n"
        return s

    @classmethod
    def help(cls):
        print(cls.get_help())


Cmds.__doc__ = Cmds.get_help()


class InternalCmds(BetterEnum):
    """A collection of commands to be run in the terminal.

    These commands can be used by the Scripts class or directly by the command line tool.
    """

    # general tools
    open_browser = ["xdg-open" if sys.platform.startswith("linux") else "explorer"]

    # git tools
    pre_commit_run_all_files = ["pre-commit", "run", "--all-files"]
    black_reformat = ["pre-commit", "run", "black", "--all-files", "--hook-stage", "manual"]
    git_update = ["git", "add", "-u"]
    """-u, or --update: This option makes git add look not at the working directory,
    but at the difference between the index (staged changes) and the current HEAD commit.
    It stages the changes to any tracked files, ready for the next commit.
    It does not add any new files, it only stages changes to already tracked files."""

    # pytest tools
    pytest = ["pytest"]
    pytest_cov = pytest + ["--cov"]
    coverage_html = ["coverage", "html"]
    open_coverage = open_browser + [f"file://{Path('htmlcov/index.html').resolve()}"]


class Scripts:
    """A collection of scripts to be run in the terminal."""

    def fix(self):
        """Fix common issues by calling `pre-commit run --all-files`."""
        subprocess.run(InternalCmds.pre_commit_run_all_files)

    def fmt(self, *args):
        """Format code using `black`."""
        subprocess.run(InternalCmds.black_reformat)
        subprocess.run(InternalCmds.git_update)

    def test(self, *args):
        """Run tests and open coverage report."""
        p = subprocess.run(" ".join(InternalCmds.pytest_cov), shell=True)

        if p.returncode == 0:
            if "--no-open" in args:
                return
            subprocess.run(InternalCmds.coverage_html)
            subprocess.run(InternalCmds.open_coverage)

    def toolbox(self, *args):
        """Run the demo toolbox UI."""
        from memic.cli.demo_toolbox import main

        main(*args)

    def cli(self, *args):
        """The main command line interface from CorentinJ/Real-Time-Voice-Cloning."""
        from memic.cli.demo_cli import main

        main(*args)

    def enc(self, *args):
        """Alias for `encoder`."""
        self.encoder(*args)

    def encoder(self, cmd, *args):
        """Run a command from the encoder cli (`encoder train` or `encoder preprocess`)."""
        if cmd == "train":
            from memic.cli.encoder_train import main
            main(*args)
        elif cmd == "preprocess":
            from memic.cli.encoder_preprocess import main
            main(*args)

    def synth(self, *args):
        """Alias for `synthesizer`."""
        self.synthesizer(*args)

    def synthesizer(self, cmd, *args):
        """Run a command from the synthesizer cli (`synthesizer train` or `synthesizer preprocess`)."""
        if cmd == "preprocess":
            self._synthesizer_preprocess(*args)
        elif cmd == "train":
            from memic.cli.synthesizer_train import main
            main(*args)

    def _synthesizer_preprocess(self, cmd, *args):
        if cmd == "audio":
            from memic.cli.synthesizer_preprocess_audio import main
            main(*args)
        elif cmd == "embeds":
            from memic.cli.synthesizer_preprocess_embeds import main
            main(*args)

    def voc(self, *args):
        """Alias for `vocoder`."""
        self.vocoder(*args)

    def vocode(self, *args):
        """Alias for `vocoder`."""
        self.vocoder(*args)

    def vocoder(self, cmd, *args):
        """Run a command from the vocoder cli (`vocoder train` or `vocoder preprocess`)."""
        if cmd == "train":
            from memic.cli.vocoder_train import main
            main(*args)
        elif cmd == "preprocess":
            from memic.cli.vocoder_preprocess import main
            main(*args)

    def _run(self, cmd, *args):
        """Run a command either from a method in this class or from a command in Cmds class."""
        if hasattr(self, cmd):
            getattr(self, cmd)(*args)
        elif hasattr(Cmds, cmd):
            logger.info(f"Running command: {getattr(Cmds, cmd)}")
            subprocess.run(" ".join(getattr(Cmds, cmd)), shell=True)
        elif cmd in ["-v", "--version"]:
            import cutwater

            print(f"Version: {cutwater.__version__}")
            from memic.utility.version_control import VersionControl

            vc = VersionControl()
            gs = vc.git_summary()
            print(f"Git Remote: {gs['remote']}")
            print(f"Git Branch: {gs['branch']}")
            print(f"Git Tag: {gs['tag']}")
            print(f"Git Commit Date: {gs['date']}")
        else:
            self.help(*args)

    def __call__(self, cmd, *args):
        self._run(cmd, *args)

    @classmethod
    def get_help(cls, func=None, *args):
        """Print command line help."""
        if func is not None and func.startswith("--"):
            func = None
        x = Path(sys.executable).parent / "memic"
        s = "The `memic` command line tool...\n"
        s += "\t* is installed into the virtual environment by pip due to pyproject.toml config\n"
        s += f"\t* lives at {x.resolve()}\n"
        s += f"\t* calls {__file__}:main() with the arguments you pass to it\n\n"

        end = "\033[0m"
        bold = "\033[1m"
        blue = "\033[34m"
        if func is not None:
            if hasattr(cls, func):
                func = getattr(cls, func)
                return func.__doc__
            elif hasattr(Cmds, func):
                cmd = " ".join(getattr(Cmds, func))
                return f"`{bold}memic {func}{end}` calls `{cmd}`"
            else:
                return help(func)

        s += "Available commands: (call `memic help <command>` for more info)\n"
        s += f"\t`{bold}{blue}memic{end}`: print help\n"

        for name in dir(cls):
            if name.startswith("_") or name == "get_help":
                continue
            func = getattr(cls, name)
            d = func.__doc__
            d = d.splitlines()[0] if isinstance(d, str) else ""
            s += f"\t`memic {bold}{blue}{name}{end}`: {d}\n"

        s += "\n"
        s += Cmds.get_help()
        s += "\n"
        s += "Misc help: (python built-in help() gets called on any unrecognized arguments (Press `q` to exit))\n"
        return s

    def help(self, *args):
        """Print command line help.

        No args:
            print a list of available commands, e.g. `memic help`
        command_name:
            print help for a specific command, e.g. `memic help help`
        other:
            print Python help documentation for a python object, e.g. `memic help int`

        """
        print(self.get_help(*args))


Scripts.__doc__ = Scripts.get_help()
scripts = Scripts()


def main():
    if len(sys.argv) == 1:
        sys.argv.append("help")
    scripts(*sys.argv[1:])


if __name__ == "__main__":
    main()
