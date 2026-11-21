"""Start the project's portable MySQL instance in the foreground on Windows."""
import subprocess
from pathlib import Path

work = Path(__file__).resolve().parents[1] / "work" / "mysql"
distributions = sorted(work.glob("mysql-8.4.*-winx64"))
if len(distributions) != 1:
    raise SystemExit("Extract one MySQL 8.4 Windows distribution into work/mysql.")
distribution = distributions[0]
if not (work / "data" / "mysql").is_dir():
    raise SystemExit("Initialize the MySQL data directory first. See docs/DATABASE.md.")

args = [
    "mysqld", "--no-defaults", "--console", f"--basedir=./{distribution.name}/",
    "--datadir=./data/", "--port=3308", "--bind-address=127.0.0.1",
    "--mysqlx=0", "--default-time-zone=+00:00", "--innodb-buffer-pool-size=64M", "--skip-log-bin",
]
raise SystemExit(subprocess.call(args, executable=distribution / "bin" / "mysqld.exe", cwd=work))
