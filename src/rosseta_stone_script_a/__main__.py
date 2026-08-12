import sys


def main():
    # Create .env interactively if missing, BEFORE importing anything that
    # reads settings, so pydantic finds the file on first load.
    from rosseta_stone_script_a.infrastructure.core import ensure_env_exists

    ensure_env_exists()

    from rosseta_stone_script_a.presentation.cli import main_cli

    main_cli()


if __name__ == "__main__":
    # 0 ok · 1 error · 3 sesión incompleta (no se envió nada) · 130 interrumpido.
    # El 3 existe para que un scheduler distinga "falló el login" de un fallo
    # cualquiera: es el caso que antes salía con 0 habiendo hecho nada.
    exit_code = 0
    try:
        main()
    except KeyboardInterrupt:
        exit_code = 130
    except Exception as exc:
        from rosseta_stone_script_a.domain.errors import SessionCaptureIncomplete

        print(f"\nError: {exc}", file=sys.stderr)
        exit_code = 3 if isinstance(exc, SessionCaptureIncomplete) else 1
    finally:
        if getattr(sys, "frozen", False):
            input("\nPresiona Enter para cerrar...")
    raise SystemExit(exit_code)
