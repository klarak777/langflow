import sys
import time
import httpx
from langflow.services.database.utils import session_getter
from langflow.services.manager import initialize_services, initialize_settings_manager
from langflow.services.utils import get_db_manager, get_settings_manager

from multiprocess import Process, cpu_count  # type: ignore
import platform
from pathlib import Path
from typing import Optional
import socket
from rich.panel import Panel
from rich import box
from rich import print as rprint
from rich.table import Table
import typer
from langflow.main import setup_app
from langflow.utils.logger import configure, logger
import webbrowser
from dotenv import load_dotenv

from rich.console import Console

console = Console()

app = typer.Typer()


def get_number_of_workers(workers=None):
    if workers == -1 or workers is None:
        workers = (cpu_count() * 2) + 1
    logger.debug(f"Number of workers: {workers}")
    return workers


def display_results(results):
    """
    Display the results of the migration.
    """
    for table_results in results:
        table = Table(title=f"Migration {table_results.table_name}")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("Status")

        for result in table_results.results:
            status = "Success" if result.success else "Failure"
            color = "green" if result.success else "red"
            table.add_row(result.name, result.type, f"[{color}]{status}[/{color}]")

        console.print(table)
        console.print()  # Print a new line


def update_settings(
    config: str,
    cache: str,
    dev: bool = False,
    remove_api_keys: bool = False,
    components_path: Optional[Path] = None,
):
    """Update the settings from a config file."""

    # Check for database_url in the environment variables
    initialize_settings_manager()
    settings_manager = get_settings_manager()
    if config:
        logger.debug(f"Loading settings from {config}")
        settings_manager.settings.update_from_yaml(config, dev=dev)
    if remove_api_keys:
        logger.debug(f"Setting remove_api_keys to {remove_api_keys}")
        settings_manager.settings.update_settings(REMOVE_API_KEYS=remove_api_keys)
    if cache:
        logger.debug(f"Setting cache to {cache}")
        settings_manager.settings.update_settings(CACHE=cache)
    if components_path:
        logger.debug(f"Adding component path {components_path}")
        settings_manager.settings.update_settings(COMPONENTS_PATH=components_path)


def serve_on_jcloud():
    """
    Deploy Langflow server on Jina AI Cloud
    """
    import asyncio
    from importlib.metadata import version as mod_version

    import click

    try:
        from lcserve.__main__ import serve_on_jcloud  # type: ignore
    except ImportError:
        click.secho(
            "🚨 Please install langchain-serve to deploy Langflow server on Jina AI Cloud "
            "using `pip install langchain-serve`",
            fg="red",
        )
        return

    app_name = "langflow.lcserve:app"
    app_dir = str(Path(__file__).parent)
    version = mod_version("langflow")
    base_image = "jinaai+docker://deepankarm/langflow"

    click.echo("🚀 Deploying Langflow server on Jina AI Cloud")
    app_id = asyncio.run(
        serve_on_jcloud(
            fastapi_app_str=app_name,
            app_dir=app_dir,
            uses=f"{base_image}:{version}",
            name="langflow",
        )
    )
    click.secho(
        "🎉 Langflow server successfully deployed on Jina AI Cloud 🎉", fg="green"
    )
    click.secho(
        "🔗 Click on the link to open the server (please allow ~1-2 minutes for the server to startup): ",
        nl=False,
        fg="green",
    )
    click.secho(f"https://{app_id}.wolf.jina.ai/", fg="blue")
    click.secho("📖 Read more about managing the server: ", nl=False, fg="green")
    click.secho("https://github.com/jina-ai/langchain-serve", fg="blue")


