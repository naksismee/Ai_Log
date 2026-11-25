"""Run the dashboard from the repository root; no shell activation required."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(description='Start the AI Log Analyzer dashboard.')
    parser.add_argument('--demo', action='store_true', help='Use local keyword vectors; no model download or API key.')
    parser.add_argument('--port', default=8000, type=int)
    parser.add_argument('--install-only', action='store_true')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error('Python 3.10 or later is required; Python 3.12 is recommended.')
    root = Path(__file__).resolve().parent
    environment = root / ('.venv-demo' if args.demo else '.venv')
    executable = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    requirements = root / 'backend' / ('requirements-demo.txt' if args.demo else 'requirements.txt')
    if not executable.exists():
        print('Creating an isolated Python environment…', flush=True)
        venv.create(environment, with_pip=True)
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = environment / '.requirements.sha256'
    if not marker.exists() or marker.read_text() != fingerprint:
        subprocess.run([str(executable), '-m', 'pip', 'install', '-r', str(requirements)], check=True)
        marker.write_text(fingerprint)
    if args.install_only:
        return
    data_dir = root / 'data' / ('demo' if args.demo else 'semantic')
    data_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'AI_LOG_ANALYZER_DATA_DIR': str(data_dir), 'LOG_WATCH_DIR': str(root / 'sample_logs'), 'ENABLE_SCHEDULER': 'false', 'ENABLE_ALERTS': 'false'}
    env['AI_LOG_ANALYZER_DEMO'] = 'true' if args.demo else 'false'
    if args.demo:
        # A preview must not send uploaded logs or alerts to external services.
        env.pop('OPENAI_API_KEY', None)
        env.pop('SLACK_WEBHOOK_URL', None)
    print(f'Open http://127.0.0.1:{args.port} — Ctrl+C stops the server.', flush=True)
    try:
        subprocess.run([str(executable), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(args.port)], cwd=root / 'backend', env=env, check=True)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
