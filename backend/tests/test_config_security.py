from pathlib import Path


def test_real_env_files_are_ignored_and_example_is_tracked():
    root = Path(__file__).resolve().parents[2]
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    example = root / "backend" / ".env.example"
    template = example.read_text(encoding="utf-8")

    assert ".env" in gitignore
    assert ".env.*" in gitignore
    assert "!.env.example" in gitignore
    assert example.is_file()
    assert "DATABASE_URL=" in template
    assert "SECRET_KEY=" in template
    assert "SMTP_PASSWORD=" in template


def test_example_configuration_contains_placeholders_not_credentials():
    root = Path(__file__).resolve().parents[2]
    template = (root / "backend" / ".env.example").read_text(encoding="utf-8")

    for line in template.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key in {"DATABASE_URL", "SECRET_KEY", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL"}:
            assert value == "", f"{key} must remain a blank placeholder"