@app.command()
def run(
    host: str = typer.Option(
        "127.0.0.1", help="Host to bind the server to.", envvar="LANGFLOW_HOST"
    ),
    workers: int = typer.Option(
        2, help="Number of worker processes.", envvar="LANGFLOW_WORKERS"
    ),
    timeout: int = typer.Option(300, help="Worker timeout in seconds."),
    port: int = typer.Option(7860, help="Port to listen on.", envvar="LANGFLOW_PORT"),
    components_path: Optional[Path] = typer.Option(
        Path(__file__).parent / "components",
        help="Path to the directory containing custom components.",
        envvar="LANGFLOW_COMPONENTS_PATH",
    ),
    config: str = typer.Option(
        Path(__file__).parent / "config.yaml", help="Path to the configuration file."
    ),
    # .env file param
    env_file: Path = typer.Option(
        None, help="Path to the .env file containing environment variables."
    ),
    log_level: str = typer.Option(
        "critical", help="Logging level.", envvar="LANGFLOW_LOG_LEVEL"
    ),
    log_file: Path = typer.Option(
        "logs/langflow.log", help="Path to the log file.", envvar="LANGFLOW_LOG_FILE"
    ),
    cache: str = typer.Option(
        envvar="LANGFLOW_LANGCHAIN_CACHE",
        help="Type of cache to use. (InMemoryCache, SQLiteCache)",
        default="SQLiteCache",
    ),
    jcloud: bool = typer.Option(False, help="Deploy on Jina AI Cloud"),
    dev: bool = typer.Option(False, help="Run in development mode (may contain bugs)"),
    # This variable does not work but is set by the .env file
    # and works with Pydantic
    # database_url: str = typer.Option(
    #     None,
    #     help="Database URL to connect to. If not provided, a local SQLite database will be used.",
    #     envvar="LANGFLOW_DATABASE_URL",
    # ),
    path: str = typer.Option(
        None,
        help="Path to the frontend directory containing build files. This is for development purposes only.",
        envvar="LANGFLOW_FRONTEND_PATH",
    ),
    open_browser: bool = typer.Option(
        True,
        help="Open the browser after starting the server.",
        envvar="LANGFLOW_OPEN_BROWSER",
    ),
    remove_api_keys: bool = typer.Option(
        False,
        help="Remove API keys from the projects saved in the database.",
        envvar="LANGFLOW_REMOVE_API_KEYS",
    ),
    backend_only: bool = typer.Option(
        False,
        help="Run only the backend server without the frontend.",
        envvar="LANGFLOW_BACKEND_ONLY",
    ),
):
    """
    Run the Langflow server.
    """
    # override env variables with .env file
    if env_file:
        load_dotenv(env_file, override=True)

    if jcloud:
        return serve_on_jcloud()

    configure(log_level=log_level, log_file=log_file)
    update_settings(
        config,
        dev=dev,
        remove_api_keys=remove_api_keys,
        cache=cache,
        components_path=components_path,
    )
    # create path object if path is provided
    static_files_dir: Optional[Path] = Path(path) if path else None
    app = setup_app(static_files_dir=static_files_dir, backend_only=backend_only)
    # check if port is being used
    if is_port_in_use(port, host):
        port = get_free_port(port)

    options = {
        "bind": f"{host}:{port}",
        "workers": get_number_of_workers(workers),
        "worker_class": "uvicorn.workers.UvicornWorker",
        "timeout": timeout,
    }

    # Define an env variable to know if we are just testing the server
    if "pytest" in sys.modules:
        return

    if platform.system() in ["Windows"]:
        # Run using uvicorn on MacOS and Windows
        # Windows doesn't support gunicorn
        # MacOS requires an env variable to be set to use gunicorn
        run_on_windows(host, port, log_level, options, app)
    else:
        # Run using gunicorn on Linux
        run_on_mac_or_linux(host, port, log_level, options, app, open_browser)


def run_on_mac_or_linux(host, port, log_level, options, app, open_browser=True):
    webapp_process = Process(
        target=run_langflow, args=(host, port, log_level, options, app)
    )
    webapp_process.start()
    status_code = 0
    while status_code != 200:
        try:
            status_code = httpx.get(f"http://{host}:{port}/health").status_code

        except Exception:
            time.sleep(1)

    print_banner(host, port)
    if open_browser:
        webbrowser.open(f"http://{host}:{port}")


def run_on_windows(host, port, log_level, options, app):
    """
    Run the Langflow server on Windows.
    """
    print_banner(host, port)
    run_langflow(host, port, log_level, options, app)


def is_port_in_use(port, host="localhost"):
    """
    Check if a port is in use.

    Args:
        port (int): The port number to check.
        host (str): The host to check the port on. Defaults to 'localhost'.

    Returns:
        bool: True if the port is in use, False otherwise.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def get_free_port(port):
    """
    Given a used port, find a free port.

    Args:
        port (int): The port number to check.

    Returns:
        int: A free port number.
    """
    while is_port_in_use(port):
        port += 1
    return port


def print_banner(host, port):
    # console = Console()

    word = "Langflow"
    colors = ["#3300cc"]

    styled_word = ""

    for i, char in enumerate(word):
        color = colors[i % len(colors)]
        styled_word += f"[{color}]{char}[/]"

    # Title with emojis and gradient text
    title = (
        f"[bold]Welcome to :chains: {styled_word} [/bold]\n\n"
        f"Access [link=http://{host}:{port}]http://{host}:{port}[/link]"
    )
    info_text = (
        "Collaborate, and contribute at our "
        "[bold][link=https://github.com/logspace-ai/langflow]GitHub Repo[/link][/bold] :rocket:"
    )

    # Create a panel with the title and the info text, and a border around it
    panel = Panel(
        f"{title}\n{info_text}", box=box.ROUNDED, border_style="blue", expand=False
    )

    # Print the banner with a separator line before and after
    rprint(panel)


def run_langflow(host, port, log_level, options, app):
    """
    Run Langflow server on localhost
    """
    try:
        if platform.system() in ["Windows"]:
            # Run using uvicorn on MacOS and Windows
            # Windows doesn't support gunicorn
            # MacOS requires an env variable to be set to use gunicorn
            import uvicorn

            uvicorn.run(app, host=host, port=port, log_level=log_level)
        else:
            from langflow.server import LangflowApplication

            LangflowApplication(app, options).run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.exception(e)
        sys.exit(1)


@app.command()
def superuser(
    username: str = typer.Option(..., prompt=True, help="Username for the superuser."),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the superuser."
    ),
):
    initialize_services()
    db_manager = get_db_manager()
    with session_getter(db_manager) as session:
        from langflow.services.auth.utils import create_super_user

        if create_super_user(session, username, password):
            # Verify that the superuser was created
            from langflow.services.database.models.user.user import User

            user = session.query(User).filter(User.username == username).first()
            if user is None:
                typer.echo("Superuser creation failed.")
                return

            typer.echo("Superuser created successfully.")

        else:
            typer.echo("Superuser creation failed.")


@app.command()
def migration(test: bool = typer.Option(False, help="Run migrations in test mode.")):
    initialize_services()
    db_manager = get_db_manager()
    if not test:
        db_manager.run_migrations()
    results = db_manager.run_migrations_test()
    display_results(results)


def main():
    app()


if __name__ == "__main__":
    main()
