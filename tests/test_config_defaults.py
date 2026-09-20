"""Tests for the config file default layer (``Context.default_config_files``)."""

import pytest

import click
from click import ParameterSource


@pytest.fixture()
def config_file(tmp_path):
    """Write an INI config file and return its path."""

    def write(content, name="click.ini"):
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    return write


def make_cmd(**context_settings):
    @click.command(context_settings=context_settings)
    @click.option("--token", default="tok-default")
    @click.option("--workers", type=int, default=1)
    def cli(token, workers):
        click.echo(f"token={token} workers={workers}")

    return cli


def source_cmd(**context_settings):
    @click.command(context_settings=context_settings)
    @click.option("--token", default="tok-default", envvar="APP_TOKEN")
    @click.pass_context
    def cli(ctx, token):
        source = ctx.get_parameter_source("token")
        click.echo(f"token={token} source={source.name}")

    return cli


def test_config_value_used(runner, config_file):
    path = config_file("[default]\ntoken = tok-config\nworkers = 4\n")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.output == "token=tok-config workers=4\n"


def test_config_source_reported(runner, config_file):
    path = config_file("[default]\ntoken = tok-config\n")
    result = runner.invoke(source_cmd(default_config_files=[path]), [])
    assert result.output == "token=tok-config source=CONFIG\n"


def test_command_line_overrides_config(runner, config_file):
    path = config_file("[default]\ntoken = tok-config\nworkers = 4\n")
    cli = make_cmd(default_config_files=[path])
    result = runner.invoke(cli, ["--token", "tok-cli", "--workers", "8"])
    assert result.output == "token=tok-cli workers=8\n"


def test_envvar_overrides_config(runner, config_file):
    path = config_file("[default]\ntoken = tok-config\n")
    cli = source_cmd(default_config_files=[path])
    result = runner.invoke(cli, [], env={"APP_TOKEN": "tok-env"})
    assert result.output == "token=tok-env source=ENVIRONMENT\n"


def test_auto_envvar_prefix_overrides_config(runner, config_file):
    path = config_file("[default]\ntoken = tok-config\n")

    @click.command(
        context_settings={
            "auto_envvar_prefix": "APP",
            "default_config_files": [path],
        }
    )
    @click.option("--token", default="tok-default")
    @click.pass_context
    def cli(ctx, token):
        source = ctx.get_parameter_source("token")
        click.echo(f"token={token} source={source.name}")

    result = runner.invoke(cli, [], env={"APP_TOKEN": "tok-env"})
    assert result.output == "token=tok-env source=ENVIRONMENT\n"


def test_config_overrides_default_map(runner, config_file):
    path = config_file("[default]\ntoken = tok-config\n")
    cli = source_cmd(
        default_config_files=[path],
        default_map={"token": "tok-map"},
    )
    result = runner.invoke(cli, [])
    assert result.output == "token=tok-config source=CONFIG\n"


def test_config_overrides_param_default(runner, config_file):
    path = config_file("[default]\nworkers = 4\n")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.output == "token=tok-default workers=4\n"


def test_default_used_when_key_missing(runner, config_file):
    path = config_file("[default]\nother = x\n")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.output == "token=tok-default workers=1\n"


def test_argument_uses_same_chain(runner, config_file):
    path = config_file("[default]\nfilename = from-config.txt\n")

    @click.command(context_settings={"default_config_files": [path]})
    @click.argument("filename", default="default.txt")
    @click.pass_context
    def cli(ctx, filename):
        source = ctx.get_parameter_source("filename")
        click.echo(f"filename={filename} source={source.name}")

    result = runner.invoke(cli, [])
    assert result.output == "filename=from-config.txt source=CONFIG\n"

    result = runner.invoke(cli, ["from-cli.txt"])
    assert result.output == "filename=from-cli.txt source=COMMANDLINE\n"


def test_unknown_keys_ignored(runner, config_file):
    path = config_file(
        "[default]\ntoken = tok-config\nnonexistent = value\n[other]\nfoo = bar\n"
    )
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.exception is None
    assert result.output == "token=tok-config workers=1\n"


def test_missing_file_silently_skipped(runner, tmp_path):
    missing = str(tmp_path / "does-not-exist.ini")
    result = runner.invoke(make_cmd(default_config_files=[missing]), [])
    assert result.exception is None
    assert result.output == "token=tok-default workers=1\n"


def test_empty_file_silently_ignored(runner, config_file):
    path = config_file("")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.exception is None
    assert result.output == "token=tok-default workers=1\n"


def test_missing_section_falls_back(runner, config_file):
    path = config_file("[unrelated]\ntoken = tok-config\n")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.output == "token=tok-default workers=1\n"


def test_invalid_config_file_raises(runner, config_file):
    path = config_file("token = no-section-header\n")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.exit_code != 0
    assert "Could not parse config file" in result.output
    assert path in result.output
    assert "line 1" in result.output


def test_invalid_config_file_bad_line_raises(runner, config_file):
    path = config_file("[default]\ntoken = ok\nnot a valid line\n")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.exit_code != 0
    assert "Could not parse config file" in result.output
    assert "line 3" in result.output


def test_config_value_type_converted(runner, config_file):
    path = config_file("[default]\nworkers = 42\n")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.output == "token=tok-default workers=42\n"


def test_config_value_conversion_error_mentions_file_and_key(
    runner, config_file
):
    path = config_file("[default]\nworkers = not-a-number\n")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.exit_code != 0
    assert "not-a-number" in result.output
    assert "from key 'workers' in config file" in result.output
    assert path in result.output


