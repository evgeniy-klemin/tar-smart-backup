# tar-smart-backup

Install
=======

Dependencies
------------

1. Python 3

    Example install on ubuntu 14.04 through virtualenv:
    ```bash
    virtualenv-3.4 venv
    . venv/bin/activate
    ```

2. On ubuntu 14.04 package `build-essential` for paramiko:

    ```bash
    sudo apt-get install build-essential
    ```

Install tar-smart-backup
------------------------

```bash
git clone https://github.com/evgeniy-klemin/tar-smart-backup
cd tar-smart-backup
pip install -r requirements.txt
```


Examples
=======

Backup
------

Make backup named "mybackup":

```bash
python tar_smart_backup.py "mybackup" backup /var/www/media --dst=/var/backups
```

Backup with syncing to remote server `backup@backup.internal:/backup`:

```bash
SYNC_OPTS="--sync --ssh-user=backup --ssh-key-rsa=/home/user/some_id_rsa --ssh-host=backup.internal --remote-dir=/backups"
python tar_smart_backup.py $SYNC_OPTS "mybackup" backup /var/www/media --dst=/var/backups
```


Restore
-------

Restore backup named "mybackup" stored in `/var/backups` to `/var/www/media`:

```bash
python tar_smart_backup.py "mybackup" restore /var/www/media --src=/var/backups
```

Restore backup named "mybackup" from remote backup server `backup@backup.internal:/backup` to `/var/www/media`, where `/var/backups` temp folder:

```bash
SYNC_OPTS="--sync --ssh-user=backup --ssh-key-rsa=/home/user/some_id_rsa --ssh-host=backup.internal --remote-dir=/backups"
python tar_smart_backup.py $SYNC_OPTS "mybackup" backup /var/www/media --dst=/var/backups
```

Options
=======

`--count` - How much backups make in each level(depth)

`--levels` - How much tar LEVEL-1 depth create

With --levels=3 --count=3 (five times calls):

* mybackup.tar.gz - tar LEVEL-0
* mybackup_01.tar.gz - tar LEVEL-1 depth=1
* mybackup_01_01.tar.gz - tar LEVEL-1 depth=2
* mybackup_01_02.tar.gz - tar LEVEL-1 depth=2
* mybackup_01_03.tar.gz - tar LEVEL-1 depth=2

In next backup call:

* mybackup.tar.gz - tar LEVEL-0
* mybackup_01.tar.gz - tar LEVEL-1 depth=1
* mybackup_02.tar.gz - tar LEVEL-1 depth=1

In next backup call:

* mybackup.tar.gz - tar LEVEL-0
* mybackup_01.tar.gz - tar LEVEL-1 depth=1
* mybackup_02.tar.gz - tar LEVEL-1 depth=1
* mybackup_02_01.tar.gz - tar LEVEL-1 depth=2
