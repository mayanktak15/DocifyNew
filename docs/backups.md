# PostgreSQL backups

Backups contain sensitive health information. Store archives in a restricted, encrypted location with a retention policy and an off-host copy. Access control, encryption, scheduling, backup monitoring, and retention are not provided by the script.

Install compatible PostgreSQL client tools (`pg_dump` and `pg_restore`), set `DATABASE_URL` in the environment without putting credentials in shell history or command arguments, and run:

```sh
python scripts/backup_database.py /secure/backups/docify-2026-11-21.dump
```

The command requires an existing destination directory and refuses to overwrite an existing file. It writes a mode-0600 temporary archive in the destination directory, runs `pg_restore --list` to check that its archive table of contents is readable, and publishes it only on success. The check does **not** prove that all data can be restored. Backup archives contain database records only; configuration, secrets and other runtime files require a separate recovery plan. A local PostgreSQL 18 drill restored a synthetic consultation into a separate database. Repeat the drill against your deployment and backup storage.

For a recovery drill, provision a separate empty PostgreSQL database and restore into that isolated database using `pg_restore --exit-on-error --no-owner --no-privileges --dbname recovery_database /secure/backups/docify-2026-11-21.dump`. Configure the isolated host and user with PostgreSQL environment variables and supply credentials through a protected `.pgpass` file; do not put passwords in command arguments. Inspect migrated schema, record counts, and application behavior before treating the backup as usable. Never restore over a live database without a separately planned recovery procedure.

For daily archives on a systemd host, the sample service and timer under `deploy/` assume a checkout and virtual environment at `/opt/docify`, a `docify` service account and PostgreSQL client tools on the host. Put the backup connection in a root-readable `/etc/docify/backup.env`, install both units in `/etc/systemd/system/`, run `systemctl daemon-reload` and enable `docify-backup.timer` with `systemctl enable --now`. The service writes to `/var/lib/docify-backups`. Configure off-host replication and retention for that directory.