def test_disabled_by_default(runner, config_file):
    """Without ``default_config_files`` the config layer is inert."""
    path = config_file("[default]\ntoken = tok-config\n")
    result = runner.invoke(make_cmd(), [])
    assert result.output == "token=tok-default workers=1\n"


def test_command_section_overrides_default_section(runner, config_file):
    path = config_file(
        "[default]\ntoken = tok-default-section\n"
        "[cli]\ntoken = tok-command-section\n"
    )
    cli = make_cmd(default_config_files=[path])
    result = runner.invoke(cli, [], prog_name="cli")
    assert result.output == "token=tok-command-section workers=1\n"


def test_later_files_override_earlier(runner, config_file):
    first = config_file("[default]\ntoken = tok-first\nworkers = 2\n", "a.ini")
    second = config_file("[default]\ntoken = tok-second\n", "b.ini")
    cli = make_cmd(default_config_files=[first, second])
    result = runner.invoke(cli, [])
    assert result.output == "token=tok-second workers=2\n"


def test_single_path_accepted(runner, config_file):
    path = config_file("[default]\ntoken = tok-config\n")
    result = runner.invoke(make_cmd(default_config_files=path), [])
    assert result.output == "token=tok-config workers=1\n"


def test_inherited_by_subcommand(runner, config_file):
    path = config_file(
        "[default]\ntoken = tok-default-section\n[sub]\ntoken = tok-sub\n"
    )

    @click.group(context_settings={"default_config_files": [path]})
    def cli():
        pass

    @cli.command()
    @click.option("--token", default="tok-default")
    @click.pass_context
    def sub(ctx, token):
        source = ctx.get_parameter_source("token")
        click.echo(f"token={token} source={source.name}")

    result = runner.invoke(cli, ["sub"])
    assert result.output == "token=tok-sub source=CONFIG\n"


def test_key_normalization(runner, config_file):
    """Keys are case-insensitive and dashes match underscores."""

    @click.command()
    @click.option("--api-token", default="default")
    def cli(api_token):
        click.echo(f"api_token={api_token}")

    for key in ("api-token", "API_TOKEN", "Api-Token"):
        path = config_file(f"[default]\n{key} = from-config\n", f"{key}.ini")
        cli.context_settings = {"default_config_files": [path]}
        result = runner.invoke(cli, [])
        assert result.output == "api_token=from-config\n"


def test_bool_flag_from_config(runner, config_file):
    path = config_file("[default]\nverbose = true\n")

    @click.command(context_settings={"default_config_files": [path]})
    @click.option("--verbose/--no-verbose", default=False)
    @click.pass_context
    def cli(ctx, verbose):
        source = ctx.get_parameter_source("verbose")
        click.echo(f"verbose={verbose} source={source.name}")

    result = runner.invoke(cli, [])
    assert result.output == "verbose=True source=CONFIG\n"


def test_bool_flag_false_from_config(runner, config_file):
    path = config_file("[default]\nverbose = false\n")

    @click.command(context_settings={"default_config_files": [path]})
    @click.option("--verbose/--no-verbose", default=True)
    def cli(verbose):
        click.echo(f"verbose={verbose}")

    result = runner.invoke(cli, [])
    assert result.output == "verbose=False\n"


def test_non_bool_flag_from_config(runner, config_file):
    path = config_file("[default]\ntransformation = upper\n")

    @click.command(context_settings={"default_config_files": [path]})
    @click.option("--upper", "transformation", flag_value="upper", default="lower")
    def cli(transformation):
        click.echo(f"transformation={transformation}")

    result = runner.invoke(cli, [])
    assert result.output == "transformation=upper\n"


def test_multiple_option_from_config(runner, config_file):
    # Splitting follows the same rules as environment variables:
    # whitespace by default.
    path = config_file("[default]\nitem = a b c\n")

    @click.command(context_settings={"default_config_files": [path]})
    @click.option("--item", multiple=True)
    def cli(item):
        click.echo(f"item={item!r}")

    result = runner.invoke(cli, [])
    assert result.output == "item=('a', 'b', 'c')\n"


def test_nargs_option_from_config(runner, config_file):
    path = config_file("[default]\npoint = 1 2\n")

    @click.command(context_settings={"default_config_files": [path]})
    @click.option("--point", nargs=2, type=int)
    def cli(point):
        click.echo(f"point={point!r}")

    result = runner.invoke(cli, [])
    assert result.output == "point=(1, 2)\n"


def test_empty_value_treated_as_unset(runner, config_file):
    path = config_file("[default]\ntoken =\n")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.output == "token=tok-default workers=1\n"


def test_percent_sign_in_value_not_interpolated(runner, config_file):
    path = config_file("[default]\ntoken = 100%sure\n")
    result = runner.invoke(make_cmd(default_config_files=[path]), [])
    assert result.output == "token=100%sure workers=1\n"


def test_config_suppresses_prompt(runner, config_file):
    path = config_file("[default]\ntoken = tok-config\n")

    @click.command(context_settings={"default_config_files": [path]})
    @click.option("--token", prompt=True)
    def cli(token):
        click.echo(f"token={token}")

    result = runner.invoke(cli, [])
    assert result.output == "token=tok-config\n"


def test_argument_conversion_error_mentions_file_and_key(runner, config_file):
    path = config_file("[default]\ncount = notanint\n")

    @click.command(context_settings={"default_config_files": [path]})
    @click.argument("count", type=int, default=1)
    def cli(count):
        click.echo(count)

    result = runner.invoke(cli, [])
    assert result.exit_code != 0
    assert "notanint" in result.output
    assert "from key 'count' in config file" in result.output
    assert path in result.output
