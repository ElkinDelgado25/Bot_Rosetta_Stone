import sys


def main():
    # Create .env interactively if missing, BEFORE importing anything that
    # reads settings, so pydantic finds the file on first load.
    from rosseta_stone_script_a.infrastructure.core import ensure_env_exists

    ensure_env_exists()

    from rosseta_stone_script_a.presentation.cli import main_cli

    main_cli()


if __name__ == "__main__":
    exit_code = 0
    try:
        main()
    except KeyboardInterrupt:
        exit_code = 130
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        if getattr(sys, "frozen", False):
            input("\nPresiona Enter para cerrar...")
    raise SystemExit(exit_code)
